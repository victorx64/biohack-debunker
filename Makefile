.PHONY: up down logs test-deepeval test-deepeval-strict test-integration test-integration-gateway test-integration-analysis test-integration-research test-integration-transcription

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

test-deepeval:
	docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm --build deepeval-analysis

test-deepeval-strict:
	DEEPEVAL_ENFORCE_GUARDRAILS=1 \
	DEEPEVAL_P95_LATENCY_DRIFT_PCT=$${DEEPEVAL_P95_LATENCY_DRIFT_PCT:-0} \
	DEEPEVAL_LLM_COST_DRIFT_PCT=$${DEEPEVAL_LLM_COST_DRIFT_PCT:-0} \
	docker compose -f docker-compose.yml -f docker-compose.deepeval.yml run --rm --build deepeval-analysis

test-integration-gateway:
	docker compose -f docker-compose.yml -f docker-compose.integration.yml run --rm --build itest-api-gateway

test-integration-analysis:
	docker compose -f docker-compose.yml -f docker-compose.integration.yml run --rm --build itest-analysis-service

test-integration-research:
	docker compose -f docker-compose.yml -f docker-compose.integration.yml run --rm --build itest-research-service

test-integration-transcription:
	docker compose -f docker-compose.yml -f docker-compose.integration.yml run --rm --build itest-transcription-service

test-integration: test-integration-gateway test-integration-analysis test-integration-research test-integration-transcription
