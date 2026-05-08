import streamlit as st
import fitz  # PyMuPDF
import json
from PIL import Image
import io
from streamlit_drawable_canvas import st_canvas

# 페이지 기본 설정
st.set_page_config(page_title="SI 데이터 추출 엔진", layout="wide")

# ==========================================
# 1. 세션 상태 관리
# ==========================================
if 'annotations' not in st.session_state:
    st.session_state.annotations = []
if 'page_idx' not in st.session_state:
    st.session_state.page_idx = 0

# ==========================================
# 2. PDF 처리 로직 (보안 및 안정성 강화)
# ==========================================
@st.cache_resource
def load_pdf(file_bytes):
    return fitz.open(stream=file_bytes, filetype="pdf")

@st.cache_data
def get_page_image(file_bytes, page_idx):
    """PDF를 웹 표준 RGB 이미지로 변환"""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    # 선명도를 위해 1.5배율 사용
    pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    img_data = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_data))
    return img.convert("RGB") # 반드시 RGB로 변환해야 웹에서 보입니다.

def get_autofit_rect(page, pdf_rect, enabled=True):
    if not enabled: return pdf_rect
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

# ==========================================
# 3. 메인 UI
# ==========================================
st.title("📄 문서 데이터 추출 엔진 - Web Prototype")

with st.sidebar:
    st.header("⚙️ 설정")
    uploaded_file = st.file_uploader("PDF 파일을 선택하세요", type=['pdf'])
    autofit_enabled = st.checkbox("✨ 정밀 오토피팅(Word-level Snap)", value=True)
    
    if st.button("🗑️ 모든 데이터 초기화"):
        st.session_state.annotations = []
        st.rerun()

if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    doc = load_pdf(file_bytes)
    total_pages = len(doc)

    # 상단 네비게이션
    nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 1])
    with nav_col1:
        if st.button("◀ 이전 페이지") and st.session_state.page_idx > 0:
            st.session_state.page_idx -= 1
            st.rerun()
    with nav_col2:
        st.write(f"### Page {st.session_state.page_idx + 1} / {total_pages}")
    with nav_col3:
        if st.button("다음 페이지 ▶") and st.session_state.page_idx < total_pages - 1:
            st.session_state.page_idx += 1
            st.rerun()

    # 이미지 로드
    bg_image = get_page_image(file_bytes, st.session_state.page_idx)
    
    # 웹 화면 너비에 맞춰 자동 리사이즈 (가로 800px 기준)
    canvas_width = 800
    scale_ratio = canvas_width / bg_image.width
    canvas_height = int(bg_image.height * scale_ratio)
    
    # PDF 실제 좌표 계산을 위한 배율 (1.5배율 pixmap + 캔버스 리사이즈 배율)
    total_scale = 1.5 / scale_ratio 

    main_col, data_col = st.columns([2, 1])

    with main_col:
        # 이미지가 제대로 로드되었는지 확인용 (디버깅)
        if bg_image:
            canvas_result = st_canvas(
                fill_color="rgba(0, 0, 255, 0.2)",
                stroke_width=2,
                stroke_color="#0000FF",
                background_image=bg_image, # 이미지 객체 직접 전달
                update_streamlit=True,
                width=canvas_width,
                height=canvas_height,
                drawing_mode="rect",
                # 파일명과 페이지 번호를 조합한 고유 키 생성 (중요)
                key=f"canvas_{uploaded_file.name}_{st.session_state.page_idx}",
            )

        # 박스 생성 로직
        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            curr_annos = [a for a in st.session_state.annotations if a['page'] == st.session_state.page_idx]
            
            if len(objects) > len(curr_annos):
                latest = objects[-1]
                # 캔버스 좌표 -> PDF 좌표 역산
                x0, y0 = latest["left"] * total_scale, latest["top"] * total_scale
                w, h = (latest["width"] * latest["scaleX"]) * total_scale, (latest["height"] * latest["scaleY"]) * total_scale
                
                user_rect = fitz.Rect(x0, y0, x0 + w, y0 + h)
                page = doc.load_page(st.session_state.page_idx)
                fitted_rect = get_autofit_rect(page, user_rect, autofit_enabled)
                text = get_sorted_text(page, fitted_rect)
                
                st.session_state.annotations.append({
                    "id": len(st.session_state.annotations) + 1,
                    "page": st.session_state.page_idx,
                    "bbox": [fitted_rect.x0, fitted_rect.y0, fitted_rect.x1, fitted_rect.y1],
                    "text": text
                })
                st.rerun()

    with data_col:
        st.subheader("📊 추출 데이터")
        for anno in reversed(st.session_state.annotations):
            with st.expander(f"항목 #{anno['id']} (P{anno['page']+1})"):
                st.write(f"**Text:** {anno['text']}")
                st.caption(f"Bbox: {anno['bbox']}")

        if st.session_state.annotations:
            st.download_button("💾 JSON 다운로드", json.dumps(st.session_state.annotations, indent=4), "result.json")
else:
    st.info("PDF 파일을 업로드하면 분석이 시작됩니다.")
