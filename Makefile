up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

research-logs:
	docker compose logs -f --tail=200 research-service

test-analysis-real:
	docker compose run --rm test-analysis-real

test-analysis-stub:
	docker compose run --rm test-analysis-stub

test-research-real:
	docker compose run --rm test-research-real

test-research-stub:
	docker compose run --rm test-research-stub
