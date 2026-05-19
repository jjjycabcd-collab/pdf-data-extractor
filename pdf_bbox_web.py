import streamlit as st
import streamlit.components.v1 as components
import fitz  # PyMuPDF
import json
import os
import shutil
import base64
from PIL import Image
from streamlit_drawable_canvas import st_canvas

# 분리한 로직 임포트
from pdf_utils import (
    get_html_diff, extract_text_with_spaces, clean_text, 
    extract_text_via_ocr, get_page_image, parse_page_ranges
)

# ==========================================
# 1. 페이지 및 상태 초기화
# ==========================================
st.set_page_config(layout="wide", page_title="상호작용 데이터 구축 - Web Editor")

# ---------------------------------------------------------
# [신규 통합 기능] 화면 모드 전환 (에디터 vs 명세서)
# ---------------------------------------------------------
st.sidebar.markdown("### 🖥️ 화면 모드")
app_mode = st.sidebar.radio("모드 선택", ["🛠️ 데이터 구축 에디터", "📖 프로그램 명세서"], label_visibility="collapsed")
st.sidebar.markdown("---")

# '프로그램 명세서'가 선택된 경우 HTML을 앱 내부에 직접 렌더링하고 실행 종료
if app_mode == "📖 프로그램 명세서":
    try:
        with open("manual.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        # 외부 링크 없이 iframe 형태로 Streamlit 화면에 완벽하게 삽입됩니다.
        components.html(html_content, height=850, scrolling=True)
    except FileNotFoundError:
        st.error("💡 'manual.html' 파일을 찾을 수 없습니다. 파이썬 스크립트와 동일한 폴더에 업로드되어 있는지 확인해 주세요.")
    
    # 명세서 화면만 보여주고, 아래 에디터 코드는 실행하지 않도록 차단
    st.stop()
# ---------------------------------------------------------

active_rect_js = "null"
tag_mode = "rect"

st.markdown(
    """
    <style>
    div[data-testid="stStatusWidget"] { visibility: hidden; display: none !important; }
    button[title^="hidden"] { display: none !important; }
    div[data-testid="stButton"]:has(button[title^="hidden"]) { display: none !important; height: 0px; margin: 0px; padding: 0px; }
    div[data-testid="stTooltipHoverTarget"]:has(button[title^="hidden"]) { display: none !important; height: 0px; margin: 0px; padding: 0px; }
    div[data-testid="stNumberInputStepUp"], div[data-testid="stNumberInputStepDown"] { display: none !important; }
    input[type="number"] { -moz-appearance: textfield; text-align: center !important; font-weight: bold; }
    input[type="number"]::-webkit-outer-spin-button, input[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    </style>
    """,
    unsafe_allow_html=True
)

if 'labels' not in st.session_state:
    st.session_state.labels = ['논문명', '저자명', '소속기관', '초록', '키워드', '참고문헌']

state_keys = {
    'file_bytes': None, 'pdf_doc': None, 'current_page': 0, 
    'annotations': [], 'crop_counter': 0, 'selected_box_id': None,
    'last_canvas_sig': None, 'file_name': "",
    'active_label': st.session_state.labels[0] if 'labels' in st.session_state else '논문명',
    'redraw_trigger': 0, 'ocr_lang': 'kor+eng', 'doc_type': '단행본',
    'exclude_keywords': '저자소개',
    'grouping_mode': False, 'active_group_id': 'G1'
}

for key, default in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

IMAGE_SAVE_DIR = "extracted_images"
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

# ==========================================
# 2. 캐싱 및 유틸리티 함수
# ==========================================
@st.cache_resource(show_spinner=False)
def get_cached_display_img(file_bytes, page_idx, canvas_w):
    full_bg, pdf_w, pdf_h = get_page_image(file_bytes, page_idx)
    if full_bg is None: return None, 0, 1.0
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    return display_img, canvas_h, canvas_w / pdf_w

def go_first(): st.session_state.current_page = 0; st.session_state.selected_box_id = None; st.session_state.redraw_trigger += 1
def go_prev(): st.session_state.current_page = max(0, st.session_state.current_page - 1); st.session_state.selected_box_id = None; st.session_state.redraw_trigger += 1
def go_next(total_pages): st.session_state.current_page = min(total_pages - 1, st.session_state.current_page + 1); st.session_state.selected_box_id = None; st.session_state.redraw_trigger += 1
def go_last(total_pages): st.session_state.current_page = max(0, total_pages - 1); st.session_state.selected_box_id = None; st.session_state.redraw_trigger += 1

def page_input_changed():
    target = st.session_state.page_input_widget - 1
    if target != st.session_state.current_page:
        st.session_state.current_page = target
        st.session_state.selected_box_id = None
        st.session_state.redraw_trigger += 1

def delete_single_item(anno_id):
    for i, a in enumerate(st.session_state.annotations):
        if a['id'] == anno_id:
            if os.path.exists(a['img_path']):
                try: os.remove(a['img_path'])
                except: pass
            st.session_state.annotations.pop(i)
            break
    st.session_state.selected_box_id = None
    st.session_state.redraw_trigger += 1

def update_label(aid):
    for a in st.session_state.annotations:
        if a['id'] == aid:
            a['label'] = st.session_state[f"lbl_sel_{aid}"]
            break

def update_group_id(aid):
    for a in st.session_state.annotations:
        if a['id'] == aid:
            a['group_id'] = st.session_state[f"group_sel_{aid}"]
            break

def set_active_label(lbl): st.session_state.active_label = lbl
def handle_esc(): st.session_state.selected_box_id = None; st.session_state.redraw_trigger += 1

def apply_text_to_final(aid, source_type):
    for a in st.session_state.annotations:
        if a['id'] == aid:
            target_text = a['text'] if source_type == 'basic' else a.get('ocr_text', '')
            a['final_text'] = target_text
            st.session_state[f"final_input_{aid}"] = target_text
            break

def update_final_text(aid):
    for a in st.session_state.annotations:
        if a['id'] == aid:
            a['final_text'] = st.session_state[f"final_input_{aid}"]
            break

def re_extract_annotation(anno, doc, page_idx):
    page = doc.load_page(page_idx)
    fit_rect = fitz.Rect(*anno['pdf_rect'])
    
    st.session_state.crop_counter += 1
    img_name = f"crop_{st.session_state.crop_counter:03d}.png"
    img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
    
    zoom = 2 if (fit_rect.y1 - fit_rect.y0) > 50 else 4
    page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fit_rect).save(img_path)
    
    anno['img_name'] = img_name
    anno['img_path'] = img_path
    anno['text'] = clean_text(extract_text_with_spaces(page, fit_rect), st.session_state.exclude_keywords)
    anno['ocr_text'] = extract_text_via_ocr(img_path, st.session_state.ocr_lang, st.session_state.exclude_keywords)
    anno['final_text'] = anno['text']

def get_canvas_obj(canvas_json, selected_id, annotations, current_page):
    if not canvas_json or "objects" not in canvas_json:
        return None
    page_annos = [a for a in annotations if a['page_idx'] == current_page]
    target_idx = -1
    for i, a in enumerate(page_annos):
        if a['id'] == selected_id:
            target_idx = i
            break
    if target_idx == -1:
        return None
    rects = [obj for obj in canvas_json["objects"] if obj.get("type") == "rect"]
    if 0 <= target_idx < len(rects):
        return rects[target_idx]
    return None

def get_next_group_id(annotations):
    max_g = 0
    for a in annotations:
        g = a.get('group_id', '')
        if g.startswith('G') and g[1:].isdigit():
            try:
                max_g = max(max_g, int(g[1:]))
            except:
                pass
    return f"G{max_g + 1}"

# ==========================================
# 3. 사이드바 구성 (에디터 전용)
# ==========================================
st.sidebar.markdown("### 📚 문서 메타데이터 설정")
doc_types = ['논문메타', '논문전문', '단행본', '기타']
st.session_state.doc_type = st.sidebar.selectbox("자료유형 선택", options=doc_types, index=doc_types.index(st.session_state.doc_type) if st.session_state.doc_type in doc_types else 0)

st.sidebar.markdown("---")
uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

if uploaded_file is not None:
    if st.session_state.file_name != uploaded_file.name:
        if os.path.exists(IMAGE_SAVE_DIR): shutil.rmtree(IMAGE_SAVE_DIR, ignore_errors=True)
        os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)
        st.session_state.file_bytes = uploaded_file.read()
        st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
        st.session_state.file_name = uploaded_file.name
        st.session_state.current_page = 0
        st.session_state.annotations = []
        st.session_state.crop_counter = 0
        st.session_state.selected_box_id = None
        st.session_state.redraw_trigger += 1
        st.session_state.active_group_id = "G1"
        st.rerun()

if st.session_state.file_bytes:
    doc = st.session_state.pdf_doc
    total_pages = len(doc)

    with st.sidebar.expander("⚡ 단어 기반 자동 탐색 (Quick-Find)", expanded=False):
        qf_keyword = st.text_input("찾을 키워드 (예: 참고문헌)")
        qf_label = st.selectbox("할당할 라벨", options=st.session_state.labels)
        if st.button("🚀 문서 전체 스캔 및 자동 박싱"):
            if qf_keyword:
                scan_count = 0
                for p_idx in range(total_pages):
                    page = doc.load_page(p_idx)
                    text_instances = page.search_for(qf_keyword)
                    
                    unique_instances = []
                    for inst in text_instances:
                        is_dup = False
                        for u in unique_instances:
                            if abs(inst.x0 - u.x0) < 5 and abs(inst.y0 - u.y0) < 5:
                                is_dup = True
                                break
                        if not is_dup:
                            unique_instances.append(inst)

                    for inst in unique_instances:
                        pad = 5
                        fit_rect = fitz.Rect(max(0, inst.x0 - pad), max(0, inst.y0 - pad), min(page.rect.width, inst.x1 + pad), min(page.rect.height, inst.y1 + pad))
                        
                        st.session_state.crop_counter += 1
                        img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                        img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
                        page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fit_rect).save(img_path)
                        
                        basic_text = clean_text(extract_text_with_spaces(page, fit_rect), st.session_state.exclude_keywords)
                        st.session_state.annotations.append({
                            'id': f"id_{st.session_state.crop_counter}", 'page_idx': p_idx,
                            'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                            'text': basic_text, 'ocr_text': "", 'final_text': basic_text,
                            'img_name': img_name, 'img_path': img_path, 'label': qf_label, 'group_id': ""
                        })
                        scan_count += 1
                
                if scan_count > 0:
                    st.session_state.redraw_trigger += 1
                    st.success(f"총 {scan_count}개의 '{qf_keyword}' 영역이 추출되었습니다.")

    st.sidebar.markdown("---")
    active_idx = st.session_state.labels.index(st.session_state.active_label) if st.session_state.active_label in st.session_state.labels else 0
    st.session_state.active_label = st.sidebar.radio("📌 현재 태깅 라벨", options=st.session_state.labels, index=active_idx)

    st.sidebar.markdown("---")
    ocr_lang_display = st.sidebar.selectbox("🌐 OCR 인식 언어 설정", ["kor+eng (한/영 혼용)", "kor+eng+chi_tra (한/영/한자 혼용)", "kor (한국어 전용)", "eng (영어 전용)", "chi_tra (한자 전용)"], index=0)
    st.session_state.ocr_lang = ocr_lang_display.split(" ")[0]
    
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)
    text_area_height = st.sidebar.slider("↕️ 교정창 세로 길이 (px)", min_value=150, max_value=1000, value=250, step=50)

    # ==========================================
    # 4. 메인 뷰어 캔버스
    # ==========================================
    canvas_w = 700
    display_img, canvas_h, pdf_to_canvas_ratio = get_cached_display_img(st.session_state.file_bytes, st.session_state.current_page, canvas_w)
    
    if display_img is None:
        st.error("PDF 페이지를 로드할 수 없습니다.")
        st.stop()
    
    tag_mode = "transform" if st.session_state.selected_box_id and not st.session_state.grouping_mode else "rect"

    st.write("###
