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
st.set_page_config(layout="wide", page_title="SI 데이터 구축 엔진 Pro")

# 상태 관리 변수 리스트
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
# 2. 유틸리티 및 분류 로직
# ==========================================
def classify_material(text):
    """텍스트 내용을 분석하여 기본 자료유형을 추천 (기존 규칙 반영)"""
    text = text.lower()
    if any(keyword in text for keyword in ["표준", "지침", "isbn", "도서"]):
        return "단행본"
    if any(keyword in text for keyword in ["보도자료", "신문", "연보", "뉴스"]):
        return "기타"
    return "단행본" # 기본값

def clean_extracted_text(text):
    """저자소개 등 불필요한 패턴 제거 (참고문헌 추출 최적화)"""
    # 간단한 정규표현식 예시: 저자소개 문구 이후를 잘라내거나 정제
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if "저자소개" not in line and "profile" not in line.lower()]
    return "\n".join(cleaned_lines).strip()

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
# 4. 핵심 로직 & 캐싱
# ==========================================
@st.cache_data(show_spinner=False)
def get_cached_bg_bytes(file_bytes, page_idx):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    # 고해상도 렌더링 (2.0배)
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
    # 텍스트 추출 및 기본적인 정제 적용
    raw_text = page.get_text("text", clip=rect)
    return clean_extracted_text(raw_text)

def save_cropped_image(page, pdf_rect):
    st.session_state.crop_counter += 1
    filename = f"crop_p{st.session_state.current_page+1}_{st.session_state.crop_counter:03d}.png"
    filepath = os.path.join(IMAGE_SAVE_DIR, filename)
    pix = page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=pdf_rect)
    pix.save(filepath)
    return filename, filepath

# ==========================================
# 5. UI 및 메인 앱 로직
# ==========================================
st.title("📄 SI 데이터 구축 엔진 - Web Editor")

with st.sidebar:
    uploaded_file = st.file_uploader("PDF 업로드", type=["pdf"])
    st.markdown("---")
    
    if uploaded_file:
        if st.session_state.file_name != uploaded_file.name:
            file_bytes = uploaded_file.read()
            st.session_state.file_bytes = file_bytes
            st.session_state.pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            st.session_state.file_name = uploaded_file.name
            st.session_state.annotations = []
            st.rerun()

        doc = st.session_state.pdf_doc
        total_pages = len(doc)
        
        autofit_enabled = st.checkbox("✨ 정밀 오토피팅 (텍스트 경계 맞춤)", value=True)
        
        col1, col2 = st.columns(2)
        col1.button("◀ 이전", on_click=go_prev, use_container_width=True)
        col2.button("다음 ▶", on_click=go_next, args=(total_pages,), use_container_width=True)
        st.write(f"**현재 페이지:** {st.session_state.current_page + 1} / {total_pages}")
        
        if st.button("🗑️ 현재 작업 전체 삭제", variant="danger"):
            clear_all_annotations()
            st.rerun()

if st.session_state.file_bytes:
    # PDF 배경 로드 (캐시 활용)
    bg_bytes = get_cached_bg_bytes(st.session_state.file_bytes, st.session_state.current_page)
    bg_image = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
    
    # 캔버스 크기 조정을 위한 비율 계산
    canvas_width = 800 
    scale = canvas_width / bg_image.width
    canvas_height = int(bg_image.height * scale)
    display_image = bg_image.resize((canvas_width, canvas_height))

    # 하이라이트 박스 그리기
    overlay = Image.new("RGBA", display_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    # PDF 좌표 -> 캔버스 좌표 변환 상수 (fitz 72dpi 기준, bg_image는 2배 확대된 상태이므로 조정 필요)
    # get_pixmap(matrix=2,2) 했으므로 원본 PDF 좌표에 2를 곱한 것이 bg_image 크기
    pdf_to_img_scale = 2.0 * scale 

    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            x0, y0, x1, y1 = [c * pdf_to_img_scale for c in anno['pdf_rect']]
            is_selected = st.session_state.selected_box_id == anno['id']
            color = (255, 0, 0, 255) if is_selected else (0, 0, 255, 180)
            fill = (255, 0, 0, 40) if is_selected else (0, 0, 255, 20)
            draw.rectangle([x0, y0, x1, y1], outline=color, width=3 if is_selected else 2, fill=fill)

    final_bg = Image.alpha_composite(display_image, overlay)

    left_col, right_col = st.columns([6, 4])

    with left_col:
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
            key=f"canvas_{st.session_state.current_page}",
        )

        if canvas_result.json_data:
            objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
            if objs:
                new_rect = objs[-1]
                rect_sig = f"{new_rect['left']}_{new_rect['top']}_{new_rect['width']}"
                
                if st.session_state.last_canvas_sig != rect_sig:
                    st.session_state.last_canvas_sig = rect_sig
                    
                    # 캔버스 좌표 -> PDF 좌표 역변환
                    pdf_x0 = new_rect["left"] / pdf_to_img_scale
                    pdf_y0 = new_rect["top"] / pdf_to_img_scale
                    pdf_x1 = (new_rect["left"] + new_rect["width"]) / pdf_to_img_scale
                    pdf_y1 = (new_rect["top"] + new_rect["height"]) / pdf_to_img_scale
                    
                    if new_rect["width"] < 10 and new_rect["height"] < 10:
                        # 클릭(선택) 모직
                        clicked_id = None
                        for anno in reversed(st.session_state.annotations):
                            if anno['page_idx'] == st.session_state.current_page:
                                ax0, ay0, ax1, ay1 = anno['pdf_rect']
                                if ax0 <= pdf_x0 <= ax1 and ay0 <= pdf_y0 <= ay1:
                                    clicked_id = anno['id']
                                    break
                        st.session_state.selected_box_id = clicked_id
                    else:
                        # 신규 추출 모직
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
                            'type': classify_material(text),
                            'img_name': img_name,
                            'img_path': img_path
                        })
                        st.session_state.selected_box_id = anno_id
                    
                    st.session_state.clear_trigger += 1
                    st.session_state.canvas_state["trigger"] = st.session_state.clear_trigger
                    st.rerun()

    with right_col:
        if st.session_state.annotations:
            # 선택된 항목 찾기
            selected_anno = next((a for a in st.session_state.annotations if a['id'] == st.session_state.selected_box_id), st.session_state.annotations[-1])
            
            st.subheader("🧐 데이터 상세 편집")
            st.image(selected_anno['img_path'], caption="추출 영역 스캔본")
            
            # 자료유형 관리
            selected_anno['type'] = st.selectbox("자료유형 분류", ["단행본", "기타"], 
                                             index=0 if selected_anno['type'] == "단행본" else 1)
            
            # 텍스트 편집
            selected_anno['text'] = st.text_area("텍스트 내용 (저자소개 자동 필터링됨)", value=selected_anno['text'], height=250)
            
            col_del, col_exp = st.columns(2)
            if col_del.button("🗑️ 삭제", use_container_width=True):
                idx = st.session_state.annotations.index(selected_anno)
                delete_box(idx, selected_anno['img_path'])
                st.rerun()

            # 전체 내보내기
            export_data = [{
                "page": a['page_idx'] + 1,
                "type": a['type'],
                "text": a['text'],
                "bbox": a['pdf_rect']
            } for a in st.session_state.annotations]
            
            col_exp.download_button(
                "💾 JSON 다운로드",
                data=json.dumps(export_data, ensure_ascii=False, indent=4),
                file_name=f"SI_Extract_{st.session_state.file_name}.json",
                mime="application/json",
                use_container_width=True
            )
        else:
            st.info("💡 PDF에서 영역을 드래그하여 데이터를 추출하세요.")
