# Godot Web IA Integrada

Laboratorio independiente para que una IA pueda **entender, construir, ejecutar, inspeccionar y corregir juegos Godot** con la menor intervención manual posible.

**Este sistema no depende de ningún repositorio de juegos ni viene ligado a un proyecto concreto. El usuario elige qué proyecto quiere trabajar.** Este repositorio contiene infraestructura genérica, adaptadores, automatización y pruebas; no contiene un juego obligatorio.

## Independencia y selección del proyecto

- No hay un repositorio de juego predeterminado, obligatorio ni privilegiado.
- El usuario selecciona explícitamente el proyecto Godot de cada sesión.
- El proyecto elegido se trata como entrada de trabajo y se copia a un workspace aislado.
- Las pruebas y demos son fixtures desechables, nunca dependencias del juego del usuario.
- No se modifica el original ni se publica automáticamente. Exportar cambios requiere revisión y aprobación explícita.

## Arquitectura

    Proyecto Godot elegido por el usuario
                |
                v
       Copia de trabajo aislada
                |
        +-------+--------+
        |                |
        v                v
    Godot Headless    Godot Editor real
    Linux             (inspección visual)
        |                |
        | archivos,      | árbol, Inspector,
        | escenas,       | recursos, preview,
        | scripts,       | capturas
        | importación,   |
        | ejecución      |
        +-------+--------+
                |
         Corrección iterativa
                |
          Diff revisado
                |
       Exportación aprobada

### Los tres entornos Godot (no confundir)

| Entorno | Responsabilidad | Qué valida |
|---|---|---|
| **Godot Headless local del agente** | Desarrollo principal: crear scripts/escenas, importar, ejecutar el juego, probar y corregir desde Linux | El proyecto y su comportamiento en el entorno local del agente |
| **Godot Headless de GitHub Actions** | Runtime independiente del runner CI, conectado al editor real para pruebas del Headless Session Bridge | El protocolo, las operaciones del puente y la integración con el editor en Actions |
| **Godot Editor real** | Inspección visual de la copia de trabajo: escenas, nodos, Inspector, recursos y preview | La presentación visual y el estado del editor |

El Headless de Actions **no es** el Headless local del agente y no sustituye su instalación. Una prueba verde en Actions no significa que el agente haya ejecutado el juego en su entorno. Del mismo modo, una ejecución local correcta no demuestra por sí sola que la integración del puente funcione en el editor real.

La disponibilidad del Headless local debe comprobarse en el entorno del agente antes de declarar pruebas locales como realizadas. Si el binario no está instalado, se informa como requisito pendiente; Actions sigue siendo una validación separada.

**Headless es el entorno principal de construcción.** Se crean y modifican scripts GDScript, escenas .tscn, recursos y datos directamente en la copia de trabajo. No se programa haciendo clic en el editor ni se automatizan coordenadas para colocar cada nodo.

**El editor real es la estación de inspección visual.** Se abre la misma copia después de la validación Headless para comprobar presentación, jerarquía, Inspector y preview. El puente permite consultar el editor y solicitar operaciones acotadas; no es el mecanismo principal de autoría.

Los adaptadores nativo y Web son distintos porque operan en runtimes diferentes. La extensión Chromium solo retransmite solicitudes; no implementa una segunda API del editor.

## Flujo de trabajo

1. El usuario selecciona explícitamente el proyecto.
2. Registrar el origen, rama y SHA cuando exista.
3. Crear una copia de trabajo aislada.
4. Construir scripts, escenas, recursos y configuraciones desde Linux Headless.
5. Importar y validar con Godot Headless; revisar código de salida y logs.
6. Ejecutar pruebas automatizadas y el juego en modo Headless.
7. Abrir la misma copia en el editor real para inspección visual.
8. Corregir desde el workspace y repetir importación/pruebas/inspección.
9. Presentar el diff para revisión.
10. Exportar o publicar únicamente los cambios aprobados y al destino elegido.

No se deben usar clics o coordenadas como método normal de construcción. Un proyecto que pasa pruebas Headless todavía necesita inspección visual para validar su presentación.

## Control semántico unificado

- **Godot Web:** el agente C++ forma parte del binario del editor. Expone editor.list_capabilities, editor.get_state y scene.get_tree. La extensión Chromium solo retransmite.
- **Editor nativo:** headless/native-editor/ contiene el complemento que escucha únicamente en 127.0.0.1, usa token aleatorio y verifica la identidad del proyecto. Ofrece inspección, edición semántica acotada, preview y captura.
- **Godot Headless:** crea/valida contenido por archivos, importa recursos, ejecuta el juego y corre pruebas. No es un editor visual ni requiere simular clics.

El complemento nativo se instala solo en una copia aislada cuando se necesita inspección visual; nunca en el proyecto original.

## Seguridad y aislamiento

- Listener TCP limitado a loopback, token aleatorio y huella de proyecto.
- JSON delimitado por línea y límite de recepción.
- Lista explícita de comandos, tipos de nodos y propiedades editables.
- Sin shell, eval, ejecución arbitraria de GDScript ni procesos recibidos como órdenes del puente.
- Validación de rutas, tipos y tamaños.
- Sin guardado/publicación automática.
- Capturas transferidas por fragmentos y verificadas en las pruebas.
- Los cambios experimentales se mantienen en la copia de trabajo.

La autoría de scripts ocurre como cambios de archivos dentro del workspace aislado y se valida con el runtime Godot; no se expone una orden remota de ejecución arbitraria de código.

## Estado real y límites

- La integración de la rama contiene el agente Web de solo lectura y el puente nativo con vocabulario semántico canónico.
- La prueba E2E del proyecto vacío ya ha validado creación del proyecto desde Project Manager, operaciones de escena, recursos, Undo/Redo, preview, capturas y transferencia exacta en ejecuciones anteriores.
- Las últimas ejecuciones de CI para el commit b42589d completaron los workflows de proyecto vacío, compilación del editor Web y comprobaciones del repositorio.
- La construcción de niveles/juegos completos en Headless y su ciclo de corrección visual siguen siendo una fase de integración que debe probarse con un proyecto sandbox real; no se declara terminada por las pruebas del puente.
- El runtime Godot debe comprobarse en cada entorno antes de afirmar que se ejecutaron pruebas locales. Si no está disponible, usar CI como validación temporal y declarar esa limitación.
- Las advertencias Vulkan/OpenGL, X11, audio y UID se investigarán después de completar el ciclo de desarrollo Headless + revisión visual.

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
- Workflow de Chromium: ejecutar indicando el ID de una compilación personalizada exitosa.

La compilación Godot Web y el runtime Linux Headless son dependencias externas versionadas. Este repositorio mantiene los parches, adaptadores, pruebas y orquestación; no copia el motor completo.

## Integridad

- No asumir ni seleccionar un repositorio de juego por defecto.
- No modificar el proyecto original para que el controlador funcione.
- No publicar automáticamente cambios experimentales.
- No ejecutar código arbitrario mediante comandos del puente.
- Mantener listeners TCP en loopback y sesiones asociadas al proyecto seleccionado.
- No fusionar a main ni desplegar servicios sin revisión y autorización.
