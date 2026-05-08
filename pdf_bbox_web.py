import streamlit as st
import fitz  # PyMuPDF
import json
import time
from PIL import Image
import io
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="SI 데이터 추출 엔진", layout="wide")

# 세션 상태 관리
if 'annotations' not in st.session_state:
    st.session_state.annotations = []
if 'page_idx' not in st.session_state:
    st.session_state.page_idx = 0

# 이미지 생성 함수 (안정성 강화)
@st.cache_data
def get_pdf_page_image(file_bytes, page_idx):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    # alpha=False로 배경을 불투명하게 강제 고정
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

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
    
    # 페이지 네비게이션
    nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 1])
    with nav_col1:
        if st.button("◀ 이전 페이지") and st.session_state.page_idx > 0:
            st.session_state.page_idx -= 1
            st.rerun()
    with nav_col2:
        st.write(f"<h3 style='text-align: center;'>Page {st.session_state.page_idx + 1}</h3>", unsafe_allow_html=True)
    with nav_col3:
        # 다음 페이지 존재 확인 후 이동
        doc_temp = fitz.open(stream=file_bytes, filetype="pdf")
        if st.button("다음 페이지 ▶") and st.session_state.page_idx < len(doc_temp) - 1:
            st.session_state.page_idx += 1
            st.rerun()

    # 이미지 로드
    bg_image = get_pdf_page_image(file_bytes, st.session_state.page_idx)
    w, h = bg_image.size
    canvas_width = 800
    canvas_height = int(canvas_width * (h / w))

    main_col, data_col = st.columns([2, 1])

    with main_col:
        # 캔버스 위젯 (Key 값에 폼 이름을 넣어 중복 방지)
        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.2)",
            stroke_width=2,
            stroke_color="#0000FF",
            background_image=bg_image,
            update_streamlit=True,
            width=canvas_width,
            height=canvas_height,
            drawing_mode="rect",
            # key가 바뀌어야 캔버스가 강제로 새로 그려집니다.
            key=f"canvas_p{st.session_state.page_idx}_{len(st.session_state.annotations)}",
        )

        # 박스 생성 로직
        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            # 현재 페이지에 그려진 박스 개수와 세션 저장 개수 비교
            current_page_annos = [a for a in st.session_state.annotations if a['page'] == st.session_state.page_idx]
            
            if len(objects) > len(current_page_annos):
                latest = objects[-1]
                pdf_scale = w / canvas_width
                x0, y0 = latest["left"] * pdf_scale, latest["top"] * pdf_scale
                x1 = (latest["left"] + latest["width"] * latest["scaleX"]) * pdf_scale
                y1 = (latest["top"] + latest["height"] * latest["scaleY"]) * pdf_scale
                
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                page = doc.load_page(st.session_state.page_idx)
                user_rect = fitz.Rect(x0, y0, x1, y1)
                
                # 오토피팅
                words = page.get_text("words")
                final_rect = user_rect
                if autofit_enabled:
                    fitted = None
                    for winfo in words:
                        w_r = fitz.Rect(winfo[:4])
                        if user_rect.intersects(w_r):
                            fitted = w_r if fitted is None else fitted | w_r
                    if fitted: final_rect = fitted
                
                extracted_text = " ".join([w[4] for w in words if final_rect.contains(fitz.Rect(w[:4]))])

                # 고유 타임스탬프를 ID로 사용하여 중복 방지
                st.session_state.annotations.append({
                    "id": float(time.time()), 
                    "page": st.session_state.page_idx,
                    "bbox": [final_rect.x0, final_rect.y0, final_rect.x1, final_rect.y1],
                    "text": extracted_text
                })
                st.rerun()

    with data_col:
        st.subheader("📊 추출 데이터 목록")
        # 역순으로 표시
        for anno in reversed(st.session_state.annotations):
            # 삭제 버튼 key에 타임스탬프 ID를 넣어 DuplicateWidgetID 방지
            with st.expander(f"항목 (P{anno['page']+1})", expanded=True):
                st.write(anno['text'])
                if st.button(f"삭제", key=f"del_{anno['id']}"):
                    st.session_state.annotations = [a for a in st.session_state.annotations if a['id'] != anno['id']]
                    st.rerun()

        if st.session_state.annotations:
            st.download_button("💾 JSON 다운로드", json.dumps(st.session_state.annotations, indent=4, ensure_ascii=False), "result.json")
else:
    st.info("좌측에서 PDF를 업로드하면 분석이 시작됩니다.")
