up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

research-logs:
	docker compose logs -f --tail=200 research-service

test-research-real:
	set -a && source .env && set +a && bash scripts/test_research_service_real.sh

test-research-stub:
	set -a && source .env && set +a && bash scripts/test_research_service_stub.sh
