.PHONY: install api live web test sim
install:
	cd backend && uv sync
	cd frontend && npm install
api:           # API only, no forwarder loop (safe on any laptop)
	cd backend && uv run uvicorn app.main:app --reload --port 8000
live:          # THE production forwarder: polls the real mailbox and replies. Run on ONE machine only.
	# restarts by itself: a crash, or `pkill -f "uvicorn app.main"` to deploy new code, brings it back in 2 s
	cd backend && while true; do WORKER=1 uv run uvicorn app.main:app --port 8000; echo "restarting"; sleep 2; done
web:
	cd frontend && npm run dev
test:
	cd backend && uv run pytest -q
sim:           # real model (OpenAI direct, not scored) + fake 5U: realistic mails end to end
	cd backend && LLM_TARGET=openai DB_PATH=:memory: BID_WAIT_SECONDS=20 uv run python -m app.sim
