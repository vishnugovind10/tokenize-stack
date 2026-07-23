.PHONY: demo demo-failures up down test lint verify-audit

demo:
	python -m stackctl demo

demo-failures:
	python -m stackctl demo-failures

demo-sim:
	python -m stackctl demo --mode sim

demo-failures-sim:
	python -m stackctl demo-failures --mode sim

up:
	python -m stackctl up

down:
	python -m stackctl down --volumes

test:
	pytest

lint:
	ruff check .
	black --check .
	mypy services/common services/auditlog services/custody stackctl

verify-audit:
	python -m stackctl verify-audit --output .tokenize-stack-audit.jsonl
