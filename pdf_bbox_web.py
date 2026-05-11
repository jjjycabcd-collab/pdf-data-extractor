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

# 깜빡임 제거 및 중복 방지용 상태 변수
if 'clear_trigger' not in st.session_state:
    st.session_state.clear_trigger = 0
if 'canvas_state' not in st.session_state:
    st.session_state.canvas_state = {"version": "4.4.0", "objects": [], "trigger": 0}
if 'last_canvas_sig' not in st.session_state:
    st.session_state.last_canvas_sig = None

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
# 3. 핵심 로직 & 캐싱
# ==========================================
@st.cache_data(show_spinner=False)
def get_cached_bg_bytes(file_bytes, page_idx):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    mat = fitz.Matrix(1.0, 1.0)
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
    col1.button("◀ 이전", on_click=go_prev)
    col2.button("다음 ▶", on_click=go_next, args=(total_pages,))
    st.sidebar.write(f"**Page:** {st.session_state.current_page + 1} / {total_pages}")

    # ==========================================
    # PDF 배경 위에 추출된 박스 레이어 합성
    # ==========================================
    bg_bytes = get_cached_bg_bytes(st.session_state.file_bytes, st.session_state.current_page)
    bg_image = Image.open(io.BytesIO(bg_bytes)).convert("RGBA")
    view_zoom = 1.0 
    
    overlay = Image.new("RGBA", bg_image.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            x0, y0, x1, y1 = anno['pdf_rect']
            zx0, zy0, zx1, zy1 = x0 * view_zoom, y0 * view_zoom, x1 * view_zoom, y1 * view_zoom
            
            if st.session_state.selected_box_id == anno['id']:
                draw.rectangle([zx0, zy0, zx1, zy1], outline=(255, 0, 0, 255), width=3)
                draw.rectangle([zx0, zy0, zx1, zy1], fill=(255, 0, 0, 50)) 
            else:
                draw.rectangle([zx0, zy0, zx1, zy1], outline=(0, 0, 255, 255), width=2)
                draw.rectangle([zx0, zy0, zx1, zy1], fill=(0, 0, 255, 30)) 

    bg_image = Image.alpha_composite(bg_image, overlay)

    left_col, right_col = st.columns([6, 4])

    with left_col:
        st.write("**PDF 뷰어 (클릭: 박스 선택 / 드래그: 새로운 영역 추출)**")
        
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
            key=f"canvas_{st.session_state.file_name}_p{st.session_state.current_page}",
        )

        if canvas_result.json_data is not None:
            objects = canvas_result.json_data["objects"]
            current_canvas_objects = [obj for obj in objects if obj["type"] == "rect"]
            
            if len(current_canvas_objects) > 0:
                new_rect = current_canvas_objects[-1]
                w, h = new_rect["width"], new_rect["height"]
                
                # ★ 핵심 버그 수정: 박스 지문(Signature)을 만들어 15번 중복 추출되는 버그 원천 차단
                rect_sig = f"{new_rect['left']:.2f}_{new_rect['top']:.2f}_{w:.2f}_{h:.2f}"
                
                # 지문이 다를 때(정말 새로운 드래그/클릭일 때)만 로직 실행
                if st.session_state.get('last_canvas_sig') != rect_sig:
                    st.session_state.last_canvas_sig = rect_sig
                    
                    if max(w, h) < 15:
                        # [클릭 이벤트] 기존 박스 선택
                        click_x = (new_rect["left"] + w/2) / view_zoom
                        click_y = (new_rect["top"] + h/2) / view_zoom
                        
                        clicked_id = None
                        for anno in reversed(st.session_state.annotations):
                            if anno['page_idx'] == st.session_state.current_page:
                                x0, y0, x1, y1 = anno['pdf_rect']
                                if x0 <= click_x <= x1 and y0 <= click_y <= y1:
                                    clicked_id = anno['id']
                                    break
                        
                        st.session_state.selected_box_id = clicked_id
                        
                        # 캔버스 점 지우기 (깜빡임 없음)
                        st.session_state.clear_trigger += 1
                        st.session_state.canvas_state = {"version": "4.4.0", "objects": [], "trigger": st.session_state.clear_trigger}
                        st.rerun()
                    
                    else:
                        # [드래그 이벤트] 새로운 박스 추출
                        page = doc.load_page(st.session_state.current_page)
                        x0 = new_rect["left"] / view_zoom
                        y0 = new_rect["top"] / view_zoom
                        x1 = (new_rect["left"] + new_rect["width"]) / view_zoom
                        y1 = (new_rect["top"] + new_rect["height"]) / view_zoom
                        
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
                        
                        # 그린 박스를 이미지로 굽고 캔버스 리셋
                        st.session_state.clear_trigger += 1
                        st.session_state.canvas_state = {"version": "4.4.0", "objects": [], "trigger": st.session_state.clear_trigger}
                        st.rerun() 
            else:
                # 캔버스가 완벽히 비워지면 락(Lock) 해제 -> 나중에 동일한 곳 그려도 인식 가능
                st.session_state.last_canvas_sig = None

    with right_col:
        st.write("**데이터 추출 목록**")
        
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            
            if st.session_state.selected_box_id not in valid_ids:
                st.session_state.selected_box_id = valid_ids[-1] if valid_ids else None

            # 목록에 페이지 번호, 좌표, 텍스트 미리보기 표시
            def format_list_item(anno_id):
                anno = anno_dict[anno_id]
                preview = anno['text'][:20].replace('\n', ' ') + ("..." if len(anno['text']) > 20 else "")
                rect = anno['pdf_rect']
                coords = f"[X:{rect[0]:.0f}, Y:{rect[1]:.0f}, W:{rect[2]-rect[0]:.0f}, H:{rect[3]-rect[1]:.0f}]"
                return f"[P{anno['page_idx'] + 1}] {coords} | {preview}"

            selected_id = st.radio(
                "항목 선택",
                options=valid_ids,
                format_func=format_list_item,
                index=valid_ids.index(st.session_state.selected_box_id) if st.session_state.selected_box_id else 0,
                label_visibility="collapsed"
            )

            # 리스트 클릭 시 자동 연동 (하이라이트 및 페이지 이동)
            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                target_page = anno_dict[selected_id]['page_idx']
                if target_page != st.session_state.current_page:
                    st.session_state.current_page = target_page
                    st.session_state.last_canvas_sig = None
                st.rerun()

            selected_anno = anno_dict[st.session_state.selected_box_id]

            st.markdown("<br>", unsafe_allow_html=True)
            st.button("🗑️ 선택 항목 삭제", use_container_width=True, on_click=delete_box, args=(st.session_state.annotations.index(selected_anno), selected_anno['img_path'], True))

            st.markdown("---")
            st.write("**🔍 선택 항목 상세 편집기**")

            if os.path.exists(selected_anno['img_path']):
                st.image(selected_anno['img_path'], use_column_width=True)
            
            new_text = st.text_area("텍스트 원문", value=selected_anno['text'], height=200)
            if new_text != selected_anno['text']:
                for a in st.session_state.annotations:
                    if a['id'] == st.session_state.selected_box_id:
                        a['text'] = new_text
                        break

            st.markdown("---")
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
            st.info("왼쪽 뷰어에서 마우스를 드래그하여 영역을 추출해주세요.")
else:
    st.info("👈 사이드바에서 PDF 파일을 업로드하여 작업을 시작하세요.")
