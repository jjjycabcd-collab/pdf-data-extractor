import streamlit as st
import fitz  # PyMuPDF
import json
import pandas as pd
from PIL import Image
import io
from streamlit_drawable_canvas import st_canvas

# 페이지 기본 설정
st.set_page_config(page_title="SI 데이터 구축 엔진 - Web Prototype", layout="wide")

# ==========================================
# 1. 세션 상태 및 초기화
# ==========================================
if 'annotations' not in st.session_state:
    st.session_state.annotations = []
if 'page_idx' not in st.session_state:
    st.session_state.page_idx = 0

# ==========================================
# 2. PDF 처리 유틸리티 (캐싱 적용)
# ==========================================
@st.cache_resource
def load_pdf(file_bytes):
    """PDF 문서를 메모리에 로드"""
    return fitz.open(stream=file_bytes, filetype="pdf")

@st.cache_data
def get_page_image(file_bytes, page_idx, scale=1.5):
    """특정 페이지를 고해상도 이미지로 변환"""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    return pix.tobytes("png")

def get_autofit_rect(page, pdf_rect, enabled=True):
    """단어(Word) 단위 정밀 오토피팅"""
    if not enabled: return pdf_rect
    words = page.get_text("words")
    fitted_rect = None
    for w in words:
        w_rect = fitz.Rect(w[:4])
        if pdf_rect.intersects(w_rect):
            fitted_rect = w_rect if fitted_rect is None else fitted_rect | w_rect 
    return fitted_rect if fitted_rect else pdf_rect

def get_sorted_text(page, rect):
    """추출된 단어를 문맥 흐름에 맞게 정렬 및 결합"""
    words = page.get_text("words", clip=rect)
    if not words: return ""
    # X 좌표 기준 갭(Gap) 분석하여 다단 처리 대응
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

# ==========================================
# 3. 메인 UI 레이아웃
# ==========================================
st.title("📄 문서 데이터 추출 엔진 - Web Prototype")
st.markdown("---")

with st.sidebar:
    st.header("⚙️ 설정 및 업로드")
    uploaded_file = st.file_uploader("PDF 파일을 선택하세요", type=['pdf'])
    autofit_enabled = st.checkbox("✨ 정밀 오토피팅(Word-level Snap)", value=True)
    
    if st.button("🗑️ 모든 데이터 초기화"):
        st.session_state.annotations = []
        st.rerun()

if uploaded_file is not None:
    # 파일 바이트 추출 (read() 포인터 문제 해결을 위해 getvalue 사용)
    file_bytes = uploaded_file.getvalue()
    doc = load_pdf(file_bytes)
    total_pages = len(doc)

    # 상단 네비게이션
    nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
    with nav_col1:
        if st.button("◀ 이전 페이지") and st.session_state.page_idx > 0:
            st.session_state.page_idx -= 1
            st.rerun()
    with nav_col2:
        st.markdown(f"<h3 style='text-align: center;'>Page {st.session_state.page_idx + 1} / {total_pages}</h3>", unsafe_allow_html=True)
    with nav_col3:
        if st.button("다음 페이지 ▶") and st.session_state.page_idx < total_pages - 1:
            st.session_state.page_idx += 1
            st.rerun()

    # 페이지 렌더링 (Scale 2.0으로 선명하게)
    img_bytes = get_page_image(file_bytes, st.session_state.page_idx, scale=2.0)
    bg_image = Image.open(io.BytesIO(img_bytes))
    
    # 캔버스 크기 자동 설정 (화면 너비에 맞춰 조정 가능)
    display_width = 900 
    scale_to_canvas = display_width / bg_image.width
    display_height = int(bg_image.height * scale_to_canvas)
    
    # PDF 실제 좌표로 변환하기 위한 전체 스케일 값
    total_scale = 2.0 * scale_to_canvas 

    # 좌우 화면 분할
    left_col, right_col = st.columns([3, 2])

    with left_col:
        st.info("💡 이미지 위를 드래그하여 영역을 선택하세요. 생성된 박스는 클릭 후 이동이나 리사이즈가 가능합니다.")
        
        # 캔버스 생성 (페이지 이동 시 key가 바뀌어 자동 리셋됨)
        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.2)",
            stroke_width=2,
            stroke_color="#0000FF",
            background_image=bg_image,
            update_streamlit=True,
            width=display_width,
            height=display_height,
            drawing_mode="rect",
            key=f"canvas_p{st.session_state.page_idx}",
        )

        # 박스 생성 감지 및 데이터 추출
        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            # 현재 페이지에 새로 그려진 박스가 있는지 확인
            current_page_annos = [a for a in st.session_state.annotations if a['page'] == st.session_state.page_idx]
            
            if len(objects) > len(current_page_annos):
                latest_obj = objects[-1]
                
                # 화면 좌표 -> PDF 절대 좌표 역산
                x0 = latest_obj["left"] / total_scale
                y0 = latest_obj["top"] / total_scale
                w = (latest_obj["width"] * latest_obj["scaleX"]) / total_scale
                h = (latest_obj["height"] * latest_obj["scaleY"]) / total_scale
                
                user_rect = fitz.Rect(x0, y0, x0 + w, y0 + h)
                
                # 오토피팅 및 텍스트 추출
                page = doc.load_page(st.session_state.page_idx)
                fitted_rect = get_autofit_rect(page, user_rect, autofit_enabled)
                text = get_sorted_text(page, fitted_rect)
                
                # 데이터 저장
                st.session_state.annotations.append({
                    "id": len(st.session_state.annotations) + 1,
                    "page": st.session_state.page_idx,
                    "bbox": [round(fitted_rect.x0, 2), round(fitted_rect.y0, 2), round(fitted_rect.x1, 2), round(fitted_rect.y1, 2)],
                    "text": text
                })
                st.rerun()

    with right_col:
        st.subheader("🔍 데이터 편집 및 QA")
        
        if not st.session_state.annotations:
            st.warning("추출된 데이터가 없습니다. 왼쪽 문서 영역에 박스를 그려주세요.")
        else:
            # 추출된 목록을 역순으로 표시 (최신 데이터 상단)
            for i, anno in enumerate(reversed(st.session_state.annotations)):
                with st.expander(f"📌 항목 #{anno['id']} (Page {anno['page']+1})", expanded=(i==0)):
                    # 1. 크롭 이미지 미리보기 (PyMuPDF의 clip 사용)
                    page = doc.load_page(anno['page'])
                    clip_rect = fitz.Rect(anno['bbox'])
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip_rect)
                    crop_img = Image.open(io.BytesIO(pix.tobytes("png")))
                    st.image(crop_img, caption="추출 영역 이미지")
                    
                    # 2. 텍스트 편집 에디터
                    edited_text = st.text_area("추출된 텍스트 편집", value=anno['text'], key=f"edit_{anno['id']}", height=150)
                    
                    # 실시간 데이터 반영
                    for original in st.session_state.annotations:
                        if original['id'] == anno['id']:
                            original['text'] = edited_text
                    
                    st.caption(f"Coordinates: {anno['bbox']}")

            # JSON 내보내기 영역
            st.markdown("---")
            if st.session_state.annotations:
                export_data = json.dumps(st.session_state.annotations, ensure_ascii=False, indent=4)
                st.download_button(
                    label="💾 전체 결과 JSON 다운로드",
                    data=export_data,
                    file_name="extracted_result.json",
                    mime="application/json",
                    use_container_width=True
                )

else:
    st.info("👈 좌측 사이드바에서 분석할 PDF 파일을 업로드해주세요.")
