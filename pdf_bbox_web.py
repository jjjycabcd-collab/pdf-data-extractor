import streamlit as st
import fitz  # PyMuPDF
import json
import os
import io
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas

# ==========================================
# 1. 페이지 및 상태 초기화
# ==========================================
st.set_page_config(layout="wide", page_title="SI 데이터 구축 엔진 - Web")

if 'file_bytes' not in st.session_state:
    st.session_state.file_bytes = None
if 'pdf_doc' not in st.session_state:
    st.session_state.pdf_doc = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = 0
if 'annotations' not in st.session_state:
    st.session_state.annotations = []
if 'crop_counter' not in st.session_state:
    st.session_state.crop_counter = 0
if 'selected_box_id' not in st.session_state:
    st.session_state.selected_box_id = None
if 'clear_trigger' not in st.session_state:
    st.session_state.clear_trigger = 0
if 'canvas_state' not in st.session_state:
    st.session_state.canvas_state = {"version": "4.4.0", "objects": [], "trigger": 0}
if 'last_canvas_sig' not in st.session_state:
    st.session_state.last_canvas_sig = None
if 'view_zoom' not in st.session_state:
    st.session_state.view_zoom = 1.3 

IMAGE_SAVE_DIR = "extracted_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# ==========================================
# 2. 버튼 콜백 함수
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
    st.session_state.annotations.pop(idx)
    if is_selected:
        st.session_state.selected_box_id = None

# ==========================================
# 3. 핵심 로직
# ==========================================
@st.cache_data(show_spinner=False)
def get_cached_bg_bytes(file_bytes, page_idx, zoom):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return pix.tobytes("png")

def get_autofit_rect(page, pdf_rect, autofit_enabled):
    if not autofit_enabled: 
        return pdf_rect
    words = page.get_text("words")
    fitted_rect = None
    for w in words:
        w_rect = fitz.Rect(w[:4])
        if pdf_rect.intersects(w_rect):
            fitted_rect = w_rect if fitted_rect is None else fitted_rect | w_rect 
    return fitted_rect if fitted_rect else pdf_rect

def get_sorted_text(page, rect):
    words = page.get_text("words", clip=rect)
    if not words: return ""
    sorted_words = sorted(words, key=lambda w: (w[1], w[0]))
    return " ".join([w[4] for w in sorted_words])

def save_cropped_image(page, pdf_rect):
    st.session_state.crop_counter += 1
    page_num = st.session_state.current_page + 1
    filename = f"crop_p{page_num}_{st.session_state.crop_counter:03d}.png"
    filepath = os.path.join(IMAGE_SAVE_DIR, filename)
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=pdf_rect)
    pix.save(filepath)
    return filename, filepath

# ==========================================
# 4. UI 레이아웃
# ==========================================
st.title("📄 SI 데이터 구축 엔진 - Web Editor")

uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

if uploaded_file is not None:
    if st.session_state.get('file_name') != uploaded_file.name:
        file_bytes = uploaded_file.read()
        st.session_state.file_bytes = file_bytes
        st.session_state.pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
        st.session_state.current_page = 0
        st.session_state.annotations = []
        st.session_state.crop_counter = 0
        st.session_state.selected_box_id = None
        st.session_state.last_canvas_sig = None
        st.session_state.file_name = uploaded_file.name

    doc = st.session_state.pdf_doc
    total_pages = len(doc)

    st.sidebar.markdown("---")
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)
    
    col1, col2 = st.sidebar.columns(2)
    col1.button("◀ 이전", on_click=go_prev, use_container_width=True)
    col2.button("다음 ▶", on_click=go_next, args=(total_pages,), use_container_width=True)
    st.sidebar.write(f"**Page:** {st.session_state.current_page + 1} / {total_pages}")

    left_col, right_col = st.columns([6, 4])

    with left_col:
        st.session_state.view_zoom = st.slider("🔍 PDF 뷰어 확대/축소", 1.0, 2.5, st.session_state.view_zoom, 0.1)
        
        # [수정] st.container의 height 인자 대신 HTML/CSS로 스크롤 구현 (구버전 호환)
        st.markdown('<div style="height:800px; overflow-y:auto; border:1px solid #ddd; padding:10px; border-radius:5px;">', unsafe_allow_html=True)
        
        zoom = st.session_state.view_zoom
        bg_bytes = get_cached_bg_bytes(st.session_state.file_bytes, st.session_state.current_page, zoom)
        bg_image = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
        
        overlay = Image.new("RGBA", bg_image.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        
        for anno in st.session_state.annotations:
            if anno['page_idx'] == st.session_state.current_page:
                x0, y0, x1, y1 = [c * zoom for c in anno['pdf_rect']]
                color = (255, 0, 0) if st.session_state.selected_box_id == anno['id'] else (0, 0, 255)
                draw.rectangle([x0, y0, x1, y1], outline=color + (255,), width=3 if color==(255,0,0) else 2)
                draw.rectangle([x0, y0, x1, y1], fill=color + (40,))

        bg_image = Image.alpha_composite(bg_image, overlay)

        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.1)",
            stroke_width=2,
            stroke_color="rgba(0, 0, 255, 0.8)",
            background_image=bg_image,
            initial_drawing=st.session_state.canvas_state,
            update_streamlit=True,
            height=int(bg_image.height),
            width=int(bg_image.width),
            drawing_mode="rect",
            key=f"canvas_p{st.session_state.current_page}_z{zoom}",
        )
        st.markdown('</div>', unsafe_allow_html=True)

        # 캔버스 데이터 처리 (기존 로직 유지)
        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            if len(objects) > 0:
                new_rect = objects[-1]
                sig = f"{new_rect['left']}_{new_rect['top']}_{new_rect['width']}"
                if st.session_state.get('last_canvas_sig') != sig:
                    st.session_state.last_canvas_sig = sig
                    if max(new_rect["width"], new_rect["height"]) < 15: # 클릭
                        cx, cy = (new_rect["left"] + new_rect["width"]/2)/zoom, (new_rect["top"] + new_rect["height"]/2)/zoom
                        clicked_id = None
                        for anno in reversed(st.session_state.annotations):
                            if anno['page_idx'] == st.session_state.current_page:
                                x0, y0, x1, y1 = anno['pdf_rect']
                                if x0 <= cx <= x1 and y0 <= cy <= y1:
                                    clicked_id = anno['id']
                                    break
                        st.session_state.selected_box_id = clicked_id
                        st.session_state.clear_trigger += 1
                        st.session_state.canvas_state = {"version": "4.4.0", "objects": [], "trigger": st.session_state.clear_trigger}
                        st.rerun()
                    else: # 드래그
                        page = doc.load_page(st.session_state.current_page)
                        x0, y0, x1, y1 = new_rect["left"]/zoom, new_rect["top"]/zoom, (new_rect["left"]+new_rect["width"])/zoom, (new_rect["top"]+new_rect["height"])/zoom
                        f_rect = get_autofit_rect(page, fitz.Rect(x0, y0, x1, y1), autofit_enabled)
                        txt = get_sorted_text(page, f_rect)
                        iname, ipath = save_cropped_image(page, f_rect)
                        aid = f"p{st.session_state.current_page}_{iname}"
                        st.session_state.annotations.append({'id': aid, 'page_idx': st.session_state.current_page, 'pdf_rect': [f_rect.x0, f_rect.y0, f_rect.x1, f_rect.y1], 'text': txt, 'img_name': iname, 'img_path': ipath})
                        st.session_state.selected_box_id = aid
                        st.session_state.clear_trigger += 1
                        st.session_state.canvas_state = {"version": "4.4.0", "objects": [], "trigger": st.session_state.clear_trigger}
                        st.rerun()

    with right_col:
        st.write(f"**📦 추출 목록 (총 {len(st.session_state.annotations)}건)**")
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            if st.session_state.selected_box_id not in valid_ids:
                st.session_state.selected_box_id = valid_ids[-1]

            # [수정] 우측 목록 스크롤 (구버전 호환)
            st.markdown('<div style="height:250px; overflow-y:auto; border:1px solid #ddd; padding:10px; border-radius:5px; margin-bottom:10px;">', unsafe_allow_html=True)
            selected_id = st.radio("목록", options=valid_ids, index=valid_ids.index(st.session_state.selected_box_id),
                                   format_func=lambda x: f"📄 P{anno_dict[x]['page_idx']+1} | {anno_dict[x]['text'][:25]}...", label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)

            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                if anno_dict[selected_id]['page_idx'] != st.session_state.current_page:
                    st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            selected_anno = anno_dict[st.session_state.selected_box_id]
            st.divider()
            if st.button("🗑️ 선택 항목 삭제", use_container_width=True):
                delete_box(st.session_state.annotations.index(selected_anno), selected_anno['img_path'], True)
                st.rerun()

            if os.path.exists(selected_anno['img_path']):
                st.image(selected_anno['img_path'], use_container_width=True)
            
            new_text = st.text_area("텍스트 원문 수정", value=selected_anno['text'], height=350)
            if new_text != selected_anno['text']:
                for a in st.session_state.annotations:
                    if a['id'] == st.session_state.selected_box_id:
                        a['text'] = new_text
                        break

            st.divider()
            json_str = json.dumps([{"page": a['page_idx']+1, "text": a['text'], "bbox": a['pdf_rect']} for a in st.session_state.annotations], ensure_ascii=False, indent=4)
            st.download_button("💾 JSON 결과 다운로드", data=json_str, file_name="extracted_data.json", use_container_width=True)
        else:
            st.info("왼쪽에서 영역을 드래그하세요.")
else:
    st.info("👈 PDF 파일을 업로드하세요.")
