import streamlit as st
import streamlit.components.v1 as components
import fitz  # PyMuPDF
import json
import os
import io
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas

# ==========================================
# 1. 페이지 및 상태 초기화
# ==========================================
st.set_page_config(layout="wide", page_title="상호작용 데이터 구축 - Web Editor")

# 숨김 버튼 제거 및 숫자 입력창 스타일 조정 CSS
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
    st.session_state.labels = ['논문명', '저자명', '소속기관', '초록', '키워드']

state_keys = {
    'file_bytes': None, 'pdf_doc': None, 'current_page': 0, 
    'annotations': [], 'crop_counter': 0, 'selected_box_id': None,
    'last_canvas_sig': None, 'file_name': "",
    'active_label': st.session_state.labels[0] if 'labels' in st.session_state else '논문명',
    'redraw_trigger': 0
}

for key, default in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

IMAGE_SAVE_DIR = "extracted_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# ==========================================
# [신규] 기술 문서 팝업(Dialog) 함수 정의
# ==========================================
@st.dialog("⚙️ 시스템 작동 원리 (Technical Documentation)", width="large")
def show_technical_document():
    st.markdown("""
    ## 🚀 PDF 상호작용 추출기 작동 원리

    이 시스템은 이미지에서 글자를 유추하는 **OCR(광학 문자 인식) 방식이 아닌, 디지털 좌표 매핑(Mapping) 방식**을 사용하여 빠르고 정확하게 데이터를 추출합니다.

    ---

    ### 1. 🎯 좌표 매핑 및 클리핑 (Clipping)
    사용자가 좌측 뷰어에서 마우스로 영역을 드래그하면, 웹 브라우저 캔버스의 상대 좌표(X, Y, Width, Height)가 **PDF 원본의 절대 좌표(BBox)**로 정밀하게 변환됩니다.
    백엔드 렌더링 엔진(`PyMuPDF`)은 이 좌표를 바탕으로 `clip=rect` 옵션을 사용하여, 지정된 박스 내부에 존재하는 디지털 텍스트 객체와 이미지 픽셀만을 정확하게 잘라내어(Clipping) 가져옵니다.

    ### 2. ✨ 정밀 오토피팅 (Auto-fitting) 알고리즘
    사용자가 드래그를 다소 러프하게 하더라도 글자 크기에 딱 맞게 보정되는 원리는 다음과 같습니다.
    - 문서 전체의 단어 단위 좌표를 백그라운드에서 스캔합니다.
    - 사용자가 그린 영역과 조금이라도 **교차(Intersect)하는 단어**들을 모두 찾아냅니다.
    - 찾아낸 단어들의 외곽선을 모두 포함하는 **최적의 최소 경계 상자(Minimum Bounding Box)**를 계산하여 좌표를 자동 보정합니다.

    ### 3. 📊 데이터 추출 방식 비교
    | 구분 | 현재 시스템 (디지털 파싱) | 기존 방식 (OCR) |
    |:---|:---|:---|
    | **정확도** | **100%** (원본 데이터 복사로 오타 원천 차단) | 80~95% (글꼴, 화질에 따라 오인식 발생) |
    | **속도** | **즉시 추출** (0.1초 이내 처리) | 느림 (AI 모델 추론 및 이미지 연산 시간 소요) |
    | **한계점** | 텍스트 레이어가 없는 스캔본(통짜 이미지) 불가 | 이미지 스캔본도 인식 가능 |

    > 💡 **결론:** 현대의 디지털 논문, 공공 문서, 표준 지침 등에서 데이터를 라벨링하고 추출하는 데 있어, 구조적 메타데이터 훼손 없이 **가장 빠르고 완벽한 하이브리드(Text + Image) 추출 방식**을 제공합니다.
    """)
    if st.button("닫기", use_container_width=True):
        st.rerun()

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

def clean_text(text):
    if not text: return ""
    lines = text.split('\n')
    return "\n".join([line.strip() for line in lines if "저자소개" not in line and line.strip()])

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
        for f in os.listdir(IMAGE_SAVE_DIR):
            try: os.remove(os.path.join(IMAGE_SAVE_DIR, f))
            except: pass
            
        st.session_state.file_bytes = uploaded_file.read()
        st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
        st.session_state.file_name = uploaded_file.name
        st.session_state.current_page = 0
        st.session_state.annotations = []
        st.session_state.crop_counter = 0
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
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)

    # [신규] 사이드바 최하단에 작동 원리 문서 호출 버튼 배치
    st.sidebar.markdown("<br><br><br>", unsafe_allow_html=True) # 아래로 공간 확보
    if st.sidebar.button("📖 작동 원리 보기 (기술 문서)", use_container_width=True):
        show_technical_document()

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
    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            r = anno['pdf_rect']
            is_sel = (st.session_state.selected_box_id == anno['id'])
            fabric_objects.append({
                "type": "rect",
                "left": r[0] * pdf_to_canvas_ratio,
                "top": r[1] * pdf_to_canvas_ratio,
                "width": (r[2] - r[0]) * pdf_to_canvas_ratio,
                "height": (r[3] - r[1]) * pdf_to_canvas_ratio,
                "fill": "rgba(255, 0, 0, 0.2)" if is_sel else "rgba(0, 0, 255, 0.1)",
                "stroke": "rgba(255, 0, 0, 0.9)" if is_sel else "rgba(0, 0, 255, 0.7)",
                "strokeWidth": 3 if is_sel else 2,
                "id": anno['id']
            })
    
    initial_drawing = {"version": "4.4.0", "objects": fabric_objects}
    tag_mode = "transform" if st.session_state.selected_box_id else "rect"

    left_col, right_col = st.columns([6, 4])

    with left_col:
        with st.expander("💡 온라인 도움말 및 사용 가이드 (단축키 안내)", expanded=False):
            st.markdown("""
            **1. 기본 조작 및 라벨 관리**
            - 좌측 사이드바에서 PDF 파일을 업로드하고, 태깅할 데이터의 속성(라벨)을 선택하거나 새로 추가/삭제할 수 있습니다.
            
            **2. 태깅 모드 가이드**
            - **Drag 모드:** 문서의 빈 공간을 마우스로 드래그하면 새로운 박스가 그려지고 데이터가 추출됩니다. (그리기 전 좌측에서 라벨을 먼저 선택하세요)
            - **Modify 모드:** 이미 그려진 박스를 클릭하면 수정 모드가 됩니다. 크기나 위치를 조절한 뒤, 빈 공간을 클릭하거나 `ESC` 키를 누르면 수정사항이 저장되고 다시 Drag 모드로 복귀합니다.
            
            **3. ⌨️ 작업 효율을 높이는 단축키**
            - `Ctrl + 1~9` : 작업 중 마우스 이동 없이 태깅할 라벨을 즉시 변경합니다. (**Ctrl 키를 꾹 누르고 있으면** 화면 중앙에 지정된 숫자 단축키 안내창이 나타납니다.)
            - `◀` / `▶` : 이전 페이지 / 다음 페이지로 이동합니다.
            - `Delete` 또는 `Backspace` : 현재 선택된 박스를 즉시 삭제합니다.
            - `ESC` : 수정 중인 작업을 취소하고 Drag 모드로 강제 복귀합니다.
            
            **4. 데이터 출력**
            - 모든 태깅 작업이 끝나면 우측 하단의 버튼을 통해 메타데이터를 **마크다운(.md)** 또는 **JSON** 형식으로 다운로드할 수 있습니다.
            """)

        st.write("### PDF 상호작용 구축 도구")

        ctrl_cols = st.columns([1.2, 1.2, 2, 1.2, 1.2, 2])
        ctrl_cols[0].button("⏮", on_click=go_first, use_container_width=True, help="첫 페이지")
        ctrl_cols[1].button("◀", on_click=go_prev, use_container_width=True, help="이전 페이지")
        
        ctrl_cols[2].number_input("페이지 입력", min_value=1, max_value=total_pages, value=st.session_state.current_page + 1, on_change=page_input_changed, key="page_input_widget", label_visibility="collapsed")
        
        ctrl_cols[3].button("▶", on_click=go_next, args=(total_pages,), use_container_width=True, help="다음 페이지")
        ctrl_cols[4].button("⏭", on_click=go_last, args=(total_pages,), use_container_width=True, help="마지막 페이지")
        
        ctrl_cols[5].markdown(f"<div style='padding-top: 5px; font-size:16px; font-weight: bold;'>/ {total_pages}</div>", unsafe_allow_html=True)

        st.markdown("---")
        
        if tag_mode == "transform":
            btn_label = "🔄 현재: Modify 모드 (클릭하여 Drag 모드로 복귀)"
        else:
            btn_label = "🖱️ 현재: Drag 모드 (기존 박스를 클릭하면 Modify 모드)"
            
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
                                            fit_rect = matched[0]
                                            for r in matched[1:]: fit_rect |= r

                                    anno['pdf_rect'] = [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1]
                                    
                                    if os.path.exists(anno['img_path']):
                                        try: os.remove(anno['img_path'])
                                        except: pass
                                        
                                    st.session_state.crop_counter += 1
                                    new_img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                                    new_img_path = os.path.join(IMAGE_SAVE_DIR, new_img_name)
                                    page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=fit_rect).save(new_img_path)
                                    
                                    anno['img_name'] = new_img_name
                                    anno['img_path'] = new_img_path
                                    anno['text'] = clean_text(page.get_text("text", clip=fit_rect))
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
                                    fit_rect = matched[0]
                                    for r in matched[1:]: fit_rect |= r
                            
                            st.session_state.crop_counter += 1
                            img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                            img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
                            page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=fit_rect).save(img_path)
                            
                            anno_id = f"id_{st.session_state.crop_counter}"
                            st.session_state.annotations.append({
                                'id': anno_id, 'page_idx': st.session_state.current_page,
                                'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                                'text': clean_text(page.get_text("text", clip=fit_rect)),
                                'img_name': img_name, 'img_path': img_path,
                                'label': st.session_state.active_label
                            })
                            
                            st.session_state.selected_box_id = None
                            st.rerun()

    with right_col:
        st.subheader("데이터 추출 목록")
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            radio_options = ["NEW_MODE"] + valid_ids

            st.markdown("""<style>.scroll-v { max-height: 350px; overflow-y: auto; border: 2px solid #4A90E2; border-radius: 8px; padding: 5px; background: #fcfcfc; }</style>""", unsafe_allow_html=True)
            st.markdown('<div class="scroll-v">', unsafe_allow_html=True)
            
            def format_label(aid):
                if aid == "NEW_MODE":
                    return "✨ [신규 태깅 모드] 빈 공간을 드래그하세요"
                a = anno_dict[aid]
                r = a['pdf_rect']
                lbl = a.get('label', '미지정')
                coords = "[X:" + str(int(r[0])) + ", Y:" + str(int(r[1])) + "]"
                return f"[P{a['page_idx']+1}] [{lbl}] {coords} | " + a['text'][:15].replace('\n', ' ') + "..."

            current_val = st.session_state.selected_box_id if st.session_state.selected_box_id in valid_ids else "NEW_MODE"
            idx = radio_options.index(current_val)

            selected_id = st.radio("목록", options=radio_options, format_func=format_label, index=idx, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != current_val:
                st.session_state.selected_box_id = None if selected_id == "NEW_MODE" else selected_id
                if selected_id != "NEW_MODE":
                    st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            st.markdown("---")
            if st.session_state.selected_box_id in anno_dict:
                curr_anno = anno_dict[st.session_state.selected_box_id]
                
                if os.path.exists(curr_anno['img_path']):
                    with open(curr_anno['img_path'], "rb") as img_file:
                        img_bytes = img_file.read()
                    st.image(img_bytes, use_column_width=True)
                else:
                    st.warning("이미지 파일을 찾을 수 없습니다. 다시 드래그하여 영역을 갱신해 주세요.")

                curr_lbl = curr_anno.get('label', '미지정')
                lbl_idx = st.session_state.labels.index(curr_lbl) if curr_lbl in st.session_state.labels else 0
                st.selectbox("🏷️ 라벨 변경", options=st.session_state.labels, index=lbl_idx, 
                             key=f"lbl_sel_{curr_anno['id']}", on_change=update_label, args=(curr_anno['id'],))

                curr_anno['text'] = st.text_area("📝 내용 수정", value=curr_anno['text'], height=150)

                c1, c2, c3, c4 = st.columns([1, 1, 1.5, 1.5])
                
                c1.button("🗑️ 삭제", type="primary", on_click=delete_single_item, args=(curr_anno['id'],))
                
                if c2.button("💾 저장"):
                    st.toast("저장 기능은 아직 준비 중입니다.", icon="🚧")
                
                md_text = "# 문서 추출 데이터\n\n"
                for a in st.session_state.annotations:
                    r = a['pdf_rect']
                    lbl = a.get('label', '미지정')
                    md_text += "### Page " + str(a['page_idx'] + 1) + "\n"
                    md_text += "- **라벨 (Label):** `" + lbl + "`\n"
                    md_text += "- **좌표 (BBox):** `[X: " + str(int(r[0])) + ", Y: " + str(int(r[1])) + ", W: " + str(int(r[2]-r[0])) + ", H: " + str(int(r[3]-r[1])) + "]`\n"
                    md_text += chr(96) + chr(96) + chr(96) + "text\n"
                    md_text += str(a['text']) + "\n"
                    md_text += chr(96) + chr(96) + chr(96) + "\n\n---\n"
                
                c3.download_button("📝 마크다운", data=md_text, file_name="result.md", mime="text/markdown")
                
                export_data = [{"page": a['page_idx']+1, "label": a.get('label', '미지정'), "bbox": a['pdf_rect'], "text": a['text']} for a in st.session_state.annotations]
                c4.download_button("📥 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                                file_name="result.json", mime="application/json")
        else:
            st.info("왼쪽 뷰어에서 영역을 드래그하여 태깅을 시작하세요.")

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
# 6. JavaScript 단축키 연동 및 가이드 오버레이
# ==========================================
shortcut_html = "<div style='text-align:center; font-size:1.2em; margin-bottom:15px; border-bottom:1px solid #555; padding-bottom:10px;'><b>⌨️ 라벨 단축키 안내 (숫자키 1~9)</b></div>"
shortcut_html += "<div style='display:grid; grid-template-columns: 40px auto; gap: 8px 15px; font-size:1.1em;'>"
for i, lbl in enumerate(st.session_state.labels):
    if i < 9:
        shortcut_html += f"<div><span style='background:#444; padding:3px 8px; border-radius:4px;'>{i+1}</span></div><div>{lbl}</div>"
shortcut_html += "</div>"

components.html(f"""
<script>
const doc = window.parent.document;
const currentMode = "{tag_mode}";

let overlay = doc.getElementById('shortcut-overlay');
if (!overlay) {{
    overlay = doc.createElement('div');
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
    doc.body.appendChild(overlay);
}}
overlay.innerHTML = "{shortcut_html}";

if (doc._my_keydown_listener) {{
    doc.removeEventListener('keydown', doc._my_keydown_listener);
    doc.removeEventListener('keyup', doc._my_keyup_listener);
}}

doc._my_keydown_listener = function(e) {{
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;

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
        if (currentMode !== 'transform') {{
            overlay.style.display = 'block';
        }}
    }} else if (['1','2','3','4','5','6','7','8','9'].includes(e.key)) {{
        if (e.ctrlKey) {{
            e.preventDefault();
        }}
        const index = parseInt(e.key) - 1;
        const targetText = 'HL_' + index;
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === targetText);
        if (btn) btn.click();
    }}
}};

doc._my_keyup_listener = function(e) {{
    if (e.key === 'Control') {{
        overlay.style.display = 'none';
    }}
}};

doc.addEventListener('keydown', doc._my_keydown_listener);
doc.addEventListener('keyup', doc._my_keyup_listener);
</script>
""", height=0)
