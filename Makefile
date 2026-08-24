.PHONY: help install test run seed-db up down logs clean

help:
	@echo "install  - srodowisko + zaleznosci backendu"
	@echo "test     - testy jednostkowe i integracyjne"
	@echo "run      - API lokalnie (uvicorn)"
	@echo "up/down  - docker compose up/down"

install:
	cd backend && python3.12 -m venv .venv && ./.venv/bin/pip install -e ".[test]"

test:
	cd backend && ./.venv/bin/python -m pytest tests/

run:
	cd backend && ./.venv/bin/uvicorn app.main:app --reload --port 8000

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

clean:
	rm -rf backend/.venv backend/airalert.db backend/**/__pycache__
