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

# 세션 상태 초기값 설정 (가장 안정적인 방식)
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
# 2. 페이징 및 데이터 관리 콜백 함수
# ==========================================
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
        if os.path.exists(anno_obj['img_path']):
            os.remove(anno_obj['img_path'])
        if anno_obj in st.session_state.annotations:
            st.session_state.annotations.remove(anno_obj)
        st.session_state.selected_box_id = None

# ==========================================
# 3. PDF 처리 및 유틸리티
# ==========================================
def clean_text(text):
    lines = text.split('\n')
    cleaned = [line.strip() for line in lines if "저자소개" not in line and line.strip()]
    return "\n".join(cleaned)

@st.cache_data(show_spinner=False)
def get_page_image(file_bytes, page_idx):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return img, page.rect.width, page.rect.height

# ==========================================
# 4. 파일 로드 로직 (기본 sample.pdf 처리)
# ==========================================
uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

if uploaded_file is not None:
    # 새 파일 업로드 시 초기화
    if st.session_state.file_name != uploaded_file.name:
        st.session_state.file_bytes = uploaded_file.read()
        st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
        st.session_state.file_name = uploaded_file.name
        st.session_state.current_page = 0
        st.session_state.annotations = []
        st.session_state.crop_counter = 0
        st.session_state.selected_box_id = None
        st.rerun()
else:
    # 업로드 파일이 없을 때 sample.pdf 로드
    if not st.session_state.file_bytes:
        sample_path = "sample.pdf"
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                st.session_state.file_bytes = f.read()
            st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
            st.session_state.file_name = "sample.pdf"

# ==========================================
# 5. 메인 에디터 인터페이스
# ==========================================
if st.session_state.file_bytes:
    doc = st.session_state.pdf_doc
    total_pages = len(doc)

    st.sidebar.markdown("---")
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)
    
    col_nav1, col_nav2 = st.sidebar.columns(2)
    col_nav1.button("◀ 이전", on_click=go_prev, use_container_width=True)
    col_nav2.button("다음 ▶", on_click=go_next, args=(total_pages,), use_container_width=True)
    
    st.sidebar.write(f"**파일:** {st.session_state.file_name}")
    st.sidebar.write(f"**페이지:** {st.session_state.current_page + 1} / {total_pages}")

    # 좌표 안정화 (700px 고정)
    full_bg, pdf_w, pdf_h = get_page_image(st.session_state.file_bytes, st.session_state.current_page)
    canvas_w = 700
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    
    overlay = Image.new("RGBA", display_img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    pdf_to_canvas_ratio = canvas_w / pdf_w

    # 하이라이트 박스 렌더링
    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            x0, y0, x1, y1 = [c * pdf_to_canvas_ratio for c in anno['pdf_rect']]
            is_sel = (st.session_state.selected_box_id == anno['id'])
            draw.rectangle([x0, y0, x1, y1], outline=(255,0,0,255) if is_sel else (0,0,255,255), width=3 if is_sel else 2)
            draw.rectangle([x0, y0, x1, y1], fill=(255,0,0,40) if is_sel else (0,0,255,20))

    final_bg = Image.alpha_composite(display_img, overlay)
    left_col, right_col = st.columns([6, 4])

    with left_col:
        st.write("**[PDF 뷰어] 드래그하여 영역을 추출하세요**")
        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.1)",
            stroke_width=2,
            stroke_color="rgba(0, 0, 255, 0.8)",
            background_image=final_bg,
            initial_drawing=st.session_state.canvas_state,
            update_streamlit=True,
            height=canvas_h,
            width=canvas_w,
            drawing_mode="rect",
            display_toolbar=False,  # <--- 이 라인을 추가하여 도구 모음을 숨깁니다.
            key=f"canvas_p{st.session_state.current_page}",
        )

        if canvas_result.json_data:
            objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
            if objs:
                new_rect = objs[-1]
                rect_sig = f"{new_rect['left']}_{new_rect['top']}_{new_rect['width']}"
                if st.session_state.last_canvas_sig != rect_sig:
                    st.session_state.last_canvas_sig = rect_sig
                    p_x0, p_y0 = new_rect["left"] / pdf_to_canvas_ratio, new_rect["top"] / pdf_to_canvas_ratio
                    p_x1, p_y1 = (new_rect["left"] + new_rect["width"]) / pdf_to_canvas_ratio, (new_rect["top"] + new_rect["height"]) / pdf_to_canvas_ratio
                    
                    if new_rect["width"] < 10: # 클릭 선택
                        clicked_id = None
                        for a in reversed(st.session_state.annotations):
                            if a['page_idx'] == st.session_state.current_page:
                                rx0, ry0, rx1, ry1 = a['pdf_rect']
                                if rx0 <= p_x0 <= rx1 and ry0 <= p_y0 <= ry1:
                                    clicked_id = a['id']
                                    break
                        st.session_state.selected_box_id = clicked_id
                    else: # 영역 추출
                        page = doc.load_page(st.session_state.current_page)
                        fit_rect = fitz.Rect(p_x0, p_y0, p_x1, p_y1)
                        if autofit_enabled:
                            words = page.get_text("words")
                            matched = [fitz.Rect(w[:4]) for w in words if fitz.Rect(w[:4]).intersects(fit_rect)]
                            if matched:
                                fit_rect = matched[0]
                                for r in matched[1:]: fit_rect |= r
                        
                        text = clean_text(page.get_text("text", clip=fit_rect))
                        st.session_state.crop_counter += 1
                        img_name = f"crop_p{st.session_state.current_page+1}_{st.session_state.crop_counter:03d}.png"
                        img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
                        page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=fit_rect).save(img_path)
                        
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

            # 5건 기준 고정 스크롤 영역 설정 (CSS)
            st.markdown("""
                <style>
                .scroll-box {
                    max-height: 200px;
                    overflow-y: scroll;
                    border: 2px solid #4A90E2;
                    border-radius: 8px;
                    padding: 10px;
                    background-color: #f9f9f9;
                    margin-bottom: 10px;
                }
                div[data-testid="stRadio"] > div { gap: 2px; }
                </style>
                """, unsafe_allow_html=True)

            st.markdown('<div class="scroll-box">', unsafe_allow_html=True)
            def format_label(aid):
                a = anno_dict[aid]
                r = a['pdf_rect']
                coords = "[X:" + str(int(r[0])) + ", Y:" + str(int(r[1])) + ", W:" + str(int(r[2]-r[0])) + ", H:" + str(int(r[3]-r[1])) + "]"
                txt = a['text'][:25].replace('\n', ' ')
                return "[P" + str(a['page_idx']+1) + "] " + coords + " | " + txt + "..."

            selected_id = st.radio("항목 선택", options=valid_ids, format_func=format_label,
                                   index=valid_ids.index(st.session_state.selected_box_id), label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            st.markdown("---")
            curr_anno = anno_dict[st.session_state.selected_box_id]
            # 구버전 호환성을 위해 use_column_width 사용
            st.image(curr_anno['img_path'], use_column_width=True)
            curr_anno['text'] = st.text_area("📝 텍스트 편집", value=curr_anno['text'], height=180)

            c1, c2 = st.columns(2)
            if c1.button("🗑️ 선택 항목 삭제", key="btn_del_selected", use_container_width=True, type="primary"):
                delete_single_item(curr_anno)
                st.rerun()
            
            export_data = [{"page": a['page_idx']+1, "bbox": a['pdf_rect'], "text": a['text'], "image": a['img_name']} for a in st.session_state.annotations]
            c2.download_button("💾 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                               file_name="extracted.json", mime="application/json", use_container_width=True)
        else:
            st.info("왼쪽에서 추출 작업을 진행해 주세요.")
else:
    st.info("👈 사이드바에서 PDF 파일을 업로드하거나 sample.pdf를 준비해 주세요.")

# ==========================================
# 6. JavaScript 단축키 주입
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
