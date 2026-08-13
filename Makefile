.DEFAULT_GOAL := help
SHELL := /bin/bash
VENV := backend/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help setup backend frontend worker dev doctor db-reset build clean test

help: ## Mostra esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Instala tudo (venv Python + node_modules) e cria o .env
	@test -f .env || cp .env.example .env
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	@echo ""
	@echo ">> Para transcrição local na GPU:"
	@echo "   $(PIP) install faster-whisper"
	@echo ""
	cd frontend && npm install
	@echo ""
	@echo "Pronto. Rode: make dev"

backend: ## Sobe só a API (porta 8000)
	cd backend && ../$(VENV)/bin/python -m uvicorn app.main:app --reload --port 8000

frontend: ## Sobe só o frontend (porta 3000)
	cd frontend && npm run dev

worker: ## Sobe um worker separado (útil para não travar a API na transcrição)
	cd backend && CLOUDSENA_WORKER_CONCURRENCY=0 ../$(VENV)/bin/python -m app.workers.runner

dev: ## Sobe API + frontend juntos
	@trap 'kill 0' EXIT; \
	(cd backend && ../$(VENV)/bin/python -m uvicorn app.main:app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

doctor: ## Verifica GPU, FFmpeg, Ollama e OMP
	@bash scripts/doctor.sh

db-reset: ## APAGA o banco e recria do zero (não toca nos seus vídeos)
	@read -p "Isso apaga transcrições e índices. Confirmar? [s/N] " ok; \
	[ "$$ok" = "s" ] && rm -rf data/database/cloudsena.db* && \
	cd backend && ../$(VENV)/bin/python -m app.db.init_db && echo "Banco recriado."

build: ## Build de produção do frontend
	cd frontend && npm run build

test: ## Checagens rápidas de sanidade
	cd backend && ../$(VENV)/bin/python -m compileall -q app && echo "backend ok"
	cd frontend && npx tsc --noEmit && echo "frontend ok"

clean: ## Remove caches e temporários
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/.next data/temp/*
