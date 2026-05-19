import streamlit as st
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

active_rect_js = "null"
tag_mode = "rect"

st.markdown(
    """
    <style>
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
    'redraw_trigger': 0, 'ocr_lang': 'kor+eng', 'doc_type': '논문메타',
    'exclude_keywords': '저자소개' 
}

for key, default in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

IMAGE_SAVE_DIR = "extracted_images"
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

# ==========================================
# 2. 캐싱 및 유틸리티 함수 (속도 최적화 핵심)
# ==========================================
@st.cache_data(show_spinner=False)
def get_cached_display_img(file_bytes, page_idx, canvas_w):
    full_bg, pdf_w, pdf_h = get_page_image(file_bytes, page_idx)
    if full_bg is None: return None, 0, 1.0
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    return display_img, canvas_h, canvas_w / pdf_w

def go_first(): st.session_state.current_page = 0; st.session_state.selected_box_id = None
def go_prev(): st.session_state.current_page = max(0, st.session_state.current_page - 1); st.session_state.selected_box_id = None
def go_next(total_pages): st.session_state.current_page = min(total_pages - 1, st.session_state.current_page + 1); st.session_state.selected_box_id = None
def go_last(total_pages): st.session_state.current_page = max(0, total_pages - 1); st.session_state.selected_box_id = None

def page_input_changed():
    target = st.session_state.page_input_widget - 1
    if target != st.session_state.current_page:
        st.session_state.current_page = target
        st.session_state.selected_box_id = None

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

def set_active_label(lbl): st.session_state.active_label = lbl
def handle_esc(): st.session_state.selected_box_id = None

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
    """명시적인 재추출 버튼 클릭 시에만 실행되는 함수 (오토피팅 무시, 드래그 영역 유지)"""
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
    if 'pending_extract' in anno:
        anno['pending_extract'] = False

# ==========================================
# 3. 사이드바 구성
# ==========================================
st.sidebar.markdown("### 📚 문서 메타데이터 설정")
doc_types = ['논문메타', '논문전문', '단행본', '기타']
st.session_state.doc_type = st.sidebar.selectbox("자료유형 선택", options=doc_types, index=doc_types.index(st.session_state.doc_type) if st.session_state.doc_type in doc_types else 0)

st.sidebar.markdown("### 🧹 자동 텍스트 필터")
filter_input = st.sidebar.text_input("제외할 문구 (쉼표로 구분)", value=st.session_state.exclude_keywords)
st.session_state.exclude_keywords = filter_input

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
                        img
