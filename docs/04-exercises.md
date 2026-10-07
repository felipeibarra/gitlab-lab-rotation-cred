# 04 · Diez ejercicios para practicar antes de la entrevista

Hazlos sobre la instancia local. Lleva un registro de hipótesis, evidencia, corrección y resultado. No necesitas completar todos en una sola sesión. Los ejercicios 3–7 tienen inyección reversible; siempre ejecuta `repair` y comprueba recuperación antes del siguiente.

## 1 · Descubrimiento e inventario

Ejecuta `make baseline`, `make inventory` y `make status`. Inspecciona miembros de los proyectos y del subgrupo `artifacts` en la UI.

Entrega una tabla con tres identidades, user IDs, scopes, expiración, acceso directo/efectivo y consumidores. Explica por qué publisher tiene acceso a `packages` aunque su membresía original esté en un grupo. Documenta los límites del descubrimiento automático.

**Aprobación:** identificas el worker externo y el schedule, y diferencias una identidad de sus credenciales. No presentas una lista de tokens como si fuera un mapa de dependencias completo.

## 2 · Migración exitosa de reader

```bash
./scripts/labctl prepare reader
./scripts/labctl cutover reader --ticket LAB-001 --owner catalogo-simulado
./scripts/labctl validate reader
./scripts/labctl retire reader --confirm reader
```

Inspecciona `closed-reader.json` y la nueva identidad en GitLab. Compara los IDs legacy/nativo. No copies el archivo de secretos.

**Aprobación:** credencial antigua rechazada, permisos legacy retirados, pipeline posterior exitoso y worker reciente autenticado como la identidad nueva.

## 3 · Credencial incorrecta: fallo de autenticación

```bash
./scripts/labctl fault invalid-token --role reader
./scripts/labctl baseline
# Investiga el primer job fallido y su código de respuesta.
./scripts/labctl repair
./scripts/labctl baseline
```

**Aprobación:** localizas la variable incorrecta sin imprimirla, diferencias token inválido de servicio inaccesible y recuperas el pipeline. No agregas permisos para solucionar una credencial que no autentica.

## 4 · Token válido, scope insuficiente

```bash
./scripts/labctl fault wrong-scope --role publisher
./scripts/labctl baseline
./scripts/labctl repair
./scripts/labctl baseline
```

La inyección crea un PAT temporal `read_user`: puede identificarse, pero no publicar. El token temporal se revoca al reparar.

**Aprobación:** explicas por qué `/user` exitoso no prueba autorización para publicar. Identificas qué operación falló; no recurres a scope/rol máximo indiscriminadamente.

## 5 · Pérdida de permiso heredado

```bash
./scripts/labctl fault missing-membership --role publisher
./scripts/labctl baseline
./scripts/labctl inventory
./scripts/labctl repair
./scripts/labctl baseline
```

Se elimina la primera membresía directa descubierta para publisher, que en el escenario sembrado es la del subgrupo `artifacts`.

**Aprobación:** reconstruyes la cadena de herencia y recuperas la membresía en el nivel correcto. Consideras que un 404 sobre un recurso privado también puede ocultar ausencia de acceso.

## 6 · Variable protegida en rama no protegida

```bash
./scripts/labctl fault protected-variable --role deployer
./scripts/labctl baseline
./scripts/labctl repair
./scripts/labctl baseline
```

En el lab, `main` del proyecto automation está deliberadamente sin protección. La variable protegida deja de estar disponible allí.

**Aprobación:** distingues “la variable existe” de “la variable se entrega a este job”. Como extensión manual, revisa environment scope y precedencia. No afirmes que el CLI inyectó esos otros casos: la inyección implementada modifica `protected`.

## 7 · Pipeline verde, consumidor externo roto

```bash
./scripts/labctl fault stale-worker --role reader
./scripts/labctl baseline
# El pipeline puede pasar, pero la validación global debe fallar por el worker.
docker compose logs --tail=20 config-sync
./scripts/labctl repair
./scripts/labctl baseline
```

**Aprobación:** detectas que un job verde no cierra todas las dependencias. Explicas por qué el catálogo puede seguir funcionando con la última configuración mientras la sincronización falla. Exiges frescura e identidad correcta, no solo un health check.

## 8 · Ensayar rollback de publisher

```bash
./scripts/labctl prepare publisher
./scripts/labctl cutover publisher --ticket LAB-002-RB --owner release-simulado
./scripts/labctl validate publisher
./scripts/labctl rollback publisher
./scripts/labctl baseline
```

Después repite prepare/cutover/validate y completa `retire publisher --confirm publisher`, con un ticket nuevo. Si ya retiraste publisher, utiliza una instancia de práctica nueva o realiza este ejercicio antes del retiro.

**Aprobación:** pruebas que el schedule vuelve al owner legacy durante rollback y que el PAT nativo de ese intento queda revocado. Sabes explicar por qué este rollback no es válido después de revocar el PAT anterior.

## 9 · Ownership, coordinación y trabajo repetitivo

Asigna dos papeles: operador y revisor (puedes simularlos en dos revisiones separadas). Usa `docs/templates/change-record.md` y la issue template. Migra deployer con su propio ticket sin copiar IDs de publisher.

Antes del cambio, registra como incertidumbre quién posee una integración. Redacta la consulta que enviarías al equipo, el criterio de escalación y el motivo para no revocar sin resolver ownership. Luego documenta el owner **simulado** acordado y completa el cambio.

Una vez cerradas todas las cuentas, inspecciona y habilita temporalmente el schedule desde GitLab. Observa una ejecución iniciada por el planificador y vuelve a pausarlo. No confundas la ejecución manual del schedule con la del owner programado.

**Aprobación:** no cambias otra cuenta mientras existe un cutover abierto; dejas ticket, actor, validación y follow-up. La atribución del cambio no se deduce del nombre del archivo.

## 10 · Cierre de remediación y defensa técnica

Completa las tres cuentas y exporta únicamente evidencia sanitizada:

```bash
./scripts/labctl status
./scripts/labctl inventory
python3 scripts/export-evidence.py
python3 scripts/check-secrets.py
```

Examina cada `closed-*.json`: permiso, token viejo denegado, identidad nueva, pipeline posterior y worker. Crea un resumen con cuántas cuentas se cerraron y cuáles siguen pendientes, sin inventar resultados. Explica cómo cambiaría el procedimiento si se sospechara exposición de un token: contención, revocación, investigación y recuperación, en vez de conservar una ventana de solapamiento normal.

**Aprobación:** presentas un portafolio verificable y sabes señalar sus límites. Una captura verde sin identidad, fecha o alcance no basta.

## Extensiones deliberadamente no automatizadas

Para profundizar: rotación dentro de la misma cuenta nativa; SSH/deploy keys; deploy tokens; un secreto externalizado en Vault; ramas protegidas; triggers y webhooks; CI_JOB_TOKEN con allowlist; discovery multi-grupo; locking distribuido. Cada extensión requiere nuevas pruebas y un nuevo mapa de consumidores.

El endpoint de rotación nativa revoca el token anterior al crear el nuevo; no equivale a crear un segundo PAT y mantener ambos durante el cutover. En una extensión de rotación sin interrupción, prepara un segundo PAT, cambia consumidores, valida y solo después revoca el anterior. Ver S2 en [SOURCES.md](SOURCES.md).
