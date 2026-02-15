.PHONY: up down logs api-test

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

api-test:
	cd apps/api && python -m pytest
