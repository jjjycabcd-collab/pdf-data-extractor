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

# CSS를 통한 강제 숨김 처리 (JS와 이중으로 숨겨 노출 원천 차단)
st.markdown(
    """
    <style>
    div[data-testid="stButton"] > button:contains("[HIDDEN]") { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True
)

if 'labels' not in st.session_state:
    st.session_state.labels = ['논문명', '저자명', '소속기관', '초록', '키워드']

state_keys = {
    'file_bytes': None, 'pdf_doc': None, 'current_page': 0, 
    'annotations': [], 'crop_counter': 0, 'selected_box_id': None,
    'last_canvas_sig': None, 'file_name': "",
    'active_label': st.session_state.labels[0] if 'labels' in st.session_state else '논문명'
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
def go_first():
    st.session_state.current_page = 0
    st.session_state.selected_box_id = None

def go_prev():
    st.session_state.current_page = max(0, st.session_state.current_page - 1)
    st.session_state.selected_box_id = None

def go_next(total_pages):
    st.session_state.current_page = min(total_pages - 1, st.session_state.current_page + 1)
    st.session_state.selected_box_id = None

def go_last(total_pages):
    st.session_state.current_page = max(0, total_pages - 1)
    st.session_state.selected_box_id = None

def delete_single_item(anno_id):
    for i, a in enumerate(st.session_state.annotations):
        if a['id'] == anno_id:
            if os.path.exists(a['img_path']):
                try: os.remove(a['img_path'])
                except: pass
            st.session_state.annotations.pop(i)
            break
    st.session_state.selected_box_id = None

def update_label(aid):
    for a in st.session_state.annotations:
        if a['id'] == aid:
            a['label'] = st.session_state[f"lbl_sel_{aid}"]
            break

def set_active_label(lbl):
    st.session_state.active_label = lbl

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
# 3. 사이드바 (파일 로드 및 라벨 관리)
# ==========================================
uploaded_file = st.sidebar.file_uploader("PDF 파일을 업로드하세요", type=["pdf"])

if uploaded_file is not None:
    if st.session_state.file_name != uploaded_file.name:
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
        st.rerun()
else:
    if not st.session_state.file_bytes:
        sample_path = "sample.pdf"
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                st.session_state.file_bytes = f.read()
            st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
            st.session_state.file_name = "sample.pdf"

if st.session_state.file_bytes:
    doc = st.session_state.pdf_doc
    total_pages = len(doc)

    st.sidebar.markdown("---")
    
    # 활성 라벨 인덱스 연동
    try:
        active_idx = st.session_state.labels.index(st.session_state.active_label)
    except ValueError:
        active_idx = 0
        st.session_state.active_label = st.session_state.labels[0]
        
    st.session_state.active_label = st.sidebar.radio("📌 현재 태깅 라벨 (드래그 전 선택)", options=st.session_state.labels, index=active_idx)
    
    with st.sidebar.expander("⚙️ 라벨 추가/삭제 관리", expanded=False):
        new_lbl = st.text_input("새 라벨 이름")
        if st.button("➕ 라벨 추가"):
            if new_lbl and new_lbl not in st.session_state.labels:
                st.session_state.labels.append(new_lbl)
                st.rerun()
                
        st.markdown("<br>", unsafe_allow_html=True)
        
        # [버그 수정] 단일 라벨 삭제가 완벽하게 작동하도록 상태 변경 로직 보완
        del_lbl = st.selectbox("삭제할 라벨 선택", options=st.session_state.labels, key="del_lbl_selector")
        if st.button("🗑️ 라벨 삭제"):
            if len(st.session_state.labels) > 1:
                if del_lbl in st.session_state.labels:
                    st.session_state.labels.remove(del_lbl)
                    # 리스트를 새로 복사 할당하여 Streamlit이 변경을 확실히 감지하게 함
                    st.session_state.labels = st.session_state.labels[:]
                
                # 삭제된 라벨이 활성 라벨이었다면 첫 번째 라벨로 변경
                if st.session_state.active_label == del_lbl:
                    st.session_state.active_label = st.session_state.labels[0]
                
                # 기존에 해당 라벨로 태깅된 데이터 일괄 미지정 처리
                for a in st.session_state.annotations:
                    if a.get('label') == del_lbl:
                        a['label'] = "미지정"
                st.rerun()
            else:
                st.error("최소 1개의 라벨은 유지해야 합니다.")

    st.sidebar.markdown("---")
    autofit_enabled = st.sidebar.checkbox("✨ 정밀 오토피팅 모드", value=True)

    # ==========================================
    # 4. 메인 에디터 화면
    # ==========================================
    full_bg, pdf_w, pdf_h = get_page_image(st.session_state.file_bytes, st.session_state.current_page)
    if full_bg is None:
        st.error("PDF 페이지를 로드할 수 없습니다.")
        st.stop()

    canvas_w = 700
    canvas_h = int(canvas_w * (pdf_h / pdf_w))
    display_img = full_bg.resize((canvas_w, canvas_h), Image.LANCZOS).convert("RGBA")
    pdf_to_canvas_ratio = canvas_w / pdf_w

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
        st.write("### PDF 상호작용 구축 도구")
        
        # [수정] 단축키 연동을 위한 숨김 버튼 (JS에서 강제 숨김 처리됨)
        # 클래스명과 텍스트로 쉽게 찾을 수 있도록 "[HIDDEN]" 키워드 삽입
        for i, lbl in enumerate(st.session_state.labels):
            if i < 9:
                st.button(f"[HIDDEN]_LBL_{i+1}", key=f"btn_shortcut_lbl_{i}", on_click=set_active_label, args=(lbl,))
        esc_pressed = st.button("[HIDDEN]_ESC", key="btn_shortcut_esc")

        ctrl_cols = st.columns([1, 1, 1, 1, 5, 2])
        ctrl_cols[0].button("⏮", on_click=go_first, use_container_width=True, help="첫 페이지")
        ctrl_cols[1].button("◀", on_click=go_prev, use_container_width=True, help="이전 페이지")
        ctrl_cols[2].button("▶", on_click=go_next, args=(total_pages,), use_container_width=True, help="다음 페이지")
        ctrl_cols[3].button("⏭", on_click=go_last, args=(total_pages,), use_container_width=True, help="마지막 페이지")
        
        new_page = ctrl_cols[4].slider("페이지 이동", min_value=1, max_value=total_pages, value=st.session_state.current_page + 1, label_visibility="collapsed")
        ctrl_cols[5].markdown(f"<div style='text-align: right; padding-top: 5px;'><b>{st.session_state.current_page + 1} / {total_pages}</b></div>", unsafe_allow_html=True)
        
        if new_page - 1 != st.session_state.current_page:
            st.session_state.current_page = new_page - 1
            st.session_state.selected_box_id = None
            st.rerun()

        st.markdown("---")
        
        if tag_mode == "transform":
            btn_label = "🔄 현재: Modify 모드 (클릭하여 Drag 모드로 복귀)"
        else:
            btn_label = "🖱️ 현재: Drag 모드 (기존 박스를 클릭하면 Modify 모드)"
            
        mode_toggle_pressed = st.button(btn_label, key="btn_mode_toggle")

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
            key=f"canvas_{st.session_state.file_name}_p{st.session_state.current_page}",
        )

        # ----------------------------------------------------
        # 핵심 캔버스 상호작용
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
                                
                                if abs(n_x0 - old_r[0]) > 0.5 or abs(n_y0 - old_r[1]) > 0.5 or abs(n_x1 - old_r[2]) > 0.5 or abs(n_y1 - old_r[3]) > 0.5:
                                    page = doc.load_page(st.session_state.current_page)
                                    fit_rect = fitz.Rect(n_x0, n_y0, n_x1, n_y1)
                                    
                                    if autofit_enabled:
                                        words = page.get_text("words")
                                        matched = [fitz.Rect(wd[:4]) for wd in words if fitz.Rect(wd[:4]).intersects(fit_rect)]
                                        if matched:
                                            fit_rect = matched[0]
                                            for r in matched[1:]: fit_rect |= r

                                    anno['pdf_rect'] = [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1]
                                    
                                    if os.path.exists(anno['img_path']):
                                        try: os.remove(anno['img_path'])
                                        except: pass
                                        
                                    st.session_state.crop_counter += 1
                                    new_img_name = f"crop_{st.session_state.crop_counter:03d}.png"
                                    new_img_path = os.path.join(IMAGE_SAVE_DIR, new_img_name)
                                    page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=fit_rect).save(new_img_path)
                                    
                                    anno['img_name'] = new_img_name
                                    anno['img_path'] = new_img_path
                                    anno['text'] = clean_text(page.get_text("text", clip=fit_rect))
                                    modified = True
                
                if mode_toggle_pressed or esc_pressed:
                    st.session_state.selected_box_id = None
                    st.rerun()
                elif modified:
                    st.rerun()

            else:
                if mode_toggle_pressed or esc_pressed:
                    st.session_state.selected_box_id = None
                    st.rerun()
                
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
                                st.rerun()
                            
                        elif w >= 10 and h >= 10:
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
                                'img_name': img_name, 'img_path': img_path,
                                'label': st.session_state.active_label
                            })
                            
                            st.session_state.selected_box_id = None
                            st.rerun()

    with right_col:
        st.subheader("데이터 추출 목록")
        if st.session_state.annotations:
            anno_dict = {a['id']: a for a in st.session_state.annotations}
            valid_ids = list(anno_dict.keys())
            radio_options = ["NEW_MODE"] + valid_ids

            st.markdown("""<style>.scroll-v { max-height: 350px; overflow-y: auto; border: 2px solid #4A90E2; border-radius: 8px; padding: 5px; background: #fcfcfc; }</style>""", unsafe_allow_html=True)
            st.markdown('<div class="scroll-v">', unsafe_allow_html=True)
            
            def format_label(aid):
                if aid == "NEW_MODE":
                    return "✨ [신규 태깅 모드] 빈 공간을 드래그하세요"
                a = anno_dict[aid]
                r = a['pdf_rect']
                lbl = a.get('label', '미지정')
                coords = "[X:" + str(int(r[0])) + ", Y:" + str(int(r[1])) + "]"
                return f"[P{a['page_idx']+1}] [{lbl}] {coords} | " + a['text'][:15].replace('\n', ' ') + "..."

            current_val = st.session_state.selected_box_id if st.session_state.selected_box_id in valid_ids else "NEW_MODE"
            idx = radio_options.index(current_val)

            selected_id = st.radio("목록", options=radio_options, format_func=format_label, index=idx, label_visibility="collapsed")
            st.markdown('</div>', unsafe_allow_html=True)
            
            if selected_id != current_val:
                st.session_state.selected_box_id = None if selected_id == "NEW_MODE" else selected_id
                if selected_id != "NEW_MODE":
                    st.session_state.current_page = anno_dict[selected_id]['page_idx']
                st.rerun()

            st.markdown("---")
            if st.session_state.selected_box_id in anno_dict:
                curr_anno = anno_dict[st.session_state.selected_box_id]
                
                if os.path.exists(curr_anno['img_path']):
                    with open(curr_anno['img_path'], "rb") as img_file:
                        img_bytes = img_file.read()
                    st.image(img_bytes, use_column_width=True)
                else:
                    st.warning("이미지 파일을 찾을 수 없습니다. 다시 드래그하여 영역을 갱신해 주세요.")

                curr_lbl = curr_anno.get('label', '미지정')
                lbl_idx = st.session_state.labels.index(curr_lbl) if curr_lbl in st.session_state.labels else 0
                st.selectbox("🏷️ 라벨 변경", options=st.session_state.labels, index=lbl_idx, 
                             key=f"lbl_sel_{curr_anno['id']}", on_change=update_label, args=(curr_anno['id'],))

                curr_anno['text'] = st.text_area("📝 내용 수정", value=curr_anno['text'], height=150)

                c1, c2, c3, c4 = st.columns([1, 1, 1.5, 1.5])
                
                c1.button("🗑️ 삭제", type="primary", on_click=delete_single_item, args=(curr_anno['id'],))
                
                if c2.button("💾 저장"):
                    st.toast("저장 기능은 아직 준비 중입니다.", icon="🚧")
                
                md_text = "# 문서 추출 데이터\n\n"
                for a in st.session_state.annotations:
                    r = a['pdf_rect']
                    lbl = a.get('label', '미지정')
                    md_text += "### Page " + str(a['page_idx'] + 1) + "\n"
                    md_text += "- **라벨 (Label):** `" + lbl + "`\n"
                    md_text += "- **좌표 (BBox):** `[X: " + str(int(r[0])) + ", Y: " + str(int(r[1])) + ", W: " + str(int(r[2]-r[0])) + ", H: " + str(int(r[3]-r[1])) + "]`\n"
                    md_text += chr(96) + chr(96) + chr(96) + "text\n"
                    md_text += str(a['text']) + "\n"
                    md_text += chr(96) + chr(96) + chr(96) + "\n\n---\n"
                
                c3.download_button("📝 마크다운", data=md_text, file_name="result.md", mime="text/markdown")
                
                export_data = [{"page": a['page_idx']+1, "label": a.get('label', '미지정'), "bbox": a['pdf_rect'], "text": a['text']} for a in st.session_state.annotations]
                c4.download_button("📥 JSON 추출", data=json.dumps(export_data, ensure_ascii=False, indent=4), 
                                file_name="result.json", mime="application/json")
        else:
            st.info("왼쪽 뷰어에서 영역을 드래그하여 태깅을 시작하세요.")

# ==========================================
# 6. JavaScript 단축키 연동 및 가이드 오버레이
# ==========================================
# 자바스크립트로 주입할 가이드 오버레이 HTML 생성
shortcut_html = "<div style='text-align:center; font-size:1.2em; margin-bottom:15px; border-bottom:1px solid #555; padding-bottom:10px;'><b>⌨️ 라벨 단축키 안내 (숫자키 1~9)</b></div>"
shortcut_html += "<div style='display:grid; grid-template-columns: 40px auto; gap: 8px 15px; font-size:1.1em;'>"
for i, lbl in enumerate(st.session_state.labels):
    if i < 9:
        shortcut_html += f"<div><span style='background:#444; padding:3px 8px; border-radius:4px;'>{i+1}</span></div><div>{lbl}</div>"
shortcut_html += "</div>"

components.html(f"""
<script>
const doc = window.parent.document;
const currentMode = "{tag_mode}";

// 1. [HIDDEN] 텍스트가 포함된 버튼의 부모 요소(div)를 완벽하게 강제 숨김 처리
setInterval(() => {{
    const btns = Array.from(doc.querySelectorAll('button'));
    btns.forEach(b => {{
        if (b.innerText.includes('[HIDDEN]')) {{
            const container = b.closest('div[data-testid="stButton"]');
            if (container) container.style.display = 'none';
        }}
    }});
}}, 50);

// 2. Ctrl 오버레이 DOM 생성
let overlay = doc.getElementById('shortcut-overlay');
if (!overlay) {{
    overlay = doc.createElement('div');
    overlay.id = 'shortcut-overlay';
    overlay.style.position = 'fixed';
    overlay.style.top = '50%';
    overlay.style.left = '50%';
    overlay.style.transform = 'translate(-50%, -50%)';
    overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.85)';
    overlay.style.color = '#fff';
    overlay.style.padding = '25px 35px';
    overlay.style.borderRadius = '12px';
    overlay.style.zIndex = '9999';
    overlay.style.display = 'none';
    overlay.style.boxShadow = '0 10px 30px rgba(0,0,0,0.5)';
    overlay.style.pointerEvents = 'none';
    doc.body.appendChild(overlay);
}}
overlay.innerHTML = "{shortcut_html}";

// 3. 기존 이벤트 리스너 제거 및 신규 부착 (중복 방지)
if (doc._my_keydown_listener) {{
    doc.removeEventListener('keydown', doc._my_keydown_listener);
    doc.removeEventListener('keyup', doc._my_keyup_listener);
}}

doc._my_keydown_listener = function(e) {{
    // 텍스트 입력창에서 입력할 때는 단축키 무시
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;

    if (e.key === 'ArrowLeft') {{
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === '◀');
        if (btn) btn.click();
    }} else if (e.key === 'ArrowRight') {{
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === '▶');
        if (btn) btn.click();
    }} else if (e.key === 'Escape') {{
        const btn_toggle = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('Modify 모드') || el.innerText.includes('Drag 모드'));
        if (btn_toggle) btn_toggle.click();
        
        const btn_esc = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === '[HIDDEN]_ESC');
        if (btn_esc) btn_esc.click();
    }} else if (e.key === 'Delete' || e.key === 'Backspace') {{
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText.includes('삭제'));
        if (btn) btn.click();
    }} else if (e.key === 'Control') {{
        // Ctrl 누를 때 오버레이 표시
        if (currentMode !== 'transform') {{
            overlay.style.display = 'block';
        }}
    }} else if (['1','2','3','4','5','6','7','8','9'].includes(e.key)) {{
        // 숫자 1~9 입력 시, 해당 숨김 라벨 버튼 클릭
        const targetText = '[HIDDEN]_LBL_' + e.key;
        const btn = Array.from(doc.querySelectorAll('button')).find(el => el.innerText === targetText);
        if (btn) btn.click();
    }}
}};

doc._my_keyup_listener = function(e) {{
    if (e.key === 'Control') {{
        overlay.style.display = 'none';
    }}
}};

doc.addEventListener('keydown', doc._my_keydown_listener);
doc.addEventListener('keyup', doc._my_keyup_listener);
</script>
""", height=0)
