# Validación de entrega

Fecha: 7 de octubre de 2026. Este documento diferencia lo comprobado de lo pendiente.

| Comprobación | Resultado |
|---|---|
| `python3 -m unittest discover -s tests -v` | **60 pruebas aprobadas**, Python 3.13.5, Linux |
| Servicios HTTP catálogo/pedidos/despliegue | Pruebas locales aprobadas; autorización GitLab simulada en tests |
| Checkpoints de cutover y validaciones de seguridad | Pruebas unitarias con mocks aprobadas |
| Compilación Python | Aprobada |
| Sintaxis de scripts Bash | Aprobada |
| YAML y referencias locales de documentación | Comprobados mediante parser/inspección estática |
| Patrones básicos de secretos en archivos publicables | Sin coincidencias; no sustituye revisión humana ni scanner completo |
| `docker compose config`, pull/build y arranque GitLab | **Pendiente en el equipo del usuario: este entorno no tiene Docker** |
| Disponibilidad/arquitecturas de los tags de Docker Hub | **No confirmadas**: consultas de manifiestos no disponibles desde este entorno |
| Migración contra API real, pipeline real y retiro | Implementados; **E2E pendiente de ejecución** |
| Cron real, rendimiento, recuperación de backups y uso empresarial | No validados ni certificados |

Las 60 pruebas NO equivalen a una migración real completada. `make baseline`, `validate` y `retire` generan las evidencias reales al ejecutar la práctica en GitLab local. No hay evidencia de cuentas empresariales ni de una entrevista aprobada.

## Comprobar en tu equipo

Ejecuta la secuencia del README, incluyendo la inspección de manifiestos antes del primer arranque. Para Apple Silicon debe aparecer `linux/arm64` en las imágenes seleccionadas. Revisa y actualiza `.env` a una versión compatible y soportada si los tags indicados no están disponibles; mantén GitLab >=18.11 para el recorrido nativo Free.

Después de iniciar todo: baseline correcta, migración reader, rollback de publisher antes del retiro, retiro de las tres cuentas y nueva baseline. Guarda IDs de pipeline, estados e identidad efectiva, nunca valores de credenciales. Una ejecución inmediata exitosa no acredita una ventana de observación de 24 horas.

El workflow de GitHub ejecuta pruebas y `docker compose config`; deliberadamente no levanta GitLab ni recibe secretos. Comprueba su resultado en Actions, separado del E2E local.
