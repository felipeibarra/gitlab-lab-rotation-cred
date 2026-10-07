# Seguridad del laboratorio

## Uso autorizado y límites

Solo una instancia GitLab desechable en tu equipo. No conectes cuentas empresariales, no pegues secretos en issues y no pruebes el CLI contra una organización real. Los ejemplos de owner/ticket son simulados.

GitLab, las apps y SSH publican sus puertos en `127.0.0.1`. Dentro de Docker, los servicios usan HTTP sin TLS. El Runner necesita controlar el daemon mediante `/var/run/docker.sock`: tener acceso a ese socket equivale a control administrativo sobre ese daemon. No uses este runner para contribuciones ajenas ni ejecutes pipelines no confiables. Los jobs no reciben el socket ni `.lab`; no son contenedores privilegiados.

## Manejo de secretos

`make init` genera una contraseña local aleatoria. `bootstrap` crea PAT locales con vencimiento de 30 días y un token de autenticación del Runner. Se guardan en `.lab`, excluido por `.gitignore` y `.dockerignore`. Los archivos secretos son 0600 y `.lab` es 0700. No los publiques aunque el repositorio sea privado. `.env` también está excluido.

El CLI mantiene respaldos de variables y estado con secretos durante la ventana de rollback. No son un vault: son archivos locales para una práctica individual. El inventario exportado no contiene valores de tokens. Los errores HTTP omiten cuerpos, headers y queries; no habilites trazas de shell ni `CI_DEBUG_TRACE` mientras uses credenciales.

El PAT root orquesta exclusivamente el laboratorio; nunca se instala como variable CI/CD. Los jobs prueban los PAT de reader, publisher y deployer. Una variable masked no impide que código malicioso lea o exfiltre el secreto.

## Antes de publicar evidencias

Revisa manualmente y ejecuta `python3 scripts/check-secrets.py`. Este scanner solo busca algunos patrones conocidos: no garantiza detectar todos los secretos ni inspecciona el historial remoto. No publiques `.lab`, `.env`, dumps de variables, logs crudos ni archivos de configuración del Runner. Revoca inmediatamente cualquier token que se haya publicado; borrarlo de Git no lo invalida.

## Retiro y limpieza

Para una migración planificada puedes mantener temporalmente el PAT anterior mientras validas. Para una credencial comprometida, define revocación urgente y recuperación con el dueño: no uses automáticamente esa ventana de coexistencia.

`retire` revoca, bloquea la identidad antigua y prueba rechazo. Borrar archivos en SSD no garantiza borrado forense; revocar es lo que inutiliza la credencial. `make down` conserva datos; `make reset CONFIRM=RESET-LOCAL-LAB` elimina volúmenes y estado local. No ejecutes reset sobre evidencia pendiente de investigar.

Consulta las fuentes S1, S2, S5, S9 y S13 de [SOURCES.md](docs/SOURCES.md). Revisa parches de GitLab y Runner antes de reutilizar el laboratorio.
