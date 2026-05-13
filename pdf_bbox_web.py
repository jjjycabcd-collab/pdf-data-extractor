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
# 2. 콜백 및 유틸리티 함수
# ==========================================
def go_prev():
    st.session_state.current_page = max(0, st.session_state.current_page - 1)
    st.session_state.selected_box_id = None
    st.session_state.clear_trigger += 1

def go_next(total_pages):
    st.session_state.current_page = min(total_pages - 1, st.session_state.current_page + 1)
    st.session_state.selected_box_id = None
    st.session_state.clear_trigger += 1

def delete_single_item(anno_id):
    for i, a in enumerate(st.session_state.annotations):
        if a['id'] == anno_id:
            if os.path.exists(a['img_path']):
                try: os.remove(a['img_path'])
                except: pass
            st.session_state.annotations.pop(i)
            break
    st.session_state.selected_box_id = None
    st.session_state.clear_trigger += 1

def clean_text(text):
    if not text: return ""
    lines = text.split('\n')
    return "\n".join([line.strip() for line in lines if "저자소개" not in line and line.strip()])

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
        # [수정] 새 PDF 로드 시 이전 작업 찌꺼기 이미지들 일괄 삭제
        for f in os.listdir(IMAGE_SAVE_DIR):
            try: os.remove(os.path.join(IMAGE_SAVE_DIR, f))
            except: pass
            
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
    col_nav1.button("◀ 이전", on_click=go_prev)
    col_nav2.button("다음 ▶", on_click=go_next, args=(total_pages,))
            
    st.sidebar.write(f"**파일:** {st.session_state.file_name}")
    st.sidebar.write(f"**페이지:** {st.session_state.current_page + 1} / {total_pages}")

    full_bg, pdf_w, pdf_h = get_page_image(st.session_state.file_bytes, st.session_state.current_page)
    if full_bg is None:
        st.error("PDF 페이지를 로드할 수 없습니다.")
        st.stop()

    canvas_w = 700
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    pdf_to_canvas_ratio = canvas_w / pdf_w

    # Fabric.js 객체 세팅
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
        header_col1, header_col2 = st.columns([7, 3])
        with header_col1:
            status_txt = "🔧 수정 모드 (새 박스를 그리려면 복귀 버튼이나 ESC를 누르세요)" if tag_mode=="transform" else "🖋️ 태깅 모드 (빈 공간 드래그: 추가 / 기존 박스 클릭: 수정)"
            st.write(f"**[상태] {status_txt}**")
        with header_col2:
            if tag_mode == "transform":
                if st.button("🔄 신규 태깅 모드로 복귀", key="btn_return_new"):
                    st.session_state.selected_box_id = None
                    st.session_state.clear_trigger += 1
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
            key=f"canvas_p{st.session_state.current_page}_m{tag_mode}_c{st.session_state.clear_trigger}",
        )

        # ----------------------------------------------------
        # 핵심 캔버스 상호작용 (무한루프 방지)
        # ----------------------------------------------------
        if canvas_result.json_data and "objects" in canvas_result.json_data:
            objs = [obj for obj in canvas_result.json_data["objects"] if obj["type"] == "rect"]
            
            if tag_mode == "transform":
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
                                
                                # 마우스를 드래그 아웃(변경 발생) 했는지 확인
                                if abs(n_x0 - old_r[0]) > 0.5 or abs(n_y0 - old_r[1]) > 0.5 or abs(n_x1 - old_r[2]) > 0.5 or abs(n_y1 - old_r[3]) > 0.5:
                                    page = doc.load_page(st.session_state.current_page)
                                    fit_rect = fitz.Rect(n_x0, n_y0, n_x1, n_y1)
                                    
                                    # 수정(리사이즈/이동) 시에도 정밀 오토피팅 활성화 시 적용
                                    if autofit_enabled:
                                        words = page.get_text("words")
                                        matched = [fitz.Rect(wd[:4]) for wd in words if fitz.Rect(wd[:4]).intersects(fit_rect)]
                                        if matched:
                                            fit_rect = matched[0]
                                            for r in matched[1:]: fit_rect |= r

                                    anno['pdf_rect'] = [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1]
                                    
                                    # [수정] 잦은 렌더링 시 브라우저가 파일을 찾지 못하는 에러 방지를 위해,
                                    # 드래그 중에 이전 파일을 강제 삭제하지 않고 남겨둠 (추후 초기화 시 일괄 정리)
                                    
                                    # 캐시 갱신을 위해 새로운 파일명으로 이미지 캡처 및 저장
                                    st.session_state.crop_counter += 1
                                    new_img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                                    new_img_path = os.path.join(IMAGE_SAVE_DIR, new_img_name)
                                    page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=fit_rect).save(new_img_path)
                                    
                                    anno['img_name'] = new_img_name
                                    anno['img_path'] = new_img_path
                                    
                                    # 새로운 영역에 해당하는 텍스트 다시 추출
                                    anno['text'] = clean_text(page.get_text("text", clip=fit_rect))
                                    
                                    modified = True
                
                if modified:
                    st.session_state.clear_trigger += 1
                    st.rerun()

            else:
                # [신규 태깅 모드]
                if len(objs) > len(fabric_objects):
                    new_obj = objs[-1]
                    obj_sig = f"{new_obj['left']:.1f}_{new_obj['top']:.1f}_{new_obj['width']:.1f}_{new_obj['height']:.1f}"
                    
                    if st.session_state.last_canvas_sig != obj_sig:
                        st.session_state.last_canvas_sig = obj_sig
                        
                        w = new_obj['width'] * new_obj.get('scaleX', 1)
                        h = new_obj['height'] * new_obj.get('scaleY', 1)
                        
                        p_x0 = new_obj["left"] / pdf_to_canvas_ratio
                        p_y0 = new_obj["top"] / pdf_to_canvas_ratio
                        p_x1 = p_x0 + (w / pdf_to_canvas_ratio)
                        p_y1 = p_y0 + (h / pdf_to_canvas_ratio)
                        
                        if w < 10 and h < 10:
                            # 1. 클릭 감지 (수정 모드 진입)
                            cx = (new_obj['left'] + w/2) / pdf_to_canvas_ratio
                            cy = (new_obj['top'] + h/2) / pdf_to_canvas_ratio
                            clicked_id = None
                            for a in reversed(st.session_state.annotations):
                                if a['page_idx'] == st.session_state.current_page:
                                    r = a['pdf_rect']
                                    if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]:
                                        clicked_id = a['id']
                                        break
                            
                            if clicked_id:
                                st.session_state.selected_box_id = clicked_id
                            st.session_state.clear_trigger += 1
                            st.rerun()
                            
                        elif w >= 10 and h >= 10:
                            # 2. 정상 드래그 감지 (새 박스 추가)
                            page = doc.load_page(st.session_state.current_page)
                            fit_rect = fitz.Rect(p_x0, p_y0, p_x1, p_y1)
                            
                            if autofit_enabled:
                                words = page.get_text("words")
                                matched = [fitz.Rect(wd[:4]) for wd in words if fitz.Rect(wd[:4]).intersects(fit_rect)]
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
                            
                            st.session_state.selected_box_id = None
                            st.session_state.clear_trigger += 1
                            st.rerun()

    with right_col:
        st.subheader("데이터 추출 목록")
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            radio_options = ["NEW_MODE"] + valid_ids

            st.markdown("""<style>.scroll-v { max-height: 200px; overflow-y: auto; border: 2px solid #4A90E2; border-radius: 8px; padding: 5px; background: #fcfcfc; }</style>""", unsafe_allow_html=True)
            st.markdown('<div class="scroll-v">', unsafe_allow_html=True)
            
            def format_label(aid):
                if aid == "NEW_MODE":
                    return "✨ [신규 태깅 모드] 빈 공간을 드래그하세요"
                a = anno_dict[aid]
                r = a['pdf_rect']
                coords = "[X:" + str(int(r[0])) + ", Y:" + str(int(r[1])) + ", W:" + str(int(r[2]-r[0])) + ", H:" + str(int(r[3]-r[1])) + "]"
                return "[P" + str(a['page_idx']+1) + "] " + coords + " | " + a['text'][:20].replace('\n', ' ') + "..."

            # 현재 상태에 맞춰 인덱스 결정
            current_val = st.session_state.selected_box_id if st.session_state.selected_box_id in valid_ids else "NEW_MODE"
            idx = radio_options.index(current_val)

            selected_id = st.radio("목록", options=radio_options, format_func=format_label, index=idx, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != current_val:
                st.session_state.selected_box_id = None if selected_id == "NEW_MODE" else selected_id
                if selected_id != "NEW_MODE":
                    st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.session_state.clear_trigger += 1
                st.rerun()

            st.markdown("---")
            if st.session_state.selected_box_id in anno_dict:
                curr_anno = anno_dict[st.session_state.selected_box_id]
                
                # [수정] 파일 경로를 직접 주지 않고 PIL 객체로 변환해서 출력하여 MediaFileStorageError 방지
                if os.path.exists(curr_anno['img_path']):
                    img_to_show = Image.open(curr_anno['img_path'])
                    st.image(img_to_show, use_column_width=True)
                else:
                    st.warning("이미지 파일을 찾을 수 없습니다. 다시 드래그하여 영역을 갱신해 주세요.")

                curr_anno['text'] = st.text_area("📝 내용 수정", value=curr_anno['text'], height=150)

                c1, c2 = st.columns(2)
                c1.button("🗑️ 삭제", type="primary", on_click=delete_single_item, args=(curr_anno['id'],))
                
                export_data = [{"page": a['page_idx']+1, "bbox": a['pdf_rect'], "text": a['text']} for a in st.session_state.annotations]
                c2.download_button("💾 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                                file_name="result.json", mime="application/json")
        else:
            st.info("왼쪽 뷰어에서 영역을 드래그하여 태깅을 시작하세요.")

# ==========================================
# 6. JavaScript 단축키 연동
# ==========================================
components.html("""
<script>
const doc = window.parent.document;
doc.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowLeft') {
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === '◀ 이전');
        if (btn) btn.click();
    } else if (e.key === 'ArrowRight') {
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === '다음 ▶');
        if (btn) btn.click();
    } else if (e.key === 'Escape') {
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('신규 태깅 모드로 복귀'));
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
