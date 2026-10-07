# 02 · Arquitectura, identidades y límites de confianza

## Recursos creados en GitLab

```text
migration-lab/                    grupo raíz privado
├── automation                   pipeline y schedule
├── config                       catalog.json privado
├── deployment                   permisos usados por el adaptador deployer
└── artifacts/                   subgrupo privado
    └── packages                 Generic Package Registry
```

| Rol | Legacy → nativa | Acceso replicado | Scope PAT | Consumidores |
|---|---|---|---|---|
| reader | lab-legacy-reader → lab-native-reader | Reporter (20) directo en config | read_api | job de lectura; config-sync externo |
| publisher | lab-legacy-publisher → lab-native-publisher | Developer (30) en artifacts; Maintainer (40) en automation | api | publicar/descargar paquete; propiedad de schedule |
| deployer | lab-legacy-deployer → lab-native-deployer | Maintainer (40) directo en deployment | api | job de despliegue → adaptador HTTP |

Las cuentas nativas se crean como **cuentas de servicio del grupo raíz**, no como usuarios convencionales renombrados. Sus membresías se agregan explícitamente. La jerarquía evita exigir a una cuenta de proyecto que acceda a proyectos ajenos: las cuentas de proyecto tienen un ámbito diferente.

El Maintainer de `publisher` en `automation` está justificado por el ejercicio de `take_ownership` del schedule. En una plataforma real considera separar la identidad publicadora de la que administra schedules; la réplica de acceso existente y una reducción de privilegios posterior deben ser cambios revisables, no dos operaciones mezcladas sin criterio de aceptación.

## Flujo del pipeline

`unit-tests` ejecuta pruebas de lógica y HTTP local. `read-private-config` verifica el user ID con el PAT reader y descarga el archivo privado. `publish-release` usa publisher para subir una versión identificada por pipeline ID al registro de paquetes, descargarla y comprobar SHA256. `deploy-local` verifica deployer y envía la configuración al adaptador. `business-smoke` comprueba que el catálogo cargó esa versión y crea un pedido por HTTP con un total correcto.

La clonación inicial del repositorio por GitLab Runner utiliza sus mecanismos normales y el job token; no usa reader. Reader se prueba en una **lectura privada adicional**, deliberadamente separada de la clonación. No se atribuye al PAT migrado una clonación realizada por otro token.

El adaptador de despliegue valida el PAT con `/user`, consulta los permisos del proyecto `deployment` y exige access level ≥40. Actualiza `release.json` de forma atómica. El catálogo lee la versión activa en cada petición. Esto es un despliegue de configuración, no un despliegue de contenedores ni Kubernetes.

Los pedidos son solicitudes de prueba, con IDs efímeros; no existe base de datos comercial ni persistencia de pedidos. PostgreSQL/Redis están incluidos en el contenedor Omnibus de GitLab y pertenecen a GitLab, no a estas aplicaciones.

## Consumidor externo

`config-sync` relee `.lab/worker/config.json` cada cinco segundos. Ese archivo contiene únicamente su token reader y el ID del proyecto de configuración. El worker no monta `secrets.json` ni el PAT root. Registra user ID, resultado y hora, pero no credenciales.

Si la API falla, conserva la última configuración válida y marca error. Esta decisión permite demostrar una distinción importante: **el servicio puede parecer sano mientras la automatización dejó de sincronizar**. La validación exige una comprobación reciente exitosa con la identidad correcta; no basta con ver un archivo en caché.

## Red y ejecución

Los contenedores comparten `gitlab-migration-lab-net`; `gitlab.lab` es un alias interno. En el host, `/etc/hosts` resuelve el mismo nombre a loopback. GitLab escucha en 8929 tanto dentro como fuera; se evitan puertos externos que el Runner no pueda resolver.

Solo loopback publica GitLab, SSH y los endpoints de prueba. El Runner usa Docker executor con `privileged=false`, un job simultáneo y sin Docker socket montado en los jobs. El proceso administrador del Runner sí monta ese socket, por lo que sigue siendo un componente altamente privilegiado.

El código de servicio se ejecuta con el UID/GID del usuario que ejecutó `init`. Así puede escribir únicamente los archivos de runtime del laboratorio, sin conceder permisos 0777 a todos.

## Consistencia y concurrencia

El CLI bloquea operaciones simultáneas mediante un lock local. Antes de modificar credenciales exige pipelines terminados y schedules pausados. Guarda un checkpoint `switching` antes del primer cambio y no asume atomicidad entre varias variables y un archivo externo.

El lock **no** es distribuido: no evita que otra persona lance un pipeline desde la UI ni coordina dos máquinas distintas. Para la práctica, una ventana de cambio sin operaciones ajenas es una precondición. En empresa hace falta un mecanismo de coordinación/freeze apropiado.

La unidad de recuperación es la cuenta. Una modificación remota que terminó pero perdió su respuesta puede requerir reconciliación manual; el CLI no reintenta ciegamente POST/PUT. No es una transacción distribuida ni un framework de migración universal.

Fuentes oficiales: S1–S7 y S9–S12 en [SOURCES.md](SOURCES.md).
