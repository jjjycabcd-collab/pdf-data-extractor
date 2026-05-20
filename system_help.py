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
       탭(Tab) 커스텀 UI 스타일 
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
    
    /* 아키텍처 다이어그램용 CSS (Flexbox 추가) */
    .arch-layer { background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 8px; padding: 1.5rem; margin-bottom: 0.5rem; }
    .arch-title { font-size: 1.1rem; font-weight: 700; color: #334155; margin-bottom: 1rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; }
    .arch-grid { display: flex; gap: 1rem; margin-top: 0.5rem; }
    .arch-grid > div { flex: 1; }
    .arch-box { background-color: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 1rem; text-align: center; box-shadow: 0 1px 2px rgba(0,0,0,0.05); height: 100%; display: flex; flex-direction: column; justify-content: center;}
    .arch-box h5 { margin: 0 0 0.5rem 0; color: #0f766e; font-weight: 700; }
    .arch-box p { font-size: 0.85rem; color: #475569; margin: 0; line-height: 1.4; }
</style>
""", unsafe_allow_html=True)
