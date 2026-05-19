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
    'exclude_keywords': '저자소개', 'latest_canvas_coords': {}
}

for key, default in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

IMAGE_SAVE_DIR = "extracted_images"
os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)

# ==========================================
# 2. 캐싱 및 유틸리티 함수
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
    """명시적인 재추출 버튼 클릭 시 실행되는 함수"""
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
                        img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
                        page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fit_rect).save(img_path)
                        
                        basic_text = clean_text(extract_text_with_spaces(page, fit_rect), st.session_state.exclude_keywords)
                        st.session_state.annotations.append({
                            'id': f"id_{st.session_state.crop_counter}", 'page_idx': p_idx,
                            'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                            'text': basic_text, 'ocr_text': "", 'final_text': basic_text,
                            'img_name': img_name, 'img_path': img_path, 'label': qf_label
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

    fabric_objects = []
    
    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            r = anno['pdf_rect']
            is_sel = (st.session_state.selected_box_id == anno['id'])
            c_left, c_top = r[0] * pdf_to_canvas_ratio, r[1] * pdf_to_canvas_ratio
            c_w, c_h = (r[2] - r[0]) * pdf_to_canvas_ratio, (r[3] - r[1]) * pdf_to_canvas_ratio
            
            if is_sel: active_rect_js = f"{{ left: {c_left}, top: {c_top}, width: {c_w}, height: {c_h} }}"
                
            fabric_objects.append({
                "type": "rect", "left": c_left, "top": c_top, "width": c_w, "height": c_h,
                "fill": "rgba(255, 0, 0, 0.2)" if is_sel else "rgba(0, 0, 255, 0.1)",
                "stroke": "rgba(255, 0, 0, 0.9)" if is_sel else "rgba(0, 0, 255, 0.7)",
                "strokeWidth": 3 if is_sel else 2, "id": anno['id']
            })
    
    initial_drawing = {"version": "4.4.0", "objects": fabric_objects}
    tag_mode = "transform" if st.session_state.selected_box_id else "rect"

    st.write("### PDF 상호작용 구축 도구")
    show_pdf = st.toggle("📄 PDF 뷰어 패널 열기/닫기", value=True)
    st.markdown("---")

    col_pdf, col_right = st.columns([6, 4]) if show_pdf else (None, st.container())
    col_list_img, col_edit = st.columns([4, 6]) if not show_pdf else (col_right, col_right)

    if col_pdf:
        with col_pdf:
            ctrl_cols = st.columns([1.2, 1.2, 2, 1.2, 1.2, 2])
            ctrl_cols[0].button("⏮", on_click=go_first, use_container_width=True)
            ctrl_cols[1].button("◀", on_click=go_prev, use_container_width=True)
            ctrl_cols[2].number_input("페이지 입력", min_value=1, max_value=total_pages, value=st.session_state.current_page + 1, on_change=page_input_changed, key="page_input_widget", label_visibility="collapsed")
            ctrl_cols[3].button("▶", on_click=go_next, args=(total_pages,), use_container_width=True)
            ctrl_cols[4].button("⏭", on_click=go_last, args=(total_pages,), use_container_width=True)
            ctrl_cols[5].markdown(f"<div style='padding-top: 5px; font-size:16px; font-weight: bold;'>/ {total_pages}</div>", unsafe_allow_html=True)

            # ==========================================
            # 상단 고정: 모드 전환 버튼 & 적용 버튼 나란히 배치
            # ==========================================
            btn_mode_cols = st.columns([1, 1])
            with btn_mode_cols[0]:
                mode_toggle_pressed = st.button("🔄 모드 전환 (현재: " + ("Modify" if tag_mode=="transform" else "Drag") + ")", use_container_width=True)
            
            apply_resize_pressed = False
            with btn_mode_cols[1]:
                if tag_mode == "transform":
                    # 수정 모드일 때는 무조건 보이게 렌더링
                    apply_resize_pressed = st.button("✅ 선택 상자 크기/위치 적용 (재추출)", type="primary", use_container_width=True)

            # 캔버스 렌더링
            canvas_result = st_canvas(
                fill_color="rgba(0, 0, 255, 0.1)", stroke_width=2, stroke_color="rgba(0, 0, 255, 0.8)",
                background_image=display_img, initial_drawing=initial_drawing, update_streamlit=True,
                height=canvas_h, width=canvas_w, drawing_mode=tag_mode, display_toolbar=False,
                key=f"canvas_{st.session_state.file_name}_p{st.session_state.current_page}_r{st.session_state.redraw_trigger}",
            )

            # ==========================================
            # [핵심 로직] 캔버스가 변할 때마다 최신 좌표를 세션에 안전하게 백업
            # ==========================================
            if canvas_result and canvas_result.json_data and "objects" in canvas_result.json_data:
                for obj in canvas_result.json_data["objects"]:
                    if "id" in obj:
                        st.session_state.latest_canvas_coords[obj["id"]] = obj

            # ==========================================
            # 1. 모드 전환 버튼 핸들러
            # ==========================================
            if mode_toggle_pressed:
                st.session_state.selected_box_id = None
                st.session_state.redraw_trigger += 1
                st.rerun()

            # ==========================================
            # 2. 크기/위치 적용 버튼 핸들러
            # ==========================================
            if apply_resize_pressed:
                sid = st.session_state.selected_box_id
                if sid and sid in st.session_state.latest_canvas_coords:
                    obj = st.session_state.latest_canvas_coords[sid]
                    n_x0 = obj['left'] / pdf_to_canvas_ratio
                    n_y0 = obj['top'] / pdf_to_canvas_ratio
                    n_x1 = n_x0 + (obj['width'] * obj.get('scaleX', 1)) / pdf_to_canvas_ratio
                    n_y1 = n_y0 + (obj['height'] * obj.get('scaleY', 1)) / pdf_to_canvas_ratio
                    
                    for anno in st.session_state.annotations:
                        if anno['id'] == sid:
                            anno['pdf_rect'] = [n_x0, n_y0, n_x1, n_y1]
                            with st.spinner("영역 캡처 및 텍스트 재인식 중..."):
                                re_extract_annotation(anno, doc, anno['page_idx'])
                            break
                
                # 재추출 완료 후 자동으로 추가(Drag) 모드로 깔끔하게 복귀
                st.session_state.selected_box_id = None
                st.session_state.redraw_trigger += 1
                st.rerun()

            # ==========================================
            # 3. 추가(Drag) 모드일 때의 상호작용 (박스 그리기 / 클릭 선택)
            # ==========================================
            if tag_mode == "rect" and not mode_toggle_pressed and not apply_resize_pressed:
                if canvas_result and canvas_result.json_data and "objects" in canvas_result.json_data:
                    objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
                    
                    # 새로운 박스가 생성되었을 때
                    if len(objs) > len(fabric_objects):
                        new_obj = objs[-1]
                        obj_sig = f"{new_obj['left']:.1f}_{new_obj['top']:.1f}_{new_obj['width']:.1f}_{new_obj['height']:.1f}"
                        
                        if st.session_state.last_canvas_sig != obj_sig:
                            st.session_state.last_canvas_sig = obj_sig
                            w = new_obj['width'] * new_obj.get('scaleX', 1)
                            h = new_obj['height'] * new_obj.get('scaleY', 1)
                            p_x0 = new_obj["left"] / pdf_to_canvas_ratio
                            p_y0 = new_obj["top"] / pdf_to_canvas_ratio
                            p_x1 = p_x0 + (w / pdf_to_canvas_ratio)
                            p_y1 = p_y0 + (h / pdf_to_canvas_ratio)
                            
                            # 너무 작은 크기면 '클릭(선택)'으로 간주
                            if w < 10 and h < 10:
                                cx, cy = p_x0 + (w / pdf_to_canvas_ratio)/2, p_y0 + (h / pdf_to_canvas_ratio)/2
                                clicked_id = None
                                for a in reversed(st.session_state.annotations):
                                    if a['page_idx'] == st.session_state.current_page:
                                        r = a['pdf_rect']
                                        if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]:
                                            clicked_id = a['id']
                                            break
                                if clicked_id:
                                    st.session_state.selected_box_id = clicked_id
                                    st.session_state.redraw_trigger += 1
                                    st.rerun()
                                    
                            # 드래그로 영역을 그렸을 때 (추출)
                            elif w >= 10 and h >= 10:
                                page = doc.load_page(st.session_state.current_page)
                                fit_rect = fitz.Rect(p_x0, p_y0, p_x1, p_y1)
                                
                                if autofit_enabled:
                                    words = page.get_text("words")
                                    matched = [fitz.Rect(wd[:4]) for wd in words if fitz.Rect(wd[:4]).intersects(fit_rect)]
                                    if matched:
                                        new_rect = matched[0]
                                        for r in matched[1:]: new_rect |= r
                                        fit_rect = new_rect
                                
                                st.session_state.crop_counter += 1
                                img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                                img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
                                page.get_pixmap(matrix=fitz.Matrix(2 if (fit_rect.y1-fit_rect.y0)>50 else 4, 2 if (fit_rect.y1-fit_rect.y0)>50 else 4), clip=fit_rect).save(img_path)
                                
                                basic_text = clean_text(extract_text_with_spaces(page, fit_rect), st.session_state.exclude_keywords)
                                ocr_text = extract_text_via_ocr(img_path, st.session_state.ocr_lang, st.session_state.exclude_keywords)
                                
                                st.session_state.annotations.append({
                                    'id': f"id_{st.session_state.crop_counter}", 'page_idx': st.session_state.current_page,
                                    'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                                    'text': basic_text, 'ocr_text': ocr_text, 'final_text': basic_text,
                                    'img_name': img_name, 'img_path': img_path, 'label': st.session_state.active_label
                                })
                                st.session_state.selected_box_id = None
                                st.session_state.redraw_trigger += 1
                                st.rerun()

    # ==========================================
    # 5. 추출 데이터 목록 및 편집 패널
    # ==========================================
    anno_dict = {a['id']: a for a in st.session_state.annotations} if st.session_state.annotations else {}

    with col_list_img:
        st.subheader("데이터 추출 목록")
        if anno_dict:
            radio_options = ["NEW_MODE"] + list(anno_dict.keys())
            def format_label(aid):
                if aid == "NEW_MODE": return "✨ [신규 추출 대기 중]"
                a = anno_dict[aid]
                return f"[P{a['page_idx']+1}] [{a.get('label', '미지정')}] | {a.get('final_text', a['text'])[:15].replace(chr(10), ' ')}..."

            current_val = st.session_state.selected_box_id if st.session_state.selected_box_id in anno_dict else "NEW_MODE"
            selected_id = st.radio("목록", options=radio_options, format_func=format_label, index=radio_options.index(current_val), label_visibility="collapsed")
            
            if selected_id != current_val:
                st.session_state.selected_box_id = None if selected_id == "NEW_MODE" else selected_id
                if selected_id != "NEW_MODE": st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.session_state.redraw_trigger += 1
                st.rerun()
                
            st.markdown("---")
            if st.button("🔄 현재 페이지 일괄 재인식 (OCR)", use_container_width=True):
                updated_count = 0
                for a in st.session_state.annotations:
                    if a['page_idx'] == st.session_state.current_page and os.path.exists(a['img_path']):
                        a['ocr_text'] = extract_text_via_ocr(a['img_path'], st.session_state.ocr_lang, st.session_state.exclude_keywords)
                        updated_count += 1
                if updated_count > 0:
                    st.success(f"현재 페이지의 {updated_count}개 항목이 성공적으로 재인식되었습니다!")
                    st.rerun()

            curr_anno = anno_dict.get(st.session_state.selected_box_id)
            if curr_anno and os.path.exists(curr_anno['img_path']):
                st.markdown("<br>", unsafe_allow_html=True)
                with open(curr_anno['img_path'], "rb") as img_file: st.image(img_file.read(), use_column_width=True)
        else:
            st.info("추출된 데이터가 없습니다. PDF를 드래그하세요.")
            curr_anno = None

    with col_edit:
        if curr_anno:
            curr_lbl = curr_anno.get('label', '미지정')
            st.selectbox("🏷️ 라벨 변경", options=st.session_state.labels, index=st.session_state.labels.index(curr_lbl) if curr_lbl in st.session_state.labels else 0, key=f"lbl_sel_{curr_anno['id']}", on_change=update_label, args=(curr_anno['id'],))

            with st.expander("📄 이 위치를 다른 페이지에도 일괄 복사", expanded=False):
                copy_target_pages = st.text_input("복사할 대상 페이지 (예: 1-5, 8)", placeholder="페이지 번호를 쉼표와 하이픈으로 입력", key=f"bulk_txt_{curr_anno['id']}")
                if st.button("📋 현재 좌표 일괄 복사 및 추출 실행", key=f"bulk_btn_{curr_anno['id']}"):
                    target_pages = parse_page_ranges(copy_target_pages, total_pages)
                    if target_pages:
                        orig_rect = curr_anno['pdf_rect']
                        copy_count = 0
                        for p_num in target_pages:
                            if p_num - 1 == curr_anno['page_idx']: continue
                            
                            page = doc.load_page(p_num - 1)
                            fit_rect = fitz.Rect(orig_rect)
                            
                            is_dup = False
                            for existing in st.session_state.annotations:
                                if existing['page_idx'] == p_num - 1 and existing.get('label') == curr_lbl:
                                    ex_r = existing['pdf_rect']
                                    if abs(ex_r[0] - fit_rect.x0) < 5 and abs(ex_r[1] - fit_rect.y0) < 5:
                                        is_dup = True
                                        break
                            if is_dup: continue
                            
                            st.session_state.crop_counter += 1
                            img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                            img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
                            page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=fit_rect).save(img_path)
                            
                            basic_text = clean_text(extract_text_with_spaces(page, fit_rect), st.session_state.exclude_keywords)
                            
                            st.session_state.annotations.append({
                                'id': f"id_{st.session_state.crop_counter}", 'page_idx': p_num - 1,
                                'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                                'text': basic_text, 
                                'ocr_text': "", 
                                'final_text': basic_text,
                                'img_name': img_name, 'img_path': img_path, 'label': curr_lbl
                            })
                            copy_count += 1
                            
                        if copy_count > 0:
                            st.success(f"{copy_count}개 페이지에 영역 복사가 완료되었습니다!")
                            st.session_state.redraw_trigger += 1
                            st.rerun()
                        else:
                            st.warning("이미 복사되었거나 유효한 대상 페이지가 없습니다.")

            col_b, col_o = st.columns(2)
            with col_b:
                st.text_area("📝 기본 추출 (PyMuPDF)", value=curr_anno['text'], height=100, disabled=True)
                st.button("⬇️ 기본 추출 채택", key=f"btn_basic_{curr_anno['id']}", on_click=apply_text_to_final, args=(curr_anno['id'], 'basic'), use_container_width=True)
            with col_o:
                st.text_area("🔍 이미지 인식 (OCR)", value=curr_anno.get('ocr_text', ''), height=100, disabled=True)
                st.button("⬇️ OCR 채택", key=f"btn_ocr_{curr_anno['id']}", on_click=apply_text_to_final, args=(curr_anno['id'], 'ocr'), use_container_width=True)
                if st.button("🔄 선택 항목 재인식", key=f"btn_reocr_{curr_anno['id']}", use_container_width=True):
                    curr_anno['ocr_text'] = extract_text_via_ocr(curr_anno['img_path'], st.session_state.ocr_lang, st.session_state.exclude_keywords)
                    st.rerun()

            st.markdown(f"<div style='border:1px solid #ddd; padding:10px; max-height:150px; overflow-y:auto;'>{get_html_diff(curr_anno['text'], curr_anno.get('ocr_text', ''))}</div>", unsafe_allow_html=True)
            curr_anno['final_text'] = st.text_area("✨ 최종 교정 텍스트 (직접 수정 가능)", value=curr_anno.get('final_text', curr_anno['text']), height=text_area_height, key=f"final_input_{curr_anno['id']}", on_change=update_final_text, args=(curr_anno['id'],))

            c1, c2, c3, c4 = st.columns([1, 1, 1.5, 1.5])
            
            c1.button("🗑️ 삭제", type="primary", on_click=delete_single_item, args=(curr_anno['id'],))
            
            if c2.button("💾 저장"):
                st.toast("저장 기능은 아직 준비 중입니다.", icon="🚧")
            
            md_text = f"# 문서 추출 데이터 ({st.session_state.doc_type})\n\n"
            for a in st.session_state.annotations:
                r = a['pdf_rect']
                lbl = a.get('label', '미지정')
                final_t = a.get('final_text', a['text'])
                
                md_text += f"### Page {a['page_idx'] + 1}\n"
                md_text += f"- **라벨:** `{lbl}`\n"
                md_text += f"- **좌표:** `[X: {int(r[0])}, Y: {int(r[1])}, W: {int(r[2]-r[0])}, H: {int(r[3]-r[1])}]`\n"
                md_text += "#### 📝 추출 데이터\n"
                md_text += f"```text\n{str(final_t)}\n```\n"
                md_text += "---\n\n"
            
            c3.download_button("📝 마크다운", data=md_text, file_name="result.md", mime="text/markdown")
            
            export_data = {
                "document_meta": {"file_name": st.session_state.file_name, "document_type": st.session_state.doc_type},
                "annotations": [{"page": a['page_idx']+1, "label": a.get('label', '미지정'), "bbox": a['pdf_rect'], "text": a.get('final_text', a['text']), "raw_basic": a['text'], "raw_ocr": a.get('ocr_text', '')} for a in st.session_state.annotations]
            }
            c4.download_button("📥 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), file_name="result.json", mime="application/json")

# ==========================================
# 6. 숨김 버튼 및 JavaScript (단축키 등)
# ==========================================
st.markdown('<div id="hidden_buttons_marker" style="display:none;"></div>', unsafe_allow_html=True)
st.markdown("""<style>div.element-container:has(#hidden_buttons_marker) ~ div.element-container { display: none !important; }</style>""", unsafe_allow_html=True)

for i, lbl in enumerate(st.session_state.labels[:9]): st.button(f"HL_{i}", key=f"btn_shortcut_lbl_{i}", on_click=set_active_label, args=(lbl,))
st.button("HE_ESC", key="btn_shortcut_esc", on_click=handle_esc)

safe_active_rect = globals().get('active_rect_js', 'null')
safe_tag_mode = globals().get('tag_mode', 'rect')

raw_js = f"""
window._current_active_rect = {safe_active_rect};
window._current_tag_mode = "{safe_tag_mode}";
if (!window._custom_js_injected) {{
    window.insertDiffText = function(el) {{
        const textToInsert = el.innerText;
        let targetTA = window._lastActiveTA;
        if (!targetTA) {{
            const labels = window.document.querySelectorAll('label');
            for (let lbl of labels) {{
                if (lbl.innerText.includes("최종 교정 텍스트")) {{
                    const container = lbl.closest('div[data-testid="stTextArea"]');
                    if (container) {{ targetTA = container.querySelector('textarea'); break; }}
                }}
            }}
        }}
        if (targetTA) {{
            const startPos = (window._lastTASelectionStart !== undefined && window._lastActiveTA === targetTA) ? window._lastTASelectionStart : targetTA.value.length;
            const endPos = (window._lastTASelectionEnd !== undefined && window._lastActiveTA === targetTA) ? window._lastTASelectionEnd : targetTA.value.length;
            const text = targetTA.value;
            const newText = text.substring(0, startPos) + textToInsert + text.substring(endPos, text.length);
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
            nativeInputValueSetter.call(targetTA, newText);
            targetTA.dispatchEvent(new Event('input', {{ bubbles: true }}));
            targetTA.dispatchEvent(new Event('change', {{ bubbles: true }}));
            targetTA.focus();
            targetTA.selectionStart = targetTA.selectionEnd = startPos + textToInsert.length;
            window._lastTASelectionStart = targetTA.selectionStart;
            window._lastTASelectionEnd = targetTA.selectionEnd;
            window._lastActiveTA = targetTA;
            const originalBg = el.style.backgroundColor;
            el.style.backgroundColor = '#fff000';
            setTimeout(() => {{ el.style.backgroundColor = originalBg; }}, 150);
        }}
    }};
    window.document.addEventListener('keydown', function(e) {{
        if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
        if (['1','2','3','4','5','6','7','8','9'].includes(e.key)) {{
            if(e.ctrlKey) e.preventDefault();
            const btn = Array.from(window.document.querySelectorAll('button')).find(el => el.innerText === 'HL_' + (parseInt(e.key)-1));
            if (btn) btn.click();
        }}
    }});
    window._custom_js_injected = true;
}}
"""
st.markdown(f'<img src="dummy" onerror="eval(atob(\'{base64.b64encode(raw_js.encode("utf-8")).decode("utf-8")}\'));" style="display:none;" />', unsafe_allow_html=True)
