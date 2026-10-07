# 03 · Runbook de migración por identidad

## Principio de operación

Mantén separados **preparar**, **cambiar consumidores**, **validar** y **revocar**. No completes un ticket solamente porque se creó una cuenta o el endpoint `/user` devolvió 200.

```text
seeded → prepared → switching → switched → validated → retiring → retired
                         |          |           |
                         +----------+-----------+→ rolling_back → seeded
```

`switching` y `rolling_back` son checkpoints de recuperación. `retiring` marca una frontera irreversible: el token puede estar revocado incluso si un paso posterior falló.

## A. Preparación operativa

Revisa la cuenta, sus IDs y todos los consumidores incluidos en el ticket. Ejecuta `inventory` y compara membresías directas y efectivas; guarda scopes y expiración de PAT, no su valor. Para reader no olvides `config-sync`. Para publisher no olvides el schedule ni la herencia desde `artifacts`.

La lista automática solo cubre el namespace sembrado. Antes de aplicar un procedimiento equivalente a una empresa necesitas descubrir variables en grupos/proyectos/schedules, secretos fuera de GitLab, integraciones, claves, triggers y recursos propiedad de la cuenta. Un token “sin uso reciente” no prueba que sea prescindible: podría ser mensual o de recuperación.

Registra ticket, owner simulado, riesgo, ventana, criterios de éxito y de rollback. En un equipo real, una persona que ejecuta no debe inventar la aprobación del dueño. Aquí `--owner` es una atribución de práctica, no una aprobación criptográfica ni un sistema real de change management.

Comprueba que no haya pipelines en curso y que los schedules estén pausados. No ejecutes otro cambio desde la UI durante el cutover. Usa:

```bash
make baseline
./scripts/labctl inventory
./scripts/labctl status
```

La baseline debe probar el servicio antes de tocar credenciales. Si ya está roto, no atribuyas automáticamente sus fallos a la migración.

## B. Preparar sin cambiar consumidores

```bash
./scripts/labctl prepare reader
./scripts/labctl probe reader --side native
```

El CLI crea una cuenta nativa mediante `POST /groups/:id/service_accounts`, crea un PAT con caducidad, replica permisos directos y compara acceso efectivo. No “resuelve” una diferencia agregando Owner. El consumidor todavía utiliza legacy.

`probe` acredita autenticación y lectura del proyecto, no todas las capacidades. La comparación guarda expiración de membresías. Si aparece un rol personalizado fuera de alcance, detiene el cambio para revisión.

## C. Cutover

```bash
./scripts/labctl cutover reader --ticket LAB-001 --owner equipo-catalogo-simulado
```

Se respalda la metadata de las variables antes de reemplazarlas. Se actualizan el PAT y el user ID esperado en el pipeline. Reader actualiza también el archivo del worker. Publisher toma ownership del schedule usando el PAT nuevo, no el PAT root.

El PAT anterior permanece válido durante este periodo controlado. Esa ventana existe para recuperar una migración planificada, **no para tolerar una credencial comprometida**. No hay garantía de cero interrupción ante un error deliberado: se mide la continuidad con comprobaciones concretas.

Si ocurre una excepción después del primer cambio, el estado permanece `switching`. No ejecutes otro cutover como si nada hubiera pasado. Revisa el estado de cada consumidor y utiliza rollback con el respaldo registrado.

## D. Validar

```bash
./scripts/labctl validate reader
```

El CLI compara permisos, verifica ownership cuando corresponde, ejecuta una pipeline completa y exige una comprobación reciente del worker. El pipeline verifica IDs de identidad, acceso al repositorio, publicación y descarga con checksum, despliegue de configuración y creación de pedido.

Abre también los jobs en GitLab. Asegúrate de que no haya variables de schedule o de pipeline de mayor precedencia que estén ocultando un secreto antiguo. La práctica usa variables de proyecto sin overrides; el inventario empresarial debe cubrir toda la precedencia.

Para el schedule, la validación automática comprueba su owner. **No ejecuta automáticamente un cron real**. Cuando termines los cutovers, puedes habilitar el schedule temporalmente y observar una ejecución originada por el planificador, verificando su identidad. Pulsar Run manualmente puede usar los permisos de quien lo pulsa y no es una prueba equivalente.

## E. Rollback reversible

```bash
./scripts/labctl rollback reader
```

Solo antes de `retiring`. Restaura valores y propiedades de las variables, archivo del worker y ownership del schedule aplicable. Ejecuta pruebas usando legacy. Después revoca el PAT nuevo y retira las membresías de la cuenta nativa; conserva la cuenta sin acceso para reutilizarla en otro intento.

El cambio vuelve a `seeded`. Ejecuta nuevamente baseline y prepare antes del siguiente intento. Si el rollback falla, conserva `rolling_back`; no avances al retiro mientras los consumidores estén mezclados.

## F. Retiro irreversible y cierre

```bash
./scripts/labctl retire reader --confirm reader
```

Antes de la frontera irreversible hay otra validación. Se rechazan PAT adicionales activos, SSH keys e impersonation tokens que estén fuera del plan conocido. El CLI comprueba que el usuario sea la identidad legacy creada para el laboratorio y que no sea root.

Después marca `retiring`, revoca el PAT, bloquea el usuario y elimina las membresías inventariadas. Exige un rechazo de autenticación con el PAT viejo: un timeout, DNS fallido o 404 no se aceptan como prueba de revocación. Comprueba acceso restante en el namespace y vuelve a ejecutar el pipeline y el worker.

El cierre genera `.lab/reports/closed-reader.json`, elimina el secreto legacy de las copias locales administradas por el CLI y registra `retired`. Eliminar un archivo no garantiza borrado forense en SSD, snapshots o backups; la revocación es el control que inutiliza la credencial.

Si un paso posterior a la revocación falla, el estado queda `retiring`. El comando permite retomar el retiro después de corregir la causa. **No intentes restaurar el PAT revocado.** La recuperación debe usar una credencial nueva válida y una configuración consistente.

## G. Observación

La comprobación automática es inmediata y el worker se consulta con una tolerancia de frescura de 15 segundos. No equivale a 24 horas de observación. Para entrenamiento extendido, repite la baseline en varias ventanas y observa una ejecución real del schedule. Registra cuántas ejecuciones observaste y durante cuánto tiempo; no afirmes un periodo que no transcurrió.

## Recuperar una inicialización incompleta

`seed` guarda IDs y tokens por etapas. Si perdió estado o detecta un username ya existente que no puede atribuir, se detiene. No adoptes usuarios ni borres proyectos a ciegas. Revisa la UI local, el estado y el evento que precedió al fallo.

Si todos los recursos se crearon pero falló la copia de código, utiliza:

```bash
./scripts/labctl sync-code
./scripts/labctl runner
docker compose --profile ci up -d --build runner config-sync
make baseline
```

Si el contenedor está arrancando aún, revisa `docker compose logs --tail=100 gitlab` y `docker compose ps`; un fallo de arranque no se arregla creando otra cuenta. Un reset es una decisión explícita de desechar la instancia de entrenamiento.

Referencias: S2, S4–S8 y S10–S12 en [SOURCES.md](SOURCES.md).
