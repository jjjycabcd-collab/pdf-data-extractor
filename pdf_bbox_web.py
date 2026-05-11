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
# 2. 핵심 유틸리티 및 데이터 정제 로직
# ==========================================
def classify_material(text):
    """텍스트 내용을 분석하여 정의된 규칙에 따라 자료유형 분류"""
    text_content = text.replace(" ", "").lower()
    
    # 단행본 분류 규칙: 표준, 지침, 도서
    if any(kw in text_content for kw in ["표준", "지침", "도서"]):
        return "단행본"
    
    # 기타 분류 규칙: 보도자료, 신문, 연보
    if any(kw in text_content for kw in ["보도자료", "신문", "연보"]):
        return "기타"
        
    return "단행본" # 기본값

def clean_extracted_text(text):
    """추출된 텍스트에서 저자소개 관련 내용을 제외하고 정제"""
    lines = text.split('\n')
    # '저자소개' 단어가 포함된 라인 및 불필요한 공백 제거
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

def delete_box(idx, img_path):
    if os.path.exists(img_path):
        os.remove(img_path)
    st.session_state.annotations.pop(idx)
    st.session_state.selected_box_id = None

def clear_all_annotations():
    for anno in st.session_state.annotations:
        if os.path.exists(anno['img_path']):
            os.remove(anno['img_path'])
    st.session_state.annotations = []
    st.session_state.selected_box_id = None

# ==========================================
# 4. PDF 처리 및 이미지 추출 로직
# ==========================================
@st.cache_data(show_spinner=False)
def get_cached_bg_bytes(file_bytes, page_idx):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
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
    # 영역 내 텍스트를 추출한 뒤 저자소개 제외 로직 적용
    raw_text = page.get_text("text", clip=rect)
    return clean_extracted_text(raw_text)

def save_cropped_image(page, pdf_rect):
    st.session_state.crop_counter += 1
    filename = f"crop_p{st.session_state.current_page+1}_{st.session_state.crop_counter:03d}.png"
    filepath = os.path.join(IMAGE_SAVE_DIR, filename)
    # 고해상도 크롭 (3.0배)
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=pdf_rect)
    pix.save(filepath)
    return filename, filepath

# ==========================================
# 5. UI 레이아웃 및 메인 로직
# ==========================================
st.title("📄 상호작업 데이터 구축 - Web Editor")

with st.sidebar:
    uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])
    st.markdown("---")
    
    if uploaded_file:
        if st.session_state.file_name != uploaded_file.name:
            st.session_state.file_bytes = uploaded_file.read()
            st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
            st.session_state.file_name = uploaded_file.name
            st.session_state.annotations = []
            st.rerun()

        doc = st.session_state.pdf_doc
        total_pages = len(doc)
        
        autofit_enabled = st.checkbox("✨ 정밀 오토피팅 모드", value=True)
        
        col1, col2 = st.columns(2)
        col1.button("◀ 이전", on_click=go_prev, use_container_width=True)
        col2.button("다음 ▶", on_click=go_next, args=(total_pages,), use_container_width=True)
        st.write(f"**현재 페이지:** {st.session_state.current_page + 1} / {total_pages}")
        
        # [수정 사항] variant="danger" 삭제 후 type="primary" 적용하여 오류 해결
        if st.button("🗑️ 현재 작업 전체 삭제", type="primary", use_container_width=True):
            clear_all_annotations()
            st.rerun()

if st.session_state.file_bytes:
    bg_bytes = get_cached_bg_bytes(st.session_state.file_bytes, st.session_state.current_page)
    bg_image = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
    
    # 캔버스 크기 및 스케일 계산
    canvas_width = 800 
    scale = canvas_width / bg_image.width
    canvas_height = int(bg_image.height * scale)
    display_image = bg_image.resize((canvas_width, canvas_height))
    
    # 추출된 박스 하이라이트 레이어
    overlay = Image.new("RGBA", display_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    pdf_to_img_scale = 2.0 * scale # get_pixmap에서 Matrix(2,2)를 사용했으므로

    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            x0, y0, x1, y1 = [c * pdf_to_img_scale for c in anno['pdf_rect']]
            is_selected = (st.session_state.selected_box_id == anno['id'])
            outline_color = (255, 0, 0, 255) if is_selected else (0, 0, 255, 180)
            fill_color = (255, 0, 0, 40) if is_selected else (0, 0, 255, 20)
            draw.rectangle([x0, y0, x1, y1], outline=outline_color, width=3 if is_selected else 2, fill=fill_color)

    final_bg = Image.alpha_composite(display_image, overlay)

    left_col, right_col = st.columns([6, 4])

    with left_col:
        st.write("**PDF 뷰어 (드래그하여 영역 추출 / 박스 클릭하여 선택)**")
        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.1)",
            stroke_width=2,
            stroke_color="rgba(0, 0, 255, 0.8)",
            background_image=final_bg,
            initial_drawing=st.session_state.canvas_state,
            update_streamlit=True,
            height=canvas_height,
            width=canvas_width,
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
                    
                    pdf_x0 = new_rect["left"] / pdf_to_img_scale
                    pdf_y0 = new_rect["top"] / pdf_to_img_scale
                    pdf_x1 = (new_rect["left"] + new_rect["width"]) / pdf_to_img_scale
                    pdf_y1 = (new_rect["top"] + new_rect["height"]) / pdf_to_img_scale
                    
                    if new_rect["width"] < 10 and new_rect["height"] < 10:
                        # 단순 클릭 시 선택 전환
                        clicked_id = None
                        for anno in reversed(st.session_state.annotations):
                            if anno['page_idx'] == st.session_state.current_page:
                                ax0, ay0, ax1, ay1 = anno['pdf_rect']
                                if ax0 <= pdf_x0 <= ax1 and ay0 <= pdf_y0 <= ay1:
                                    clicked_id = anno['id']
                                    break
                        st.session_state.selected_box_id = clicked_id
                    else:
                        # 드래그 시 데이터 추출
                        page = st.session_state.pdf_doc.load_page(st.session_state.current_page)
                        fit_rect = get_autofit_rect(page, fitz.Rect(pdf_x0, pdf_y0, pdf_x1, pdf_y1), autofit_enabled)
                        text = get_sorted_text(page, fit_rect)
                        img_name, img_path = save_cropped_image(page, fit_rect)
                        
                        anno_id = f"id_{st.session_state.crop_counter}"
                        st.session_state.annotations.append({
                            'id': anno_id,
                            'page_idx': st.session_state.current_page,
                            'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                            'text': text,
                            'type': classify_material(text), # 자동 분류 적용
                            'img_name': img_name,
                            'img_path': img_path
                        })
                        st.session_state.selected_box_id = anno_id
                    
                    st.session_state.clear_trigger += 1
                    st.session_state.canvas_state["trigger"] = st.session_state.clear_trigger
                    st.rerun()

    with right_col:
        st.write("**🔍 추출 데이터 편집기**")
        if st.session_state.annotations:
            # 현재 선택된 항목 매칭
            selected_anno = next((a for a in st.session_state.annotations if a['id'] == st.session_state.selected_box_id), st.session_state.annotations[-1])
            
            if os.path.exists(selected_anno['img_path']):
                st.image(selected_anno['img_path'], use_container_width=True)
            
            # 자료유형 및 텍스트 편집
            m_types = ["단행본", "기타"]
            selected_anno['type'] = st.selectbox("자료유형 분류", m_types, 
                                             index=m_types.index(selected_anno['type']) if selected_anno['type'] in m_types else 0)
            
            selected_anno['text'] = st.text_area("내용 편집 (저자소개 필터링됨)", value=selected_anno['text'], height=250)
            
            # 삭제 및 다운로드 버튼
            c1, c2 = st.columns(2)
            if c1.button("🗑️ 삭제", use_container_width=True):
                idx = st.session_state.annotations.index(selected_anno)
                delete_box(idx, selected_anno['img_path'])
                st.rerun()

            export_data = [{
                "page": a['page_idx'] + 1,
                "type": a['type'],
                "text": a['text'],
                "bbox": [round(val, 2) for val in a['pdf_rect']],
                "image": a['img_name']
            } for a in st.session_state.annotations]
            
            c2.download_button(
                "💾 JSON 결과 추출",
                data=json.dumps(export_data, ensure_ascii=False, indent=4),
                file_name=f"Result_{st.session_state.file_name}.json",
                mime="application/json",
                use_container_width=True
            )
        else:
            st.info("왼쪽 뷰어에서 영역을 드래그하여 데이터 구축을 시작하세요.")
else:
    st.info("👈 사이드바에서 PDF 파일을 업로드하세요.")
