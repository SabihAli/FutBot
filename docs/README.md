# FutBot ⚽

FutBot is an advanced AI Football Analyst powered by a multi-LLM Retrieval-Augmented Generation (RAG) pipeline. It analyzes the latest football news from major sources to provide accurate, up-to-date answers about the football world, significantly reducing hallucinations.

## Features
- **Live News Retrieval**: Syncs the latest football news for up-to-date insights.
- **Multi-LLM Pipeline**: Uses an orchestrator, generator, and judge LLM to ensure accurate responses.
- **Hallucination Resistant**: Grounded in real articles.
- **Responsive Web UI**: A beautiful frontend to interact with the bot.

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.10+ (if running locally without Docker)
- API keys (defined in `.env`)

### Installation & Execution
1. Clone the repository:
   ```bash
   git clone https://github.com/SabihAli/FutBot.git
   cd FutBot
   ```

2. Setup environment variables:
   Create a `.env` file based on your required API keys (OpenAI, etc.).

3. Run with Docker Compose:
   ```bash
   docker-compose up --build
   ```

4. Access the App:
   - Frontend: `http://localhost:8000` (or as configured)
   - API Docs: `http://localhost:8000/docs`

## Architecture
- **Frontend**: Vanilla HTML/JS/CSS with a responsive sidebar and chat interface.
- **Backend (src)**: FastAPI server handling the orchestration and generation.
- **Vector Store**: ChromaDB / BM25 for retrieval.

## Development
See `PROJECT_PLAN.md`, `football_rag_prd.md`, and [`UI_REQUIREMENTS.md`](UI_REQUIREMENTS.md) (living UI spec for Phase 8) for detailed development guidelines and architecture.
