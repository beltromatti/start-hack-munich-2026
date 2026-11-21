.PHONY: install api live web test sim fake-inbox
install:
	cd backend && uv sync
	cd frontend && npm install
api:           # API only, no forwarder loop (safe on any laptop)
	cd backend && uv run uvicorn app.main:app --reload --port 8000
live:          # THE production forwarder on the real mailbox. ONE machine only. Restarts by itself;
	# deploy new code with: pkill -f "bin/uvicorn app.main"
	backend/live.sh

web:
	cd frontend && npm run dev
test:
	cd backend && uv run pytest -q
sim:           # real model (OpenAI direct, not scored) + fake 5U: realistic mails end to end
	cd backend && LLM_TARGET=openai DB_PATH=:memory: BID_WAIT_SECONDS=20 uv run python -m app.sim
fake-inbox:  # 31 synthetic 5U mails into backend/data/inbox, answer key in backend/synthetic/expected.json
	cd backend && uv run python -m synthetic.build
