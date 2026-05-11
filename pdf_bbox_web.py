import streamlit as st
import fitz  # PyMuPDF
import json
import os
from PIL import Image
from streamlit_drawable_canvas import st_canvas

# ==========================================
# 1. 페이지 및 상태 초기화
# ==========================================
st.set_page_config(layout="wide", page_title="SI 데이터 구축 엔진 - Web")

if 'pdf_doc' not in st.session_state:
    st.session_state.pdf_doc = None
if 'current_page' not in st.session_state:
    st.session_state.current_page = 0
if 'annotations' not in st.session_state:
    st.session_state.annotations = []
if 'crop_counter' not in st.session_state:
    st.session_state.crop_counter = 0

# 이미지 임시 저장 경로
IMAGE_SAVE_DIR = "extracted_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# ==========================================
# 2. 핵심 로직 함수
# ==========================================
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
    # 데이터 추출용 크롭 이미지는 고해상도(3.0) 유지
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=pdf_rect)
    pix.save(filepath)
    return filename, filepath

# ==========================================
# 3. UI 및 메인 앱 로직
# ==========================================
st.title("📄 SI 데이터 구축 엔진 - Web Editor")

# 파일 업로드
uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

if uploaded_file is not None:
    if st.session_state.pdf_doc is None or st.session_state.get('file_name') != uploaded_file.name:
        pdf_bytes = uploaded_file.read()
        st.session_state.pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        st.session_state.current_page = 0
        st.session_state.annotations = []
        st.session_state.file_name = uploaded_file.name

    doc = st.session_state.pdf_doc
    total_pages = len(doc)

    st.sidebar.markdown("---")
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)
    
    col1, col2 = st.sidebar.columns(2)
    if col1.button("◀ 이전") and st.session_state.current_page > 0:
        st.session_state.current_page -= 1
        st.rerun()
    if col2.button("다음 ▶") and st.session_state.current_page < total_pages - 1:
        st.session_state.current_page += 1
        st.rerun()
    
    st.sidebar.write(f"**Page:** {st.session_state.current_page + 1} / {total_pages}")

    # ==========================================
    # ★ 하얀 캔버스 완벽 해결 렌더링 로직 ★
    # ==========================================
    page = doc.load_page(st.session_state.current_page)
    
    # 웹 화면 렌더링용 줌 (네트워크 과부하 차단을 위해 1.0으로 고정)
    view_zoom = 1.0 
    mat = fitz.Matrix(view_zoom, view_zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    
    # 임시 버퍼(BytesIO) 일절 금지. 픽셀 데이터를 물리 메모리에서 직접 PIL Image로 강제 생성
    # 이 방식은 Python 가비지 컬렉터가 이미지를 지우는 것을 완벽하게 막아줍니다.
    bg_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # 메인 레이아웃 분할
    left_col, right_col = st.columns([6, 4])

    with left_col:
        st.write("**PDF 뷰어 (드래그하여 영역 추출)**")
        
        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.1)",
            stroke_width=2,
            stroke_color="rgba(0, 0, 255, 0.8)",
            background_image=bg_image,
            update_streamlit=True,
            height=bg_image.height,
            width=bg_image.width,
            drawing_mode="rect",
            key=f"canvas_{st.session_state.current_page}_{uploaded_file.name}",
        )

        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            current_canvas_objects = [obj for obj in objects if obj["type"] == "rect"]
            page_annotations = [a for a in st.session_state.annotations if a['page_idx'] == st.session_state.current_page]
            
            if len(current_canvas_objects) > len(page_annotations):
                new_rect = current_canvas_objects[-1]
                
                # Canvas 뷰어 좌표(view_zoom 적용)를 PDF 원본 좌표로 맵핑
                x0 = new_rect["left"] / view_zoom
                y0 = new_rect["top"] / view_zoom
                x1 = (new_rect["left"] + new_rect["width"]) / view_zoom
                y1 = (new_rect["top"] + new_rect["height"]) / view_zoom
                
                user_pdf_rect = fitz.Rect(x0, y0, x1, y1)
                fitted_pdf_rect = get_autofit_rect(page, user_pdf_rect, autofit_enabled)
                
                text = get_sorted_text(page, fitted_pdf_rect)
                img_name, img_path = save_cropped_image(page, fitted_pdf_rect)
                
                new_anno = {
                    'id': f"p{st.session_state.current_page}_{img_name}",
                    'page_idx': st.session_state.current_page,
                    'pdf_rect': [fitted_pdf_rect.x0, fitted_pdf_rect.y0, fitted_pdf_rect.x1, fitted_pdf_rect.y1],
                    'text': text,
                    'img_name': img_name,
                    'img_path': img_path
                }
                st.session_state.annotations.append(new_anno)
                st.rerun() 

    with right_col:
        st.write("**🔍 추출 목록 및 텍스트 편집기**")
        
        if not st.session_state.annotations:
            st.info("왼쪽 뷰어에서 드래그하여 데이터를 추출해보세요.")
        
        for idx, anno in enumerate(st.session_state.annotations):
            with st.expander(f"Page {anno['page_idx'] + 1} - {anno['img_name']}", expanded=True):
                if os.path.exists(anno['img_path']):
                    crop_img = Image.open(anno['img_path'])
                    st.image(crop_img, use_column_width=True)
                
                new_text = st.text_area("텍스트 수정", value=anno['text'], height=100, key=f"text_{idx}")
                if new_text != anno['text']:
                    st.session_state.annotations[idx]['text'] = new_text
                
                if st.button("🗑️ 삭제", key=f"del_{idx}"):
                    if os.path.exists(anno['img_path']):
                        os.remove(anno['img_path'])
                    st.session_state.annotations.pop(idx)
                    st.rerun()

        st.markdown("---")
        if st.session_state.annotations:
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
                label="💾 JSON 결과 최종 추출 (다운로드)",
                data=json_string,
                file_name="extracted_data.json",
                mime="application/json",
                use_container_width=True
            )
else:
    st.info("👈 사이드바에서 PDF 파일을 업로드하여 작업을 시작하세요.")
