.PHONY: up down logs test-deepeval

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

test-deepeval:
	docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm --build deepeval-analysis
