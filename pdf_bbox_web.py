import streamlit as st
import fitz  # PyMuPDF
import json
import os
import io
import re
import shutil
import difflib
import pytesseract
import base64
from PIL import Image
from streamlit_drawable_canvas import st_canvas

# Windows 환경 등에서 Tesseract 경로를 못 찾을 경우 아래 주석을 풀고 설치 경로를 지정해주세요.
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ==========================================
# 1. 페이지 및 상태 초기화
# ==========================================
st.set_page_config(layout="wide", page_title="상호작용 데이터 구축 - Web Editor")

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
    'redraw_trigger': 0,
    'ocr_lang': 'kor+eng',
    'group_counter': 0  # 고유 그룹 ID 발급용 카운터 추가
}

for key, default in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

IMAGE_SAVE_DIR = "extracted_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# ==========================================
# 2. 콜백 및 유틸리티 함수
# ==========================================
def go_first():
    st.session_state.current_page = 0
    st.session_state.selected_box_id = None

def go_prev():
    st.session_state.current_page = max(0, st.session_state.current_page - 1)
    st.session_state.selected_box_id = None

def go_next(total_pages):
    st.session_state.current_page = min(total_pages - 1, st.session_state.current_page + 1)
    st.session_state.selected_box_id = None

def go_last(total_pages):
    st.session_state.current_page = max(0, total_pages - 1)
    st.session_state.selected_box_id = None

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

def set_active_label(lbl):
    st.session_state.active_label = lbl

def handle_esc():
    st.session_state.selected_box_id = None

def add_label_callback():
    new_lbl = st.session_state.get('new_lbl_input', '').strip()
    if new_lbl and new_lbl not in st.session_state.labels:
        st.session_state.labels.append(new_lbl)
    st.session_state.new_lbl_input = ""

def delete_label_callback():
    del_target = st.session_state.get('del_lbl_select')
    if del_target and len(st.session_state.labels) > 1:
        if del_target in st.session_state.labels:
            st.session_state.labels.remove(del_target)
            if st.session_state.active_label == del_target:
                st.session_state.active_label = st.session_state.labels[0]
            for a in st.session_state.annotations:
                if a.get('label') == del_target:
                    a['label'] = "미지정"

# [신규] 그룹 병합 기능용 콜백 함수
def merge_with_previous_group(current_id):
    annos = st.session_state.annotations
    current_idx = next((i for i, a in enumerate(annos) if a['id'] == current_id), None)
    
    if current_idx is not None and current_idx > 0:
        # 직전 항목의 그룹 ID를 가져와 현재 항목에 덮어씀
        prev_group_id = annos[current_idx - 1]['group_id']
        annos[current_idx]['group_id'] = prev_group_id
        st.toast(f"이전 항목과 그룹(Group {prev_group_id})이 연동되었습니다!", icon="🔗")

def get_html_diff(text1, text2):
    if not text1 and not text2:
        return ""
    matcher = difflib.SequenceMatcher(None, text1, text2)
    result = []
    
    del_style = "background-color: #ffcccc; color: #cc0000; text-decoration: line-through; cursor: pointer; border-radius: 3px; padding: 0 3px;"
    ins_style = "background-color: #ccffcc; color: #006600; font-weight: bold; cursor: pointer; border-radius: 3px; padding: 0 3px;"
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            result.append(text1[i1:i2])
        elif tag == 'delete':
            result.append(f"<span onclick='window.insertDiffText(this)' title='클릭하여 커서 위치에 삽입' style='{del_style}'>{text1[i1:i2]}</span>")
        elif tag == 'insert':
            result.append(f"<span onclick='window.insertDiffText(this)' title='클릭하여 커서 위치에 삽입' style='{ins_style}'>{text2[j1:j2]}</span>")
        elif tag == 'replace':
            result.append(f"<span onclick='window.insertDiffText(this)' title='클릭하여 커서 위치에 삽입' style='{del_style} margin-right: 2px;'>{text1[i1:i2]}</span>")
            result.append(f"<span onclick='window.insertDiffText(this)' title='클릭하여 커서 위치에 삽입' style='{ins_style}'>{text2[j1:j2]}</span>")
            
    return "".join(result).replace('\n', '<br>')

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

def extract_text_with_spaces(page, clip_rect):
    words = page.get_text("words", clip=clip_rect)
    if not words:
        return ""
    words.sort(key=lambda w: (w[5], w[6], w[7]))
    lines = []
    current_line_words = []
    if words:
        prev_block_line = (words[0][5], words[0][6])
        for w in words:
            curr_block_line = (w[5], w[6])
            word_text = w[4]
            if curr_block_line != prev_block_line:
                lines.append(" ".join(current_line_words))
                current_line_words = [word_text]
                prev_block_line = curr_block_line
            else:
                current_line_words.append(word_text)
        if current_line_words:
            lines.append(" ".join(current_line_words))
    return "\n".join(lines)

def clean_text(text):
    if not text: return ""
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if "저자소개" not in line and line:
            line = re.sub(r'\s+', ' ', line)
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def extract_text_via_ocr(img_path, lang):
    try:
        img = Image.open(img_path).convert('L')
        img = img.point(lambda x: 0 if x < 150 else 255, '1')
        ocr_text = pytesseract.image_to_string(img, lang=lang, config='--psm 4')
        return clean_text(ocr_text)
    except Exception as e:
        return f"[OCR 에러: Tesseract가 설치되어 있는지 확인하세요]\n{str(e)}"

@st.cache_data(show_spinner=False)
def get_page_image(file_bytes, page_idx):
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return img, page.rect.width, page.rect.height
    except:
        return None, 0, 0

# ==========================================
# 3. 사이드바 (파일 로드 및 라벨 관리)
# ==========================================
uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

if uploaded_file is not None:
    if st.session_state.file_name != uploaded_file.name:
        if os.path.exists(IMAGE_SAVE_DIR):
            shutil.rmtree(IMAGE_SAVE_DIR, ignore_errors=True)
        os.makedirs(IMAGE_SAVE_DIR, exist_ok=True)
            
        st.session_state.file_bytes = uploaded_file.read()
        st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
        st.session_state.file_name = uploaded_file.name
        st.session_state.current_page = 0
        st.session_state.annotations = []
        st.session_state.crop_counter = 0
        st.session_state.group_counter = 0
        st.session_state.selected_box_id = None
        st.session_state.redraw_trigger += 1
        st.rerun()
else:
    if not st.session_state.file_bytes:
        sample_path = "sample.pdf"
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                st.session_state.file_bytes = f.read()
            st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
            st.session_state.file_name = "sample.pdf"

if st.session_state.file_bytes:
    doc = st.session_state.pdf_doc
    total_pages = len(doc)

    st.sidebar.markdown("---")
    try:
        active_idx = st.session_state.labels.index(st.session_state.active_label)
    except ValueError:
        active_idx = 0
        st.session_state.active_label = st.session_state.labels[0]
        
    st.session_state.active_label = st.sidebar.radio("📌 현재 태깅 라벨 (드래그 전 선택)", options=st.session_state.labels, index=active_idx)
    
    with st.sidebar.expander("⚙️ 라벨 추가/삭제 관리", expanded=False):
        st.text_input("새 라벨 이름", key="new_lbl_input")
        st.button("➕ 라벨 추가", on_click=add_label_callback)
        st.markdown("<br>", unsafe_allow_html=True)
        st.selectbox("삭제할 라벨 선택", options=st.session_state.labels, key="del_lbl_select")
        if len(st.session_state.labels) <= 1:
            st.warning("최소 1개의 라벨은 유지해야 합니다.")
        st.button("🗑️ 선택한 항목 삭제", on_click=delete_label_callback, disabled=(len(st.session_state.labels) <= 1))

    st.sidebar.markdown("---")
    
    ocr_lang_display = st.sidebar.selectbox(
        "🌐 OCR 인식 언어 설정", 
        [
            "kor+eng (한/영 혼용)", 
            "kor+eng+chi_tra (한/영/한자 혼용)", 
            "kor (한국어 전용)", 
            "eng (영어 전용)",
            "chi_tra (한자 전용)"
        ], 
        index=0
    )
    st.session_state.ocr_lang = ocr_lang_display.split(" ")[0]
    
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("↕️ **UI 크기 설정**")
    text_area_height = st.sidebar.slider("교정창 세로 길이 (px)", min_value=150, max_value=1000, value=250, step=50)

    # ==========================================
    # 4. 메인 에디터 화면
    # ==========================================
    full_bg, pdf_w, pdf_h = get_page_image(st.session_state.file_bytes, st.session_state.current_page)
    if full_bg is None:
        st.error("PDF 페이지를 로드할 수 없습니다.")
        st.stop()

    canvas_w = 700
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    pdf_to_canvas_ratio = canvas_w / pdf_w

    fabric_objects = []
    active_rect_js = "null"
    
    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            r = anno['pdf_rect']
            is_sel = (st.session_state.selected_box_id == anno['id'])
            
            c_left = r[0] * pdf_to_canvas_ratio
            c_top = r[1] * pdf_to_canvas_ratio
            c_w = (r[2] - r[0]) * pdf_to_canvas_ratio
            c_h = (r[3] - r[1]) * pdf_to_canvas_ratio
            
            if is_sel:
                active_rect_js = f"{{ left: {c_left}, top: {c_top}, width: {c_w}, height: {c_h} }}"
                
            fabric_objects.append({
                "type": "rect",
                "left": c_left,
                "top": c_top,
                "width": c_w,
                "height": c_h,
                "fill": "rgba(255, 0, 0, 0.2)" if is_sel else "rgba(0, 0, 255, 0.1)",
                "stroke": "rgba(255, 0, 0, 0.9)" if is_sel else "rgba(0, 0, 255, 0.7)",
                "strokeWidth": 3 if is_sel else 2,
                "id": anno['id']
            })
    
    initial_drawing = {"version": "4.4.0", "objects": fabric_objects}
    tag_mode = "transform" if st.session_state.selected_box_id else "rect"

    show_pdf = st.toggle("📄 PDF 뷰어 패널 열기/닫기 (체크 해제 시 편집 전용 넓은 화면 모드)", value=True)
    st.markdown("---")

    if show_pdf:
        col_pdf, col_right = st.columns([6, 4])
        col_list_img = col_right
        col_edit = col_right
    else:
        col_pdf = None
        col_list_img, col_edit = st.columns([4, 6])

    if col_pdf:
        with col_pdf:
            ctrl_cols = st.columns([1.2, 1.2, 2, 1.2, 1.2, 2])
            ctrl_cols[0].button("⏮", on_click=go_first, use_container_width=True, help="첫 페이지")
            ctrl_cols[1].button("◀", on_click=go_prev, use_container_width=True, help="이전 페이지")
            ctrl_cols[2].number_input("페이지 입력", min_value=1, max_value=total_pages, value=st.session_state.current_page + 1, on_change=page_input_changed, key="page_input_widget", label_visibility="collapsed")
            ctrl_cols[3].button("▶", on_click=go_next, args=(total_pages,), use_container_width=True, help="다음 페이지")
            ctrl_cols[4].button("⏭", on_click=go_last, args=(total_pages,), use_container_width=True, help="마지막 페이지")
            ctrl_cols[5].markdown(f"<div style='padding-top: 5px; font-size:16px; font-weight: bold;'>/ {total_pages}</div>", unsafe_allow_html=True)

            st.markdown("---")
            
            if tag_mode == "transform":
                btn_label = "🔄 현재: Modify 모드 (빈 공간을 클릭하면 Drag 모드로 자동 복귀합니다)"
            else:
                btn_label = "🖱️ 현재: Drag 모드 (기존 박스를 클릭하면 Modify 모드로 전환됩니다)"
                
            mode_toggle_pressed = st.button(btn_label, help="mode_toggle")

            canvas_result = st_canvas(
                fill_color="rgba(0, 0, 255, 0.1)",
                stroke_width=2,
                stroke_color="rgba(0, 0, 255, 0.8)",
                background_image=display_img,
                initial_drawing=initial_drawing,
                update_streamlit=True,
                height=canvas_h,
                width=canvas_w,
                drawing_mode=tag_mode,
                display_toolbar=False,
                key=f"canvas_{st.session_state.file_name}_p{st.session_state.current_page}_r{st.session_state.redraw_trigger}",
            )

            if canvas_result.json_data and "objects" in canvas_result.json_data:
                objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
                
                if tag_mode == "transform":
                    modified = False
                    for obj in objs:
                        if "id" in obj:
                            for anno in st.session_state.annotations:
                                if anno['id'] == obj['id']:
                                    old_r = anno['pdf_rect']
                                    n_x0 = obj['left'] / pdf_to_canvas_ratio
                                    n_y0 = obj['top'] / pdf_to_canvas_ratio
                                    n_x1 = n_x0 + (obj['width'] * obj.get('scaleX', 1)) / pdf_to_canvas_ratio
                                    n_y1 = n_y0 + (obj['height'] * obj.get('scaleY', 1)) / pdf_to_canvas_ratio
                                    
                                    if abs(n_x0 - old_r[0]) > 0.5 or abs(n_y0 - old_r[1]) > 0.5 or abs(n_x1 - old_r[2]) > 0.5 or abs(n_y1 - old_r[3]) > 0.5:
                                        page = doc.load_page(st.session_state.current_page)
                                        fit_rect = fitz.Rect(n_x0, n_y0, n_x1, n_y1)
                                        
                                        if autofit_enabled:
                                            words = page.get_text("words")
                                            matched = [fitz.Rect(wd[:4]) for wd in words if fitz.Rect(wd[:4]).intersects(fit_rect)]
                                            if matched:
                                                new_rect = matched[0]
                                                for r in matched[1:]: new_rect |= r
                                                fit_rect = new_rect

                                        anno['pdf_rect'] = [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1]
                                        
                                        if os.path.exists(anno['img_path']):
                                            try: os.remove(anno['img_path'])
                                            except: pass
                                            
                                        st.session_state.crop_counter += 1
                                        new_img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                                        new_img_path = os.path.join(IMAGE_SAVE_DIR, new_img_name)
                                        
                                        box_height = fit_rect.y1 - fit_rect.y0
                                        zoom_f = 2 if box_height > 50 else 4
                                        page.get_pixmap(matrix=fitz.Matrix(zoom_f, zoom_f), clip=fit_rect).save(new_img_path)
                                        
                                        anno['img_name'] = new_img_name
                                        anno['img_path'] = new_img_path
                                        
                                        basic_text = clean_text(extract_text_with_spaces(page, fit_rect))
                                        ocr_text = extract_text_via_ocr(new_img_path, st.session_state.ocr_lang)
                                        
                                        anno['text'] = basic_text
                                        anno['ocr_text'] = ocr_text
                                        anno['final_text'] = basic_text
                                        modified = True
                    
                    if mode_toggle_pressed:
                        st.session_state.selected_box_id = None
                        st.rerun()
                    elif modified:
                        st.rerun()

                else:
                    if mode_toggle_pressed:
                        st.session_state.selected_box_id = None
                        st.rerun()
                    
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
                            
                            if w < 10 and h < 10:
                                cx = (new_obj['left'] + w/2) / pdf_to_canvas_ratio
                                cy = (new_obj['top'] + h/2) / pdf_to_canvas_ratio
                                clicked_id = None
                                for a in reversed(st.session_state.annotations):
                                    if a['page_idx'] == st.session_state.current_page:
                                        r = a['pdf_rect']
                                        if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]:
                                            clicked_id = a['id']
                                            break
                                if clicked_id:
                                    st.session_state.selected_box_id = clicked_id
                                    st.rerun()
                                
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
                                st.session_state.group_counter += 1 # 새 박스 생성 시 고유 그룹 카운터 증가
                                
                                img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                                img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
                                
                                box_height = fit_rect.y1 - fit_rect.y0
                                zoom_f = 2 if box_height > 50 else 4
                                page.get_pixmap(matrix=fitz.Matrix(zoom_f, zoom_f), clip=fit_rect).save(img_path)
                                
                                basic_text = clean_text(extract_text_with_spaces(page, fit_rect))
                                ocr_text = extract_text_via_ocr(img_path, st.session_state.ocr_lang)
                                
                                anno_id = f"id_{st.session_state.crop_counter}"
                                st.session_state.annotations.append({
                                    'id': anno_id, 'page_idx': st.session_state.current_page,
                                    'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                                    'text': basic_text,
                                    'ocr_text': ocr_text,
                                    'final_text': basic_text,
                                    'img_name': img_name, 'img_path': img_path,
                                    'label': st.session_state.active_label,
                                    'group_id': st.session_state.group_counter # [신규] 기본 단독 그룹 부여
                                })
                                
                                st.session_state.selected_box_id = None
                                st.rerun()

    anno_dict = {a['id']: a for a in st.session_state.annotations} if st.session_state.annotations else {}

    with col_list_img:
        st.subheader("데이터 추출 목록")
        if anno_dict:
            valid_ids = list(anno_dict.keys())
            radio_options = ["NEW_MODE"] + valid_ids

            st.markdown("""<style>.scroll-v { max-height: 250px; overflow-y: auto; border: 2px solid #4A90E2; border-radius: 8px; padding: 5px; background: #fcfcfc; }</style>""", unsafe_allow_html=True)
            st.markdown('<div class="scroll-v">', unsafe_allow_html=True)
            
            def format_label(aid):
                if aid == "NEW_MODE":
                    return "✨ [신규 태깅 모드] 빈 공간을 드래그하세요" if show_pdf else "✨ [신규 추출 대기] PDF 뷰어를 열어주세요"
                a = anno_dict[aid]
                r = a['pdf_rect']
                lbl = a.get('label', '미지정')
                g_id = a.get('group_id', 0)
                coords = "[X:" + str(int(r[0])) + ", Y:" + str(int(r[1])) + "]"
                display_text = a.get('final_text', a['text'])
                # 목록 식별용 포맷에 [그룹 번호] 추가 표시
                return f"[G{g_id}] [P{a['page_idx']+1}] [{lbl}] {coords} | " + display_text[:15].replace('\n', ' ') + "..."

            current_val = st.session_state.selected_box_id if st.session_state.selected_box_id in valid_ids else "NEW_MODE"
            idx = radio_options.index(current_val)

            selected_id = st.radio("목록", options=radio_options, format_func=format_label, index=idx, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != current_val:
                st.session_state.selected_box_id = None if selected_id == "NEW_MODE" else selected_id
                if selected_id != "NEW_MODE":
                    st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            curr_anno = anno_dict.get(st.session_state.selected_box_id)
            if curr_anno:
                if not show_pdf:
                    st.markdown("---")
                if os.path.exists(curr_anno['img_path']):
                    with open(curr_anno['img_path'], "rb") as img_file:
                        img_bytes = img_file.read()
                    st.image(img_bytes, use_column_width=True)
                else:
                    st.warning("이미지 파일을 찾을 수 없습니다.")
        else:
            st.info("추출된 데이터가 없습니다. PDF를 드래그하세요.")
            curr_anno = None

    with col_edit:
        if curr_anno:
            if not show_pdf:
                st.subheader("상세 데이터 교정")
            else:
                st.markdown("---")
            
            # [그룹화 UI 라인 신설]
            c_g1, c_g2 = st.columns([4, 6])
            with c_g1:
                st.markdown(f"#### 🔗 현재 그룹: `Group {curr_anno.get('group_id', 0)}`")
            with c_g2:
                # 현재 항목의 전체 리스트 중 위치 인덱스 계산
                curr_list_idx = list(anno_dict.keys()).index(curr_anno['id'])
                if curr_list_idx > 0:
                    st.button("🔗 이전 항목과 그룹 연결 (2단/이어지는 문장)", 
                              key=f"merge_g_{curr_anno['id']}", 
                              on_click=merge_with_previous_group, 
                              args=(curr_anno['id'],),
                              use_container_width=True,
                              help="목록에서 바로 위에 있는 항목과 같은 그룹번호로 병합합니다.")
                else:
                    st.button("🔗 연결할 이전 항목 없음", disabled=True, use_container_width=True)

            curr_lbl = curr_anno.get('label', '미지정')
            lbl_idx = st.session_state.labels.index(curr_lbl) if curr_lbl in st.session_state.labels else 0
            st.selectbox("🏷️ 라벨 변경", options=st.session_state.labels, index=lbl_idx, 
                         key=f"lbl_sel_{curr_anno['id']}", on_change=update_label, args=(curr_anno['id'],))

            st.markdown("##### 🔍 텍스트 추출 결과 비교")
            col_b, col_o = st.columns(2)
            with col_b:
                st.text_area("📝 기본 추출 (PyMuPDF)", value=curr_anno['text'], height=100, disabled=True)
                st.button("⬇️ 기본 추출 채택", key=f"btn_basic_{curr_anno['id']}", on_click=apply_text_to_final, args=(curr_anno['id'], 'basic'), use_container_width=True)
            with col_o:
                st.text_area("🔍 이미지 인식 (OCR)", value=curr_anno.get('ocr_text', ''), height=100, disabled=True)
                st.button("⬇️ OCR 채택", key=f"btn_ocr_{curr_anno['id']}", on_click=apply_text_to_final, args=(curr_anno['id'], 'ocr'), use_container_width=True)
                if st.button("🔄 재인식 (설정 언어 적용)", key=f"btn_reocr_{curr_anno['id']}", use_container_width=True, help="사이드바의 언어 설정으로 OCR을 다시 수행합니다."):
                    curr_anno['ocr_text'] = extract_text_via_ocr(curr_anno['img_path'], st.session_state.ocr_lang)
                    st.rerun()

            st.markdown("##### 💡 두 추출 결과 차이점 (기본 vs OCR)")
            diff_html = get_html_diff(curr_anno['text'], curr_anno.get('ocr_text', ''))
            st.markdown(f"""
            <div style='border:1px solid #ddd; padding:10px; border-radius:5px; background:#fff; max-height:150px; overflow-y:auto; font-size:1.0em; line-height: 1.6;'>
                {diff_html}
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<span style='font-size:0.85em; color:gray;'>* ✨색칠된 단어를 <b>클릭</b>하면 아래 입력창 커서 위치에 바로 삽입됩니다.</span>", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            
            curr_anno['final_text'] = st.text_area("✨ 최종 교정 텍스트 (직접 수정 가능)", 
                                                   value=curr_anno.get('final_text', curr_anno['text']), 
                                                   height=text_area_height, 
                                                   key=f"final_input_{curr_anno['id']}", 
                                                   on_change=update_final_text, 
                                                   args=(curr_anno['id'],))

            c1, c2, c3, c4 = st.columns([1, 1, 1.5, 1.5])
            c1.button("🗑️ 삭제", type="primary", on_click=delete_single_item, args=(curr_anno['id'],))
            if c2.button("💾 저장"):
                st.toast("저장 기능은 아직 준비 중입니다.", icon="🚧")
            
            # ====================================================
            # [그룹 정렬 파이프라인 수립] 출력 데이터 생성 시 동일 그룹 병합
            # ====================================================
            # 1. 고유한 그룹 번호 순서대로 정렬하기 위해 고유 그룹 리스트 생성
            unique_groups = sorted(list(set([a.get('group_id', 0) for a in st.session_state.annotations])))
            
            md_text = "# 문서 추출 데이터 (그룹 병합 완료)\n\n"
            export_data = []
            
            for gid in unique_groups:
                # 동일한 그룹 아이디를 가진 단락들 필터링
                group_annos = [a for a in st.session_state.annotations if a.get('group_id', 0) == gid]
                if not group_annos: continue
                
                # 라벨과 페이지는 그룹 내 첫 번째 항목을 기준 데이터로 채택
                primary_anno = group_annos[0]
                lbl = primary_anno.get('label', '미지정')
                pages_str = ", ".join(sorted(list(set([str(a['page_idx']+1) for a in group_annos]))))
                
                # 그룹 내부의 텍스트들을 순서대로 스페이스로 묶어 결합
                merged_final_text = " ".join([a.get('final_text', a['text']) for a in group_annos])
                merged_raw_basic = "\n[단락 구분]\n".join([a['text'] for a in group_annos])
                merged_raw_ocr = "\n[단락 구분]\n".join([a.get('ocr_text', '') for a in group_annos])
                
                # 마크다운 빌드
                md_text += f"## 🔗 Group {gid} (Page: {pages_str})\n"
                md_text += f"- **최종 지정 라벨 (Label):** `{lbl}`\n"
                md_text += "#### 📝 통합 최종 추출 데이터\n```text\n" + merged_final_text + "\n```\n"
                md_text += "---\n\n"
                
                # JSON 빌드
                export_data.append({
                    "group_id": gid,
                    "pages": [a['page_idx']+1 for a in group_annos],
                    "label": lbl,
                    "text": merged_final_text,
                    "raw_basic_chunks": [a['text'] for a in group_annos],
                    "raw_ocr_chunks": [a.get('ocr_text', '') for a in group_annos],
                    "bboxes": [a['pdf_rect'] for a in group_annos]
                })
            # ====================================================
            
            c3.download_button("📝 마크다운", data=md_text, file_name="result.md", mime="text/markdown")
            c4.download_button("📥 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                            file_name="result.json", mime="application/json")
        else:
            if not show_pdf:
                st.info("왼쪽 목록에서 편집할 항목을 선택하세요.")

# ==========================================
# 5. 숨김 버튼 마커 및 JS 연동
# ==========================================
st.markdown('<div id="hidden_buttons_marker" style="display:none;"></div>', unsafe_allow_html=True)
st.markdown(
    """
    <style>
    div.element-container:has(#hidden_buttons_marker) ~ div.element-container { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True
)

for i, lbl in enumerate(st.session_state.labels):
    if i < 9:
        st.button(f"HL_{i}", key=f"btn_shortcut_lbl_{i}", on_click=set_active_label, args=(lbl,))
st.button("HE_ESC", key="btn_shortcut_esc", on_click=handle_esc)

# ==========================================
# 6. JavaScript (Base64 인젝션: 빈 공간 클릭 감지 복귀)
# ==========================================
shortcut_html = "<div style='text-align:center; font-size:1.2em; margin-bottom:15px; border-bottom:1px solid #555; padding-bottom:10px;'><b>⌨️ 라벨 단축키 안내 (숫자키 1~9)</b></div>"
shortcut_html += "<div style='display:grid; grid-template-columns: 40px auto; gap: 8px 15px; font-size:1.1em;'>"
for i, lbl in enumerate(st.session_state.labels):
    if i < 9:
        shortcut_html += f"<div><span style='background:#444; padding:3px 8px; border-radius:4px;'>{i+1}</span></div><div>{lbl}</div>"
shortcut_html += "</div>"

raw_js_code = f"""
window._current_active_rect = {active_rect_js};
window._current_tag_mode = "{tag_mode}";

if (!window._custom_js_injected) {{
    const trackCaret = function(e) {{
        if (e.target.tagName === 'TEXTAREA') {{
            window._lastTASelectionStart = e.target.selectionStart;
            window._lastTASelectionEnd = e.target.selectionEnd;
            window._lastActiveTA = e.target;
        }}
    }};
    window.document.addEventListener('keyup', trackCaret, true);
    window.document.addEventListener('click', trackCaret, true);
    window.document.addEventListener('focusout', trackCaret, true);
    
    window.insertDiffText = function(element) {{
        const textToInsert = element.innerText;
        let targetTA = window._lastActiveTA;
        
        if (!targetTA) {{
            const labels = window.document.querySelectorAll('label');
            for (let lbl of labels) {{
                if (lbl.innerText.includes("최종 교정 텍스트")) {{
                    const container = lbl.closest('div[data-testid="stTextArea"]');
                    if (container) {{
                        targetTA = container.querySelector('textarea');
                        break;
                    }}
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
            
            const originalBg = element.style.backgroundColor;
            element.style.backgroundColor = '#fff000';
            setTimeout(() => {{ element.style.backgroundColor = originalBg; }}, 150);
        }}
    }};

    setInterval(() => {{
        if (window._current_tag_mode !== "transform") return;
        const iframes = window.document.querySelectorAll('iframe[title="streamlit_drawable_canvas.st_canvas"]');
        if (iframes.length > 0) {{
            try {{
                const cw = iframes[0].contentWindow;
                if (cw && !cw._bg_click_listener_attached) {{
                    cw.document.addEventListener('mousedown', function(e) {{
                        const activeRect = window._current_active_rect;
                        if (activeRect && window._current_tag_mode === "transform") {{
                            if (e.target.tagName === 'CANVAS') {{
                                const x = e.offsetX;
                                const y = e.offsetY;
                                const pad = 25; 
                                const inBox = (
                                    x >= activeRect.left - pad &&
                                    x <= activeRect.left + activeRect.width + pad &&
                                    y >= activeRect.top - pad &&
                                    y <= activeRect.top + activeRect.height + pad
                                );
                                
                                if (!inBox) {{
                                    const btn_esc = window.document.querySelectorAll('button');
                                    const escBtn = Array.from(btn_esc).find(el => el.innerText === 'HE_ESC');
                                    if (escBtn) escBtn.click();
                                }}
                            }}
                        }}
                    }});
                    cw._bg_click_listener_attached = true;
                }}
            }} catch(e) {{ 
                console.error("CORS prevented iframe background click detection.");
            }}
        }}
    }}, 1000);

    window._my_keydown_listener = function(e) {{
        if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
        const doc = window.document;
        let overlay = doc.getElementById('shortcut-overlay');

        if (e.key === 'ArrowLeft') {{
            const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === '◀');
            if (btn) btn.click();
        }} else if (e.key === 'ArrowRight') {{
            const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === '▶');
            if (btn) btn.click();
        }} else if (e.key === 'Escape') {{
            const btn_toggle = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('Modify 모드') || el.innerText.includes('Drag 모드'));
            if (btn_toggle) btn_toggle.click();
            const btn_esc = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === 'HE_ESC');
            if (btn_esc) btn_esc.click();
        }} else if (e.key === 'Delete' || e.key === 'Backspace') {{
            const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.trim() === '🗑️ 삭제');
            if (btn) btn.click();
        }} else if (e.key === 'Control') {{
            if (overlay) overlay.style.display = 'block';
        }} else if (['1','2','3','4','5','6','7','8','9'].includes(e.key)) {{
            if (e.ctrlKey) e.preventDefault();
            const index = parseInt(e.key) - 1;
            const targetText = 'HL_' + index;
            const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === targetText);
            if (btn) btn.click();
        }}
    }};

    window._my_keyup_listener = function(e) {{
        if (e.key === 'Control') {{
            const doc = window.document;
            let overlay = doc.getElementById('shortcut-overlay');
            if (overlay) overlay.style.display = 'none';
        }}
    }};

    window.document.addEventListener('keydown', window._my_keydown_listener);
    window.document.addEventListener('keyup', window._my_keyup_listener);
    window._custom_js_injected = true;
}}

let overlay = window.document.getElementById('shortcut-overlay');
if (!overlay) {{
    overlay = window.document.createElement('div');
    overlay.id = 'shortcut-overlay';
    overlay.style.position = 'fixed';
    overlay.style.top = '50%';
    overlay.style.left = '50%';
    overlay.style.transform = 'translate(-50%, -50%)';
    overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.85)';
    overlay.style.color = '#fff';
    overlay.style.padding = '25px 35px';
    overlay.style.borderRadius = '12px';
    overlay.style.zIndex = '9999';
    overlay.style.display = 'none';
    overlay.style.boxShadow = '0 10px 30px rgba(0,0,0,0.5)';
    overlay.style.pointerEvents = 'none';
    window.document.body.appendChild(overlay);
}}
overlay.innerHTML = "{shortcut_html}";
"""

js_b64 = base64.b64encode(raw_js_code.encode('utf-8')).decode('utf-8')

st.markdown(f"""
    <div style="display:none;">
        <img src="dummy" onerror="eval(atob('{js_b64}'));" />
    </div>
""", unsafe_allow_html=True)
