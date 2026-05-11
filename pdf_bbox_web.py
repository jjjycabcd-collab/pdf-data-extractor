import streamlit as st
import fitz  # PyMuPDF
import json
import os
import io
import re
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas

# ==========================================
# 1. 페이지 및 상태 초기화
# ==========================================
# 타이틀 수정: 상호작업 데이터 구축
st.set_page_config(layout="wide", page_title="상호작용 데이터 구축 - Web Editor")

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
# 2. 유틸리티 및 분류 로직 (이전과 동일)
# ==========================================
# ...classify_material, clean_extracted_text 함수 내용...

# ==========================================
# 3. 버튼 콜백 함수 (이전과 동일)
# ==========================================
# ...go_prev, go_next, delete_box, clear_all_annotations 함수 내용...

# ==========================================
# 4. 핵심 로직 & 캐싱 (이전과 동일)
# ==========================================
# ...get_cached_bg_bytes, get_autofit_rect, get_sorted_text, save_cropped_image 함수 내용...

# ==========================================
# 5. UI 및 메인 앱 로직
# ==========================================
# 타이틀 출력 수정
st.title("📄 상호작용 데이터 구축 - Web Editor")

uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])
# ...이하 내용 동일...

if uploaded_file is not None:
    # ...이하 내용 동일...

        doc = st.session_state.pdf_doc
        total_pages = len(doc)
        
        autofit_enabled = st.checkbox("✨ 정밀 오토피팅 모드", value=True)
        
        col1, col2 = st.columns(2)
        col1.button("◀ 이전", on_click=go_prev, use_container_width=True)
        col2.button("다음 ▶", on_click=go_next, args=(total_pages,), use_container_width=True)
        st.sidebar.write(f"**현재 페이지:** {st.session_state.current_page + 1} / {total_pages}")
        
        # === 오류 수정된 버튼 부분 (140번 라인 근처) ===
        # variant="danger" 대신 type="primary"를 사용하여 오류 해결
        if st.sidebar.button("🗑️ 현재 작업 전체 삭제", type="primary"):
            clear_all_annotations()
            st.rerun()

# ...이하 PDF 처리 및 캔버스 설정, 데이터 편집기 내용 동일...
