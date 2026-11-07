# Godot Web IA Integrada

Entorno de desarrollo dividido en dos puestos de trabajo:

- **Puesto de la IA:** editor real de Godot Web publicado en Render. Está pensado para que el agente trabaje en el navegador remoto.
- **Puesto del usuario:** Godot Editor para Android, instalado y ejecutado por el usuario en su teléfono. No necesita abrir el editor web para trabajar.

La meta es que ambos puestos puedan inspeccionar y modificar el mismo proyecto mediante un relay y una sincronización explícita, con propuestas, historial y recuperación. Esa sincronización de extremo a extremo aún está en desarrollo.

> **Estado actual:** editor web 4.7.2-stable publicado; complemento AI Bridge de solo lectura; relay HTTP/WebSocket creado en Render Free y en proceso de validación. Aún no existe una sesión compartida funcional ni escritura remota.

## Acceso

- Editor web de la IA: https://godot-web-ia-integrada-rt2l.onrender.com
- Relay: https://godot-web-ia-relay.onrender.com
- Estado del relay: https://godot-web-ia-relay.onrender.com/health
- Render editor: https://dashboard.render.com/static/srv-dbna2s3rjlhs7386eol0
- Render relay: https://dashboard.render.com/web/srv-dbna8ep5efls73aoqb8g

**Infraestructura:** el editor está publicado como sitio estático y el relay como servicio web con plan `free`. No se ha contratado ni seleccionado un plan de pago. El relay es efímero: al suspenderse o reiniciarse pierde las sesiones activas.

## Base del motor

El código fuente oficial está fijado como submódulo en `engine/godot`, en el commit del tag **4.7.2-stable**. La distribución web inicial utiliza el paquete oficial precompilado.

- Motor: https://github.com/godotengine/godot
- Versión fijada: 4.7.2-stable
- Paquete web: Godot_v4.7.2-stable_web_editor.zip

## Qué funciona ahora

### Editor web de la IA
- Carga de la distribución oficial del editor desde el navegador.
- Descarga del paquete oficial verificada por SHA-256 durante el build.
- Encabezados COOP/COEP y metadatos de viewport.
- Proyecto de prueba empaquetado en `bridge-sandbox.zip`.

### AI Bridge v0.1
Complemento para el editor Godot que conecta por WebSocket seguro y autentica con un token temporal. Actualmente permite solo:
- `ping`
- `project.get_state`
- `project.list_files`
- `scene.inspect`
- `script.read`

Las operaciones de escritura todavía están bloqueadas.

### Relay v0.1
- Servicio Python/FastAPI desplegado en Render con plan `free`.
- Crea sesiones efímeras con credenciales separadas para editor y controlador.
- Recibe peticiones autenticadas del controlador y las reenvía al complemento conectado.
- No almacena proyectos ni archivos.
- Las sesiones expiran a los 30 minutos o al reiniciarse el servicio.

## Lo que falta para el objetivo completo

- Verificar el arranque y el endpoint de salud del relay.
- Probar el emparejamiento editor-controlador de extremo a extremo.
- Proporcionar una interfaz segura para iniciar sesión sin exponer secretos.
- Integrar un controlador accesible al agente desde su entorno de trabajo.
- Añadir conexión/sincronización con Godot Android del usuario.
- Crear workspace separado para IA, diffs, snapshots y aprobación de cambios.
- Añadir edición segura de escenas/scripts y runner aislado.
- Capturas reales del editor y del viewport.

El relay gratuito puede dormir y su memoria es temporal. Por eso no debe ser el almacenamiento del proyecto. La persistencia y el historial se diseñarán de forma independiente.

## Desarrollo

- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Protocolo del puente](docs/BRIDGE_PROTOCOL.md)
- [Relay](relay/README.md)
- [Código del complemento](examples/bridge-sandbox/addons/godot_ai_bridge/plugin.gd)
