# Headless tooling

El sistema Headless genérico del laboratorio está organizado por entorno de control:

- [Native Editor Session Bridge](native-editor/tools/headless_bridge/README.md): proceso Godot Headless que controla una instancia nativa del editor Godot por TCP local.
- [Arquitectura e invariantes](../docs/HEADLESS_SESSION_BRIDGE.md): aislamiento de proyectos, seguridad, estructura y pruebas.

El controlador de Godot Web dentro de Chromium vive por separado en `browser-extension/` y `scripts/bridge/`; no se debe duplicar aquí.
