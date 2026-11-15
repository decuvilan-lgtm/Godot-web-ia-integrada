# Headless Session Bridge

## Propósito

El Headless Session Bridge permite que un proceso Godot ejecutado con `--headless` descubra y controle, mediante una API local acotada, una instancia gráfica de Godot Editor que ya está abierta. El editor gráfico muestra la interfaz, el Inspector, las escenas y el preview del juego; el proceso Headless actúa como operador.

Este módulo pertenece a **Godot Web IA Integrada**. No pertenece a ningún juego concreto.

## Módulos que no deben confundirse

| Módulo | Función |
|---|---|
| `headless/native-editor/` | Puente TCP local para operar una instancia nativa del editor Godot desde un proceso Headless. |
| `examples/bridge-sandbox/` | Sandbox del Command Center / agente web; prueba la integración HTTP del puesto Godot Web. |
| `browser-extension/` y `scripts/bridge/` | Control semántico del editor Godot Web dentro del Chromium de Actions. |
| Runtime Linux Headless | Motor y entorno para importación, compilación y pruebas técnicas sin interfaz. |
| `relay/` y `database/` | Transporte, cola de órdenes, sesiones y persistencia de resultados del Command Center. |

Son componentes relacionados, pero no intercambiables. No se deben duplicar protocolos ni hacer que uno simule ser otro.

## Estructura

```text
headless/
├── README.md
└── native-editor/
    ├── addons/
    │   └── headless_session_bridge/
    │       ├── plugin.cfg
    │       └── plugin.gd
    └── tools/
        └── headless_bridge/
            ├── bridge_probe.gd
            ├── session_watcher.gd
            ├── README.md
            ├── verify_fresh_project_features.sh
            └── verify_capture_transfer.sh
```

El complemento es propiedad del laboratorio. Se copia temporalmente a un workspace de prueba o a una copia de trabajo aislada del proyecto seleccionado; **no se instala ni se activa en el repositorio original del juego**. La activación modifica únicamente el `project.godot` de esa copia temporal.

## Flujo

1. Obtener el proyecto externo y registrar repositorio, rama y SHA de origen.
2. Crear una copia de trabajo aislada; conservar el original intacto.
3. Inyectar el addon y las herramientas Headless en esa copia de trabajo.
4. Abrir la copia con Godot Editor.
5. El addon inicia un listener TCP solo en `127.0.0.1`, genera un token aleatorio por instancia y publica un registro local en `user://headless_bridge.json`.
6. El proceso Headless `session_watcher.gd` mantiene el descubrimiento y heartbeat, y `bridge_probe.gd` envía comandos acotados.
7. El operador inspecciona, modifica con operaciones permitidas y observa el editor/preview.
8. Los cambios se comparan con el SHA base; solo se exporta/publica un diff revisado y aprobado. No se copia de vuelta todo el proyecto ni se sobrescriben cambios remotos ajenos.

## Seguridad y límites

- Listener enlazado exclusivamente a localhost; no es un servicio remoto ni debe exponerse a Internet.
- Token aleatorio por sesión, huella del proyecto y versión de protocolo comprobados en cada solicitud.
- JSON delimitado por línea y límite de recepción de 64 KiB.
- Lista explícita de comandos, tipos de nodos y propiedades editables.
- Las modificaciones de escena se realizan mediante el sistema de Undo/Redo del editor y se etiquetan como acciones del Headless Bridge.
- No se permite shell, ejecución arbitraria de GDScript, eval, escritura arbitraria ni ejecución de procesos.
- Las rutas de recursos se validan y las operaciones tienen límites de tamaño y profundidad.
- Las escenas no se guardan automáticamente; la publicación requiere revisión.
- Capturas de editor, escritorio y vídeo se recuperan por fragmentos y se verifican mediante comparación de bytes en las pruebas.
- El sistema es experimental y local. No asumir que el listener TCP es adecuado para control remoto.

## Pruebas

El workflow `.github/workflows/test-headless-session-bridge.yml` crea un proyecto **Bridge Sandbox** usando el Project Manager real de Godot, instala el addon únicamente en ese proyecto descartable y prueba la conexión, inspección, cambios undoables, recursos visuales, preview, capturas y transferencia exacta de archivos.

El workflow no abre ni modifica un proyecto de juego real. Los artefactos de Actions son evidencia de esa ejecución, no una afirmación general de que todas las instalaciones o versiones estén verificadas.

Ejecutar las pruebas manualmente desde Actions o al modificar este módulo en la rama de integración. Antes de integrar a `main`, exigir un workflow verde y revisar los artefactos de evidencia.

## Estado conocido

- El código del addon, watcher, probe y pruebas está integrado como herramienta genérica del laboratorio; no pertenece a un juego concreto.
- La ejecución E2E anterior del sandbox terminó correctamente: [run 43763946788](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43763946788). Verificó creación de un proyecto nuevo desde Project Manager, instalación aislada del addon, escena real, conexión, Inspector, edición, Undo/Redo, preview, capturas, vídeo y transferencia de evidencias.
- La integración consolidada vuelve a ejecutar el workflow en PR #55; su resultado actual debe consultarse en Actions antes de considerar validado este cambio.
- El control del editor Godot Web vía Chromium es un módulo distinto y tiene su propio estado en `docs/CHROMIUM_GODOT_CONTROLLER.md`.

