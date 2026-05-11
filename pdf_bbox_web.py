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
# 2. 콜백 및 유틸리티 함수 (에러 방지 핵심)
# ==========================================
# 콜백을 사용해야 페이지 이동 시 무한 루프(RecursionError)가 발생하지 않습니다.
def go_prev():
    if st.session_state.current_page > 0:
        st.session_state.current_page -= 1
        st.session_state.selected_box_id = None
        st.session_state.clear_trigger += 1

def go_next(total_pages):
    if st.session_state.current_page < total_pages - 1:
        st.session_state.current_page += 1
        st.session_state.selected_box_id = None
        st.session_state.clear_trigger += 1

def reset_mode():
    st.session_state.selected_box_id = None
    st.session_state.clear_trigger += 1

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
        st.session_state.clear_trigger += 1

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
        st.session_state.clear_trigger += 1
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
    # 안전한 페이지 이동 콜백 사용
    col_nav1.button("◀ 이전", on_click=go_prev)
    col_nav2.button("다음 ▶", on_click=go_next, args=(total_pages,))
            
    st.sidebar.write(f"**파일:** {st.session_state.file_name}")
    st.sidebar.write(f"**페이지:** {st.session_state.current_page + 1} / {total_pages}")

    # 이미지 로드 및 700px 고정 비율 계산
    full_bg, pdf_w, pdf_h = get_page_image(st.session_state.file_bytes, st.session_state.current_page)
    if full_bg is None:
        st.error("PDF 페이지를 로드할 수 없습니다.")
        st.stop()

    canvas_w = 700
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    pdf_to_canvas_ratio = canvas_w / pdf_w

    # Fabric.js 객체 렌더링 (저장된 박스들)
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
        status_txt = "🔧 수정 모드 (조정 완료 시 자동 복귀)" if tag_mode=="transform" else "🖋️ 태깅 모드 (빈 공간 드래그: 추가 / 기존 박스 클릭: 수정)"
        st.write(f"**[상태] {status_txt}**")
        
        # ESC 기능 및 수동 해제용 숨김 버튼
        st.markdown("<div style='display:none'>", unsafe_allow_html=True)
        st.button("모드초기화", key="btn_hidden_reset", on_click=reset_mode)
        st.markdown("</div>", unsafe_allow_html=True)

        # clear_trigger를 key에 포함시켜 모드 전환/성공 시 캔버스를 완전히 리셋 (꼬임 방지)
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
            key=f"canvas_p{st.session_state.current_page}_m{tag_mode}_{st.session_state.clear_trigger}",
        )

        # ==========================================
        # 5. 핵심 캔버스 이벤트 로직
        # ==========================================
        if canvas_result.json_data and "objects" in canvas_result.json_data:
            objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
            
            if tag_mode == "transform":
                # [수정 모드] 박스 크기 변경 시 데이터 업데이트
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
                                
                                # 위치나 크기가 실제로 변했는지 확인
                                if abs(n_x0 - old_r[0]) > 0.5 or abs(n_y0 - old_r[1]) > 0.5 or abs(n_x1 - old_r[2]) > 0.5 or abs(n_y1 - old_r[3]) > 0.5:
                                    anno['pdf_rect'] = [n_x0, n_y0, n_x1, n_y1]
                                    modified = True
                
                # 조정을 마쳤으면 자동으로 선택 해제하고 신규 태깅 모드로 복귀
                if modified:
                    st.session_state.selected_box_id = None
                    st.session_state.clear_trigger += 1
                    st.rerun()

            else:
                # [신규 태깅 모드] 드래그 추출 또는 기존 박스 클릭
                if len(objs) > len(fabric_objects):
                    new_obj = objs[-1]
                    obj_sig = f"{new_obj['left']}_{new_obj['top']}_{new_obj['width']}"
                    
                    if st.session_state.last_canvas_sig != obj_sig:
                        st.session_state.last_canvas_sig = obj_sig
                        
                        p_x0 = new_obj["left"] / pdf_to_canvas_ratio
                        p_y0 = new_obj["top"] / pdf_to_canvas_ratio
                        p_x1 = p_x0 + (new_obj["width"] / pdf_to_canvas_ratio)
                        p_y1 = p_y0 + (new_obj["height"] / pdf_to_canvas_ratio)
                        
                        # (1) 단순 클릭 감지 (너비와 높이가 10px 미만인 경우)
                        if new_obj['width'] < 10 and new_obj['height'] < 10:
                            clicked_id = None
                            for a in reversed(st.session_state.annotations):
                                if a['page_idx'] == st.session_state.current_page:
                                    r = a['pdf_rect']
                                    if r[0] <= p_x0 <= r[2] and r[1] <= p_y0 <= r[3]:
                                        clicked_id = a['id']
                                        break
                            
                            # 기존 박스를 클릭했다면 해당 박스 선택
                            if clicked_id:
                                st.session_state.selected_box_id = clicked_id
                            
                            # 클릭 판정이 끝났으므로 캔버스 찌꺼기 제거를 위해 리셋
                            st.session_state.clear_trigger += 1
                            st.rerun()
                            
                        # (2) 정상적인 드래그 (신규 박스 추가)
                        elif new_obj['width'] >= 10 and new_obj['height'] >= 10:
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
                            # 새로 그렸을 때는 선택상태로 들어가지 않고 계속 그릴 수 있게 둠
                            st.session_state.selected_box_id = None
                            st.session_state.clear_trigger += 1
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
                coords = "[X:" + str(int(r[0])) + ", Y:" + str(int(r[1])) + ", W:" + str(int(r[2]-r[0])) + ", H:" + str(int(r[3]-r[1])) + "]"
                return "[P" + str(a['page_idx']+1) + "] " + coords + " | " + a['text'][:20].replace('\n', ' ') + "..."

            idx = valid_ids.index(st.session_state.selected_box_id) if st.session_state.selected_box_id in valid_ids else 0
            selected_id = st.radio("선택", options=valid_ids, format_func=format_label, index=idx, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != st.session_state.selected_box_id:
                st.session_state.selected_box_id = selected_id
                st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.session_state.clear_trigger += 1
                st.rerun()

            st.markdown("---")
            if st.session_state.selected_box_id in anno_dict:
                curr_anno = anno_dict[st.session_state.selected_box_id]
                # 오류 방지를 위한 use_column_width 통일
                st.image(curr_anno['img_path'], use_column_width=True)
                curr_anno['text'] = st.text_area("📝 내용 수정", value=curr_anno['text'], height=150)

                c1, c2 = st.columns(2)
                if c1.button("🗑️ 삭제"):
                    delete_single_item(curr_anno)
                    st.rerun()
                
                export_data = [{"page": a['page_idx']+1, "bbox": a['pdf_rect'], "text": a['text']} for a in st.session_state.annotations]
                c2.download_button("💾 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                                file_name="result.json", mime="application/json")
        else:
            st.info("왼쪽 뷰어에서 영역을 드래그하여 추출하세요.")

# ==========================================
# 6. JavaScript 단축키 연동
# ==========================================
components.html("""
<script>
const doc = window.parent.document;
doc.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowLeft') {
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('이전'));
        if (btn) btn.click();
    } else if (e.key === 'ArrowRight') {
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('다음'));
        if (btn) btn.click();
    } else if (e.key === 'Escape') {
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('모드초기화'));
        if (btn) btn.click();
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'INPUT') {
            const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('삭제'));
            if (btn) btn.click();
        }
    }
});
</script>
""", height=0)
