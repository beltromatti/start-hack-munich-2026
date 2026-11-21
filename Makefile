.PHONY: install api web test
install:
	cd backend && uv sync
	cd frontend && npm install
api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000
web:
	cd frontend && npm run dev
test:
	cd backend && uv run pytest -q
