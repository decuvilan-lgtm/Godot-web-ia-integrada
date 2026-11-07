# Arquitectura técnica

## Regla de puestos separados

Este proyecto tiene dos editores con propietarios distintos:

- **Godot Web desplegado en Render: puesto de la IA.** El agente trabaja en una copia remota aislada. No es la interfaz que debe usar el usuario desde su teléfono.
- **Godot Android: puesto del usuario.** El usuario trabaja en su editor Android modificado, en su propio dispositivo. No se reemplaza por el editor web ni se le exige usar una versión móvil de la web.
- **Neon Command Center:** autoridad persistente para workspaces, dispositivos, órdenes, resultados, revisiones, snapshots, propuestas y eventos.
- **Render relay Free:** transporte HTTP/WSS y ejecución de API. No es almacenamiento autoritativo.
- **GitHub:** código y revisiones de implementación; no es el canal de sincronización de cada cambio de proyecto.

La IA prepara trabajo en su puesto web. El proyecto aceptado del usuario permanece separado. Ningún cambio llega al puesto Android sin diff, validación, snapshot y aprobación explícita.

## Topología

```text
        ChatGPT / controlador IA
                  |
          órdenes autenticadas
                  |
          Render FastAPI relay
                  |
          Neon Postgres (cola)
             /          \
            /            \
   Godot Web (IA)     Godot Android (usuario)
   workspace aislado  proyecto aceptado
            \            /
             \          /
          propuestas y revisiones
                  |
        aprobación explícita del usuario
```

Neon Postgres es la fuente de verdad. Neon Realtime puede notificar cambios, pero las órdenes y resultados deben poder recuperarse consultando Postgres después de una desconexión. El relay puede suspenderse o reiniciarse sin perder el estado autoritativo.

## Estado real de implementación

### 1. Editor Godot Web

- Distribución oficial Godot Web 4.7.2-stable publicada como sitio estático.
- Build con verificación SHA-512 del paquete oficial.
- Encabezados COOP/COEP y metadatos de viewport.
- El proyecto sandbox se empaqueta por separado para importarlo/abrirlo en el editor.
- El sandbox ahora habilita el complemento HTTP del Command Center para el rol `web_editor`.

**Importante:** habilitar el complemento dentro del sandbox no significa que el editor web publicado esté ya emparejado ni que el controlador IA pueda manipular automáticamente la interfaz. Falta probar el flujo dentro del navegador Godot Web real y conectar un controlador autorizado que encole órdenes.

### 2. Cliente del puesto web de la IA

Complemento `examples/bridge-sandbox/addons/godot_command_center/plugin.gd`:

- Emparejamiento de un solo uso.
- Rol `web_editor` validado por el servidor.
- Token Bearer en memoria; no se guarda en el proyecto.
- Polling de la cola durable y confirmación de resultados.
- Acciones iniciales de solo lectura: `ping`, `project.get_state`, `project.list_files`, `scene.inspect`, `script.read`.
- Límites de archivos, nodos, profundidad y tamaño de scripts.
- Sin escritura arbitraria, shell ni ejecución de procesos.

El antiguo complemento WebSocket se conserva como referencia, pero no está habilitado en el sandbox por defecto.

### 3. Cliente del puesto Android del usuario

El PR #3 del repositorio `Godot-engine4-v4.7.2-stable-difusion-modificado` incorpora un cliente experimental al addon Live Link existente:

- Se empareja con un código temporal y recibe el rol `android_editor` del servidor.
- Consulta la misma cola Neon y confirma resultados.
- Token Bearer solo en memoria; debe volver a emparejarse después de reiniciar el editor.
- Ejecuta el mismo conjunto de cinco acciones de solo lectura.
- No escribe archivos ni modifica escenas.

Este cliente se añade mediante el flujo reproducible del repositorio Android. Ese repositorio descarga upstream Godot 4.7.2-stable durante el workflow y aplica parches versionados; no se debe editar una copia temporal del motor.

### 4. Relay FastAPI y Neon

El PR #1 de este repositorio añade al relay FastAPI existente:

- API `/v1/command-center` para pairing, órdenes, leases, resultados y consulta.
- Tokens y códigos almacenados como hashes.
- Idempotencia obligatoria en creación de órdenes.
- CORS restringido al origen del editor web.
- Respuestas no-cache para rutas sensibles.
- Inicialización de pool Neon y reconexión acotada si la base no está disponible.
- Página administrativa same-origin para generar códigos temporales.

La API falla de forma cerrada si faltan las credenciales de Neon. El PR sigue siendo borrador: Render todavía no tiene la URL de Neon ni el secreto administrativo configurados, y no se ha desplegado esta versión.

## Separación de datos y seguridad

Estados separados:

- **Agent workspace:** copia remota de trabajo en Godot Web.
- **Accepted workspace:** proyecto del usuario en Godot Android.
- **Proposal:** conjunto de cambios con diff contra una revisión base.
- **Snapshot:** punto de recuperación previo a aplicar una propuesta.
- **Revision:** identidad inmutable de un estado de proyecto.

Invariantes:

1. El agente no sobrescribe el proyecto aceptado.
2. Cada propuesta indica la revisión base exacta.
3. La aprobación verifica que la revisión aceptada no cambió desde que se creó la propuesta.
4. Un conflicto de revisión bloquea la aplicación automática.
5. Cada operación mutante futura será idempotente y auditable.
6. Las credenciales persistentes se guardan como hashes; los secretos no se registran en logs ni se incluyen en proyectos.
7. El relay nunca es la única ubicación de una orden pendiente o un resultado.
8. No se habilita shell remoto ni ejecución arbitraria de procesos.

## Próximas fases

1. Completar CI del cliente web y comprobar su carga en el Godot Web desplegado.
2. Configurar Neon URL y secreto administrativo en el relay Render Free después de revisar el PR.
3. Desplegar la API y comprobar health/ready sin alterar otros servicios.
4. Emparejar primero el puesto web de la IA como `web_editor` y luego el editor del usuario como `android_editor`.
5. Probar órdenes reales de lectura en ambos puestos.
6. Conectar un controlador IA autenticado capaz de encolar órdenes para el puesto web. Un WebSocket o una API no concede por sí solo a ChatGPT control de navegador; hace falta una herramienta de interacción compatible y verificable.
7. Implementar propuestas, diffs, validación, snapshots, aprobación y rollback.
8. Realizar pruebas de desconexión, duplicados, conflictos de revisión, reinicio/suspensión Render y pruebas físicas Android.

## Limitaciones conocidas

- La build web ronda los 93 MB en la última medición; debe evaluarse la carga real antes de optimizar.
- El smoke test headless valida que el plugin se importe y cargue, no que funcione en el navegador real.
- La observación HTTP de tres minutos prueba la entrega local de archivos estáticos, no la estabilidad del servicio Render desplegado.
- No hay pairing real, APK actualizado probado, conexión de extremo a extremo ni escritura remota.
- El plan Render debe permanecer en Free.
