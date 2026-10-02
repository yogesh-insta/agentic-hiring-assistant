.PHONY: test test-python test-go test-web up agents api trace

test: test-python test-go test-web

.venv/bin/pytest:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"

test-python: .venv/bin/pytest
	.venv/bin/pytest

test-go:
	cd services/api && go test ./...

test-web:
	cd apps/web && npm install && npm test

up:
	docker compose up --build

agents:
	PYTHONPATH=. .venv/bin/python -m services.agents.main

api:
	cd services/api && ENV=local AGENTS_URL=http://127.0.0.1:8090 WEB_DIR=../../apps/web go run .

trace: .venv/bin/pytest
	PYTHONPATH=. .venv/bin/python -c 'from agents.pipelines.graph import load_graph_cassette; from services.agents.hiring import Runner; brief=next(c["brief"] for c in load_graph_cassette()["cases"] if c["id"]=="barista-fitzroy"); print(Runner().confirm(brief)["artifact"]["trajectory"])'
