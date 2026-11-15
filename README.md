# Godot Web IA Integrada

Laboratorio para que una IA pueda **entender, construir, ejecutar, inspeccionar y corregir juegos Godot** con la menor intervención manual posible.

Este repositorio contiene la infraestructura genérica. Los proyectos de juegos conservan su código, recursos, instrucciones y pruebas en sus propios repositorios.

## Arquitectura

    Proyecto de juego (origen)
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
    Diff revisado -> publicación explícita en el repositorio del juego

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

1. Registrar repositorio, rama y SHA del proyecto de origen.
2. Crear una copia aislada para experimentar.
3. Detectar qué entorno está disponible y consultar sus capacidades reales.
4. Inspeccionar antes de modificar; validar rutas, tipos y argumentos.
5. Aplicar cambios pequeños y recuperables.
6. Ejecutar la vista previa o pruebas Headless según corresponda.
7. Capturar errores, logs, capturas y vídeo disponibles.
8. Corregir y repetir las pruebas.
9. Revisar el diff y publicar únicamente los cambios aprobados.

## Estado real

- El agente Web tiene tres comandos de inspección probados en Chromium; todavía no edita proyectos.
- El puente del editor nativo pasó una prueba E2E en un proyecto desechable, con inspección, edición limitada, Undo/Redo, vista previa y captura.
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
- No publicar automáticamente cambios experimentales.
- No ejecutar GDScript arbitrario, shell ni procesos recibidos como comandos del agente.
- Mantener los listeners TCP en loopback y las sesiones asociadas a un proyecto concreto.
- No fusionar a main ni desplegar servicios sin revisión y autorización.
