.PHONY: up down logs research-logs test-mock-integration test-analysis-mock test-research-mock test-transcription-mock

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

research-logs:
	docker compose logs -f --tail=200 research-service

test-analysis-mock:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-analysis-mock

test-research-mock:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-research-mock

test-transcription-mock:
	docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm test-transcription-mock

test-mock-integration:
	docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build mock-external-service research-service analysis-service
	$(MAKE) test-analysis-mock
	$(MAKE) test-research-mock
	$(MAKE) test-transcription-mock
