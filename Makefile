.PHONY: up down logs research-logs test-integration test-analysis test-research test-transcription test-gateway

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

research-logs:
	docker compose logs -f --tail=200 research-service

test-analysis:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-analysis

test-research:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-research

test-transcription:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-transcription

test-gateway:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-gateway

test-integration:
	docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build external-service research-service analysis-service transcription-service
	$(MAKE) test-analysis
	$(MAKE) test-research
	$(MAKE) test-transcription
	$(MAKE) test-gateway
