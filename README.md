# GitLab Lab · Rotación de credenciales y cuentas de servicio

Laboratorio práctico para preparar una entrevista de **GitLab Administrator / Platform Engineer — Service Account Migration**. El objetivo es demostrar una migración controlada de identidades no humanas, no solamente levantar contenedores.

**GitHub almacena este código. GitLab Self-Managed local ejecuta los pipelines y administra las identidades.** No necesitas conectar GitHub como repositorio externo premium de GitLab: `seed` y `sync-code` copian los archivos permitidos al proyecto local usando su API.

> Estado de entrega: código generado y comprobado con pruebas unitarias e integración HTTP local. El flujo completo con Docker, GitLab y Runner todavía debe ejecutarse en tu equipo. Consulta [VALIDATION.md](docs/VALIDATION.md). No se incluyen tokens reales, resultados de migraciones inventados ni experiencia empresarial ficticia.

## Qué vas a practicar

| Requerimiento del puesto | Implementación del laboratorio |
|---|---|
| Migrar cuentas una a una | Tres usuarios legacy → tres cuentas nativas de grupo, mediante la API real |
| Cambiar credenciales y mantener continuidad | PAT nuevos, variables CI/CD, proceso externo y cambio de ownership de schedule |
| Replicar permisos | Membresías directas, permisos heredados y fechas de expiración; comparación antes/después |
| Depurar automatizaciones | Fallos reproducibles de token, scopes, membresías, variable protegida y consumidor externo |
| Retirar acceso antiguo | Revocar PAT, bloquear usuario, quitar membresías, prueba negativa y pipeline posterior |
| Coordinar y documentar | Ticket, owner simulado, runbook, inventario, registro de cambio y evidencias sin secretos |

## Arquitectura resumida

```text
GitHub: código + documentación + pruebas de calidad
                        |
              seed / sync-code (API)
                        v
GitLab local ── Runner Docker ── pipeline real
  |                                 |
  |  reader  ─────> repo privado de configuración
  |  publisher ──> Generic Package Registry + checksum
  |  deployer ───> servicio deployer ──> release.json
  |                                         |
  +─ config-sync (consumidor externo)       catálogo <── pedidos
         token en archivo                     ^           |
         status + identidad                   +─ smoke ───+
```

El pipeline cambia la **configuración activa** del catálogo, publica y vuelve a descargar un paquete real, y crea una solicitud de pedido por HTTP. No reconstruye ni reemplaza la imagen Docker desde CI. El servicio `deployer` es un adaptador didáctico que consulta los permisos reales de GitLab; **no sustituye ni emula la funcionalidad comercial Protected Environments**.

## Requisitos

macOS con Docker Desktop (incluido Apple Silicon) o Linux con Docker Engine y Compose v2; Python **3.10 o superior**; Git; Make. El código Python usa exclusivamente la biblioteca estándar.

Como presupuesto inicial de este laboratorio, reserva **10–12 GB de RAM para Docker, 4 CPU y aproximadamente 35 GB libres**. Es una recomendación de dimensionamiento para la práctica, no un requisito mínimo certificado ni una medición. GitLab es el componente más pesado.

Versiones fijadas en `.env.example`: GitLab **19.4.1-ee.0**, Runner **alpine-v19.4.0** y Python **3.12-slim**. Compose no fuerza arquitectura. En Apple Silicon comprueba que los tags elegidos tengan una variante ARM64; los manifiestos de esas imágenes no pudieron consultarse desde este entorno. No se presenta una ejecución en ARM64 como validada. Revisa actualizaciones de seguridad antes de reutilizar el laboratorio en el futuro. Las fuentes y las limitaciones de comprobación están en [SOURCES.md](docs/SOURCES.md).

## 1. Clonar el repositorio

```bash
git clone --branch development https://github.com/felipeibarra/gitlab-lab-rotation-cred.git
cd gitlab-lab-rotation-cred
make test
```

No necesitas crear otro repositorio ni autenticar `gh` para levantar este laboratorio. Este repositorio de GitHub almacena código y documentación; GitLab se levanta localmente y utiliza sus propias credenciales desechables. Nunca reutilices un PAT de GitHub o de tu empresa.

## 2. Inicializar y levantar

```bash
make init

# Una sola vez, si no existe esa entrada en tu equipo:
printf '\n127.0.0.1 gitlab.lab\n' | sudo tee -a /etc/hosts

make doctor
# Verifica que los tags estén disponibles para tu arquitectura:
docker buildx imagetools inspect gitlab/gitlab-ee:19.4.1-ee.0
docker buildx imagetools inspect gitlab/gitlab-runner:alpine-v19.4.0
make up
make bootstrap
make baseline
```

`make up` inicia GitLab, catálogo, pedidos y deployer. `make bootstrap` espera readiness, crea un PAT administrativo **solo para el GitLab local**, siembra grupos/proyectos/usuarios, copia el código y configura el Runner con su authentication token. Después inicia el Runner y `config-sync`.

`bootstrap` es una operación inicial, no un comando de reinicio. Para una instalación ya configurada utiliza `make start`. Si la siembra se interrumpe, consulta el runbook: el estado se guarda por etapas y el script se detiene ante identidades existentes que no puede atribuir con seguridad.

| Interfaz | Dirección local |
|---|---|
| GitLab | `http://gitlab.lab:8929` |
| Catálogo | `http://127.0.0.1:18081/products` |
| Pedidos | `http://127.0.0.1:8082/health` |
| Despliegue actual | `http://127.0.0.1:8083/release` |

El puerto del catálogo es `18081` para evitar conflictos comunes en `8081`. Si ese puerto también está ocupado, define `CATALOG_PORT` en `.env`. También puedes configurar `ORDERS_PORT` y `DEPLOYER_PORT` (por defecto `8082` y `8083`).

Usuario UI: `root`. Su contraseña está en el archivo privado local `.lab/root_password`. Ábrelo únicamente en tu equipo. Los scripts no imprimen esta contraseña ni los PAT.

## 3. Primera migración: reader

```bash
./scripts/labctl inventory
./scripts/labctl prepare reader
./scripts/labctl probe reader --side native

./scripts/labctl cutover reader \
  --ticket LAB-001 \
  --owner equipo-catalogo-simulado

./scripts/labctl validate reader
./scripts/labctl retire reader --confirm reader
./scripts/labctl status
```

La migración exitosa termina en `retired`, no en `prepared` ni en `switched`. `validate` usa los PAT de las automatizaciones en los jobs; el PAT administrativo solo orquesta el laboratorio. `retire` revalida antes de revocar y exige comprobar que el PAT anterior ya no autentica. Luego ejecuta un pipeline nuevo y elimina las copias locales del secreto anterior.

Repite la secuencia para `publisher` y `deployer`, **una identidad por vez**, con `LAB-002` y `LAB-003`. En `publisher` se replica un permiso heredado del subgrupo `artifacts` y se transfiere la propiedad del schedule. Los schedules se crean pausados para impedir disparos inesperados durante la práctica.

### Rollback antes del retiro

```bash
# Solo después de cutover y antes de retire:
./scripts/labctl rollback reader
```

Restaura variables y consumidor externo, comprueba la operación legacy y revoca el PAT nuevo. No intenta “desrevocar” una credencial. Después de comenzar `retire`, una incidencia exige recuperación hacia adelante; no reutilices el secreto antiguo.

## 4. Probar fallos deliberados

Antes de inyectar un fallo, espera que no haya pipelines en curso.

```bash
./scripts/labctl fault wrong-scope --role publisher
./scripts/labctl baseline       # Debe fallar: autenticación no equivale a autorización.
./scripts/labctl repair
./scripts/labctl baseline       # Debe volver a pasar.
```

Otros casos implementados: `invalid-token`, `missing-membership`, `protected-variable` y `stale-worker` (este último solo para `reader`). `repair` revierte únicamente la inyección registrada. La guía [04-exercises.md](docs/04-exercises.md) contiene diez ejercicios y sus evidencias de aprobación.

## Comandos operativos

```bash
make test                     # Sin GitLab ni Docker: pruebas unitarias y HTTP local.
make status
make inventory                # No imprime los valores de PAT ni variables.
docker compose --profile ci ps
docker compose logs --tail=80 config-sync
./scripts/labctl sync-code     # Después de editar código; invalida la baseline previa.
make baseline
make down                     # Conserva datos y credenciales locales.
make start                    # Reanuda todo después de down.
```

Para borrar exclusivamente este laboratorio, después de guardar evidencia sanitizada:

```bash
make reset CONFIRM=RESET-LOCAL-LAB
```

Ese último comando **elimina volúmenes de GitLab y `.lab`**. No lo ejecutes para solucionar un fallo sin investigar: destruye la evidencia. No elimina el repositorio de GitHub.

## Evidencia y límites

Los resultados reales se generan en `.lab/reports/` y los eventos del operador en `.lab/events.jsonl`. Todo `.lab/` está excluido de Git. Copia solo evidencia revisada a `evidence/`: IDs, estados, errores redactados, diffs de permisos y explicaciones. No copies tokens, archivos de Runner, respaldos de variables ni el estado privado completo.

El inventario automático se limita a los cuatro proyectos y dos grupos sembrados. No pretende descubrir todas las dependencias de una empresa. SSH keys, deploy keys, deploy tokens, webhooks, SAML/LDAP, Vault, runners distribuidos y políticas premium requieren ampliaciones específicas; revisa el análisis del requerimiento. El scanner incluido es una barrera básica, no una garantía de ausencia de secretos.

**Seguridad:** HTTP y un Runner con acceso al Docker socket son concesiones exclusivamente locales. Los puertos se publican en loopback. No expongas la red, no uses secretos empresariales y no ejecutes pipelines ajenos. Consulta [SECURITY.md](SECURITY.md).

## Ruta de lectura

[Análisis del puesto](docs/01-requirement-analysis.md) · [Arquitectura](docs/02-architecture.md) · [Runbook](docs/03-runbook.md) · [Ejercicios](docs/04-exercises.md) · [Diagnóstico](docs/05-troubleshooting.md) · [Preparación de entrevista](docs/06-interview.md) · [Fuentes oficiales](docs/SOURCES.md).
