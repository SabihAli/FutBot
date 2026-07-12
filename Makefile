# FutBot development Makefile
#
# The FastAPI backend also serves the frontend at /. Run only ONE of
# `make backend` or `make frontend` at a time (both bind to PORT).
#
#   make install   - install deps + bootstrap prerequisites
#   make backend   - run server, hot-reload on src/
#   make frontend  - run server, hot-reload on frontend/

PYTHON ?= python
PORT   ?= 8000

export PYTHONPATH := .

.PHONY: help install backend frontend

help:
	@echo "FutBot Makefile targets:"
	@echo "  make install   Install Python dependencies and bootstrap prerequisites"
	@echo "  make backend   Run API + UI at http://localhost:$(PORT) (reload src/)"
	@echo "  make frontend  Run API + UI at http://localhost:$(PORT) (reload frontend/)"
	@echo ""
	@echo "Variables: PYTHON=$(PYTHON)  PORT=$(PORT)"

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -c "import nltk; [nltk.download(r, quiet=True) for r in ('punkt', 'punkt_tab')]"
	$(PYTHON) -c "import os; os.makedirs('data', exist_ok=True)"
	@$(PYTHON) -c "import os; print('Note: create a .env file with API keys (see README).') if not os.path.exists('.env') else print('.env found')"
	@echo "Optional: install Tesseract OCR for image text extraction (e.g. choco install tesseract on Windows)"

backend: install-check
	$(PYTHON) -m uvicorn src.api:app --host 0.0.0.0 --port $(PORT) --reload --reload-dir src

frontend: install-check
	$(PYTHON) -m uvicorn src.api:app --host 0.0.0.0 --port $(PORT) --reload --reload-dir frontend

# Lightweight guard so backend/frontend fail fast with a helpful message
install-check:
	@$(PYTHON) -c "import uvicorn" || (echo "Dependencies missing. Run: make install" && exit 1)
