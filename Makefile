SHELL := /bin/bash
.PHONY: help init doctor up bootstrap start test baseline inventory status down reset
help:
	@printf '%s\n' 'init       Crea credenciales locales' 'doctor     Verifica Python, Docker, Compose y DNS' 'up         Levanta GitLab y microservicios' 'bootstrap  Espera GitLab; crea identidades, repos y runner' 'baseline   Prueba CI/CD y worker externo' 'test       Pruebas sin GitLab' 'inventory  Inventario real de permisos y PAT (sin valores)' 'status     Estado de migraciones' 'start      Reanuda TODOS los servicios ya configurados' 'down       Detiene sin borrar datos' 'reset      BORRA el lab; requiere CONFIRM=RESET-LOCAL-LAB'
init:
	./scripts/labctl init
doctor:
	./scripts/labctl doctor
up: doctor
	docker compose up -d --build gitlab catalog orders deployer
bootstrap:
	./scripts/labctl wait
	./scripts/labctl auth
	./scripts/labctl seed
	./scripts/labctl runner
	docker compose --profile ci up -d --build runner config-sync
start:
	docker compose --profile ci up -d --build
baseline:
	./scripts/labctl baseline
test:
	python3 -m unittest discover -s tests -v
inventory:
	./scripts/labctl inventory
status:
	./scripts/labctl status
down:
	docker compose --profile ci down
reset:
	./scripts/reset-lab.sh '$(CONFIRM)'
