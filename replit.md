# RAG Knowledge Base Application

## Overview
A RAG (Retrieval-Augmented Generation) application similar to Google's NotebookLM. Users can upload documents or add URLs to build a knowledge base and chat with their data using Google Gemini AI with advanced reasoning capabilities.

## Tech Stack
- **Framework**: Streamlit
- **LLM & Embeddings**: Google Gemini 3 Pro (LLM via langchain-google-genai), gemini-embedding-001 (direct genai SDK with retry, 768 dimensions)
- **Vector Database**: PostgreSQL + pgvector (Replit managed, stable)
- **Orchestration**: LangChain

## Project Structure
```
├── app.py              # Main Streamlit UI application
├── ingest.py           # Document loading and text splitting logic
├── rag_chain.py        # Vector store and LLM chain setup
├── pages/
│   └── chat_widget.py  # Embeddable chat widget for external sites
├── embed_code.html     # Sample embed code for chat widget integration
├── chroma_db/          # ChromaDB persistent storage (auto-created)
└── .streamlit/
    └── config.toml     # Streamlit server configuration
```

## Supported File Types
- PDF (.pdf)
- Word Documents (.doc, .docx)
- PowerPoint (.ppt, .pptx)
- Excel (.xls, .xlsx)
- Websites (any URL)
- YouTube videos (transcripts)

## Configuration
- **GOOGLE_API_KEY**: Required secret for Google Gemini API access. Add via Replit Secrets tab.
- Server runs on port 5000

## Running the Application
```bash
streamlit run app.py --server.port 5000
```

## Features
1. **Multi-modal Data Ingestion**: Upload files or add URLs via sidebar
2. **Vector Database**: Documents are chunked, embedded, and stored in ChromaDB
3. **Chat Interface**: Ask questions about your documents
4. **Source Attribution**: View which documents/sections answers came from
5. **Session Memory**: Chat history maintained during session
6. **Embeddable Chat Widget**: `/chat_widget` page for embedding in external websites
7. **Korean Language Support**: Default responses in Korean with advanced reasoning

## RAG Settings
- **Chunk Size**: 2,000 tokens with 400 overlap for better context preservation
- **Retrieval**: 12 chunks per query for comprehensive context
- **Temperature**: 0.2 for focused, accurate responses
- **Max Output**: 16,384 tokens for detailed responses

## Technical Notes
- ChromaDB uses `force_refresh=True` to ensure new documents are immediately searchable
- Global vectorstore cache prevents stale data issues
- Chain of Thought prompting for improved reasoning quality

## Recent Changes
- Migrated embedding model from text-embedding-004 (shutdown) to gemini-embedding-001 (Feb 2026)
- Added floating chat popup button (KakaoTalk-style) using DOM injection via st.components.v1.html
- Upgraded to Gemini 3 Pro for stronger reasoning (Feb 2026)
- Implemented hybrid search with keyword extraction and boosting
- Enhanced reasoning with step-by-step analysis prompts (Feb 2026)
- Added Korean language support in responses
- Increased chunk size (2000) and retrieval count (12) for better context
- Added embeddable chat widget with popup integration examples
- Migrated from ChromaDB to PostgreSQL + pgvector for stability
- Initial implementation of RAG application (Feb 2026)
