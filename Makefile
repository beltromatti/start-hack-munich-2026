.PHONY: install api web test fake-inbox
install:
	cd backend && uv sync
	cd frontend && npm install
api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000
web:
	cd frontend && npm run dev
test:
	cd backend && uv run pytest -q
fake-inbox:  # 31 synthetic 5U mails into backend/data/inbox, answer key in backend/synthetic/expected.json
	cd backend && uv run python -m synthetic.build
