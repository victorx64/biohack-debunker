up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

research-logs:
	docker compose logs -f --tail=200 research-service
