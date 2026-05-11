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

# 세션 상태 초기값 설정
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
# 2. 데이터 분류 및 정제 로직 (개인화 설정 반영)
# ==========================================
def classify_material(text):
    """텍스트 내용을 분석하여 자료유형 자동 분류"""
    text_clean = text.replace(" ", "").lower()
    # 단행본 분류: 표준, 지침, 도서
    if any(kw in text_clean for kw in ["표준", "지침", "도서"]):
        return "단행본"
    # 기타 분류: 보도자료, 신문, 연보
    if any(kw in text_clean for kw in ["보도자료", "신문", "연보"]):
        return "기타"
    return "단행본"

def clean_extracted_text(text):
    """저자소개 제외 및 텍스트 정제"""
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines if "저자소개" not in line and line.strip()]
    return "\n".join(cleaned_lines)

# ==========================================
# 3. 버튼 콜백 함수
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

def delete_box(idx, img_path, is_selected):
    if os.path.exists(img_path):
        os.remove(img_path)
    if idx < len(st.session_state.annotations):
        st.session_state.annotations.pop(idx)
    if is_selected:
        st.session_state.selected_box_id = None

# ==========================================
# 4. PDF 처리 로직
# ==========================================
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

def get_sorted_text(page, rect):
    raw_text = page.get_text("text", clip=rect)
    return clean_extracted_text(raw_text)

def save_cropped_image(page, pdf_rect):
    st.session_state.crop_counter += 1
    filename = f"crop_p{st.session_state.current_page+1}_{st.session_state.crop_counter:03d}.png"
    filepath = os.path.join(IMAGE_SAVE_DIR, filename)
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=pdf_rect)
    pix.save(filepath)
    return filename, filepath

# ==========================================
# 5. UI 및 메인 앱 로직
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
    col_nav1.button("◀ 이전", on_click=go_prev, use_container_width=True, key="btn_prev")
    col_nav2.button("다음 ▶", on_click=go_next, args=(total_pages,), use_container_width=True, key="btn_next")
    st.sidebar.write(f"**Page:** {st.session_state.current_page + 1} / {total_pages}")

    # PDF 배경 합성
    bg_bytes = get_cached_bg_bytes(st.session_state.file_bytes, st.session_state.current_page)
    bg_image = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
    
    overlay = Image.new("RGBA", bg_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    img_scale = 1.5 # get_pixmap의 matrix 값과 동일하게 설정

    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            x0, y0, x1, y1 = [c * img_scale for c in anno['pdf_rect']]
            is_sel = (st.session_state.selected_box_id == anno['id'])
            draw.rectangle([x0, y0, x1, y1], outline=(255,0,0,255) if is_sel else (0,0,255,255), width=3 if is_sel else 2)
            draw.rectangle([x0, y0, x1, y1], fill=(255,0,0,40) if is_sel else (0,0,255,20))

    bg_image = Image.alpha_composite(bg_image, overlay)
    left_col, right_col = st.columns([6, 4])

    with left_col:
        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.1)",
            stroke_width=2,
            stroke_color="rgba(0, 0, 255, 0.8)",
            background_image=bg_image,
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
                    
                    if new_rect["width"] < 15: # 클릭 인식
                        clicked_id = None
                        for a in reversed(st.session_state.annotations):
                            if a['page_idx'] == st.session_state.current_page:
                                rx0, ry0, rx1, ry1 = a['pdf_rect']
                                if rx0 <= p_x0 <= rx1 and ry0 <= p_y0 <= ry1:
                                    clicked_id = a['id']
                                    break
                        st.session_state.selected_box_id = clicked_id
                    else: # 드래그 추출
                        page = doc.load_page(st.session_state.current_page)
                        fit_rect = get_autofit_rect(page, fitz.Rect(p_x0, p_y0, p_x1, p_y1), autofit_enabled)
                        text = get_sorted_text(page, fit_rect)
                        img_name, img_path = save_cropped_image(page, fit_rect)
                        
                        anno_id = f"id_{st.session_state.crop_counter}"
                        st.session_state.annotations.append({
                            'id': anno_id, 'page_idx': st.session_state.current_page,
                            'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                            'text': text, 'img_name': img_name, 'img_path': img_path,
                            'type': classify_material(text)
                        })
                        st.session_state.selected_box_id = anno_id
                    
                    st.session_state.clear_trigger += 1
                    st.session_state.canvas_state["trigger"] = st.session_state.clear_trigger
                    st.rerun()

    with right_col:
        st.write("**데이터 추출 목록**")
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            
            if st.session_state.selected_box_id not in valid_ids:
                st.session_state.selected_box_id = valid_ids[-1]

            def format_func(aid):
                a = anno_dict[aid]
                return f"[P{a['page_idx']+1}] {a['text'][:20]}..."

            selected_id = st.radio("항목 선택", options=valid_ids, format_func=format_func, 
                                   index=valid_ids.index(st.session_state.selected_box_id), label_visibility="collapsed")
            
            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            curr_anno = anno_dict[st.session_state.selected_box_id]
            st.image(curr_anno['img_path'], use_container_width=True)
            
            # 자료유형 수정
            types = ["단행본", "기타"]
            curr_anno['type'] = st.selectbox("자료유형", types, index=types.index(curr_anno['type']) if curr_anno['type'] in types else 0)
            curr_anno['text'] = st.text_area("텍스트 편집", value=curr_anno['text'], height=200)

            if st.button("🗑️ 선택 항목 삭제", use_container_width=True, key="btn_delete"):
                idx = st.session_state.annotations.index(curr_anno)
                delete_box(idx, curr_anno['img_path'], True)
                st.rerun()
            
            # 다운로드 버튼
            export_data = [{"page": a['page_idx']+1, "type": a.get('type','단행본'), "text": a['text'], "bbox": a['pdf_rect']} for a in st.session_state.annotations]
            st.download_button("💾 JSON 결과 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                               file_name="extracted.json", mime="application/json", use_container_width=True)
        else:
            st.info("영역을 드래그하여 데이터를 추출하세요.")

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
            // 텍스트 영역 입력 중에는 삭제 작동 방지
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
