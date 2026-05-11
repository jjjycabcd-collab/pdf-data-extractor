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
    if not text: return ""
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
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return img, page.rect.width, page.rect.height
    except:
        return None, 0, 0

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

    # 이미지 및 좌표 설정
    full_bg, pdf_w, pdf_h = get_page_image(st.session_state.file_bytes, st.session_state.current_page)
    if full_bg is None:
        st.error("PDF 페이지를 로드할 수 없습니다.")
        st.stop()

    canvas_w = 700
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    pdf_to_canvas_ratio = canvas_w / pdf_w

    # Fabric.js 객체 렌더링
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
                "id": anno['id']
            })
    
    initial_drawing = {"version": "4.4.0", "objects": fabric_objects}
    tag_mode = "transform" if st.session_state.selected_box_id else "rect"

    left_col, right_col = st.columns([6, 4])

    with left_col:
        # 상태 안내 및 초기화용 숨겨진 버튼
        status_txt = "🔧 수정 모드 (조정 완료 시 자동 복귀)" if tag_mode=="transform" else "🖋️ 태깅 모드 (기존 박스 클릭 시 수정 가능)"
        st.write(f"**[상태] {status_txt}**")
        
        # ESC 기능 및 수동 해제용
        if tag_mode == "transform":
            if st.button("✨ 편집 완료 (다시 그리기 모드)", key="btn_manual_reset"):
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

        # ----------------------------------------------------
        # 핵심 상호작용 로직
        # ----------------------------------------------------
        if canvas_result.json_data and "objects" in canvas_result.json_data:
            objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
            
            if tag_mode == "transform":
                # [수정 모드] 위치/크기 변경 시 업데이트 후 자동 복귀
                modified = False
                for obj in objs:
                    if "id" in obj:
                        for anno in st.session_state.annotations:
                            if anno['id'] == obj['id']:
                                old_r = anno['pdf_rect']
                                n_x0 = obj['left'] / pdf_to_canvas_ratio
                                n_y0 = obj['top'] / pdf_to_canvas_ratio
                                n_x1 = n_x0 + (obj['width'] * obj.get('scaleX', 1)) / pdf_to_canvas_ratio
                                n_y1 = n_y0 + (obj['height'] * obj.get('scaleY', 1)) / pdf_to_canvas_ratio
                                
                                if abs(n_x0 - old_r[0]) > 0.5 or abs(n_y0 - old_r[1]) > 0.5:
                                    anno['pdf_rect'] = [n_x0, n_y0, n_x1, n_y1]
                                    modified = True
                if modified:
                    # 수정을 마쳤으므로 '선택'을 풀어 연속 태깅이 가능하도록 함
                    st.session_state.selected_box_id = None
                    st.rerun()
            else:
                # [태깅 모드] 드래그 추출 또는 기존 박스 클릭 인식
                if len(objs) > len(fabric_objects):
                    new_obj = objs[-1]
                    # (1) 클릭 판정 (작은 박스면 클릭으로 간주)
                    if new_obj['width'] < 10 and new_obj['height'] < 10:
                        cx, cy = new_obj['left'] / pdf_to_canvas_ratio, new_obj['top'] / pdf_to_canvas_ratio
                        clicked_id = None
                        for a in reversed(st.session_state.annotations):
                            if a['page_idx'] == st.session_state.current_page:
                                r = a['pdf_rect']
                                if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]:
                                    clicked_id = a['id']
                                    break
                        if clicked_id:
                            st.session_state.selected_box_id = clicked_id
                            st.rerun()
                    # (2) 드래그 판정 (새로운 태깅 추가)
                    elif new_obj['width'] > 10:
                        p_x0, p_y0 = new_obj["left"] / pdf_to_canvas_ratio, new_obj["top"] / pdf_to_canvas_ratio
                        p_x1, p_y1 = p_x0 + (new_obj["width"]/pdf_to_canvas_ratio), p_y0 + (new_obj["height"]/pdf_to_canvas_ratio)
                        
                        page = doc.load_page(st.session_state.current_page)
                        fit_rect = fitz.Rect(p_x0, p_y0, p_x1, p_y1)
                        
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
                        # ★ 중요: 새 박스를 추가한 뒤 선택 상태를 만들지 않아 연속 태깅 가능하게 유지
                        st.session_state.selected_box_id = None 
                        st.rerun()

    with right_col:
        st.subheader("데이터 추출 목록")
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            
            st.markdown("""<style>.scroll-v { max-height: 200px; overflow-y: auto; border: 2px solid #4A90E2; border-radius: 8px; padding: 5px; background: #f9f9f9; }</style>""", unsafe_allow_html=True)
            st.markdown('<div class="scroll-v">', unsafe_allow_html=True)
            
            def format_label(aid):
                a = anno_dict[aid]
                r = a['pdf_rect']
                return f"[P{a['page_idx']+1}] [X:{int(r[0])}, Y:{int(r[1])}] | {a['text'][:20]}..."

            idx = valid_ids.index(st.session_state.selected_box_id) if st.session_state.selected_box_id in valid_ids else 0
            selected_id = st.radio("선택", options=valid_ids, format_func=format_label, index=idx, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            st.markdown("---")
            if st.session_state.selected_box_id in anno_dict:
                curr_anno = anno_dict[st.session_state.selected_box_id]
                st.image(curr_anno['img_path'], use_column_width=True)
                curr_anno['text'] = st.text_area("📝 내용 수정", value=curr_anno['text'], height=150)

                c1, c2 = st.columns(2)
                if c1.button("🗑️ 삭제", use_container_width=True, type="primary"):
                    delete_single_item(curr_anno)
                    st.rerun()
                
                export_data = [{"page": a['page_idx']+1, "bbox": a['pdf_rect'], "text": a['text']} for a in st.session_state.annotations]
                c2.download_button("💾 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                                file_name="result.json", mime="application/json")
        else:
            st.info("왼쪽 뷰어에서 드래그하여 태깅을 시작하세요.")

# JS 단축키 및 모드 초기화용
components.html("""<script>const doc = window.parent.document; doc.addEventListener('keydown', function(e) { if (e.key === 'ArrowLeft') { const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('이전')); if (btn) btn.click(); } else if (e.key === 'ArrowRight') { const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('다음')); if (btn) btn.click(); } else if (e.key === 'Escape') { const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('편집 완료')); if (btn) btn.click(); } });</script>""", height=0)
