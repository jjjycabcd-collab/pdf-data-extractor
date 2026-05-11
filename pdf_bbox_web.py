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
st.set_page_config(layout="wide", page_title="상호작업 데이터 구축 - Web Editor")

state_keys = {
    'file_bytes': None, 'pdf_doc': None, 'current_page': 0, 
    'annotations': [], 'crop_counter': 0, 'selected_box_id': None,
    'clear_trigger': 0, 'canvas_state': {"version": "4.4.0", "objects": [], "trigger": 0},
    'last_canvas_sig': None, 'file_name': ""
}

for key, default in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

IMAGE_SAVE_DIR = "extracted_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# ==========================================
# 2. 유틸리티 함수
# ==========================================
def clean_extracted_text(text):
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines if "저자소개" not in line and line.strip()]
    return "\n".join(cleaned_lines)

def go_prev():
    if st.session_state.current_page > 0:
        st.session_state.current_page -= 1
        st.session_state.selected_box_id = None
        st.session_state.last_canvas_sig = None

def go_next(total_pages):
    if st.session_state.current_page < total_pages - 1:
        st.session_state.current_page += 1
        st.session_state.selected_box_id = None
        st.session_state.last_canvas_sig = None

def delete_single_item(anno_obj):
    """현재 선택된 단 하나의 항목만 삭제"""
    if anno_obj:
        # 이미지 파일 삭제
        if os.path.exists(anno_obj['img_path']):
            os.remove(anno_obj['img_path'])
        # 리스트에서 제거
        if anno_obj in st.session_state.annotations:
            st.session_state.annotations.remove(anno_obj)
        # 선택 상태 초기화
        st.session_state.selected_box_id = None

@st.cache_data(show_spinner=False)
def get_cached_bg_bytes(file_bytes, page_idx):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    return pix.tobytes("png")

def get_autofit_rect(page, pdf_rect, autofit_enabled):
    if not autofit_enabled: return pdf_rect
    words = page.get_text("words")
    fitted_rect = None
    for w in words:
        w_rect = fitz.Rect(w[:4])
        if pdf_rect.intersects(w_rect):
            fitted_rect = w_rect if fitted_rect is None else fitted_rect | w_rect 
    return fitted_rect if fitted_rect else pdf_rect

def save_cropped_image(page, pdf_rect):
    st.session_state.crop_counter += 1
    filename = f"crop_p{st.session_state.current_page+1}_{st.session_state.crop_counter:03d}.png"
    filepath = os.path.join(IMAGE_SAVE_DIR, filename)
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=pdf_rect)
    pix.save(filepath)
    return filename, filepath

# ==========================================
# 3. 메인 UI 레이아웃
# ==========================================
st.title("📄 상호작업 데이터 구축 - Web Editor")

uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

if uploaded_file is not None:
    if st.session_state.file_name != uploaded_file.name:
        st.session_state.file_bytes = uploaded_file.read()
        st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
        st.session_state.file_name = uploaded_file.name
        st.session_state.annotations = []
        st.rerun()

    doc = st.session_state.pdf_doc
    total_pages = len(doc)

    st.sidebar.markdown("---")
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)
    
    col_nav1, col_nav2 = st.sidebar.columns(2)
    col_nav1.button("◀ 이전", on_click=go_prev)
    col_nav2.button("다음 ▶", on_click=go_next, args=(total_pages,))
    st.sidebar.write(f"**Page:** {st.session_state.current_page + 1} / {total_pages}")

    # PDF 배경 로드
    bg_bytes = get_cached_bg_bytes(st.session_state.file_bytes, st.session_state.current_page)
    bg_image = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
    
    overlay = Image.new("RGBA", bg_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    img_scale = 1.5 

    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            x0, y0, x1, y1 = [c * img_scale for c in anno['pdf_rect']]
            is_sel = (st.session_state.selected_box_id == anno['id'])
            draw.rectangle([x0, y0, x1, y1], outline=(255,0,0,255) if is_sel else (0,0,255,255), width=3 if is_sel else 2)
            draw.rectangle([x0, y0, x1, y1], fill=(255,0,0,40) if is_sel else (0,0,255,20))

    bg_composite = Image.alpha_composite(bg_image, overlay)
    left_col, right_col = st.columns([6, 4])

    with left_col:
        st.write("**[PDF 뷰어] 드래그하여 영역을 추출하세요**")
        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.1)",
            stroke_width=2,
            stroke_color="rgba(0, 0, 255, 0.8)",
            background_image=bg_composite,
            initial_drawing=st.session_state.canvas_state,
            update_streamlit=True,
            height=bg_image.height,
            width=bg_image.width,
            drawing_mode="rect",
            key=f"canvas_p{st.session_state.current_page}",
        )

        if canvas_result.json_data:
            objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
            if objs:
                new_rect = objs[-1]
                rect_sig = f"{new_rect['left']}_{new_rect['top']}_{new_rect['width']}"
                if st.session_state.last_canvas_sig != rect_sig:
                    st.session_state.last_canvas_sig = rect_sig
                    p_x0, p_y0 = new_rect["left"] / img_scale, new_rect["top"] / img_scale
                    p_x1, p_y1 = (new_rect["left"] + new_rect["width"]) / img_scale, (new_rect["top"] + new_rect["height"]) / img_scale
                    
                    if new_rect["width"] < 15: 
                        clicked_id = None
                        for a in reversed(st.session_state.annotations):
                            if a['page_idx'] == st.session_state.current_page:
                                rx0, ry0, rx1, ry1 = a['pdf_rect']
                                if rx0 <= p_x0 <= rx1 and ry0 <= p_y0 <= ry1:
                                    clicked_id = a['id']
                                    break
                        st.session_state.selected_box_id = clicked_id
                    else: 
                        page = doc.load_page(st.session_state.current_page)
                        fit_rect = get_autofit_rect(page, fitz.Rect(p_x0, p_y0, p_x1, p_y1), autofit_enabled)
                        raw_text = page.get_text("text", clip=fit_rect)
                        text = clean_extracted_text(raw_text)
                        img_name, img_path = save_cropped_image(page, fit_rect)
                        
                        anno_id = f"id_{st.session_state.crop_counter}"
                        st.session_state.annotations.append({
                            'id': anno_id, 'page_idx': st.session_state.current_page,
                            'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                            'text': text, 'img_name': img_name, 'img_path': img_path
                        })
                        st.session_state.selected_box_id = anno_id
                    
                    st.session_state.clear_trigger += 1
                    st.session_state.canvas_state["trigger"] = st.session_state.clear_trigger
                    st.rerun()

    with right_col:
        st.subheader("데이터 추출 목록")
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            
            if st.session_state.selected_box_id not in valid_ids:
                st.session_state.selected_box_id = valid_ids[-1]

            # --- [수정] 5건 기준 스크롤바 영역 설정 ---
            st.markdown("""
                <style>
                .scroll-container {
                    max-height: 230px; 
                    overflow-y: auto;
                    border: 1px solid #e6e9ef;
                    border-radius: 8px;
                    padding: 5px;
                    background-color: #f8f9fb;
                }
                div[data-testid="stRadio"] > div { gap: 2px; }
                </style>
                """, unsafe_allow_html=True)

            st.markdown('<div class="scroll-container">', unsafe_allow_html=True)
            def format_label(aid):
                txt = anno_dict[aid]['text'][:30].replace('\n', ' ')
                return f"[P{anno_dict[aid]['page_idx']+1}] " + txt + "..."

            selected_id = st.radio(
                "항목 선택", options=valid_ids, format_func=format_label,
                index=valid_ids.index(st.session_state.selected_box_id), 
                label_visibility="collapsed"
            )
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            st.markdown("---")
            curr_anno = anno_dict[st.session_state.selected_box_id]
            
            # 자료유형 제거, 이미지와 텍스트 편집기 노출
            st.image(curr_anno['img_path'], use_column_width=True)
            curr_anno['text'] = st.text_area("📝 텍스트 편집", value=curr_anno['text'], height=350)

            c1, c2 = st.columns(2)
            # [수정] 현재 보고 있는 'curr_anno' 하나만 삭제
            if c1.button("🗑️ 선택 항목 삭제", key="btn_del_selected"):
                delete_single_item(curr_anno)
                st.rerun()
            
            export_data = [{"page": a['page_idx']+1, "text": a['text'], "bbox": a['pdf_rect'], "image": a['img_name']} for a in st.session_state.annotations]
            c2.download_button("💾 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                               file_name="extracted.json", mime="application/json")
        else:
            st.info("왼쪽에서 추출 작업을 진행해 주세요.")

# ==========================================
# 4. JavaScript 단축키 (이전/다음/삭제)
# ==========================================
components.html(
    """
    <script>
    const doc = window.parent.document;
    doc.addEventListener('keydown', function(e) {
        if (e.key === 'ArrowLeft') {
            const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('이전'));
            if (btn) btn.click();
        } else if (e.key === 'ArrowRight') {
            const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('다음'));
            if (btn) btn.click();
        } else if (e.key === 'Delete' || e.key === 'Backspace') {
            // 입력창 안에서는 단축키 비활성화
            if (e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'INPUT') {
                const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('삭제'));
                if (btn) btn.click();
            }
        }
    });
    </script>
    """,
    height=0,
)
