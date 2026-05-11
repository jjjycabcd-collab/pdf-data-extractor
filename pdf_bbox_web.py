import streamlit as st
import fitz  # PyMuPDF
import json
import os
import io
from PIL import Image, ImageDraw
from streamlit_drawable_canvas import st_canvas

# ==========================================
# 1. 페이지 설정 및 CSS (UI 가독성 최적화)
# ==========================================
st.set_page_config(layout="wide", page_title="SI 데이터 구축 엔진 - Web")

st.markdown("""
    <style>
    /* 메인 에디터 텍스트 영역 강조 */
    .stTextArea textarea {
        font-size: 16px !important;
        font-family: 'Malgun Gothic', sans-serif !important;
        line-height: 1.6 !important;
        background-color: #f9f9f9;
    }
    /* 사이드바 및 버튼 스타일 */
    .stButton>button {
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# 세션 상태 초기화 (기존 로직 유지)
if 'file_bytes' not in st.session_state:
    st.session_state.update({
        'file_bytes': None, 'pdf_doc': None, 'current_page': 0,
        'annotations': [], 'crop_counter': 0, 'selected_box_id': None,
        'clear_trigger': 0, 'canvas_state': {"version": "4.4.0", "objects": [], "trigger": 0},
        'last_canvas_sig': None, 'view_zoom': 1.5, 'file_name': ""
    })

IMAGE_SAVE_DIR = "extracted_images"
if not os.path.exists(IMAGE_SAVE_DIR):
    os.makedirs(IMAGE_SAVE_DIR)

# ==========================================
# 2. 핵심 함수 (데이터 처리)
# ==========================================
def delete_box(idx, img_path):
    if os.path.exists(img_path):
        os.remove(img_path)
    st.session_state.annotations.pop(idx)
    st.session_state.selected_box_id = None

@st.cache_data(show_spinner=False)
def get_pdf_page_image(file_bytes, page_idx, zoom):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    page = doc.load_page(page_idx)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")

def get_autofit_text_rect(page, rect, enabled):
    if not enabled: return rect
    words = page.get_text("words")
    fitted = None
    for w in words:
        w_rect = fitz.Rect(w[:4])
        if rect.intersects(w_rect):
            fitted = w_rect if fitted is None else fitted | w_rect
    return fitted if fitted else rect

def extract_content(page, rect):
    # 텍스트 추출 및 정렬
    words = page.get_text("words", clip=rect)
    text = " ".join([w[4] for w in sorted(words, key=lambda w: (w[1], w[0]))])
    
    # 고해상도 이미지 크롭 (3.0배율 고정)
    st.session_state.crop_counter += 1
    fname = f"crop_p{st.session_state.current_page+1}_{st.session_state.crop_counter:03d}.png"
    fpath = os.path.join(IMAGE_SAVE_DIR, fname)
    page.get_pixmap(matrix=fitz.Matrix(3.0, 3.0), clip=rect).save(fpath)
    return text, fname, fpath

# ==========================================
# 3. 메인 UI 레이아웃
# ==========================================
st.title("📄 SI 데이터 구축 엔진 - Web Editor")

# [사이드바] 파일 업로드 및 페이지 컨트롤
with st.sidebar:
    uploaded_file = st.file_uploader("PDF 업로드", type=["pdf"])
    if uploaded_file and st.session_state.file_name != uploaded_file.name:
        st.session_state.file_bytes = uploaded_file.read()
        st.session_state.pdf_doc = fitz.open(stream=st.session_state.file_bytes, filetype="pdf")
        st.session_state.file_name = uploaded_file.name
        st.session_state.annotations = []
        st.rerun()

    if st.session_state.pdf_doc:
        doc = st.session_state.pdf_doc
        total_p = len(doc)
        st.write(f"**페이지: {st.session_state.current_page + 1} / {total_p}**")
        c1, c2 = st.columns(2)
        if c1.button("◀ 이전", use_container_width=True) and st.session_state.current_page > 0:
            st.session_state.current_page -= 1
            st.rerun()
        if c2.button("다음 ▶", use_container_width=True) and st.session_state.current_page < total_p - 1:
            st.session_state.current_page += 1
            st.rerun()
        
        st.divider()
        autofit = st.checkbox("✨ 정밀 오토피팅", value=True)
        zoom_val = st.slider("🔍 뷰어 확대", 1.0, 2.5, st.session_state.view_zoom, 0.1)
        st.session_state.view_zoom = zoom_val

# 메인 편집 영역 분할
if st.session_state.pdf_doc:
    left_col, right_col = st.columns([6, 4])

    # --- 좌측: PDF 뷰어 ---
    with left_col:
        st.subheader("PDF Viewer")
        bg_img = get_pdf_page_image(st.session_state.file_bytes, st.session_state.current_page, st.session_state.view_zoom)
        
        # 기존 박스 오버레이 그리기
        overlay = Image.new("RGBA", bg_img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        for anno in st.session_state.annotations:
            if anno['page_idx'] == st.session_state.current_page:
                r = [c * st.session_state.view_zoom for c in anno['pdf_rect']]
                is_sel = st.session_state.selected_box_id == anno['id']
                color = (255, 0, 0) if is_sel else (0, 0, 255)
                draw.rectangle(r, outline=color + (255,), width=3 if is_sel else 2)
                draw.rectangle(r, fill=color + (40 if is_sel else 20,))
        
        canvas_result = st_canvas(
            background_image=Image.alpha_composite(bg_img, overlay),
            fill_color="rgba(0, 0, 255, 0.1)", stroke_width=2, stroke_color="rgba(0, 0, 255, 0.8)",
            update_streamlit=True, height=bg_img.height, width=bg_img.width,
            drawing_mode="rect", key=f"canvas_p{st.session_state.current_page}_{st.session_state.view_zoom}"
        )

        # 캔버스 이벤트 처리 (드래그 시 신규 생성)
        if canvas_result.json_data and canvas_result.json_data["objects"]:
            obj = canvas_result.json_data["objects"][-1]
            sig = f"{obj['left']}_{obj['top']}_{obj['width']}_{obj['height']}"
            if st.session_state.last_canvas_sig != sig:
                st.session_state.last_canvas_sig = sig
                if obj['width'] > 10 and obj['height'] > 10:
                    page = doc.load_page(st.session_state.current_page)
                    z = st.session_state.view_zoom
                    raw_rect = fitz.Rect(obj['left']/z, obj['top']/z, (obj['left']+obj['width'])/z, (obj['top']+obj['height'])/z)
                    fit_rect = get_autofit_text_rect(page, raw_rect, autofit)
                    txt, iname, ipath = extract_content(page, fit_rect)
                    
                    new_id = f"id_{st.session_state.crop_counter}"
                    st.session_state.annotations.append({
                        'id': new_id, 'page_idx': st.session_state.current_page,
                        'pdf_rect': [fit_rect.x0, fit_rect.y0, fit_rect.x1, fit_rect.y1],
                        'text': txt, 'img_name': iname, 'img_path': ipath
                    })
                    st.session_state.selected_box_id = new_id
                    st.rerun()

    # --- 우측: 데이터 목록 및 대형 편집기 ---
    with right_col:
        st.subheader("Data Editor")
        
        if st.session_state.annotations:
            # 1. 추출 목록 (selectbox로 공간 절약 - 5건 이상이어도 스크롤 없이 관리 가능)
            anno_options = {a['id']: a for a in st.session_state.annotations}
            option_list = list(anno_options.keys())
            
            def get_label(aid):
                a = anno_options[aid]
                return f"📄 [P{a['page_idx']+1}] {a['text'][:30]}..."

            # 현재 선택된 항목 인덱스 계산
            curr_idx = option_list.index(st.session_state.selected_box_id) if st.session_state.selected_box_id in option_list else len(option_list)-1
            
            selected_id = st.selectbox("📦 추출 목록 선택", options=option_list, format_func=get_label, index=curr_idx)
            st.session_state.selected_box_id = selected_id
            target_anno = anno_options[selected_id]

            # 2. 대형 상세 편집기
            with st.expander("🔍 이미지 및 텍스트 상세 편집", expanded=True):
                # 이미지 크게 보기
                if os.path.exists(target_anno['img_path']):
                    st.image(target_anno['img_path'], use_container_width=True, caption="추출된 영역 이미지")
                
                # 텍스트 크게 편집 (높이 대폭 확대)
                edited_text = st.text_area("텍스트 원문 (수정 시 즉시 반영)", value=target_anno['text'], height=400)
                if edited_text != target_anno['text']:
                    target_anno['text'] = edited_text

                # 현재 항목 삭제 버튼
                if st.button("🗑️ 현재 항목 삭제", use_container_width=True):
                    idx = st.session_state.annotations.index(target_anno)
                    delete_box(idx, target_anno['img_path'])
                    st.rerun()

            st.divider()
            
            # 3. 최종 결과 내보내기
            export_json = json.dumps([{"page": a['page_idx']+1, "text": a['text']} for a in st.session_state.annotations], ensure_ascii=False, indent=4)
            st.download_button("💾 JSON 최종 결과 다운로드", data=export_json, file_name="result.json", use_container_width=True)
            
        else:
            st.info("좌측 PDF에서 영역을 드래그하여 데이터를 추출하세요.")

else:
    st.info("사이드바에서 PDF 파일을 업로드해 주세요.")
