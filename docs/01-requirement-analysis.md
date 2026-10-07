# 01 · Qué pide realmente el puesto

## Lectura del requerimiento

El trabajo descrito es una iniciativa **operativa, temporal y delimitada de remediación de accesos**, no principalmente desarrollo de aplicaciones ni diseño de una plataforma nueva. Los microservicios de este repositorio son consumidores de prueba: permiten observar el impacto de cambios de identidad sobre un sistema que funciona.

El resultado esperado por cada cuenta es: dependencias identificadas, propietario identificado, permisos adecuados, nueva identidad válida, credenciales distribuidas correctamente, automatización verificada y acceso anterior retirado con evidencia. El riesgo principal no es crear mal un usuario: es olvidar un consumidor, alterar un permiso heredado, interrumpir trabajos en vuelo o revocar antes de comprobar.

La frase “Needs to hire 2 Freelancers” indica dos incorporaciones previstas en el aviso; no especifica cómo dividirán el trabajo. Una práctica útil es simular un operador y un revisor. El rol es mid/senior: se espera criterio para decidir cuándo no proceder, no solo ejecutar instrucciones.

El texto termina en “Location, Time & Engagement” sin los detalles correspondientes. No se pueden inferir horario, tarifa, duración, zona horaria exigida ni disponibilidad de guardia. Tampoco se especifican versión, plan o tipo de despliegue de GitLab, número de cuentas, almacén de secretos ni ventana de mantenimiento.

## Matriz de competencias y prueba

| Competencia | Trabajo observable | Criterio de éxito |
|---|---|---|
| GitLab administration | Grupos, subgrupo, proyectos privados, usuarios legacy y SA nativas por API | Identidad nueva figura en Service Accounts API, no es solo un nombre con prefijo bot |
| CI/CD | Runner Docker y cinco etapas | Pipeline con lectura, publicación, despliegue y transacción de negocio |
| Credential cutover | PAT paralelo; actualizar variables y archivo externo | Jobs usan nuevo user ID y worker acredita lectura reciente |
| Permission replication | Inventario directo/heredado y expiración | Comparación exacta en el namespace conocido, sin ampliar a Owner para “arreglar” |
| Debugging | 401/403/404, scope incorrecto, variable protegida, permiso heredado perdido | Causa identificada y mínima corrección suficiente |
| Secure decommission | Revocar, bloquear y retirar membresías | Token anterior denegado; nueva automatización continúa |
| Migration ownership | Schedule y responsables simulados | Owner correcto y aprobación de práctica documentada |
| Operación repetible | Tres identidades separadas, estados, checkpoints y runbook | No mezclar IDs, no migrar otra cuenta durante un cutover abierto |
| Comunicación | Ticket y evidencia sanitizada | Un tercero puede reconstruir qué cambió, por qué y cómo se comprobó |

## Qué preguntar en la entrevista

Aclara si “convertir” significa **crear una identidad nueva y mover consumidores** o **convertir in-place** una cuenta existente mediante una función específica de su versión. Este laboratorio practica el primer enfoque; cambian el user ID y los PAT. No afirma que una conversión conserve IDs, tokens o atribución histórica.

Pregunta por GitLab.com/Self-Managed/Dedicated; versión exacta y tier; ubicación de secretos; inventario aprobado; cantidad y criticidad de consumidores; schedules y otros recursos propiedad de las cuentas; scopes permitidos; membresías heredadas; ramas/entornos protegidos; criterios de aceptación; periodo de observación; autoridad para revocar y plan de recuperación.

Una cuestión decisiva es si se trata de **rotación planificada** o de **credenciales presuntamente expuestas**. El solapamiento breve puede facilitar continuidad en una migración planificada. Ante exposición, la contención puede requerir revocar inmediatamente y aceptar una interrupción controlada. No uses el runbook normal como excusa para mantener una credencial comprometida activa.

## Qué no debe confundirse

La cuenta de servicio es la identidad; un PAT es una credencial de esa identidad. Un project access token normalmente incorpora su propio bot y alcance de proyecto; no es automáticamente la cuenta nativa solicitada. Un deploy token no equivale a un PAT de API. Un job token tiene ciclo de vida y permisos distintos. El authentication token del Runner autentica al Runner, no a la cuenta que publica un paquete.

Autenticar en `/user` demuestra quién eres. No demuestra que puedas leer el repositorio, publicar un paquete, ejecutar un schedule o desplegar. Por eso hay pruebas funcionales para cada consumidor.

## Alcance empresarial no automatizado aquí

El laboratorio no reproduce SSO/SAML/LDAP, grupos compartidos fuera del árbol, roles personalizados, protected environments de pago, Vault/KMS, credenciales SSH, webhooks, cientos de cuentas o auditoría corporativa completa. Son extensiones a analizar, no capacidades que debas afirmar haber probado.

Fuentes conceptuales y de API: [SOURCES.md](SOURCES.md), especialmente S1–S8.
