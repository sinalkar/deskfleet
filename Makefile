.PHONY: help dev api ui test lint fmt build seed smoke up down clean

PY ?= python3
PIP ?= $(PY) -m pip

help:
	@echo "DeskFleet — make targets"
	@echo "  make install   install api + dev deps"
	@echo "  make dev       run API (uvicorn --reload) and Streamlit UI"
	@echo "  make api       run API only"
	@echo "  make ui        run Streamlit UI only"
	@echo "  make test      run pytest (no API keys needed)"
	@echo "  make lint      ruff check"
	@echo "  make fmt       ruff format"
	@echo "  make build     docker build api + ui images"
	@echo "  make seed      load sample tickets against a running API"
	@echo "  make smoke     curl /health and /resolve"
	@echo "  make up        docker compose up --build"
	@echo "  make down      docker compose down"

install:
	$(PIP) install -r requirements-dev.txt
	$(PIP) install -r apps/ui/requirements.txt

dev:
	@echo "Starting API on :8080 and UI on :8501 (Ctrl-C to stop)"
	( cd apps/api && uvicorn src.main:app --reload --host 0.0.0.0 --port 8080 ) & \
	( cd apps/ui && streamlit run app.py --server.port 8501 ) ; \
	wait

api:
	cd apps/api && uvicorn src.main:app --reload --host 0.0.0.0 --port 8080

ui:
	cd apps/ui && streamlit run app.py --server.port 8501

test:
	pytest tests/ -v

lint:
	ruff check .

fmt:
	ruff format .

build:
	docker build -t deskfleet-api apps/api
	docker build -t deskfleet-ui apps/ui

seed:
	$(PY) scripts/seed_tickets.py

smoke:
	bash scripts/smoke_test.sh

up:
	docker compose up --build

down:
	docker compose down

clean:
	rm -f *.db apps/api/*.db
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
