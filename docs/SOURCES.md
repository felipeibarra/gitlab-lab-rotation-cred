# Fuentes oficiales y compatibilidad

Revisión documental: **7 de octubre de 2026**. Estas referencias fundamentan el diseño; no sustituyen una ejecución end-to-end del laboratorio en tu equipo. Los ejemplos empresariales son escenarios de entrenamiento, no hechos atribuidos a una organización.

| ID | Fuente oficial | Uso en el laboratorio |
|---|---|---|
| S1 | [Service accounts](https://docs.gitlab.com/user/profile/service_accounts/) | Identidades nativas, PAT, límites y membresías |
| S2 | [Service accounts API](https://docs.gitlab.com/api/service_accounts/) | Crear SA de grupo, listar y crear sus PAT; Free GA desde 18.11 |
| S3 | [Users API](https://docs.gitlab.com/api/users/) | Usuarios legacy y bloqueo |
| S4 | [Members API](https://docs.gitlab.com/api/members/) | Acceso directo, heredado y expiración |
| S5 | [Personal access tokens](https://docs.gitlab.com/user/profile/personal_access_tokens/) | Scopes, caducidad y diferencia entre token e identidad |
| S6 | [Personal access tokens API](https://docs.gitlab.com/api/personal_access_tokens/) | Inventario de metadata y revocación |
| S7 | [Project-level CI/CD variables API](https://docs.gitlab.com/api/project_level_variables/) | Reemplazo y preservación de metadata de variables |
| S8 | [Pipeline schedules API](https://docs.gitlab.com/api/pipeline_schedules/) | Schedule pausado y take_ownership |
| S9 | [Runner authentication token workflow](https://docs.gitlab.com/ci/runners/new_creation_workflow/) | Alta moderna del Runner, sin registration token legado |
| S10 | [Generic packages](https://docs.gitlab.com/user/packages/generic_packages/) | Publicación, descarga y validación por checksum |
| S11 | [CI/CD variables](https://docs.gitlab.com/ci/variables/) | Precedencia, variables protegidas y límites de masked |
| S12 | [Pipeline schedules](https://docs.gitlab.com/ci/pipelines/schedules/) | Diferencia entre ejecución programada y manual |
| S13 | [Install GitLab in Docker](https://docs.gitlab.com/install/docker/) | Instalación local de GitLab |
| S14 | [GitLab Runner Docker executor](https://docs.gitlab.com/runner/executors/docker/) | Aislamiento de jobs y red Docker |

## Versiones del proyecto

`.env.example` fija `gitlab/gitlab-ee:19.4.1-ee.0` y `gitlab/gitlab-runner:alpine-v19.4.0`. Se usa la imagen EE sin activar una licencia de pago. La disponibilidad de SA nativas Free desde 18.11 está documentada en S2; una instalación anterior puede requerir otra licencia o configuración y queda fuera del camino principal.

La aplicación y los jobs usan `python:3.12-slim`; el host requiere Python >=3.10. No se fijan digests, por lo que los tags de imágenes pueden cambiar: para una reproducción estricta registra los digests reales después de `docker compose pull`. No se promete compatibilidad con cualquier versión futura de GitLab.

El presupuesto de RAM/CPU/disco indicado en README es una recomendación para este lab, no una medición ni un mínimo certificado. Docker en macOS ejecuta contenedores Linux dentro de una VM. La validación de una imagen/arquitectura no equivale a probar su arranque.

## Alcance funcional

El deployment consiste en actualizar configuración de la aplicación, no reemplazar su imagen. El adaptador deployer usa la API y los roles reales de GitLab, pero **no implementa Protected Environments**. El registro de eventos local tampoco es el servicio comercial Audit Events. No se requiere una integración premium entre GitHub y GitLab: se copian archivos allowlisted por API al proyecto local.
