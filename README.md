# Godot Web IA Integrada

Laboratorio genérico para **inspección visual y pruebas interactivas de proyectos Godot** mediante el Godot Web real desplegado en Render. GitHub conserva cada proyecto y su historial; Godot Web solo permite observar y probar una versión sincronizada. El laboratorio nunca es el lugar de almacenamiento, edición definitiva ni entrega del proyecto completo.

Dragon Realm, Escondite, Ajedrez 2c2 y cualquier otro proyecto son objetivos de prueba intercambiables. Ninguno es una dependencia ni recibe un tratamiento especial fuera de las instrucciones que su propio repositorio proporcione.

## 1. Propósito y límites

El sistema permite seleccionar un proyecto Godot, preparar una versión identificable, cargarla en el editor web real de Render, inspeccionar su presentación, ejecutar interacciones y recopilar evidencia técnica.

### Lo que sí hace Godot Web

- Mostrar visualmente el proyecto seleccionado en el editor Godot Web desplegado.
- Ejecutar el proyecto cuando el flujo de importación y el propio proyecto lo permitan.
- Permitir inspecciones del editor, escenas visibles y ejecución del juego.
- Recibir entradas automatizadas de teclado, ratón y táctil.
- Ejecutar secuencias de pruebas descritas por el propio proyecto.
- Producir capturas, grabaciones, observaciones visuales, OCR, eventos, logs y diagnósticos disponibles.

### Lo que no hace Godot Web

- **No entrega el proyecto completo.**
- No es la fuente de verdad de los archivos del juego.
- No conserva ni publica cambios del código del juego como autoridad.
- No sustituye GitHub ni el sistema de trabajo del proyecto.
- No se considera sincronizado solo porque una pestaña siga abierta.
- No garantiza que una modificación en GitHub aparezca automáticamente en una instancia ya importada.

Los resultados del laboratorio son evidencia y diagnósticos, no una copia entregable del juego. El proyecto completo se obtiene del repositorio y de la revisión/commit correspondiente.

## 2. Fuentes de verdad y responsabilidades

| Componente | Responsabilidad |
|---|---|
| Repositorio GitHub del juego | Fuente de verdad del código, recursos, comandos, perfiles de control y pruebas específicas del proyecto |
| GitHub Actions | Orquesta la preparación, importación, ejecución del controlador genérico y publicación de evidencias; no almacena comandos particulares de cada juego |
| Relay en Render | Valida y entrega archivos al flujo de importación; ofrece APIs genéricas de coordinación y transferencia |
| Godot Web en Render | Laboratorio visual real: editor, ejecución, observación y pruebas interactivas |
| Chromium + Playwright/CDP | Controla la interfaz real del navegador, envía entradas y captura evidencia |
| Godot Headless | Ejecuta validaciones no visuales cuando son compatibles; complementa, no reemplaza, las pruebas visuales |
| Almacenamiento duradero de resultados | Conserva diagnósticos y evidencias publicados según su política de retención |

**Regla de propiedad:** el repositorio de cada juego contiene las instrucciones para probar ese juego. El repositorio del laboratorio contiene únicamente el motor genérico capaz de leerlas y ejecutarlas de forma controlada. No existe una memoria central de comandos de botones o mecánicas que se aplique indiscriminadamente a todos los proyectos.

## 3. Contrato de pruebas propio de cada repositorio

Cada proyecto debe llevar sus propias instrucciones de control y prueba dentro de su repositorio. Una estructura recomendada es:

```text
godot-lab/
  lab-manifest.json
  control-profile.json
  commands/
    smoke-test.json
    navigation.json
    gameplay-basic.json
  CONTROL_PROFILE.md
  TEST_HISTORY.md
```

Los nombres pueden adaptarse si el proyecto ya tiene una estructura equivalente. Lo importante es que las instrucciones viajen con el proyecto y su commit, no que queden guardadas como comandos particulares en el repositorio del laboratorio.

### 3.1 Qué debe declarar el repositorio

- Identidad del proyecto y ruta de `project.godot`.
- Escenas iniciales y condiciones necesarias para cada prueba.
- Controles reales: teclas, botones, zonas táctiles, gestos y combinaciones.
- Forma de interacción: pulsación breve, mantener, arrastrar, soltar, alternar o repetir.
- Comandos/secuencias de prueba con precondiciones y resultados esperados.
- Selectores semánticos o referencias visuales preferidas; coordenadas relativas como último recurso.
- Resolución de referencia, escala y contexto en el que se verificó cada posición.
- Cómo reconocer que una acción funcionó: cambio de escena, texto, animación, estado visible, señal de log u otra evidencia.
- Limitaciones conocidas, pasos no reproducibles y pruebas pendientes.

### 3.2 El perfil se aprende y verifica en ese proyecto

En un proyecto nuevo, el sistema primero inspecciona la interfaz y experimenta con sus controles. Una acción no se considera dominada por haber enviado una tecla o pulsado una coordenada: debe observarse el efecto y repetirse para confirmar que el resultado es reproducible. Después se documenta en los archivos del propio repositorio.

Cada instrucción tiene estado **Verificado**, **Pendiente** u **Obsoleto**, junto con la versión/commit, escena, contexto, evidencia y fecha de última comprobación. Los cambios de interfaz, escenas, configuración de entrada o lógica relacionada invalidan las partes afectadas del perfil y obligan a revisarlas.

### 3.3 El laboratorio no almacena comandos específicos de juegos

El controlador central solo conoce operaciones genéricas y seguras, por ejemplo enviar una entrada, esperar, capturar pantalla, inspeccionar texto y comprobar una condición. No decide que todos los juegos se mueven con WASD, que todos tienen un botón de salto ni que una coordenada sirve para todos.

GitHub Actions no debe convertirse en una biblioteca de comandos por juego. Debe localizar el manifiesto del repositorio seleccionado, validar su identidad y pasar sus instrucciones al ejecutor genérico. No se copia un perfil entre repositorios ni se heredan controles de otro juego sin una verificación explícita.

### 3.4 Seguridad de las instrucciones

Los archivos del repositorio son datos de entrada no confiables. El ejecutor valida el esquema, limita las operaciones disponibles, duración, frecuencia, rutas y recursos. No ejecuta automáticamente comandos de shell arbitrarios ni scripts externos solo porque estén declarados en el manifiesto. Cualquier adaptador ejecutable específico requiere revisión, aislamiento y autorización adecuados.

### 3.5 Identidad y vigencia

Cada perfil se vincula como mínimo a repositorio, ruta del proyecto, rama/ref y SHA verificado. El informe de prueba registra qué versión del perfil se utilizó. Si el proyecto no incluye un perfil, se realiza descubrimiento controlado y se propone documentarlo; no se improvisa reutilizando comandos de otro repositorio.

Para proyectos de solo lectura, el laboratorio puede conservar una copia de trabajo del perfil en un espacio aislado asociado a la identidad exacta del repositorio, pero no escribirá en el repositorio fuente sin autorización. Cuando el repositorio sea editable y la tarea lo permita, el perfil definitivo debe incorporarse allí.

## 4. Principio de sincronización: una versión por prueba

Cada carga del laboratorio representa una revisión concreta del proyecto. La identidad mínima es repositorio, rama/ref, SHA exacto, ruta de `project.godot`, identificador de ejecución y estado de importación.

**Cada vez que cambie el código o cualquier recurso que deba verificarse, el workflow debe preparar y cargar nuevamente el proyecto actualizado en Godot Web.** No se confía en hot reload ni en la detección automática de cambios de GitHub por una pestaña abierta.

Si el código no cambió y la sesión sigue viva con la misma revisión, se pueden enviar más pruebas sin volver a importar. Antes de cada conjunto de pruebas se comprueba qué SHA está cargado y se lee el perfil de control correspondiente a esa revisión.

## 5. Ciclo operativo completo

1. Seleccionar repositorio, rama/ref y subcarpeta del proyecto.
2. Leer el manifiesto y los comandos que vienen dentro de ese repositorio.
3. Validar identidad, esquema, seguridad y compatibilidad de las instrucciones.
4. Activar Render bajo demanda si está suspendido.
5. Preparar el ZIP temporal desde el SHA exacto e importarlo en Godot Web real.
6. Confirmar que la versión visible corresponde al SHA esperado.
7. Ejecutar las pruebas descritas por el repositorio mediante el controlador genérico.
8. Registrar acciones enviadas, respuestas observadas y aserciones verificadas por separado.
9. Si se descubre un control nuevo, probarlo de forma reproducible y documentarlo en el repositorio del proyecto cuando esté autorizado.
10. Publicar evidencia y diagnósticos; nunca el proyecto completo desde Godot Web.

## 6. Importación y cambios

Cuando cambia código o recursos, se obtiene el nuevo commit, se prepara un nuevo paquete y se vuelve a importar. No se parchea únicamente la copia temporal del editor. Si cambia la interfaz o la lógica de entrada, también se revisa la vigencia del perfil de controles.

Una pestaña persistente no significa que sus archivos estén actualizados. El SHA cargado y el SHA del perfil usado deben registrarse en el manifiesto de cada ejecución.

## 7. Sesiones y límites de Render Free

- Se reutiliza la sesión mientras el servicio siga vivo y la revisión no haya cambiado.
- La finalización de una tarea no debe cerrar deliberadamente el navegador.
- No se envían heartbeats artificiales, cron ni tráfico periódico para impedir la suspensión.
- Si Render suspende o reinicia el servicio, la memoria del navegador puede desaparecer.
- En la siguiente solicitud explícita, se despierta el servicio y se reconstruye el laboratorio desde GitHub.
- Los resultados generados deben publicarse en almacenamiento duradero antes de dar la tarea por completada.

La recuperación es lógica y basada en GitHub/resultados duraderos; no significa que la misma pestaña sobreviva a una suspensión.

## 8. Contrato de artefactos

Cada ejecución publica evidencia separada del proyecto fuente, cuando esté disponible:

```text
godot-visual-test-<run-id>/
  result.json
  manifest.json
  logs/
  screenshots/
  video/
  frames/
  events/
  ocr/
```

El manifiesto registra repositorio, rama, SHA, carpeta del proyecto, versión del perfil de controles, comandos ejecutados, fecha, workflow y estado de cada prueba. Solo se incluyen archivos realmente generados. Los resultados parciales se etiquetan como parciales.

**Nunca se empaqueta ni se presenta el proyecto entero como resultado de Godot Web.**

## 9. Aislamiento y protección

- Cada ejecución identifica proyecto, commit y perfil.
- Los controles específicos viven con el proyecto; el repositorio del laboratorio no contiene perfiles universales de juegos.
- El repositorio fuente solo se modifica mediante el flujo autorizado.
- Los proyectos de solo lectura no se modifican.
- No se mezclan resultados ni sesiones de proyectos diferentes.
- No se exponen tokens, claves ni credenciales en el navegador, los proyectos o los logs.
- Se validan los archivos de instrucciones como datos no confiables.
- No se usan force-push, resets destructivos ni limpiezas que puedan descartar cambios ajenos.

## 10. Estado de capacidades

- **Implementado:** existe código para la capacidad.
- **Verificado:** una ejecución identificable produjo evidencia de que funciona.
- **Pendiente:** falta implementación o una prueba concluyente.

No se declara que un comando de control funciona solo porque exista en un JSON. Debe ejecutarse en el proyecto y producir la respuesta esperada.

## 11. Documentación técnica relacionada

- [Funcionamiento completo del sistema](docs/SYSTEM_OPERATION.md)
- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Flujo Headless + GitHub](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md)
- [Importación GitHub → Godot Web](docs/GITHUB_TO_GODOT_WEB.md)
- [Capacidades de inspección verificadas](docs/VERIFIED_GODOT_INSPECTION_CAPABILITIES.md)
- [Observación visual](docs/VISUAL_OBSERVATION.md)
- [Pruebas interactivas](docs/INTERACTIVE_GAMEPLAY_TESTING.md)
- [Contrato de comandos visuales](docs/VISUAL_COMMANDS.md)
- [Relay y variables de entorno](relay/README.md)

## 12. Recorrido resumido: lo más importante

1. **Cada juego trae sus propios comandos:** los controles y secuencias viven en el repositorio del juego.
2. **El laboratorio es genérico:** interpreta instrucciones del proyecto; no impone WASD, botones ni coordenadas universales.
3. **Los comandos no se guardan en GitHub Actions:** Actions solo coordina y ejecuta el controlador genérico.
4. **Los controles se prueban antes de documentarse:** se verifica la respuesta y la reproducibilidad.
5. **Cada perfil queda ligado a un SHA:** los cambios relevantes pueden dejar instrucciones obsoletas.
6. **GitHub es la fuente de verdad:** allí vive el proyecto completo y sus instrucciones específicas.
7. **Godot Web es solo el laboratorio visual:** inspecciona, ejecuta y prueba; nunca entrega el juego entero.
8. **Si cambia el código, se vuelve a importar:** no se confía en actualizaciones automáticas de la pestaña.
9. **Las pruebas generan evidencia:** diagnósticos, logs, capturas, vídeos, eventos y resultados estructurados.
10. **Render se suspende naturalmente:** se despierta solo ante una nueva solicitud explícita.
