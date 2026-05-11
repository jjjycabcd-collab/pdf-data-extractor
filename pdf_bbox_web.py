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

# CSS를 통해 라디오 버튼과 텍스트 영역의 가독성 향상
st.markdown("""
    <style>
    div[data-testid="stExpander"] div[role="button"] p { font-weight: bold; }
    .stRadio > div { gap: 0px; }
    /* 선택된 항목 강조 스타일 */
    div[data-testid="stVerticalBlock"] > div:has(input[checked]) {
        background-color: #f0f2f6;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

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
# 3. 핵심 로직 (정밀 오토피팅 & 캐싱)
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
    x_coords = sorted([w[0] for w in words])
    gaps = [x_coords[i+1] - x_coords[i] for i in range(len(x_coords)-1)]
    max_gap = max(gaps) if gaps else 0
    threshold = rect.width * 0.15 
    
    if max_gap > threshold:
        split_idx = gaps.index(max_gap)
        split_x = (x_coords[split_idx] + x_coords[split_idx+1]) / 2
        left_col = sorted([w for w in words if w[0] < split_x], key=lambda w: (w[1], w[0]))
        right_col = sorted([w for w in words if w[0] >= split_x], key=lambda w: (w[1], w[0]))
        sorted_words = left_col + right_col
    else:
        sorted_words = sorted(words, key=lambda w: (w[1], w[0]))
    return " ".join([w[4] for w in sorted_words])

def save_cropped_image(page, pdf_rect):
    st.session_state.crop_counter += 1
    page_num = st.session_state.current_page + 1
    filename = f"crop_p{page_num}_{st.session_state.crop_counter:03d}.png"
    filepath = os.path.join(IMAGE_SAVE_DIR, filename)
    # 고해상도 저장을 위해 매트릭스 3.0 유지
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=pdf_rect)
    pix.save(filepath)
    return filename, filepath

# ==========================================
# 4. UI 및 메인 앱 로직
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

    # ==========================================
    # 메인 레이아웃 구성
    # ==========================================
    left_col, right_col = st.columns([6, 4])

    with left_col:
        st.session_state.view_zoom = st.slider("🔍 PDF 뷰어 확대/축소", 1.0, 2.5, st.session_state.view_zoom, 0.1)
        
        # [수정사항] 좌측 뷰어에 독립 스크롤 생성 (높이 800px)
        with st.container(height=800, border=True):
            zoom = st.session_state.view_zoom
            bg_bytes = get_cached_bg_bytes(st.session_state.file_bytes, st.session_state.current_page, zoom)
            bg_image = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
            
            overlay = Image.new("RGBA", bg_image.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            
            for anno in st.session_state.annotations:
                if anno['page_idx'] == st.session_state.current_page:
                    x0, y0, x1, y1 = anno['pdf_rect']
                    zx0, zy0, zx1, zy1 = x0 * zoom, y0 * zoom, x1 * zoom, y1 * zoom
                    
                    if st.session_state.selected_box_id == anno['id']:
                        draw.rectangle([zx0, zy0, zx1, zy1], outline=(255, 0, 0, 255), width=3)
                        draw.rectangle([zx0, zy0, zx1, zy1], fill=(255, 0, 0, 50)) 
                    else:
                        draw.rectangle([zx0, zy0, zx1, zy1], outline=(0, 0, 255, 255), width=2)
                        draw.rectangle([zx0, zy0, zx1, zy1], fill=(0, 0, 255, 30)) 

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

        # 캔버스 로직 (클릭/드래그 처리)
        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            current_canvas_objects = [obj for obj in objects if obj["type"] == "rect"]
            
            if len(current_canvas_objects) > 0:
                new_rect = current_canvas_objects[-1]
                w, h = new_rect["width"], new_rect["height"]
                rect_sig = f"{new_rect['left']:.2f}_{new_rect['top']:.2f}_{w:.2f}_{h:.2f}"
                
                if st.session_state.get('last_canvas_sig') != rect_sig:
                    st.session_state.last_canvas_sig = rect_sig
                    
                    if max(w, h) < 15:
                        click_x = (new_rect["left"] + w/2) / zoom
                        click_y = (new_rect["top"] + h/2) / zoom
                        clicked_id = None
                        for anno in reversed(st.session_state.annotations):
                            if anno['page_idx'] == st.session_state.current_page:
                                x0, y0, x1, y1 = anno['pdf_rect']
                                if x0 <= click_x <= x1 and y0 <= click_y <= y1:
                                    clicked_id = anno['id']
                                    break
                        st.session_state.selected_box_id = clicked_id
                        st.session_state.clear_trigger += 1
                        st.session_state.canvas_state = {"version": "4.4.0", "objects": [], "trigger": st.session_state.clear_trigger}
                        st.rerun()
                    else:
                        page = doc.load_page(st.session_state.current_page)
                        x0, y0 = new_rect["left"] / zoom, new_rect["top"] / zoom
                        x1, y1 = (new_rect["left"] + new_rect["width"]) / zoom, (new_rect["top"] + new_rect["height"]) / zoom
                        user_pdf_rect = fitz.Rect(x0, y0, x1, y1)
                        fitted_pdf_rect = get_autofit_rect(page, user_pdf_rect, autofit_enabled)
                        text = get_sorted_text(page, fitted_pdf_rect)
                        img_name, img_path = save_cropped_image(page, fitted_pdf_rect)
                        anno_id = f"p{st.session_state.current_page}_{img_name}"
                        new_anno = {
                            'id': anno_id,
                            'page_idx': st.session_state.current_page,
                            'pdf_rect': [fitted_pdf_rect.x0, fitted_pdf_rect.y0, fitted_pdf_rect.x1, fitted_pdf_rect.y1],
                            'text': text,
                            'img_name': img_name,
                            'img_path': img_path
                        }
                        st.session_state.annotations.append(new_anno)
                        st.session_state.selected_box_id = anno_id
                        st.session_state.clear_trigger += 1
                        st.session_state.canvas_state = {"version": "4.4.0", "objects": [], "trigger": st.session_state.clear_trigger}
                        st.rerun() 
            else:
                st.session_state.last_canvas_sig = None

    with right_col:
        # [수정사항] 데이터 추출 목록 영역
        st.write(f"**📦 추출 목록 (총 {len(st.session_state.annotations)}건)**")
        
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            
            if st.session_state.selected_box_id not in valid_ids:
                st.session_state.selected_box_id = valid_ids[-1] if valid_ids else None

            def format_list_item(anno_id):
                anno = anno_dict[anno_id]
                preview = anno['text'][:25].replace('\n', ' ') + ("..." if len(anno['text']) > 25 else "")
                return f"📄 P{anno['page_idx'] + 1} | {preview}"

            # [수정사항] 목록 5건 정도 보이고 스크롤 되도록 설정 (높이 약 250px)
            with st.container(height=250, border=True):
                selected_id = st.radio(
                    "항목 선택",
                    options=valid_ids,
                    format_func=format_list_item,
                    index=valid_ids.index(st.session_state.selected_box_id) if st.session_state.selected_box_id else 0,
                    label_visibility="collapsed"
                )

            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                target_page = anno_dict[selected_id]['page_idx']
                if target_page != st.session_state.current_page:
                    st.session_state.current_page = target_page
                    st.session_state.last_canvas_sig = None
                st.rerun()

            selected_anno = anno_dict[st.session_state.selected_box_id]

            # [수정사항] 상세 편집기 영역 - 이미지와 텍스트를 크게 배치
            st.markdown("---")
            st.write("**🔍 상세 편집 및 확인**")
            
            # 삭제 버튼을 편집기 상단에 배치하여 빠른 작업 유도
            if st.button("🗑️ 현재 항목 삭제", use_container_width=True):
                delete_box(st.session_state.annotations.index(selected_anno), selected_anno['img_path'], True)
                st.rerun()

            # [수정사항] 이미지와 텍스트 박스를 크게 보여주기 위해 세로 스크롤 컨테이너 활용
            with st.container(height=500, border=False):
                if os.path.exists(selected_anno['img_path']):
                    # 추출 이미지를 컨테이너 너비에 맞춰 크게 표시
                    st.image(selected_anno['img_path'], use_container_width=True, caption="추출된 영역 이미지")
                
                # 텍스트 영역을 더 높게 설정 (height=300)
                new_text = st.text_area("추출 텍스트 편집", value=selected_anno['text'], height=300)
                if new_text != selected_anno['text']:
                    for a in st.session_state.annotations:
                        if a['id'] == st.session_state.selected_box_id:
                            a['text'] = new_text
                            break

            st.markdown("---")
            # JSON 내보내기
            export_data = []
            for anno in st.session_state.annotations:
                export_data.append({
                    "page": anno['page_idx'] + 1,
                    "bbox": [round(x, 2) for x in anno['pdf_rect']],
                    "image_file": anno['img_name'],
                    "text": anno['text']
                })
            json_string = json.dumps(export_data, ensure_ascii=False, indent=4)
            st.download_button(
                label="💾 JSON 결과 최종 추출",
                data=json_string,
                file_name="extracted_data.json",
                mime="application/json",
                use_container_width=True
            )
        else:
            st.info("왼쪽 뷰어에서 영역을 드래그하면 이곳에 편집창이 나타납니다.")
else:
    st.info("👈 사이드바에서 PDF 파일을 업로드하여 작업을 시작하세요.")
