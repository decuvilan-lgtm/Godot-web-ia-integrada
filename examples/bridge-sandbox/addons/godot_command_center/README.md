# Godot Command Center

Complemento del puesto remoto **Godot Web de la IA**. Se usa dentro del proyecto aislado `examples/bridge-sandbox`; no se instala en el editor Android del usuario.

## Conexión inicial

1. Abre el proyecto `examples/bridge-sandbox` en el editor Godot Web publicado.
2. Comprueba que el dock **Command Center** aparece en la zona derecha del editor. El proyecto ya habilita este complemento en `project.godot`.
3. Abre `https://godot-web-ia-relay.onrender.com/command-center/admin` en otra pestaña.
4. Introduce allí el secreto administrativo leído desde el entorno privado del servicio Render. **No lo pegues en el chat, en el proyecto ni en GitHub.**
5. Selecciona el workspace `default`, el dispositivo **Godot Web** (`web_editor`) y genera un código temporal.
6. El código es de un solo uso y caduca a los 120 segundos. Pégalo en **Código de emparejamiento** dentro del dock y pulsa **Emparejar como Godot Web (IA)**.
7. Cuando el dock confirme la conexión, pulsa **Iniciar recepción de órdenes**.

El campo **API HTTPS** ya apunta al Relay de producción. Solo cámbialo para una instancia de pruebas que controles.

## Capacidades actuales

- Emparejamiento seguro con credencial del dispositivo mantenida en memoria.
- Recepción de órdenes durables y confirmación de resultados.
- Inspección de estado del proyecto, lista de archivos, escenas y lectura de scripts.
- Captura de los SubViewports `editor_2d` y `editor_3d`, con subida a Neon mediante el proxy autenticado de Render.
- Secuencias de imágenes en tiempo real, con cada fotograma como activo independiente.

## Límites deliberados

- Es de solo lectura: no escribe archivos, no modifica escenas y no ejecuta comandos del sistema.
- No captura todavía la interfaz completa del editor ni la vista de juego.
- No implementa zoom con restauración exacta de la vista.
- WebP y hojas de contacto se rechazan antes de encolar la orden.
- No emparejes aquí el editor Android. Es un dispositivo y un espacio de trabajo separados.

Para la transferencia visual, sigue [LIVE_VISUAL_TRANSFER_RUNBOOK.md](../../../../docs/LIVE_VISUAL_TRANSFER_RUNBOOK.md).
