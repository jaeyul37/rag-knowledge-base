import streamlit as st
import os
from rag_chain import get_rag_response_with_sources, get_document_count

st.set_page_config(
    page_title="AI CHATBOT",
    page_icon="💬",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    [data-testid="stSidebar"] {display: none;}
    [data-testid="collapsedControl"] {display: none;}
    .stApp {background-color: #ffffff;}
    .main .block-container {padding-top: 1rem; padding-bottom: 1rem; max-width: 100%;}
</style>
""", unsafe_allow_html=True)

if "widget_messages" not in st.session_state:
    st.session_state.widget_messages = []

if "widget_sources" not in st.session_state:
    st.session_state.widget_sources = []


def get_api_key():
    if os.environ.get("GOOGLE_API_KEY"):
        return os.environ.get("GOOGLE_API_KEY")
    if "GOOGLE_API_KEY" in st.secrets:
        return st.secrets["GOOGLE_API_KEY"]
    return None


api_key = get_api_key()

if not api_key:
    st.error("API Key가 설정되지 않았습니다")
    st.stop()

doc_count = get_document_count(api_key)

st.markdown("### 💬 AI CHATBOT")

if doc_count == 0:
    st.info("지식 기반에 문서가 없습니다. 메인 앱에서 문서를 추가해 주세요.")
else:
    st.caption(f"📚 {doc_count}개 문서 로드됨")

for i, message in enumerate(st.session_state.widget_messages):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        if message["role"] == "assistant" and i < len(st.session_state.widget_sources):
            sources = st.session_state.widget_sources[i]
            if sources:
                with st.expander("📖 출처", expanded=False):
                    for j, source in enumerate(sources):
                        source_name = source.metadata.get("filename", source.metadata.get("source", "알 수 없음"))
                        st.caption(f"**{j+1}. {source_name}**")

if prompt := st.chat_input("질문을 입력하세요..."):
    st.session_state.widget_messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        if doc_count == 0:
            response = "먼저 지식 기반에 문서를 추가해 주세요."
            sources = []
        else:
            with st.spinner("답변 생성 중..."):
                chat_history = st.session_state.widget_messages[:-1]
                response, sources = get_rag_response_with_sources(prompt, chat_history, api_key)
        
        st.markdown(response)
        
        if sources:
            with st.expander("📖 출처", expanded=False):
                for j, source in enumerate(sources):
                    source_name = source.metadata.get("filename", source.metadata.get("source", "알 수 없음"))
                    st.caption(f"**{j+1}. {source_name}**")
    
    st.session_state.widget_messages.append({"role": "assistant", "content": response})
    st.session_state.widget_sources.append(sources)
