# 06 · Preparación de entrevista

## Presentación técnica después de ejecutar el laboratorio

Adapta esta explicación solo a lo que realmente terminaste:

> Construí un laboratorio local con GitLab, Runner Docker y servicios HTTP. Practiqué reemplazar identidades legacy por cuentas nativas de servicio, preservando permisos directos y heredados. Separé la creación de la identidad del cambio de consumidores, comprobé los user IDs efectivos y validé lectura privada, publicación de paquetes, despliegue de configuración y un proceso externo. Antes del retiro mantuve una ruta de rollback; después revoqué la credencial antigua, retiré permisos y exigí pruebas negativas y positivas. Los resultados están documentados como práctica local, no como experiencia de producción empresarial.

## Preguntas que debes poder responder

**¿Cómo empiezas con cientos de cuentas?**

Con alcance e inventario: identidad, owner, credenciales, tipos/scopes/expiración, membresías directas/heredadas, consumidores y frecuencia de uso. Clasifico criticidad y dependencias, selecciono una primera cuenta representativa, ejecuto un cambio controlado, observo y ajusto el runbook antes de ampliar. Un script que crea usuarios no sustituye descubrir dependencias.

**¿Qué diferencias hay entre una cuenta de servicio y un access token?**

La cuenta es la identidad; puede poseer varias credenciales. Los permisos efectivos dependen de alcance del token, membresías y políticas. Tokens de proyecto/grupo, deploy tokens, CI_JOB_TOKEN y Runner authentication token tienen modelos distintos; no deben sustituirse solo porque todos sean cadenas de texto.

**¿Cómo evitas interrumpir CI/CD?**

Con baseline, coordinación, drenaje de jobs, schedules pausados, nueva credencial preparada, actualización explícita de cada consumidor, verificación funcional y observación antes de revocar. Crear un segundo PAT permite una ventana de solapamiento planificada; un endpoint de rotación inmediata puede invalidar el anterior en el acto.

**¿Cómo replicas permisos sin sobreprivilegiar?**

Distingo membresía directa de herencia. Replico en el punto apropiado y comparo acceso efectivo, expiración y políticas relevantes. No transformo todos los permisos efectivos en membresías directas ni concedo Owner para hacer pasar una prueba. Roles personalizados y grupos compartidos requieren tratamiento explícito.

**El token devuelve 200 en /user pero el pipeline falla. ¿Qué investigas?**

La operación exacta, scope, membresía y políticas del recurso, disponibilidad/precedencia de variables y contexto del job. Un fallo antes del script puede pertenecer al Runner o al job token, no a la identidad migrada.

**¿Cuándo consideras terminada una cuenta?**

Cuando todos los consumidores inventariados usan la identidad nueva, sus operaciones funcionan, el owner acepta la validación, el acceso antiguo queda revocado/retirado y existe evidencia posterior al retiro. Un endpoint verde y un ticket actualizado no bastan.

**¿Qué haces si ya revocaste el token y falla un consumidor?**

No afirmo que pueda desrevocarlo. Recupero hacia adelante con una credencial válida nueva, corrijo el consumidor y vuelvo a comprobar. Investigo la dependencia omitida y ajusto el inventario/runbook.

**¿Qué cambia si el token fue expuesto?**

La contención y revocación pueden tener prioridad sobre el solapamiento normal. Coordino la interrupción, reviso alcance y uso, recupero con una credencial nueva y preservo evidencia. Nunca publico el secreto para demostrar exposición.

**¿Has hecho esto en enterprise?**

Responde con tu experiencia real. El laboratorio demuestra práctica concreta, pero no permite afirmar que administraste una flota empresarial, resolviste una incidencia real o coordinaste equipos que no existieron. Explica qué controles adicionales aplicarías y qué elementos no has probado.

## Guion de demostración

Muestra arquitectura y alcance; enseña las cuentas legacy/nativas en GitLab; compara inventario; abre un pipeline donde los jobs acrediten el user ID nuevo; muestra un fallo controlado y su reparación; termina con el reporte de cierre y la prueba de rechazo del token anterior. Oculta credenciales y evita abrir `config.toml` o `.lab/secrets.json` durante una pantalla compartida.

## Preguntas para quien entrevista

Averigua versión y despliegue de GitLab, tier, cantidad de cuentas, qué significa “convertir”, fuente de inventario, ownership, almacén de secretos, controles de acceso, credenciales expuestas, criterios de cierre, observación, responsabilidades de ambos freelancers y horarios/guardias. El aviso no proporciona estos detalles.

## Autoevaluación

Evalúa de 0 a 2: inventario, modelos de identidad, permisos, cutover, diagnóstico, rollback, decommission, coordinación y evidencia. 0 significa que no puedes explicarlo; 1, que lo explicas pero no lo probaste; 2, que lo demuestras con evidencia propia. No sustituyas una respuesta que falta por una historia inventada.
