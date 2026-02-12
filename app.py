import streamlit as st
from datetime import date
from ingest import load_file, load_url, split_documents, crawl_website, search_google_news
from rag_chain import (
    add_documents_to_vectorstore,
    get_document_count,
    clear_vectorstore,
    clear_vectorstore_by_type,
    get_document_counts_by_type,
    get_rag_response_with_sources,
    migrate_file_types
)

st.set_page_config(
    page_title="RAG Knowledge Base",
    page_icon="📚",
    layout="wide"
)

if "migrated" not in st.session_state:
    migrate_file_types()
    st.session_state.migrated = True

import streamlit.components.v1 as components
components.html("""
<script>
(function() {
    var pdoc = window.parent.document;
    var existing = pdoc.getElementById('chat-float-container');
    if (existing) existing.remove();
    var container = pdoc.createElement('div');
    container.id = 'chat-float-container';
    container.innerHTML = '<div style="position:fixed;bottom:28px;right:28px;z-index:999999;display:flex;flex-direction:column;align-items:center;gap:8px;">' +
        '<div style="background:#1E293B;color:#fff;padding:5px 14px;border-radius:8px;font-size:12px;font-weight:700;white-space:nowrap;box-shadow:0 2px 10px rgba(0,0,0,0.3);letter-spacing:0.5px;">AI CHATBOT</div>' +
        '<button id="chat-float-btn" style="width:64px;height:64px;border-radius:50%;border:none;background:linear-gradient(135deg,#3B82F6,#2563EB);color:#fff;font-size:28px;cursor:pointer;box-shadow:0 4px 20px rgba(59,130,246,0.5);transition:transform 0.2s,box-shadow 0.2s;display:flex;align-items:center;justify-content:center;line-height:1;">&#x1F4AC;</button>' +
        '</div>';
    pdoc.body.appendChild(container);
    var btn = pdoc.getElementById('chat-float-btn');
    btn.addEventListener('mouseenter', function() {
        this.style.transform = 'scale(1.1)';
        this.style.boxShadow = '0 6px 28px rgba(59,130,246,0.65)';
    });
    btn.addEventListener('mouseleave', function() {
        this.style.transform = 'scale(1)';
        this.style.boxShadow = '0 4px 20px rgba(59,130,246,0.5)';
    });
    btn.addEventListener('click', function() {
        var w = 390, h = 620;
        var left = (screen.width - w - 40);
        var top2 = (screen.height - h - 80);
        window.parent.open(
            window.parent.location.origin + '/chat_widget',
            'AI_CHATBOT',
            'width=' + w + ',height=' + h + ',left=' + left + ',top=' + top2 + ',resizable=yes,scrollbars=yes'
        );
    });
})();
</script>
""", height=0)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "sources" not in st.session_state:
    st.session_state.sources = []


def get_api_key():
    import os
    if os.environ.get("GOOGLE_API_KEY"):
        return os.environ.get("GOOGLE_API_KEY")
    if "GOOGLE_API_KEY" in st.secrets:
        return st.secrets["GOOGLE_API_KEY"]
    return None


def main():
    st.title("📚 RAG 지식 기반")
    st.markdown("문서를 업로드하거나 URL을 추가하여 지식 기반을 구축하고, 데이터와 대화하세요!")
    
    api_key = get_api_key()
    
    if not api_key:
        st.error("⚠️ Google API Key를 찾을 수 없습니다. Replit의 Secrets 탭에 GOOGLE_API_KEY를 추가해 주세요.")
        st.info("API 키 추가 방법:\n1. Replit 왼쪽 사이드바에서 'Secrets'를 클릭하세요\n2. 키 이름을 'GOOGLE_API_KEY'로 설정하고 API 키 값을 입력하세요")
        return
    
    with st.sidebar:
        st.header("📁 데이터 수집")
        
        doc_count = get_document_count(api_key)
        st.metric("지식 기반 문서 수", doc_count)
        
        st.subheader("파일 업로드")
        uploaded_files = st.file_uploader(
            "PDF, DOCX, PPTX, XLSX 파일을 업로드하세요",
            type=["pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls"],
            accept_multiple_files=True
        )
        
        if uploaded_files:
            if st.button("파일 처리", type="primary"):
                with st.spinner("파일 처리 중..."):
                    total_chunks = 0
                    for file in uploaded_files:
                        try:
                            documents = load_file(file)
                            chunks = split_documents(documents)
                            add_documents_to_vectorstore(chunks, api_key)
                            total_chunks += len(chunks)
                            st.success(f"✅ {file.name}: {len(chunks)}개 청크 추가됨")
                        except Exception as e:
                            error_msg = str(e)
                            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                                st.error(f"❌ {file.name} API 할당량 초과. 잠시 후 다시 시도하거나 Google API 할당량을 확인하세요.")
                            elif "quota" in error_msg.lower():
                                st.error(f"❌ API 할당량 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.")
                            else:
                                st.error(f"❌ {file.name} 처리 오류: {error_msg}")
                    
                    if total_chunks > 0:
                        st.success(f"지식 기반에 {total_chunks}개 청크가 추가되었습니다!")
                        st.rerun()
        
        st.divider()
        
        st.subheader("URL 추가")
        url_input = st.text_input(
            "웹사이트 URL 또는 YouTube 링크를 입력하세요",
            placeholder="https://example.com 또는 https://youtube.com/watch?v=..."
        )
        
        is_youtube = url_input and ("youtube.com" in url_input or "youtu.be" in url_input)
        
        if not is_youtube and url_input:
            crawl_entire_site = st.checkbox("🌐 웹사이트 전체 크롤링", value=True, 
                help="이 웹사이트의 모든 페이지를 크롤링합니다 (최대 30페이지)")
            if crawl_entire_site:
                max_pages = st.slider("최대 크롤링 페이지 수", 5, 30, 15)
                use_js_rendering = st.checkbox("⚡ JavaScript 렌더링 사용", value=False,
                    help="동적 웹사이트는 켜세요. 단, 메모리를 많이 사용하여 불안정할 수 있습니다.")
            else:
                max_pages = 1
                use_js_rendering = False
        else:
            crawl_entire_site = False
            max_pages = 1
            use_js_rendering = False
        
        if url_input:
            button_text = "웹사이트 크롤링" if crawl_entire_site else "URL 처리"
            if st.button(button_text, type="primary"):
                try:
                    if crawl_entire_site and not is_youtube:
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        def update_progress(current, total, current_url):
                            progress_bar.progress(current / total)
                            status_text.text(f"크롤링 중 {current}/{total}: {current_url[:50]}...")
                        
                        mode_text = "JS 렌더링" if use_js_rendering else "HTTP"
                        status_text.text(f"웹사이트 크롤링 시작 ({mode_text} 모드)...")
                        documents = crawl_website(url_input, max_pages=max_pages, progress_callback=update_progress, use_js=use_js_rendering)
                        
                        if not documents:
                            st.error("❌ 이 웹사이트에서 콘텐츠를 찾을 수 없습니다.")
                        else:
                            status_text.text(f"{len(documents)}개 페이지 발견. 처리 중...")
                            chunks = split_documents(documents)
                            add_documents_to_vectorstore(chunks, api_key)
                            progress_bar.progress(1.0)
                            status_text.empty()
                            st.success(f"✅ {len(documents)}개 페이지 크롤링, {len(chunks)}개 청크 추가 완료!")
                            st.rerun()
                    else:
                        with st.spinner("URL에서 콘텐츠 가져오는 중..."):
                            documents = load_url(url_input, api_key=api_key)
                            chunks = split_documents(documents)
                            add_documents_to_vectorstore(chunks, api_key)
                            st.success(f"✅ URL에서 {len(chunks)}개 청크 추가 완료!")
                            st.rerun()
                except Exception as e:
                    error_msg = str(e)
                    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                        st.error("❌ API 할당량 초과. 잠시 후 다시 시도하거나 Google API 할당량을 확인하세요.")
                    elif "quota" in error_msg.lower():
                        st.error("❌ API 할당량 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.")
                    else:
                        st.error(f"❌ URL 처리 오류: {error_msg}")
        
        st.divider()
        
        st.subheader("📰 뉴스 검색")
        
        col_year, col_month = st.columns(2)
        with col_year:
            current_year = date.today().year
            news_year = st.selectbox(
                "연도",
                options=list(range(current_year, current_year - 5, -1)),
                index=0
            )
        with col_month:
            current_month = date.today().month
            news_month = st.selectbox(
                "월",
                options=list(range(1, 13)),
                index=current_month - 1,
                format_func=lambda x: f"{x}월"
            )
        
        if st.button("🔍 뉴스검색", type="primary"):
            search_month_str = f"{news_year}-{news_month:02d}"
            with st.spinner(f"{news_year}년 {news_month}월 태재대학교 뉴스 검색 중..."):
                try:
                    news_docs = search_google_news("태재대학교", search_month_str)
                    
                    if not news_docs:
                        st.warning(f"⚠️ {news_year}년 {news_month}월의 태재대학교 관련 뉴스를 찾을 수 없습니다.")
                    else:
                        chunks = split_documents(news_docs)
                        add_documents_to_vectorstore(chunks, api_key)
                        st.success(f"✅ {news_year}년 {news_month}월: {len(news_docs)}건의 뉴스 기사에서 {len(chunks)}개 청크를 저장했습니다!")
                        st.rerun()
                except Exception as e:
                    error_msg = str(e)
                    if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                        st.error("❌ API 할당량 초과. 잠시 후 다시 시도해 주세요.")
                    else:
                        st.error(f"❌ 뉴스 검색 오류: {error_msg}")
        
        st.divider()
        
        st.subheader("🗑️ 지식 기반 관리")
        
        type_counts = get_document_counts_by_type()
        type_labels = {
            "file": "📄 파일",
            "pdf": "📄 PDF",
            "docx": "📝 Word",
            "pptx": "📊 PPT",
            "xlsx": "📈 Excel",
            "web": "🌐 웹사이트",
            "website": "🌐 웹사이트",
            "youtube": "🎬 YouTube",
            "news": "📰 뉴스",
        }
        
        if type_counts:
            for doc_type, count in type_counts.items():
                label = type_labels.get(doc_type, f"📁 {doc_type}")
                col_label, col_btn = st.columns([3, 1])
                with col_label:
                    st.markdown(f"{label}: **{count}**개 청크")
                with col_btn:
                    if st.button("삭제", key=f"del_{doc_type}", type="secondary"):
                        deleted = clear_vectorstore_by_type(doc_type)
                        st.success(f"✅ {label} 데이터 {deleted}개 청크 삭제 완료!")
                        st.rerun()
        else:
            st.caption("저장된 데이터가 없습니다.")
        
        if type_counts:
            if st.button("🗑️ 전체 초기화", type="secondary"):
                clear_vectorstore(api_key)
                st.session_state.messages = []
                st.session_state.sources = []
                st.success("지식 기반이 초기화되었습니다!")
                st.rerun()
        
        if st.button("🔄 대화 기록 삭제", type="secondary"):
            st.session_state.messages = []
            st.session_state.sources = []
            st.rerun()
    
    st.header("💬 지식 기반과 대화하기")
    
    if doc_count == 0:
        st.info("👋 환영합니다! 사이드바에서 문서를 업로드하거나 URL을 추가하여 지식 기반을 구축하세요.")
    
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            
            if message["role"] == "assistant" and i < len(st.session_state.sources):
                sources = st.session_state.sources[i]
                if sources:
                    with st.expander("📖 출처 보기"):
                        for j, source in enumerate(sources):
                            source_name = source.metadata.get("filename", source.metadata.get("source", "알 수 없음"))
                            doc_type = source.metadata.get("type", "unknown")
                            extra_info = ""
                            if doc_type == "pdf":
                                extra_info = f" ({source.metadata.get('page', 'N/A')}페이지)"
                            elif doc_type == "pptx":
                                extra_info = f" ({source.metadata.get('slide', 'N/A')}번 슬라이드)"
                            elif doc_type == "xlsx":
                                extra_info = f" (시트: {source.metadata.get('sheet', 'N/A')})"
                            
                            st.markdown(f"**출처 {j+1}: {source_name}{extra_info}**")
                            st.text(source.page_content[:500] + "..." if len(source.page_content) > 500 else source.page_content)
                            st.divider()
    
    if prompt := st.chat_input("문서에 대해 질문하세요..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            if doc_count == 0:
                response = "먼저 문서를 업로드하거나 URL을 추가하여 지식 기반를 구축해 주세요."
                sources = []
            else:
                with st.spinner("답변 생성 중..."):
                    chat_history = st.session_state.messages[:-1]
                    response, sources = get_rag_response_with_sources(prompt, chat_history, api_key)
            
            st.markdown(response)
            
            if sources:
                with st.expander("📖 출처 보기"):
                    for j, source in enumerate(sources):
                        source_name = source.metadata.get("filename", source.metadata.get("source", "알 수 없음"))
                        doc_type = source.metadata.get("type", "unknown")
                        extra_info = ""
                        if doc_type == "pdf":
                            extra_info = f" ({source.metadata.get('page', 'N/A')}페이지)"
                        elif doc_type == "pptx":
                            extra_info = f" ({source.metadata.get('slide', 'N/A')}번 슬라이드)"
                        elif doc_type == "xlsx":
                            extra_info = f" (시트: {source.metadata.get('sheet', 'N/A')})"
                        
                        st.markdown(f"**출처 {j+1}: {source_name}{extra_info}**")
                        st.text(source.page_content[:500] + "..." if len(source.page_content) > 500 else source.page_content)
                        st.divider()
        
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.sources.append(sources)


if __name__ == "__main__":
    main()
