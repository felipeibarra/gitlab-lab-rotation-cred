# 05 · Diagnóstico sin exponer secretos

Usa siempre esta secuencia: **conectividad → identidad → scope → membresía efectiva → política/contexto del job → operación real → consumidor externo**. Cambiar a un token root para que “pase” ocultaría la causa y anularía la prueba.

| Síntoma | Hipótesis y comprobación | Corrección controlada |
|---|---|---|
| Host gitlab.lab no resuelve | `make doctor`; entrada host y alias Docker | Corregir DNS local, no rotar credenciales |
| GitLab no responde | `docker compose ps`; logs; RAM/disco y readiness | Corregir arranque; conservar estado |
| `Bind ... :8081 failed: port is already allocated` | Otro proceso o contenedor ocupa el puerto local del catálogo | El puerto por defecto es `18081`; usa `CATALOG_PORT` en `.env` para elegir otro puerto libre y vuelve a ejecutar `docker compose up -d --build gitlab catalog orders deployer` |
| No matching manifest | Inspeccionar tag/arquitectura con `docker buildx imagetools inspect` | Usar tag verificado, no imágenes de terceros al azar |
| HTTP 401 | Token ausente, inválido, revocado o usuario bloqueado | Verificar variable/identidad sin imprimir valor |
| HTTP 403 | Scope, rol o política insuficiente | Identificar operación y mínimo permiso necesario |
| HTTP 404 en recurso privado | ID/ruta equivocados o recurso no visible | Comprobar existencia como admin y acceso con la identidad objetivo |
| Pipeline pending | Runner offline, tags distintos, protegido o no registrado | Revisar Runner y tag `migration-lab`; no modificar PAT de automatización |
| Clone falla antes del script | URL, DNS, Runner/job token, acceso del proyecto | No atribuirlo al reader de lectura adicional |
| Variable “vacía” | Protected/contexto, environment scope, precedencia | Comparar metadata y contexto del pipeline |
| /user funciona pero publish falla | Token read_user o falta Developer en paquetes | Probar la operación concreta y revisar scope/rol |
| Pipeline verde pero baseline falla | `config-sync` desactualizado o sin acceso | Revisar status reciente y user_id del worker |
| Permission denied en /runtime | UID/GID de build diferente al del host | Revisar `.env`, reconstruir imagen, evitar chmod 777 |
| native API responde 403/404 | Versión/tier, permisos del operador o ruta equivocada | Comprobar versión real y acceso a Service Accounts API |
| Compare permissions falla | Herencia, expiración o permiso extra | Corregir el nivel original, no conceder Owner por defecto |
| Migration blocked by pipeline | Hay pending/running/manual no terminado | Resolver el pipeline antes del cutover |
| Estado switching | Un cambio remoto pudo completarse parcialmente | Revisar consumidores y ejecutar rollback con checkpoint |
| Estado retiring | La credencial vieja puede estar revocada | Corregir hacia adelante y retomar retire; no restaurar ese secreto |

## Comandos seguros de primer diagnóstico

```bash
./scripts/labctl status
./scripts/labctl inventory
./scripts/labctl probe publisher

docker compose --profile ci ps
docker compose logs --tail=80 runner
docker compose logs --tail=30 config-sync
docker compose logs --tail=100 gitlab

docker buildx imagetools inspect gitlab/gitlab-ee:19.4.1-ee.0
docker buildx imagetools inspect gitlab/gitlab-runner:alpine-v19.4.0
```

Los logs de productos pueden contener información operativa sensible. Revísalos localmente y redáctalos antes de adjuntarlos. No actives `CI_DEBUG_TRACE`, `set -x`, `env`, `printenv` ni dumps de request/response para investigar una credencial.

`inventory` imprime metadata de tokens, no valores de credenciales. `probe` no publica ni despliega. `baseline` y `validate` sí realizan operaciones funcionales. No uses resultados de un comando como prueba de algo que ese comando no comprobó.

## Reintentos y estado parcial

El cliente reintenta lecturas ante algunos errores transitorios. No reintenta ciegamente escrituras, porque un POST que perdió su respuesta pudo haber creado un recurso. Inspecciona si existe antes de repetirlo. `seed` se detiene al encontrar un usuario ajeno a su estado, en lugar de adoptarlo automáticamente.

Si `make bootstrap` terminó la siembra pero falló después, no repitas todo sin revisar. Usa `sync-code`, `runner` y el arranque del perfil `ci` según la etapa pendiente. Si solo apagaste los contenedores, `make start` es suficiente.

## No hacer

No subir `.lab`, no copiar tokens a issues, no ampliar a Owner o `api` sin justificarlo, no revocar mientras un job sigue usando el secreto viejo, no borrar volúmenes como primer diagnóstico, no afirmar “revocado” ante un error de red y no afirmar “cero downtime” sin medir continuidad.

Fuentes: S5–S12 en [SOURCES.md](SOURCES.md).
