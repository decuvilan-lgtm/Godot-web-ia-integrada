# Godot Web IA Integrada

Entorno de desarrollo basado en el editor real de Godot Web, con una capa de automatización propia y separada del proyecto del usuario.

> **Estado actual:** el editor web oficial 4.7.2-stable ya está desplegado en Render. El repositorio incluye un complemento de editor para conexión WebSocket autenticada y operaciones de inspección de solo lectura. Todavía no existe un relay remoto desplegado ni una sesión compartida de extremo a extremo; no se debe confundir el complemento con un agente remoto completo.

## Acceso

- Editor web: https://godot-web-ia-integrada-rt2l.onrender.com
- Render Dashboard: https://dashboard.render.com/static/srv-dbna2s3rjlhs7386eol0
- Despliegue: sitio estático de Render, sin base de datos ni servidor de pago.
- Build: descarga el paquete oficial y verifica su SHA-256 antes de publicarlo.

## Base del motor

El código fuente oficial está fijado como submódulo en `engine/godot`, en el commit del tag **4.7.2-stable**. La distribución web inicial utiliza el paquete oficial precompilado; esto permite publicar el editor sin compilar el motor completo en cada despliegue.

- Motor: https://github.com/godotengine/godot
- Versión fijada: 4.7.2-stable
- Paquete web: Godot_v4.7.2-stable_web_editor.zip
- Licencia del motor: MIT; consultar los avisos incluidos en la distribución oficial.

## Qué funciona ahora

### Editor web
- Carga de la distribución oficial del editor desde el navegador.
- Descarga de 4.7.2-stable verificada por SHA-256 durante el build.
- Metadatos de viewport móvil y encabezados COOP/COEP en el sitio.
- Proyecto de prueba empaquetado en `bridge-sandbox.zip`.

### Complemento Godot AI Bridge v0.1
El complemento está en `examples/bridge-sandbox/addons/godot_ai_bridge`. Se ejecuta como `EditorPlugin`, muestra un dock de conexión y requiere:
- una URL `wss://`;
- un token temporal introducido en el editor, guardado solo en memoria.

Tras autenticarse, acepta únicamente estas acciones de lectura:
- `ping`
- `project.get_state`
- `project.list_files`
- `scene.inspect`
- `script.read`

El protocolo limita cantidad/profundidad de nodos, cantidad de archivos y tamaño de archivos de texto. Las operaciones de escritura todavía están bloqueadas.

## Lo que falta para el objetivo completo

- Relay WebSocket remoto y emparejamiento de sesiones.
- API de edición de escenas y scripts con propuestas/diffs.
- Snapshots y separación real entre espacio del usuario y espacio del agente.
- Runner aislado para ejecutar pruebas y recopilar logs.
- Capturas reales de la interfaz y del viewport.
- Sincronización persistente entre sesión remota y Android.
- Pruebas de compatibilidad y rendimiento en dispositivos Android.

La infraestructura actual es solo un sitio estático gratuito. No se ha creado una base de datos ni un servicio de backend. Los límites del editor web frente al editor nativo (depuración, exportación y funciones de plataforma) se evalúan por separado.

## Desarrollo

- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Protocolo actual del puente](docs/BRIDGE_PROTOCOL.md)
- [Código del complemento](examples/bridge-sandbox/addons/godot_ai_bridge/plugin.gd)
