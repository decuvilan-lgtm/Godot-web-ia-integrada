# Godot Web IA Integrada

Laboratorio independiente para que una IA pueda **entender, construir, ejecutar, inspeccionar y corregir juegos Godot** con la menor intervención manual posible.

**Este sistema no depende de ningún repositorio de juegos ni viene ligado a un proyecto concreto. El usuario elige qué proyecto quiere trabajar.** El repositorio de este laboratorio contiene únicamente la infraestructura genérica de control, automatización, pruebas y diagnóstico; no contiene un juego obligatorio ni necesita que el usuario adopte uno de nuestros proyectos de ejemplo.

## Independencia y selección del proyecto

- No hay un repositorio de juego predeterminado, obligatorio ni privilegiado.
- El usuario selecciona explícitamente el proyecto Godot sobre el que quiere trabajar en cada sesión.
- La infraestructura debe poder trabajar con cualquier proyecto compatible que el usuario elija, sin exigir que ese proyecto se cree dentro de este repositorio ni que se adapte para satisfacer al controlador.
- El proyecto seleccionado se trata como entrada de trabajo. El sistema registra su origen e identidad cuando corresponda y crea una copia aislada para experimentar.
- Las pruebas, demos y proyectos sandbox de este repositorio son fixtures desechables: sirven para verificar el controlador y **nunca son dependencias del juego del usuario**.
- No se debe consultar, modificar, clonar ni publicar en otro repositorio por suposición. El destino siempre debe corresponder al proyecto que el usuario seleccionó.
- Los cambios experimentales permanecen en la copia de trabajo. Exportar o publicar cambios al proyecto elegido requiere revisión y aprobación explícita.

En resumen: **el laboratorio aporta las herramientas; el usuario decide qué juego se abre y trabaja.** Cambiar de proyecto no debe requerir modificar el código del laboratorio ni adaptar el juego para un repositorio específico.

## Arquitectura

    Proyecto Godot elegido explícitamente por el usuario
             |
             v
    Copia de trabajo aislada y verificable
             |
             +--> Godot Headless (Linux)
             |      Importación, validación, scripts y pruebas automatizadas
             |
             +--> Godot Editor nativo
             |      Headless Session Bridge: inspección y edición semántica
             |
             +--> Godot Web Editor (Chromium)
                    Adaptador nativo integrado + extensión de transporte
                    Inspección del editor y observación visual
             |
             v
    Ejecución / vista previa / diagnóstico / evidencias
             |
             v
    Diff revisado -> exportación aprobada al proyecto elegido

### Tres entornos, responsabilidades distintas

| Entorno | Responsabilidad | Estado actual |
|---|---|---|
| Godot Headless en Linux | Importar proyectos, ejecutar scripts y pruebas técnicas | Runtime externo al repositorio; no es un editor visual |
| Godot Editor nativo | Editar escenas, nodos, recursos y controlar la vista previa | Headless Session Bridge integrado en esta rama; capacidades acotadas |
| Godot Web Editor en Chromium | Inspeccionar el editor y observar el juego en navegador | Agente C++ integrado en el binario; actualmente de solo lectura |

Los adaptadores nativo y Web no son dos implementaciones intercambiables: resuelven entornos distintos. Comparten el objetivo semántico, pero conservan transportes adecuados a cada plataforma.

## Control semántico unificado

- **Godot Web:** el agente C++ forma parte del binario del editor. Expone editor.list_capabilities, editor.get_state y scene.get_tree. La extensión Chromium solo retransmite solicitudes y respuestas.
- **Editor nativo:** headless/native-editor/ contiene el complemento que escucha únicamente en 127.0.0.1, usa token aleatorio y verifica la identidad del proyecto. Permite un conjunto mayor de operaciones de edición y vista previa.
- **Godot Headless:** se usa para importación, ejecución y pruebas no visuales; no sustituye el control del editor abierto.

No se inyectan complementos, cambios a project.godot ni archivos del controlador en el proyecto original. El complemento nativo se instala solamente en una copia aislada y desechable.

## Flujo de trabajo seguro

1. El usuario selecciona explícitamente el proyecto Godot que quiere trabajar; no se asume ningún repositorio.
2. Identificar el origen disponible y registrar repositorio, rama y SHA si el proyecto procede de Git.
3. Crear una copia aislada para experimentar, sin alterar el original.
4. Detectar qué entorno está disponible y consultar sus capacidades reales.
5. Inspeccionar antes de modificar; validar rutas, tipos y argumentos.
6. Aplicar cambios pequeños y recuperables.
7. Ejecutar la vista previa o pruebas Headless según corresponda.
8. Capturar errores, logs, capturas y vídeo disponibles.
9. Corregir y repetir las pruebas.
10. Presentar el diff para revisión; exportar o publicar únicamente los cambios aprobados por el usuario y en el destino que haya elegido.

## API semántica y pruebas

El puente nativo publica un vocabulario canónico de comandos (`editor.*`, `scene.*`, `project.*`, `preview.*` y `capture.*`) y anuncia las capacidades reales de la sesión con `editor.list_capabilities`. Conserva alias internos anteriores por compatibilidad; los clientes nuevos deben usar los nombres canónicos. La API Web comparte los comandos de inspección que realmente soporta y declara el resto como pendiente, sin fingir paridad.

La prueba E2E crea un proyecto Godot vacío desde Project Manager, crea una escena desde el editor real y ejercita el puente, la edición permitida, Undo/Redo, recursos, vista previa, capturas y vídeo. Ese proyecto es temporal y no depende de ningún juego externo.

## Estado real

- El agente Web tiene tres comandos de inspección probados en Chromium; todavía no edita proyectos.
- El puente del editor nativo expone el vocabulario semántico canónico para inspección, edición acotada, recursos, Undo/Redo, vista previa y captura; la validación E2E de los últimos cambios está en curso.
- La extensión Chromium es transporte; no contiene una segunda implementación del editor.
- El prototipo de complemento instalado dentro de proyectos (browser-extension/godot-addon) se retiró del flujo activo para evitar duplicar el agente Web integrado.
- La vista previa nativa tiene inicio/parada y captura probados; depuración interactiva, pausa/reanudación y observación estructurada completa siguen pendientes.
- No debe describirse el sistema como un desarrollador autónomo completo hasta superar pruebas con proyectos de distinta complejidad.

## Documentación

- [Control y arquitectura unificados](docs/UNIFIED_EDITOR_CONTROL.md)
- [Arquitectura general](docs/ARCHITECTURE.md)
- [Agente integrado en Godot Web](docs/BUILTIN_WEB_EDITOR_AGENT.md)
- [Control Chromium](docs/CHROMIUM_GODOT_CONTROLLER.md)
- [Headless Session Bridge](docs/HEADLESS_SESSION_BRIDGE.md)
- [Flujo de desarrollo Headless](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md)
- [Pruebas interactivas de gameplay](docs/INTERACTIVE_GAMEPLAY_TESTING.md)
- [Pipeline de diagnósticos](docs/DIAGNOSTICS_PIPELINE.md)

## Pruebas principales

- python -m unittest discover -s scripts/bridge -p 'test_*.py' -v
- python -m unittest discover -s tests -p 'test_*.py' -v
- python -m unittest discover -s tests -p 'test_web_agent_patcher.py' -v
- bash scripts/test-bridge-sandbox.sh
- Workflow de Chromium: ejecutar manualmente indicando el ID de una compilación personalizada exitosa.

La compilación del motor Godot Web y el runtime Linux Headless son dependencias externas versionadas. Este repositorio mantiene los parches, adaptadores, pruebas y la orquestación; no copia el motor completo.

## Integridad

- No modificar repositorios de juegos para que el controlador funcione.
- No asumir ni seleccionar un repositorio de juego por defecto.
- No publicar automáticamente cambios experimentales.
- No ejecutar GDScript arbitrario, shell ni procesos recibidos como comandos del agente.
- Mantener los listeners TCP en loopback y las sesiones asociadas al proyecto concreto elegido.
- No fusionar a main ni desplegar servicios sin revisión y autorización.
