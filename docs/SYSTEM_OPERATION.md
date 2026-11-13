# Funcionamiento completo del sistema

## 1. Objetivo general

Este sistema conecta repositorios de proyectos Godot con el Godot Web real desplegado en Render para realizar inspección visual y pruebas interactivas reproducibles. Su finalidad es observar el resultado de una versión concreta del proyecto, enviar interacciones y devolver evidencia útil para diagnosticar problemas.

El laboratorio no es el lugar donde se desarrolla, conserva o entrega el proyecto completo. El proyecto vive en su repositorio GitHub. Godot Web es una superficie temporal de observación y prueba.

## 2. Separación de componentes

### 2.1 Repositorio del proyecto

Es la fuente de verdad. Conserva todos los scripts, escenas, recursos, configuraciones, ramas y commits. Las modificaciones permanentes del juego se realizan en este repositorio mediante el flujo autorizado.

### 2.2 Repositorio Godot Web IA Integrada

Contiene la infraestructura del laboratorio: Relay, workflows, perfiles de prueba, automatización y documentación. No debe confundirse con el repositorio del juego seleccionado.

### 2.3 GitHub Actions

Orquesta la ejecución bajo demanda. Obtiene la revisión seleccionada, prepara el paquete para la web, activa el servicio cuando haga falta, realiza la importación, ejecuta las pruebas y publica los resultados.

### 2.4 Relay en Render

Actúa como puente de transferencia y coordinación. Valida los parámetros, entrega los archivos necesarios y expone las funciones de coordinación disponibles. No es la fuente de verdad del código del juego.

### 2.5 Godot Web en Render

Es el editor web real desplegado. Se utiliza para ver el proyecto, inspeccionar su presentación y probar su ejecución. No es un mock, pero el navegador que lo controla puede funcionar headless. Su contenido importado es una copia de prueba de una revisión de GitHub.

### 2.6 Automatización del navegador

Playwright y Chromium interactúan con la interfaz web real. Pueden capturar pantallas, enviar teclado/ratón/táctil y registrar secuencias. El modo headless de Chromium no significa que se esté usando un motor Godot simulado.

### 2.7 Godot Headless

Cuando la compatibilidad lo permite, realiza validaciones de importación, parseo o ejecución sin interfaz. Sus resultados complementan la inspección visual; no la sustituyen.

## 3. Regla fundamental: GitHub manda, Godot Web observa

El proyecto completo y actualizado siempre se obtiene del repositorio fuente. Godot Web no devuelve un ZIP completo del juego ni se utiliza para guardar cambios definitivos.

Los artefactos de Godot Web son exclusivamente evidencia: capturas, vídeos, frames, logs, diagnósticos, eventos, OCR y reportes. El resultado identifica el SHA exacto que se probó para que pueda recuperarse el proyecto desde GitHub.

## 4. Identidad de una versión cargada

Cada importación debe quedar asociada a:

- Repositorio.
- Rama o referencia.
- SHA de commit.
- Ruta del proyecto que contiene `project.godot`.
- Identificador del workflow y de la ejecución.
- Estado de importación y verificación.

La identidad no se deduce del nombre del proyecto ni de que la pestaña siga abierta. Antes de probar, el sistema confirma qué revisión está cargada.

## 5. Flujo de carga e importación

### 5.1 Seleccionar proyecto

La solicitud aporta repositorio, rama/ref y ruta relativa. El Relay/workflow valida el acceso, la ruta y la presencia de `project.godot`.

### 5.2 Activar el laboratorio

Si Render está suspendido, una solicitud explícita inicia una petición de activación y una espera acotada de salud. No hay cron, sondeos de fondo ni tráfico periódico para mantenerlo despierto.

### 5.3 Preparar el paquete

El workflow descarga el commit exacto. Si el proyecto está dentro de una subcarpeta, prepara un ZIP temporal cuya raíz contiene `project.godot`. Cualquier exclusión necesaria para la variante web se registra y afecta solo al paquete temporal, nunca al repositorio fuente.

### 5.4 Abrir Godot Web

Playwright abre el editor web desplegado en Render y completa el flujo de importación. Se valida la apertura por señales observables, registros y capturas. No se considera importación exitosa únicamente porque la URL haya cargado.

### 5.5 Verificar revisión

Se conserva el SHA de origen y el manifiesto del paquete. Si no puede demostrarse qué revisión está abierta, la ejecución debe marcarse como no verificada o fallida antes de atribuir resultados al commit.

## 6. Ciclo de pruebas

Una vez importada una revisión, se pueden realizar varias pruebas en la misma sesión activa, siempre que el código y los recursos no hayan cambiado.

### 6.1 Inspección visual

Capturar editor, escenas visibles, interfaz del juego, estados, animaciones y errores visuales. Se pueden usar OCR y comparaciones de capturas si están configurados.

### 6.2 Pruebas interactivas

Enviar acciones de teclado, ratón y táctil. Las acciones pueden ser puntuales o mantenidas durante un intervalo. Los controles deben soltarse de forma segura incluso si una acción falla.

### 6.3 Diagnósticos

Recopilar la salida y el debugger disponibles, advertencias, errores, eventos, logs del navegador y observaciones del controlador. La cobertura real depende de qué información exponga el editor web y el proyecto.

### 6.4 Evidencia

Generar capturas PNG, vídeos WebM, secuencias de frames, eventos temporizados, resultados OCR y reportes JSON. Cada archivo se asocia a una ejecución y a la revisión probada.

### 6.5 Interpretación

El informe separa:
- Acción enviada.
- Reacción visual observada.
- Aserción comprobada.
- Diagnóstico del motor disponible.
- Incertidumbre o prueba no ejecutada.

No se infiere que una mecánica funciona solo porque se haya enviado una tecla o porque haya aparecido una captura.

## 7. Qué ocurre cuando cambia el código

Este punto es obligatorio y no depende de que Render siga activo.

1. Se modifica el proyecto en el repositorio fuente.
2. Se registra el cambio mediante el flujo Git autorizado.
3. Se obtiene el nuevo SHA.
4. Se vuelve a ejecutar el workflow de importación/sincronización.
5. Se prepara un paquete nuevo desde ese SHA.
6. Se importa o carga la nueva revisión en Godot Web.
7. Se verifica la identidad de la revisión.
8. Se repiten las pruebas sobre la versión actualizada.

No se asume que Godot Web observe los cambios de GitHub en tiempo real. No se parchea una copia interna del editor como sustituto de volver a subir el proyecto. Una sesión abierta puede seguir mostrando la versión anterior; por eso cada conjunto de pruebas debe declarar su SHA.

Si el código no cambió, se puede continuar enviando nuevas interacciones a la misma revisión y sesión activa.

## 8. Sesión de navegador y Render Free

La sesión permite mantener el navegador abierto y realizar múltiples pruebas mientras el servicio está disponible. Al completar una tarea, el sistema no debe cerrar deliberadamente la pestaña o el contexto.

Render Free puede suspender el servicio por inactividad. No se intenta evitar esa suspensión mediante heartbeats artificiales, cron o sondeos. El tiempo de vida real depende de Render; cualquier TTL interno es un límite propio de la aplicación, no una garantía sobre la plataforma.

Cuando Render suspende o reinicia el servicio, la memoria del proceso y el navegador pueden desaparecer. No se promete conservar literalmente la pestaña. En la siguiente solicitud explícita:

1. GitHub Actions activa el servicio.
2. Espera la disponibilidad mediante reintentos limitados.
3. Recupera repositorio, rama, ruta y SHA requeridos desde la solicitud/manifiesto.
4. Reconstruye el paquete e importa de nuevo el proyecto.
5. Reanuda las pruebas desde el estado lógico documentado.

La recuperación es reconstrucción bajo demanda, no resurrección de una pestaña que ya no existe.

## 9. Entrega de resultados

Cada tarea publica un paquete de evidencia. Según lo que se haya generado, puede contener:

- `result.json`: estado general y resumen.
- `manifest.json`: identidad del proyecto, SHA, configuración y archivos de evidencia.
- Logs de salida, debugger y navegador disponibles.
- Capturas del editor y del juego.
- Vídeo o secuencia de frames.
- Eventos y timeline de interacciones.
- OCR y observaciones.
- Diagnósticos, errores, advertencias y aserciones.

El paquete de evidencia **no incluye el proyecto completo**. El juego se recupera desde el repositorio fuente, usando el SHA del manifiesto. La retención debe corresponder a la configuración real del proveedor; no se debe prometer persistencia de artefactos que solo estén en memoria local del Relay.

Los resultados deben publicarse fuera de la memoria efímera antes de dar una tarea por completada. Si un proceso cae antes de subir una evidencia que solo existía en memoria local, esa evidencia puede perderse; el sistema debe minimizar esa ventana y declarar cualquier pérdida.

## 10. Seguridad y aislamiento

- Mantener separados repositorio de infraestructura y repositorio de juego.
- No escribir en el repositorio fuente durante una importación o prueba, salvo que la tarea de desarrollo lo autorice expresamente.
- No incluir secretos en ZIP, navegador, capturas o logs.
- Validar repositorio, rama, ruta y tamaño.
- Mantener aislados los artefactos por proyecto y ejecución.
- Tratar código de terceros como no confiable.
- Evitar acciones destructivas y limpieza que pueda eliminar cambios ajenos.
- No utilizar force-push ni resets destructivos.
- Limitar concurrencia y consumo de recursos del navegador.

## 11. Condiciones para declarar una prueba válida

Una prueba visual/interactiva válida debe identificar el proyecto y SHA, confirmar la importación de la revisión, registrar las acciones, capturar la evidencia disponible y describir con honestidad las aserciones logradas y las pendientes.

Una prueba no es válida como verificación del último cambio si el editor estaba mostrando un commit anterior o no se pudo identificar la revisión cargada.

## 12. Recorrido resumido

1. Seleccionar repositorio, rama, carpeta y commit.
2. Despertar Render solo por una solicitud explícita si está suspendido.
3. Preparar y cargar el proyecto en el Godot Web real de Render.
4. Confirmar el SHA importado.
5. Inspeccionar visualmente y ejecutar pruebas interactivas.
6. Recopilar diagnósticos, logs/debugger, capturas, vídeos y eventos.
7. Si cambia el código, volver a ejecutar el workflow y reimportar la nueva versión.
8. Si no cambia, seguir probando en la misma sesión activa.
9. Publicar solo la evidencia y los diagnósticos; nunca el proyecto completo desde Godot Web.
10. Si Render suspende, reconstruir el laboratorio en la siguiente solicitud y volver a cargar el commit necesario.
