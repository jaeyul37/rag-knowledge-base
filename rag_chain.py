import os
import json
import time
from typing import List, Dict, Any, Generator
import psycopg2
from psycopg2.extras import execute_values
from pgvector.psycopg2 import register_vector
from google import genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage


_db_connection = None
_genai_clients = {}


def get_db_connection():
    global _db_connection
    if _db_connection is None or _db_connection.closed:
        _db_connection = psycopg2.connect(os.environ.get("DATABASE_URL"))
        register_vector(_db_connection)
    return _db_connection


def _get_genai_client(api_key: str):
    if api_key not in _genai_clients:
        _genai_clients[api_key] = genai.Client(api_key=api_key)
    return _genai_clients[api_key]


def embed_texts(texts: List[str], api_key: str, max_retries: int = 5) -> List[List[float]]:
    client = _get_genai_client(api_key)
    all_embeddings = []
    for text in texts:
        for attempt in range(max_retries):
            try:
                result = client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=text,
                    config={"output_dimensionality": 768}
                )
                all_embeddings.append(result.embeddings[0].values)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    raise Exception(f"Embedding failed after {max_retries} retries: {e}")
    return all_embeddings


def embed_query(query: str, api_key: str, max_retries: int = 5) -> List[float]:
    return embed_texts([query], api_key, max_retries)[0]


def get_llm(api_key: str) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        google_api_key=api_key,
        temperature=0.2,
        streaming=True,
        max_output_tokens=16384
    )


def add_documents_to_vectorstore(documents: List[Document], api_key: str) -> int:
    if not documents:
        return 0
    
    texts = [doc.page_content for doc in documents]
    embeddings = embed_texts(texts, api_key)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        data = []
        for doc, embedding in zip(documents, embeddings):
            data.append((
                doc.page_content,
                embedding,
                json.dumps(doc.metadata)
            ))
        
        execute_values(
            cur,
            "INSERT INTO documents (content, embedding, metadata) VALUES %s",
            data,
            template="(%s, %s::vector, %s::jsonb)"
        )
        conn.commit()
        return len(documents)
    except Exception as e:
        conn.rollback()
        raise Exception(f"Database error: {str(e)}")
    finally:
        cur.close()


KR_EN_MAP = {
    "태재대학교": "Taejae TAEJAE taejae.ac.kr",
    "태재": "Taejae TAEJAE taejae",
    "비전": "vision visions", "목표": "goal goals objective", "교육": "education educational",
    "철학": "philosophy", "인재": "talent leader", "핵심역량": "core competency",
    "학생": "student students", "캠퍼스": "campus", "글로벌": "global",
    "혁신": "innovation", "미래": "future", "학습": "learning study",
    "리더": "leader leadership", "연구": "research", "개발": "development",
    "기술": "technology", "과학": "science", "공학": "engineering",
    "경영": "management business", "경제": "economics economy",
    "사회": "society social", "문화": "culture cultural",
    "정책": "policy", "전략": "strategy strategic", "계획": "plan planning",
    "평가": "evaluation assessment", "분석": "analysis",
    "설계": "design", "구현": "implementation", "운영": "operation management",
    "관리": "management administration", "시스템": "system",
    "프로그램": "program", "프로젝트": "project",
    "데이터": "data", "정보": "information", "보안": "security",
    "네트워크": "network", "서버": "server", "클라우드": "cloud",
    "인공지능": "artificial intelligence AI", "머신러닝": "machine learning",
    "딥러닝": "deep learning", "알고리즘": "algorithm",
    "소프트웨어": "software", "하드웨어": "hardware",
    "입학": "admission enrollment", "졸업": "graduation",
    "장학금": "scholarship", "등록금": "tuition fee",
    "수업": "class course lecture", "시험": "exam examination",
    "성적": "grade score", "학점": "credit",
    "교수": "professor faculty", "직원": "staff employee",
    "규정": "regulation rule", "규칙": "rule",
    "지침": "guideline", "정관": "articles charter",
    "예산": "budget", "회계": "accounting finance",
    "계약": "contract agreement", "구매": "procurement purchase",
    "출장": "business trip travel", "여비": "travel expenses",
    "인사": "personnel HR", "복무": "service duty",
    "급여": "salary pay", "보수": "compensation remuneration",
    "채용": "recruitment hiring", "퇴직": "retirement resignation",
    "징계": "discipline disciplinary", "상벌": "reward punishment",
    "안전": "safety", "환경": "environment",
    "시설": "facility facilities", "건물": "building",
    "도서관": "library", "기숙사": "dormitory",
    "위원회": "committee commission", "회의": "meeting conference",
    "보고서": "report", "문서": "document",
    "승인": "approval", "허가": "permission permit",
    "감사": "audit inspection", "점검": "inspection check",
    "협력": "cooperation collaboration", "파트너": "partner partnership",
    "산학": "industry-academia", "산학협력": "industry-academia cooperation",
    "특허": "patent", "저작권": "copyright",
    "논문": "thesis paper", "학위": "degree",
    "커리큘럼": "curriculum", "교과": "curriculum course",
    "성과": "performance result", "목적": "purpose objective",
    "조직": "organization", "부서": "department division",
}

def expand_query(query: str) -> str:
    expanded = query
    for kr, en in KR_EN_MAP.items():
        if kr in query:
            expanded += f" {en}"
    
    return expanded


def extract_keywords(query: str) -> List[str]:
    import re
    
    stop_words = {
        '은', '는', '이', '가', '을', '를', '의', '에', '에서', '으로', '로',
        '와', '과', '도', '만', '까지', '부터', '에게', '한테', '께',
        '있다', '없다', '하다', '되다', '이다', '아니다',
        '그', '이', '저', '것', '수', '등', '및', '또는', '그리고',
        '무엇', '어떤', '어떻게', '왜', '언제', '어디',
        '좀', '더', '매우', '가장', '정말', '아주',
        '대해', '대한', '관한', '관해', '대하여', '관하여',
        '알려', '알려줘', '설명', '뭐', '뭔가', '인가', '인지',
    }
    
    suffixes = ['은', '는', '이', '가', '을', '를', '의', '에서', '에게', '으로', '에', '로', '와', '과', '도', '만', '요', '까']
    
    cleaned = re.sub(r'[?!.,;:\'"()（）「」『』\[\]{}]', ' ', query)
    
    tokens = cleaned.split()
    
    keywords = []
    for token in tokens:
        token = token.strip()
        if len(token) < 2 or token in stop_words:
            continue
        
        stripped = token
        for suffix in sorted(suffixes, key=len, reverse=True):
            if len(stripped) > len(suffix) + 1 and stripped.endswith(suffix):
                stripped = stripped[:-len(suffix)]
                break
        
        base = stripped if len(stripped) >= 2 else token
        keywords.append(base)
        if base != token:
            keywords.append(token)
        
        if base in KR_EN_MAP:
            for en_word in KR_EN_MAP[base].split():
                if len(en_word) >= 2:
                    keywords.append(en_word)
    
    return list(dict.fromkeys(keywords))


def search_similar_documents(query: str, api_key: str, k: int = 12) -> List[Document]:
    expanded_query = expand_query(query)
    query_embedding = embed_query(expanded_query, api_key)
    
    keywords = extract_keywords(query)
    
    conn = get_db_connection()
    conn.rollback()
    cur = conn.cursor()
    
    try:
        vec_str = '[' + ','.join(str(x) for x in query_embedding) + ']'
        
        if keywords:
            content_or_meta = lambda kw: f"(content ILIKE '%{kw}%' OR metadata->>'filename' ILIKE '%{kw}%' OR metadata->>'source' ILIKE '%{kw}%')"
            
            keyword_conditions = " OR ".join([content_or_meta(kw) for kw in keywords])
            
            boost_parts = []
            for kw in keywords:
                boost_parts.append(f"(CASE WHEN {content_or_meta(kw)} THEN 0.03 ELSE 0 END)")
            
            all_match_conditions = " AND ".join([content_or_meta(kw) for kw in keywords])
            boost_parts.append(f"(CASE WHEN {all_match_conditions} THEN 0.3 ELSE 0 END)")
            
            boost_expr = " + ".join(boost_parts)
            
            keyword_count_expr = " + ".join([f"(CASE WHEN {content_or_meta(kw)} THEN 1 ELSE 0 END)" for kw in keywords])
            
            cur.execute(f"""
                WITH semantic AS (
                    SELECT content, metadata, 
                           1 - (embedding <=> '{vec_str}'::vector) as base_similarity
                    FROM documents
                    ORDER BY embedding <=> '{vec_str}'::vector
                    LIMIT 50
                ),
                keyword AS (
                    SELECT content, metadata,
                           1 - (embedding <=> '{vec_str}'::vector) as base_similarity
                    FROM documents
                    WHERE {keyword_conditions}
                    ORDER BY ({keyword_count_expr}) DESC
                    LIMIT 50
                ),
                combined AS (
                    SELECT DISTINCT ON (content) content, metadata, base_similarity
                    FROM (
                        SELECT * FROM semantic
                        UNION ALL
                        SELECT * FROM keyword
                    ) t
                    ORDER BY content, base_similarity DESC
                )
                SELECT content, metadata,
                       base_similarity + {boost_expr} as final_similarity
                FROM combined
                ORDER BY final_similarity DESC
                LIMIT {k}
            """)
        else:
            cur.execute(f"""
                SELECT content, metadata, 1 - (embedding <=> '{vec_str}'::vector) as similarity
                FROM documents
                ORDER BY embedding <=> '{vec_str}'::vector
                LIMIT {k}
            """)
        
        results = cur.fetchall()
        
        documents = []
        for content, metadata, similarity in results:
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            documents.append(Document(
                page_content=content,
                metadata=metadata
            ))
        
        return documents
    except Exception as e:
        print(f"Search error: {e}")
        return []
    finally:
        cur.close()


def get_document_count(api_key: str) -> int:
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM documents")
        count = cur.fetchone()[0]
        cur.close()
        return count
    except Exception:
        return 0


def migrate_file_types():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE documents 
            SET metadata = jsonb_set(metadata, '{type}', '"file"') 
            WHERE metadata->>'type' IN ('pdf', 'docx', 'pptx', 'xlsx')
        """)
        updated = cur.rowcount
        conn.commit()
        cur.close()
        if updated > 0:
            print(f"Migrated {updated} documents to type 'file'")
    except Exception as e:
        if _db_connection:
            _db_connection.rollback()
        print(f"Migration skipped: {e}")


def clear_vectorstore(api_key: str):
    global _db_connection
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM documents")
        conn.commit()
        cur.close()
    except Exception as e:
        if _db_connection:
            _db_connection.rollback()
        raise Exception(f"Failed to clear database: {str(e)}")


def clear_vectorstore_by_type(doc_type: str):
    global _db_connection
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM documents WHERE metadata->>'type' = %s", (doc_type,))
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        return deleted
    except Exception as e:
        if _db_connection:
            _db_connection.rollback()
        raise Exception(f"Failed to clear documents by type: {str(e)}")


def get_document_counts_by_type():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT COALESCE(metadata->>'type', 'unknown') as doc_type, COUNT(*) as cnt
            FROM documents
            GROUP BY doc_type
            ORDER BY cnt DESC
        """)
        results = cur.fetchall()
        cur.close()
        return {row[0]: row[1] for row in results}
    except Exception:
        return {}


def format_docs(docs: List[Document]) -> str:
    formatted = []
    for i, doc in enumerate(docs):
        source = doc.metadata.get("filename", doc.metadata.get("source", "Unknown"))
        doc_type = doc.metadata.get("type", "unknown")
        extra_info = ""
        if doc_type == "pdf":
            extra_info = f", Page {doc.metadata.get('page', 'N/A')}"
        elif doc_type == "pptx":
            extra_info = f", Slide {doc.metadata.get('slide', 'N/A')}"
        elif doc_type == "xlsx":
            extra_info = f", Sheet: {doc.metadata.get('sheet', 'N/A')}"
        
        formatted.append(f"[Source {i+1}: {source}{extra_info}]\n{doc.page_content}")
    
    return "\n\n---\n\n".join(formatted)


def build_rag_prompt():
    system_template = """You are an expert AI research assistant with deep analytical and reasoning capabilities, similar to Google's NotebookLM.
Your task is to provide comprehensive, insightful, and well-reasoned answers based on the provided context.

## IMPORTANT: Always respond in Korean (한국어) unless the user explicitly asks for another language.

## Your Core Capabilities:
1. **Deep Reasoning & Inference**: Go beyond surface-level information. Analyze implications, draw logical conclusions, and identify underlying patterns or meanings that aren't explicitly stated.
2. **Multi-source Synthesis**: Connect information across different documents to build comprehensive understanding. Identify relationships, contradictions, and complementary information.
3. **Critical Analysis**: Evaluate the reliability, completeness, and significance of information. Note limitations, assumptions, and potential biases.
4. **Contextual Understanding**: Consider the broader context of questions and provide answers that address both explicit and implicit needs.
5. **Structured Reasoning**: Use step-by-step logical analysis when answering complex questions.

## Reasoning Process (Think Step-by-Step):
When answering complex questions, follow this process:
1. **Understand**: What is the user really asking? What information do they need?
2. **Gather**: What relevant information exists in the provided context?
3. **Analyze**: How do different pieces of information relate? What patterns emerge?
4. **Infer**: What conclusions can be logically drawn? What are the implications?
5. **Synthesize**: How can this be organized into a clear, comprehensive answer?

## Response Guidelines:
- Start with a direct answer, then provide supporting details and reasoning
- Use clear headings, bullet points, or numbered lists for complex information
- Always cite sources with specific references (e.g., [Source 1, Page 3])
- When making inferences, clearly indicate what is directly stated vs. what is inferred
- If information is incomplete, acknowledge gaps and provide the best possible answer with available data
- Suggest follow-up questions when relevant to deepen understanding
- For analytical questions, provide multiple perspectives when applicable

## Quality Standards:
- Be thorough but concise - every sentence should add value
- Prioritize accuracy over completeness - don't speculate without basis
- Acknowledge uncertainty when it exists
- Connect answers to the user's practical needs

## Context from Knowledge Base:
{context}
"""
    return ChatPromptTemplate.from_messages([
        ("system", system_template),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}")
    ])


def stream_rag_response(
    question: str, 
    chat_history: List[Dict[str, str]], 
    api_key: str
) -> Generator[str, None, tuple]:
    relevant_docs = search_similar_documents(question, api_key)
    
    if not relevant_docs:
        yield "I couldn't find any relevant information in the knowledge base. Please make sure you've uploaded some documents first."
        return [], ""
    
    context = format_docs(relevant_docs)
    
    history_messages = []
    for msg in chat_history:
        if msg["role"] == "user":
            history_messages.append(HumanMessage(content=msg["content"]))
        else:
            history_messages.append(AIMessage(content=msg["content"]))
    
    prompt = build_rag_prompt()
    llm = get_llm(api_key)
    
    chain = prompt | llm
    
    full_response = ""
    for chunk in chain.stream({
        "context": context,
        "chat_history": history_messages,
        "question": question
    }):
        if hasattr(chunk, 'content'):
            full_response += chunk.content
            yield chunk.content
    
    return relevant_docs, full_response


def get_rag_response_with_sources(
    question: str, 
    chat_history: List[Dict[str, str]], 
    api_key: str
) -> tuple:
    relevant_docs = search_similar_documents(question, api_key)
    
    if not relevant_docs:
        return "I couldn't find any relevant information in the knowledge base. Please make sure you've uploaded some documents first.", []
    
    context = format_docs(relevant_docs)
    
    history_messages = []
    for msg in chat_history:
        if msg["role"] == "user":
            history_messages.append(HumanMessage(content=msg["content"]))
        else:
            history_messages.append(AIMessage(content=msg["content"]))
    
    prompt = build_rag_prompt()
    llm = get_llm(api_key)
    
    chain = prompt | llm
    
    response = chain.invoke({
        "context": context,
        "chat_history": history_messages,
        "question": question
    })
    
    content = response.content
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)
        content = "\n".join(text_parts)
    
    return content, relevant_docs
