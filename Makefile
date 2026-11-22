.PHONY: install api live web test sim build account tunnel
install:
	cd backend && uv sync
	cd frontend && npm install
api:           # API only, no forwarder loop (safe on any laptop)
	cd backend && uv run uvicorn app.main:app --reload --port 8000
live:          # THE production forwarder on the real mailbox. ONE machine only. Restarts by itself;
	# deploy new code with: pkill -f "uvicorn app.main:app --port 8000"
	backend/live.sh

web:
	cd frontend && npm run dev
test:
	cd backend && uv run pytest -q
sim:           # real model (OpenAI direct, not scored) + fake 5U: realistic mails end to end
	cd backend && LLM_TARGET=openai DB_PATH=:memory: BID_WAIT_SECONDS=20 uv run python -m app.sim
build:         # the desk UI into frontend/dist, served by the API on :8000
	cd frontend && npm run build
account:       # a desk account (the first one closes the desk): make account USERNAME=mattia NAME="Mattia Beltrami"
	cd backend && uv run python -m app.accounts add $(USERNAME) "$(NAME)" --generate
tunnel:        # the desk on its public address through Cloudflare (deploy/tunnel.sh, docs/deploy.md)
	deploy/tunnel.sh run
