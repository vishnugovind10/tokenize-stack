.PHONY: demo demo-failures up down test lint verify-audit

demo:
	python -m stackctl demo

demo-failures:
	python -m stackctl demo-failures

up:
	docker compose up --build

down:
	docker compose down --volumes

test:
	pytest

lint:
	ruff check .
	black --check .
	mypy services/common services/auditlog services/custody stackctl

verify-audit:
	python -m stackctl demo --audit-out .tokenize-stack-audit.jsonl
	python -m services.auditlog.verifier .tokenize-stack-audit.jsonl
