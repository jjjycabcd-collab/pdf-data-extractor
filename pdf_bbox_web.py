import streamlit as st
import streamlit.components.v1 as components
import fitz  # PyMuPDF
import json
import os
import io
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas

# ==========================================
# 1. 페이지 및 상태 초기화
# ==========================================
st.set_page_config(layout="wide", page_title="상호작용 데이터 구축 - Web Editor")

state_keys = {
    'file_bytes': None, 'pdf_doc': None, 'current_page': 0, 
    'annotations': [], 'crop_counter': 0, 'selected_box_id': None,
    'clear_trigger': 0, 'last_canvas_sig': None, 'file_name': ""
}

for key, default in state_keys.items():
    if key not in st.session_state:
        st.session_state[key] = default

IMAGE_SAVE_DIR = "extracted_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# ==========================================
# 2. 유틸리티 함수
# ==========================================
def clean_text(text):
    lines = text.split('\n')
    return "\n".join([line.strip() for line in lines if "저자소개" not in line and line.strip()])

def delete_single_item(anno_obj):
    if anno_obj:
        if os.path.exists(anno_obj['img_path']):
            os.remove(anno_obj['img_path'])
        if anno_obj in st.session_state.annotations:
            st.session_state.annotations.remove(anno_obj)
        st.session_state.selected_box_id = None

@st.cache_data(show_spinner=False)
def get_page_image(file_bytes, page_idx):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return img, page.rect.width, page.rect.height

# ==========================================
# 3. 파일 로드 로직
# ==========================================
uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

if uploaded_file is not None:
    if st.session_state.file_name != uploaded_file.name:
        st.session_state.file_bytes = uploaded_file.read()
        st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
        st.session_state.file_name = uploaded_file.name
        st.session_state.current_page = 0
        st.session_state.annotations = []
        st.session_state.crop_counter = 0
        st.session_state.selected_box_id = None
        st.rerun()
else:
    if not st.session_state.file_bytes:
        sample_path = "sample.pdf"
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                st.session_state.file_bytes = f.read()
            st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
            st.session_state.file_name = "sample.pdf"

# ==========================================
# 4. 메인 에디터 화면
# ==========================================
if st.session_state.file_bytes:
    doc = st.session_state.pdf_doc
    total_pages = len(doc)

    st.sidebar.markdown("---")
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)
    
    col_nav1, col_nav2 = st.sidebar.columns(2)
    if col_nav1.button("◀ 이전"):
        st.session_state.current_page = max(0, st.session_state.current_page - 1)
        st.session_state.selected_box_id = None
        st.rerun()
    if col_nav2.button("다음 ▶"):
        st.session_state.current_page = min(total_pages - 1, st.session_state.current_page + 1)
        st.session_state.selected_box_id = None
        st.rerun()
            
    st.sidebar.write(f"**파일:** {st.session_state.file_name}")
    st.sidebar.write(f"**페이지:** {st.session_state.current_page + 1} / {total_pages}")

    # 캔버스 크기 및 스케일 설정
    full_bg, pdf_w, pdf_h = get_page_image(st.session_state.file_bytes, st.session_state.current_page)
    canvas_w = 700
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    pdf_to_canvas_ratio = canvas_w / pdf_w

    # Fabric.js 객체 생성 (기존 태그들)
    fabric_objects = []
    for anno in st.session_state.annotations:
        if anno['page_idx'] == st.session_state.current_page:
            r = anno['pdf_rect']
            is_sel = (st.session_state.selected_box_id == anno['id'])
            fabric_objects.append({
                "type": "rect",
                "left": r[0] * pdf_to_canvas_ratio,
                "top": r[1] * pdf_to_canvas_ratio,
                "width": (r[2] - r[0]) * pdf_to_canvas_ratio,
                "height": (r[3] - r[1]) * pdf_to_canvas_ratio,
                "fill": "rgba(255, 0, 0, 0.2)" if is_sel else "rgba(0, 0, 255, 0.1)",
                "stroke": "rgba(255, 0, 0, 0.9)" if is_sel else "rgba(0, 0, 255, 0.7)",
                "strokeWidth": 3 if is_sel else 2,
                "id": anno['id']  # 커스텀 ID 저장
            })
    
    initial_drawing = {"version": "4.4.0", "objects": fabric_objects}
    tag_mode = "transform" if st.session_state.selected_box_id else "rect"

    left_col, right_col = st.columns([6, 4])

    with left_col:
        # 모드 안내 및 선택 해제 버튼
        status_txt = "🔧 영역 수정 모드 (박스 핸들을 드래그하세요)" if tag_mode=="transform" else "🖋️ 새 영역 태깅 모드 (드래그하여 박스를 그리세요)"
        st.write(f"**{status_txt}**")
        
        if tag_mode == "transform":
            if st.button("➕ 새 영역 추가하러 가기 (선택 해제)"):
                st.session_state.selected_box_id = None
                st.rerun()

        canvas_result = st_canvas(
            fill_color="rgba(0, 0, 255, 0.1)",
            stroke_width=2,
            stroke_color="rgba(0, 0, 255, 0.8)",
            background_image=display_img,
            initial_drawing=initial_drawing,
            update_streamlit=True,
            height=canvas_h,
            width=canvas_w,
            drawing_mode=tag_mode,
            display_toolbar=False,
            key=f"canvas_p{st.session_state.current_page}_m{tag_mode}",
        )

        # 캔버스 상호작용 로직
        if canvas_result.json_data:
            objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
            
            if tag_mode == "transform":
                # [편집 모드] 조정된 좌표를 실시간 업데이트
                for obj in objs:
                    if "id" in obj:
                        for anno in st.session_state.annotations:
                            if anno['id'] == obj['id']:
                                # 캔버스 좌표 -> 원본 PDF 좌표로 역변환하여 저장
                                new_x0 = obj['left'] / pdf_to_canvas_ratio
                                new_y0 = obj['top'] / pdf_to_canvas_ratio
                                new_x1 = new_x0 + (obj['width'] * obj['scaleX']) / pdf_to_canvas_ratio
                                new_y1 = new_y0 + (obj['height'] * obj['scaleY']) / pdf_to_canvas_ratio
                                anno['pdf_rect'] = [new_x0, new_y0, new_x1, new_y1]
            else:
                # [그리기 모드] 새 박스 생성
                if objs:
                    last_obj = objs[-1]
                    rect_sig = f"{last_obj['left']}_{last_obj['width']}_{len(objs)}"
                    if st.session_state.last_canvas_sig != rect_sig:
                        st.session_state.last_canvas_sig = rect_sig
                        
                        p_x0 = last_obj["left"] / pdf_to_canvas_ratio
                        p_y0 = last_obj["top"] / pdf_to_canvas_ratio
                        p_x1 = p_x0 + (last_obj["width"] / pdf_to_canvas_ratio)
                        p_y1 = p_y0 + (last_obj["height"] / pdf_to_canvas_ratio)
                        
                        if last_obj["width"] > 5: # 드래그 시 추출
                            page = doc.load_page(st.session_state.current_page)
                            fit_rect = fitz.Rect(p_x0, p_y0, p_x1, p_y1)
                            
                            # 오토피팅
                            if autofit_enabled:
                                words = page.get_text("words")
                                matched = [fitz.Rect(w[:4]) for w in words if fitz.Rect(w[:4]).intersects(fit_rect)]
                                if matched:
                                    fit_rect = matched[0]
                                    for r in matched[1:]: fit_rect |= r
                            
                            st.session_state.crop_counter += 1
                            img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                            img_path = os.path.join(IMAGE_SAVE_DIR, img_name)
                            page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=fit_rect).save(img_path)
                            
                            anno_id = f"id_{st.session_state.crop_counter}"
                            st.session_state.annotations.append({
                                'id': anno_id, 'page_idx': st.session_state.current_page,
                                'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                                'text': clean_text(page.get_text("text", clip=fit_rect)),
                                'img_name': img_name, 'img_path': img_path
                            })
                            st.session_state.selected_box_id = anno_id
                            st.rerun()

    with right_col:
        st.subheader("데이터 추출 목록")
        if st.session_state.annotations:
            # 목록 정렬 (페이지 순)
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            
            if st.session_state.selected_box_id not in valid_ids:
                st.session_state.selected_box_id = valid_ids[-1] if valid_ids else None

            # 스크롤 목록
            st.markdown("""<style>.scroll-v { max-height: 200px; overflow-y: auto; border: 2px solid #4A90E2; border-radius: 8px; padding: 5px; background: #f9f9f9; }</style>""", unsafe_allow_html=True)
            st.markdown('<div class="scroll-v">', unsafe_allow_html=True)
            
            def format_label(aid):
                a = anno_dict[aid]
                r = a['pdf_rect']
                return f"[P{a['page_idx']+1}] [X:{int(r[0])}, Y:{int(r[1])}] | {a['text'][:25]}..."

            selected_id = st.radio("선택", options=valid_ids, format_func=format_label,
                                   index=valid_ids.index(st.session_state.selected_box_id), label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            st.markdown("---")
            curr_anno = anno_dict[st.session_state.selected_box_id]
            st.image(curr_anno['img_path'], use_column_width=True)
            curr_anno['text'] = st.text_area("📝 내용 수정", value=curr_anno['text'], height=150)

            c1, c2 = st.columns(2)
            if c1.button("🗑️ 삭제", use_container_width=True, type="primary"):
                delete_single_item(curr_anno)
                st.rerun()
            
            export_data = [{"page": a['page_idx']+1, "bbox": a['pdf_rect'], "text": a['text']} for a in st.session_state.annotations]
            c2.download_button("💾 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                               file_name="result.json", mime="application/json", use_container_width=True)
        else:
            st.info("영역을 드래그하여 태깅을 시작하세요.")

# ==========================================
# 5. JavaScript 단축키
# ==========================================
components.html("""<script>const doc = window.parent.document; doc.addEventListener('keydown', function(e) { if (e.key === 'ArrowLeft') { const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('이전')); if (btn) btn.click(); } else if (e.key === 'ArrowRight') { const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('다음')); if (btn) btn.click(); } else if (e.key === 'Delete' || e.key === 'Backspace') { if (e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'INPUT') { const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('삭제')); if (btn) btn.click(); } } });</script>""", height=0)
