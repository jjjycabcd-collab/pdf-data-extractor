import streamlit as st
import fitz  # PyMuPDF
import json
from PIL import Image
import io
from streamlit_drawable_canvas import st_canvas

# 1. PDF 로드 함수 (캐싱 적용으로 속도 향상 및 오류 방지)
@st.cache_resource
def load_pdf(file_bytes):
    return fitz.open(stream=file_bytes, filetype="pdf")

# 2. 페이지 렌더링 함수 (캐싱 적용)
@st.cache_data
def get_page_image(file_bytes, page_idx, scale_factor):
    doc = fitz.open(stream=file_bytes, filetype="pdf") # 캐시용으로 새로 열기
    page = doc.load_page(page_idx)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale_factor, scale_factor))
    return pix.tobytes("png")

st.title("📄 문서 데이터 추출 엔진 - Web Prototype")

with st.sidebar:
    uploaded_file = st.file_uploader("PDF 파일 업로드", type=['pdf'])
    autofit_enabled = st.checkbox("✨ 정밀 오토피팅 모드", value=True)

if uploaded_file is not None:
    # 핵심: 파일 바이트를 한 번만 읽어서 보관
    file_bytes = uploaded_file.getvalue() 
    doc = load_pdf(file_bytes)
    total_pages = len(doc)
    
    # ... (중략: 페이지 네비게이션 버튼 로직) ...

    # 3. 이미지 가져오기
    scale_factor = 1.5 # 웹 화면에 맞게 조절
    img_bytes = get_page_image(file_bytes, st.session_state.page_idx, scale_factor)
    bg_image = Image.open(io.BytesIO(img_bytes))
    
    canvas_width = bg_image.width
    canvas_height = bg_image.height

    main_col, data_col = st.columns([2, 1])

    with main_col:
        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.2)",
            stroke_width=2,
            stroke_color="#0000FF",
            background_image=bg_image, # 드디어 이미지가 보일 겁니다!
            update_streamlit=True,
            height=canvas_height,
            width=canvas_width,
            drawing_mode="rect",
            key=f"canvas_p{st.session_state.page_idx}", # 페이지마다 캔버스 초기화
        )
    
    # ... (이하 추출 로직 동일) ...
