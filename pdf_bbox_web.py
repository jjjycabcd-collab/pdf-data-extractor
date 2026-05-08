import streamlit as st
import fitz  # PyMuPDF
import json
from PIL import Image
import io
from streamlit_drawable_canvas import st_canvas

st.set_page_config(page_title="SI 데이터 추출 엔진", layout="wide")

if 'annotations' not in st.session_state:
    st.session_state.annotations = []
if 'page_idx' not in st.session_state:
    st.session_state.page_idx = 0

# 1. 이미지 생성 로직 (가장 안정적인 방식으로 변경)
def get_pdf_page_image(file_bytes, page_idx):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    
    # 배율을 2.0으로 높여서 더 선명하게 (하얀 화면 방지를 위해 alpha=False 추가)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    
    # 바이트 데이터를 PIL 이미지로 변환
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return img

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
    
    # 네비게이션
    nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 1])
    with nav_col1:
        if st.button("◀ 이전 페이지") and st.session_state.page_idx > 0:
            st.session_state.page_idx -= 1
            st.rerun()
    with nav_col2:
        st.write(f"### Page {st.session_state.page_idx + 1}")
    with nav_col3:
        if st.button("다음 페이지 ▶"):
            # 다음 페이지가 있는지 확인 후 이동
            temp_doc = fitz.open(stream=file_bytes, filetype="pdf")
            if st.session_state.page_idx < len(temp_doc) - 1:
                st.session_state.page_idx += 1
                st.rerun()

    # 이미지 로드
    bg_image = get_pdf_page_image(file_bytes, st.session_state.page_idx)

    main_col, data_col = st.columns([2, 1])

    with main_col:
        # [디버깅] 이미지가 실제로 생성되었는지 캔버스 바로 위에 작게 보여줍니다.
        # 만약 여기서도 하얀색이라면 PDF 로딩 자체가 문제인 것이고, 
        # 여기가 잘 나온다면 캔버스의 문제입니다.
        with st.expander("🖼️ 원본 이미지 미리보기 (안 보일 경우 클릭)"):
            st.image(bg_image, use_column_width=True)

        # 캔버스 설정
        canvas_width = 800
        w, h = bg_image.size
        aspect_ratio = h / w
        canvas_height = int(canvas_width * aspect_ratio)

        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.2)",
            stroke_width=2,
            stroke_color="#0000FF",
            background_image=bg_image,
            update_streamlit=True,
            width=canvas_width,
            height=canvas_height,
            drawing_mode="rect",
            # 키값이 고정되어 있으면 이미지가 안 변할 수 있으므로 페이지 번호를 포함
            key=f"canvas_p{st.session_state.page_idx}", 
        )

        # 박스 생성 시 데이터 추출 (기존 로직 동일)
        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            curr_annos = [a for a in st.session_state.annotations if a['page'] == st.session_state.page_idx]
            
            if len(objects) > len(curr_annos):
                latest = objects[-1]
                # 좌표 역산 배율
                pdf_scale = w / canvas_width
                
                x0 = latest["left"] * pdf_scale
                y0 = latest["top"] * pdf_scale
                x1 = (latest["left"] + latest["width"] * latest["scaleX"]) * pdf_scale
                y1 = (latest["top"] + latest["height"] * latest["scaleY"]) * pdf_scale
                
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                page = doc.load_page(st.session_state.page_idx)
                
                user_rect = fitz.Rect(x0, y0, x1, y1)
                
                # 오토피팅 로직 (간소화)
                words = page.get_text("words")
                fitted_rect = None
                if autofit_enabled:
                    for w_info in words:
                        w_rect = fitz.Rect(w_info[:4])
                        if user_rect.intersects(w_rect):
                            fitted_rect = w_rect if fitted_rect is None else fitted_rect | w_rect
                
                final_rect = fitted_rect if fitted_rect else user_rect
                text = " ".join([w[4] for w in words if final_rect.contains(fitz.Rect(w[:4]))])

                st.session_state.annotations.append({
                    "id": len(st.session_state.annotations) + 1,
                    "page": st.session_state.page_idx,
                    "bbox": [final_rect.x0, final_rect.y0, final_rect.x1, final_rect.y1],
                    "text": text
                })
                st.rerun()

    with data_col:
        st.subheader("📊 추출 데이터 목록")
        for anno in reversed(st.session_state.annotations):
            with st.expander(f"항목 #{anno['id']} (P{anno['page']+1})"):
                st.write(anno['text'])
                if st.button(f"삭제 #{anno['id']}", key=f"del_{anno['id']}"):
                    st.session_state.annotations.remove(anno)
                    st.rerun()

else:
    st.info("PDF 파일을 업로드해주세요.")
