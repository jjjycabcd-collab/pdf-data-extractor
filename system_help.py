import streamlit as st
import plotly.graph_objects as go
import os

# 1. 페이지 기본 설정 및 테마 반영
st.set_page_config(
    page_title="PDF 상호작용 어노테이션 도구 명세서",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 자체 스타일링을 위한 테일윈드 및 커스텀 CSS 주입
st.markdown("""
<style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    html, body, [data-testid="stAppViewContainer"] {
        font-family: 'Pretendard', sans-serif;
        background-color: #fafaf9;
        color: #292524;
    }
    
    /* -----------------------------------
       새로 추가된 탭(Tab) 커스텀 UI 스타일 
    ------------------------------------ */
    div[data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 2px solid #e7e5e4;
    }
    button[data-baseweb="tab"] {
        background-color: #f5f5f4 !important;
        border: 1px solid #e7e5e4 !important;
        border-bottom: none !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 10px 20px !important;
        color: #57534e !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #ffffff !important;
        border-top: 3px solid #0d9488 !important;
        border-left: 1px solid #e7e5e4 !important;
        border-right: 1px solid #e7e5e4 !important;
        color: #0d9488 !important;
        font-weight: 700 !important;
        margin-bottom: -2px !important;
    }
    div[data-testid="stTabView"] > div {
        padding-top: 1.5rem;
    }
    /* ----------------------------------- */

    .main-title {
        font-size: 2rem;
        font-weight: 800;
        color: #1c1917;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-title {
        font-size: 1.1rem;
        color: #292524;
        text-align: center;
        margin-bottom: 2rem;
        max-width: 800px;
        margin-left: auto;
        margin-right: auto;
        line-height: 1.6;
    }
    .step-box {
        background-color: #f5f5f4;
        padding: 1.5rem;
        border-radius: 0.75rem;
        border: 1px solid #e7e5e4;
        min-height: 200px;
        margin-bottom: 1.5rem;
    }
    .limit-card {
        background-color: #f5f5f4;
        padding: 1.5rem;
        border-radius: 0.75rem;
        border: 1px solid #e7e5e4;
        height: 100%;
    }
    .accent-text {
        color: #0d9488;
        font-weight: 600;
    }
    
    /* 아키텍처 다이어그램용 CSS */
    .arch-layer { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 1.5rem; margin-bottom: 0.5rem; }
    .arch-title { font-size: 1.1rem; font-weight: 700; color: #334155; margin-bottom: 1rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }
    .arch-box { background-color: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 1rem; text-align: center; box-shadow: 0 1px 2px rgba(0,0,0,0.05); height: 100%; display: flex; flex-direction: column; justify-content: center;}
    .arch-box h5 { margin: 0 0 0.5rem 0; color: #0f766e; font-weight: 700; }
    .arch-box p { font-size: 0.85rem; color: #475569; margin: 0; line-height: 1.4; }
    .arrow-down { text-align: center; font-size: 1.2rem; font-weight: bold; color: #94a3b8; margin: 0.5rem 0; }

    /* 비교표 테이블 CSS */
    .compare-table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
    .compare-table th { background-color: #f1f5f9; color: #334155; padding: 12px; border: 1px solid #cbd5e1; font-weight: 700; text-align: center; }
    .compare-table td { padding: 12px; border: 1px solid #cbd5e1; color: #475569; font-size: 0.95rem; }
    .compare-table td:first-child { font-weight: 600; text-align: center; background-color: #f8fafc; }
    .highlight-text { color: #0284c7; font-weight: 700; }
</style>
""", unsafe_allow_html=True)

# 2. 상단 헤더 및 타이틀
st.markdown('<h1 class="main-title">📄 PDF 메타데이터 추출 및 상호작용 어노테이션 에디터</h1>', unsafe_allow_html=True)
st.markdown('''
<p class="sub-title">
    본 시스템은 PDF 문서에서 핵심 메타데이터를 효율적으로 추출하고, 구조화된 학습/구축 데이터를 생성하기 위해 개발된 
    웹 기반 상호작용 도구입니다. 수작업을 최소화하고 데이터 정확도를 극대화합니다.
</p>
''', unsafe_allow_html=True)

# 상단 탭 내비게이션 구성
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚙️ 처리 절차", "🏗️ 기존 아키텍처(Python)", "🛠️ 사용 기술 및 모듈", "⚠️ 한계점 및 개선",
    "🔄 eGov(3.9) 전환 절차", "☕ Java 기반 아키텍처"
])

# -------------------------------------------------------------------------
# TAB 1: 프로그램 처리 절차
# -------------------------------------------------------------------------
with tab1:
    st.subheader("⚙️ 프로그램 처리 절차")
    st.caption("파이프라인의 각 단계를 선택하여 상세 동작 메커니즘을 확인하세요.")
    st.write("")

    workflow_data = {
        "1. 문서 업로드 및 분류": {
            "icon": "📤",
            "content": """
                - **문서 로드:** 사용자가 PDF 파일을 업로드하면 시스템 메모리에 바이트 형태로 로드하여 렌더링을 준비합니다.
                - **자료유형 설정:** 사이드바를 통해 문서의 메타데이터(자료유형)를 설정합니다.  
                  *(지침: 표준/지침 및 도서류는 **'단행본'**, 보도자료/신문/연보 등은 **'기타'**로 분류)*
                - **필터링 자동화:** 텍스트 추출 시 자동으로 배제할 필터 키워드(예: '저자소개')를 설정하여 정제(Cleaning) 과정을 자동화합니다.
            """,
            "image": "image_a19926.png"
        },
        "2. 영역 지정 및 스캔": {
            "icon": "🔍",
            "content": """
                - **수동 지정:** 캔버스 UI를 통해 추출 영역(Bounding Box)을 드래그합니다. '오토피팅' 모드가 작동하여 대략적으로 그린 박스를 실제 텍스트 좌표에 맞춰 정밀 보정합니다.
                - **자동 스캔 (Quick-Find):** '참고문헌' 등 특정 키워드 입력 시 문서 전체를 스캔하여 해당 키워드가 포함된 좌표를 자동 박싱하고 일괄 추출합니다.
            """,
            "image": "image_a19944.png"
        },
        "3. 하이브리드 추출": {
            "icon": "⚙️",
            "content": """
                지정된 좌표를 바탕으로 두 가지 추출 방식이 **동시에 진행**됩니다.
                - **기본 추출 (PyMuPDF):** PDF 내부에 포함된 텍스트 레이어를 읽어 들여 빠르고 정확하게 텍스트를 추출합니다.
                - **이미지 인식 (OCR):** 지정 영역을 고해상도 이미지로 크롭 후 Tesseract 엔진으로 변환합니다. (스캔본 및 손상 문서 대비)
            """,
            "image": "image_a19967.png"
        },
        "4. 데이터 교정 및 그룹핑": {
            "icon": "📝",
            "content": """
                - **Diff 시각화 교정:** 기본 추출 텍스트와 OCR 텍스트 간 차이점을 HTML Diff로 시각화합니다. 색칠된 텍스트 클릭 시 최종 교정 창 커서 위치에 바로 삽입됩니다.
                - **단락 그룹핑:** 다단(2단, 3단) 논문이나 페이지를 넘나드는 문단 처리를 위해 '그룹 묶기(G1, G2 등)' 기능으로 논리적 연관 데이터를 병합합니다.
            """,
            "image": "image_a199a5.png"
        },
        "5. 구조화 및 내보내기": {
            "icon": "📊",
            "content": """
                - **데이터 취합:** 최종 교정된 텍스트, 좌표(Bbox), 라벨링 정보, 그룹 ID 등을 구조적으로 취합합니다.
                - **Export:** 취합된 데이터를 바탕으로 Markdown 형식 보고서나 기계학습 파이프라인에 바로 활용 가능한 JSON 스키마 파일로 즉시 다운로드합니다.
            """,
            "image": "image_a19c8a.png"
        }
    }

    step_cols = st.columns([1, 2])
    with step_cols[0]:
        selected_step = st.radio(
            "파이프라인 단계 선택",
            options=list(workflow_data.keys()),
            label_visibility="collapsed"
        )

    with step_cols[1]:
        step_info = workflow_data[selected_step]
        st.markdown(f'### {step_info["icon"]} {selected_step}')
        st.markdown(f'<div class="step-box">{step_info["content"]}</div>', unsafe_allow_html=True)
        
        img_path = step_info["image"]
        if os.path.exists(img_path):
            st.image(img_path, use_column_width=True, caption=f"{selected_step} 예시 화면")
        else:
            st.warning(f"⚠️ 이미지를 찾을 수 없습니다: `{img_path}`\n\n깃허브 리포지토리에 파일이 업로드되어 있는지 확인해주세요.")


# -------------------------------------------------------------------------
# TAB 2: 시스템 아키텍처 구성도 (Python)
# -------------------------------------------------------------------------
with tab2:
    st.subheader("🏗️ 기존 시스템 아키텍처 구성도 (Python 기반)")
    st.caption("현재 운영 중인 Streamlit 기반 클라이언트 프론트엔드 및 파이프라인의 제어 흐름입니다.")
    st.write("")

    st.markdown('<div class="arch-layer">', unsafe_allow_html=True)
    st.markdown('<div class="arch-title">🌐 Client Layer (Presentation)</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: 
        st.markdown('<div class="arch-box"><h5>🖥️ Web Browser UI</h5><p>- Streamlit & Drawable Canvas<br>- 사용자 Bbox 드래그 및 파라미터 제어</p></div>', unsafe_allow_html=True)
    with c2: 
        st.markdown('<div class="arch-box"><h5>⚡ DOM Injector</h5><p>- Custom JS 동적 주입<br>- 단축키 이벤트 & 교정 커서 동기화</p></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="arrow-down">⬇️ WebSockets / HTTP Request</div>', unsafe_allow_html=True)

    st.markdown('<div class="arch-layer">', unsafe_allow_html=True)
    st.markdown('<div class="arch-title">🧠 Core Application Layer (Business Logic)</div>', unsafe_allow_html=True)
    c3, c4, c5 = st.columns(3)
    with c3: 
        st.markdown('<div class="arch-box"><h5>📄 Native Extractor</h5><p>- PyMuPDF (fitz) 엔진<br>- 텍스트 좌표 맵핑 & 오토피팅 제어</p></div>', unsafe_allow_html=True)
    with c4: 
        st.markdown('<div class="arch-box"><h5>👁️ OCR Processing</h5><p>- PyTesseract / PIL 모듈<br>- 다국어 인식 & 이미지 전처리</p></div>', unsafe_allow_html=True)
    with c5: 
        st.markdown('<div class="arch-box"><h5>🔄 State & Data Controller</h5><p>- Streamlit Session State 관리<br>- 데이터 병합 및 그룹핑 연산</p></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="arrow-down">⬇️ Data Parsing & Serialization</div>', unsafe_allow_html=True)

    st.markdown('<div class="arch-layer">', unsafe_allow_html=True)
    st.markdown('<div class="arch-title">💾 Infrastructure & Storage Layer</div>', unsafe_allow_html=True)
    c6, c7 = st.columns(2)
    with c6: 
        st.markdown('<div class="arch-box"><h5>☁️ Cloud Environment</h5><p>- Python 3.11 Runtime<br>- Host OS Binary (Tesseract-OCR)</p></div>', unsafe_allow_html=True)
    with c7: 
        st.markdown('<div class="arch-box"><h5>📦 Output Artifacts</h5><p>- 구축 메타데이터 JSON Schema<br>- Markdown 구조화 문서 생성</p></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# -------------------------------------------------------------------------
# TAB 3: 사용 기술 및 모듈 분석
# -------------------------------------------------------------------------
with tab3:
    st.subheader("🛠️ 기존 시스템 사용 기술 및 모듈 분석")
    st.caption("현재 구성된 기술 스택의 핵심 역할과 성능 지표를 확인하세요.")
    st.write("")

    tech_data = {
        "Streamlit & Canvas": {
            "desc": "파이썬 기반의 직관적인 웹 UI 구현 및 상태(session_state) 관리. streamlit-drawable-canvas를 통해 PDF 이미지 위에서 사용자가 직접 Bbox를 그리는 핵심 프론트엔드 역할을 수행합니다.",
            "metrics": [90, 40, 85, 95, 60]
        },
        "PyMuPDF (fitz)": {
            "desc": "PDF 페이지 로드, 고해상도 이미지 변환, 좌표 기반 Native 텍스트 추출 및 정밀 단어 좌표 탐색을 담당하는 초고속 PDF 제어 엔진입니다.",
            "metrics": [95, 95, 80, 50, 40]
        },
        "PyTesseract & PIL": {
            "desc": "이미지 픽셀 기반 텍스트 인식(OCR) 엔진. Pillow로 리사이징 및 흑백화 전처리 후 다국어 혼용 문서의 텍스트를 추출하여 Native 추출의 맹점을 보완합니다.",
            "metrics": [40, 70, 95, 40, 90]
        },
        "JavaScript & difflib": {
            "desc": "JS Injection을 통한 DOM 동적 제어(단축키, 커서 삽입) 기능 구현. 파이썬 difflib를 활용해 Native vs OCR 텍스트 유사도를 분석하여 교정 편의성을 극대화합니다.",
            "metrics": [85, 90, 75, 85, 30]
        }
    }

    tech_cols = st.columns([1, 1])
    
    with tech_cols[0]:
        selected_tech = st.selectbox("분석할 기술 모듈 선택", options=list(tech_data.keys()))
        st.write("")
        st.markdown(f"#### {selected_tech}")
        st.info(tech_data[selected_tech]["desc"])

    with tech_cols[1]:
        categories = ['처리 속도 (Speed)', '정밀도 (Accuracy)', '범용성 (Versatility)', '상호작용성 (Interactive)', '리소스 소모 (Resource)']
        
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=tech_data[selected_tech]["metrics"],
            theta=categories,
            fill='toself',
            name='성능 지표',
            fillcolor='rgba(13, 148, 136, 0.2)',
            line=dict(color='rgba(13, 148, 136, 1)', width=2),
            marker=dict(color='rgba(13, 148, 136, 1)')
        ))

        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=False, range=[0, 100]),
                angularaxis=dict(tickfont=dict(family="Pretendard", size=12))
            ),
            showlegend=False,
            margin=dict(l=40, r=40, t=20, b=20),
            height=300,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig, use_container_width=True)


# -------------------------------------------------------------------------
# TAB 4: 한계점 및 개선 방안
# -------------------------------------------------------------------------
with tab4:
    st.subheader("⚠️ 프로그램 한계점 및 개선 방안")
    st.caption("시스템 최적화 과정에서 발생한 아키텍처 한계와 이를 극복하기 위한 향후 대안입니다.")
    st.write("")

    limit_cols1 = st.columns(2)
    limit_cols2 = st.columns(2)

    with limit_cols1[0]:
        st.markdown('''
        <div class="limit-card">
            <h4>💾 메모리 의존성 (OOM 리스크)</h4>
            <p style="font-size:0.9rem; margin-top:0.5rem;"><b>현상:</b> 업로드된 PDF 파일 전체를 서버 메모리(session_state)에 로드하여 처리합니다.</p>
            <p style="font-size:0.9rem;"><b>한계:</b> 500페이지 이상 대용량 파일 또는 다중 접속 시 Out Of Memory 에러 발생 가능성이 존재합니다.</p>
            <hr style="margin: 0.8rem 0; border:0; border-top:1px solid #e7e5e4;">
            <p style="font-size:0.9rem;" class="accent-text">💡 개선대안: 파일 시스템/DB를 활용한 페이징 처리 및 eGov 기반 세션 관리로 전환</p>
        </div>
        ''', unsafe_allow_html=True)

    with limit_cols1[1]:
        st.markdown('''
        <div class="limit-card">
            <h4>⚡ 단일 스레드 병목 현상</h4>
            <p style="font-size:0.9rem; margin-top:0.5rem;"><b>현상:</b> OCR 및 PDF 파싱이 Streamlit의 단일 프로세스 사이클에서 동기적으로 실행됩니다.</p>
            <p style="font-size:0.9rem;"><b>한계:</b> 다중 Bbox 처리 시 응답 지연(UI 프리징)이 발생할 수 있습니다.</p>
            <hr style="margin: 0.8rem 0; border:0; border-top:1px solid #e7e5e4;">
            <p style="font-size:0.9rem;" class="accent-text">💡 개선대안: Java Spring 비동기 처리(@Async) 또는 클라우드 메시지 큐(MQ) 도입</p>
        </div>
        ''', unsafe_allow_html=True)

    st.write("")
    
    with limit_cols2[0]:
        st.markdown('''
        <div class="limit-card">
            <h4>🎯 오토피팅(Auto-fitting) 오작동</h4>
            <p style="font-size:0.9rem; margin-top:0.5rem;"><b>현상:</b> 텍스트 레이어 좌표를 참조하여 박스를 정밀하게 자동 조절합니다.</p>
            <p style="font-size:0.9rem;"><b>한계:</b> 텍스트 레이어가 물리적 이미지와 틀어진 불량 PDF나 복잡한 배경 이미지의 경우 엉뚱한 위치로 피팅될 수 있습니다.</p>
            <hr style="margin: 0.8rem 0; border:0; border-top:1px solid #e7e5e4;">
            <p style="font-size:0.9rem;" class="accent-text">💡 개선대안: 레이어 불일치 임계값 감지 로직 추가 및 오토피팅 수동 강제 오버라이드 기능</p>
        </div>
        ''', unsafe_allow_html=True)

    with limit_cols2[1]:
        st.markdown('''
        <div class="limit-card">
            <h4>🔄 단방향 저장 구조 (영속성 부재)</h4>
            <p style="font-size:0.9rem; margin-top:0.5rem;"><b>현상:</b> 추출된 데이터는 브라우저 세션 유지 중에만 존재하며 최종 JSON 다운로드로 마무리됩니다.</p>
            <p style="font-size:0.9rem;"><b>한계:</b> 새로고침이나 예기치 않은 종료 시 작업 내역이 모두 소실됩니다.</p>
            <hr style="margin: 0.8rem 0; border:0; border-top:1px solid #e7e5e4;">
            <p style="font-size:0.9rem;" class="accent-text">💡 개선대안: eGovFrame + RDBMS 연동을 통한 실시간 데이터베이스 영구 저장</p>
        </div>
        ''', unsafe_allow_html=True)


# -------------------------------------------------------------------------
# TAB 5: eGov(3.9) 전환 절차
# -------------------------------------------------------------------------
with tab5:
    st.subheader("🔄 전자정부표준프레임워크(3.9) 변환 방법 및 절차")
    st.caption("동일한 기능과 UI를 유지하면서 Java/Spring 기반의 엔터프라이즈 환경으로 마이그레이션하기 위한 전략입니다.")
    st.write("")

    egov_steps = {
        "1. 아키텍처 및 라이브러리 맵핑 (Analysis)": {
            "icon": "📝",
            "content": """
                - **Python -> Java 대체 모듈 선정:**
                  - `PyMuPDF` ➔ 오픈소스(`Apache PDFBox`, `iText`) 또는 상용 솔루션(`Aspose.PDF for Java`) 적용 (엔터프라이즈 환경의 정밀한 렌더링 및 좌표 매핑)
                  - `PyTesseract` ➔ `Tess4J` (Tesseract JNA 래퍼 활용)
                  - `Streamlit UI` ➔ `JSP` + `HTML5 Canvas (Fabric.js)`
                - **데이터베이스 설계:** 현재 인메모리(Session State)로 관리되는 메타데이터를 RDBMS(Oracle 등) 및 MyBatis VO 모델로 정규화 설계합니다.
            """
        },
        "2. 프론트엔드 UI 재구축 (Frontend)": {
            "icon": "🎨",
            "content": """
                - **Canvas 인터랙션 구현:** `Fabric.js`나 `Konva.js`와 같은 JavaScript 캔버스 라이브러리를 사용하여 JSP 화면 내에 PDF 이미지를 띄우고, Bbox 드래그 앤 드롭 기능을 개발합니다.
                - **비동기 통신(Ajax) 연결:** 사용자가 박스를 그릴 때마다 해당 좌표 데이터를 Fetch API나 jQuery Ajax를 통해 Spring Controller로 비동기 전송합니다.
            """
        },
        "3. 비즈니스 로직 이관 (Backend)": {
            "icon": "⚙️",
            "content": """
                - **eGov 3.9 (Spring MVC) 구성:** Controller - Service - DAO 계층 구조에 따라 PDF 처리 및 추출 비즈니스 로직을 구현합니다.
                - **하이브리드 추출 구현:** 전달받은 박스 좌표(`X, Y, W, H`)를 기반으로 Java 라이브러리를 이용한 텍스트 추출과 `Tess4J`를 이용한 이미지 OCR 추출을 동시 수행(Multi-threading)하는 로직을 작성합니다.
            """
        },
        "4. 검증 및 시스템 연동 (Integration)": {
            "icon": "🔗",
            "content": """
                - **Diff 검증 모듈 포팅:** Python의 `difflib` 대신 Java의 `java-diff-utils` 라이브러리를 적용하여 Native/OCR 간 텍스트 비교 하이라이팅을 구현합니다.
                - **데이터 영속성 확보:** 최종 교정된 어노테이션 데이터를 JSON 형태뿐만 아니라, MyBatis를 통해 시스템 DB에 실시간 적재하여 데이터 손실을 방지합니다.
            """
        }
    }

    egov_cols = st.columns([1.2, 2.8])
    with egov_cols[0]:
        selected_egov_step = st.radio(
            "마이그레이션 단계 선택",
            options=list(egov_steps.keys()),
            key="egov_radio",
            label_visibility="collapsed"
        )

    with egov_cols[1]:
        egov_info = egov_steps[selected_egov_step]
        st.markdown(f'### {egov_info["icon"]} {selected_egov_step}')
        st.markdown(f'<div class="step-box" style="min-height: 200px;">{egov_info["content"]}</div>', unsafe_allow_html=True)
    
    st.markdown("<br><hr><br>", unsafe_allow_html=True)
    
    # AS-IS vs TO-BE 비교표
    st.markdown("#### 📊 기술 스택 전환 비교표 (AS-IS vs TO-BE)")
    st.markdown('''
    <table class="compare-table">
        <thead>
            <tr>
                <th width="15%">구분</th>
                <th width="35%">AS-IS (현재 Python 환경)</th>
                <th width="35%">TO-BE (eGov 3.9 환경)</th>
                <th width="15%">기대 효과</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>프론트엔드 UI</td>
                <td>Streamlit (Python 기반 동적 렌더링)</td>
                <td>JSP, HTML5 Canvas (Fabric.js), AJAX</td>
                <td>표준 웹 접근성 및 렌더링 최적화</td>
            </tr>
            <tr>
                <td>백엔드 프레임워크</td>
                <td>Streamlit 단일 스레드 (Session State)</td>
                <td>eGovFrame 3.9 (Spring MVC, Java)</td>
                <td>대용량 트래픽 처리 및 안정성</td>
            </tr>
            <tr>
                <td>PDF 파싱 및 추출</td>
                <td>PyMuPDF (fitz)</td>
                <td>Apache PDFBox / iText <br><span class="highlight-text">+ Aspose.PDF (고성능/유료)</span></td>
                <td>엔터프라이즈급 정밀 렌더링 및 좌표 매핑</td>
            </tr>
            <tr>
                <td>이미지 OCR 엔진</td>
                <td>PyTesseract (Python)</td>
                <td>Tess4J (Tesseract JNA 래퍼)</td>
                <td>멀티스레딩 병렬 처리 지원</td>
            </tr>
            <tr>
                <td>텍스트 교정(Diff)</td>
                <td>difflib (Python)</td>
                <td>java-diff-utils (Java)</td>
                <td>동일 수준의 시각적 알고리즘 유지</td>
            </tr>
            <tr>
                <td>데이터 및 상태 관리</td>
                <td>Session State (브라우저 종속 인메모리)</td>
                <td><span class="highlight-text">Oracle</span> + MyBatis</td>
                <td>데이터 영구 저장 및 무결성 보장</td>
            </tr>
        </tbody>
    </table>
    ''', unsafe_allow_html=True)


# -------------------------------------------------------------------------
# TAB 6: Java 기반 아키텍처
# -------------------------------------------------------------------------
with tab6:
    st.subheader("☕ eGov(3.9) 기반 아키텍처 구성도 및 사용 기술")
    st.caption("대용량 트래픽 처리와 데이터 무결성 보장을 위해 재설계된 3-Tier 기반 아키텍처 모델입니다.")
    st.write("")

    st.markdown('<div class="arch-layer">', unsafe_allow_html=True)
    st.markdown('<div class="arch-title">🌐 Presentation Layer (Client & Web)</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1: 
        st.markdown('<div class="arch-box"><h5>🖥️ JSP & HTML5 UI</h5><p>- eGov UI 표준 템플릿<br>- Bootstrap / Tailwind CSS</p></div>', unsafe_allow_html=True)
    with c2: 
        st.markdown('<div class="arch-box"><h5>🎨 Fabric.js (Canvas)</h5><p>- PDF 렌더링 및 오버레이<br>- Bbox 드로잉 & 이벤트 리스너</p></div>', unsafe_allow_html=True)
    with c3: 
        st.markdown('<div class="arch-box"><h5>⚡ REST / Ajax</h5><p>- JSON 기반 비동기 데이터 통신<br>- 좌표 및 텍스트 교환</p></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="arrow-down">⬇️ Spring DispatcherServlet</div>', unsafe_allow_html=True)

    st.markdown('<div class="arch-layer">', unsafe_allow_html=True)
    st.markdown('<div class="arch-title">🧠 Business Logic Layer (eGovFrame 3.9)</div>', unsafe_allow_html=True)
    c4, c5, c6 = st.columns(3)
    with c4: 
        st.markdown('<div class="arch-box"><h5>🎯 Spring Controller</h5><p>- Request 매핑 및 권한 검증<br>- View(JSP) 및 API 라우팅</p></div>', unsafe_allow_html=True)
    with c5: 
        st.markdown('<div class="arch-box"><h5>📄 Java PDF 엔진</h5><p>- PDFBox 또는 Aspose.PDF<br>- PDF Document 파싱 및 텍스트 추출</p></div>', unsafe_allow_html=True)
    with c6: 
        st.markdown('<div class="arch-box"><h5>👁️ Tess4J (OCR)</h5><p>- Tesseract 엔진 Java 연동<br>- 이미지 크롭 및 문자인식<br>- java-diff-utils 교정 로직</p></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="arrow-down">⬇️ MyBatis ORM</div>', unsafe_allow_html=True)

    st.markdown('<div class="arch-layer">', unsafe_allow_html=True)
    st.markdown('<div class="arch-title">💾 Data Access Layer (DBMS & Storage)</div>', unsafe_allow_html=True)
    c7, c8 = st.columns(2)
    with c7: 
        st.markdown('<div class="arch-box"><h5>🗄️ Relational DB (RDBMS)</h5><p>- Oracle<br>- 문서 메타, Bbox 좌표, 텍스트 데이터 영구 저장</p></div>', unsafe_allow_html=True)
    with c8: 
        st.markdown('<div class="arch-box"><h5>📂 File System / NAS</h5><p>- 원본 PDF 파일 저장소<br>- 추출 완료된 학습용 JSON/XML 산출물 관리</p></div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# 3. 푸터 영역
st.markdown("""
<div style="text-align:center; padding: 2rem 0; font-size:0.8rem; color:#78716c;">
    PDF Meta-Extractor Architecture Documentation © 2026
</div>
""", unsafe_allow_html=True)
