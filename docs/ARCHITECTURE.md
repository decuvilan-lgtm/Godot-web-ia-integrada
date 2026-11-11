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

## Identidad persistente del proyecto y consultas múltiples

En esta fase, el **workspace Neon es el contenedor persistente del proyecto remoto de la IA**. El editor Godot Web conserva el mismo proyecto abierto; una consulta no crea un workspace, proyecto Godot ni sesión nueva.

- El dispositivo emparejado determina el `workspace_id`; el cliente no puede elegir ni crear otro workspace al enviar una consulta.
- Cada consulta crea únicamente una fila `commands`, con su propio UUID e `idempotency_key`.
- Todas las consultas del mismo puesto se insertan bajo el mismo `workspace_id`, por lo que se refieren al mismo proyecto abierto.
- Las claves de idempotencia son únicas por workspace: una repetición idéntica reutiliza el resultado/ID anterior; una consulta distinta usa una clave nueva.
- Se pueden encolar varias consultas antes de que el editor termine la anterior. La cola durable las procesa una por una en el puesto web para evitar operaciones simultáneas que compitan por el estado del editor. Cada orden pendiente tiene una ventana de expiración de 10 minutos; el lease de ejecución se renueva/reclama por separado.
- `sessions` representa una conexión/pareja de dispositivos, no un proyecto ni una consulta. Crear una consulta no crea ni renueva una sesión.
- Una captura, secuencia, inspección o lectura es una operación/resultado, nunca un proyecto nuevo.

No existe un endpoint de creación de proyectos en el flujo de consultas. Si en el futuro se necesita trabajar con varios proyectos Godot diferentes, se añadirá un registro explícito de proyectos y una selección deliberada; nunca se inferirá que cada consulta representa un proyecto nuevo.

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

- Render Relay ejecuta FastAPI y es transporte; Neon Postgres es la fuente de verdad.
- El Command Center está desplegado y usa el esquema `command_center`, el workspace `default` y la cola durable con idempotencia, leases y resultados.
- El puente WebSocket efímero anterior queda desactivado por defecto mediante `RELAY_LEGACY_BRIDGE_ENABLED=false`. El Command Center HTTP/Neon es el único puente de producción.
- No se habilitan escritura arbitraria, shell ni ejecución de procesos. Las órdenes disponibles siguen siendo de lectura y captura visual soportada.

 
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

2. Abrir `examples/bridge-sandbox` en Godot Web, confirmar el dock y emparejar solo el dispositivo `web_editor`.
4. Ejecutar una prueba de extremo a extremo: `godot_enqueue_command` → polling del editor → resultado → `godot_command_status`.
5. Realizar una captura real y comprobar almacenamiento privado, metadatos, hash y recuperación.
7. Completar propuestas, diffs, validación, snapshots, aprobación y rollback antes de habilitar operaciones mutantes.
8. Probar suspensión/reinicio del relay, reconexión, idempotencia, credenciales revocadas y aislamiento entre workspaces.

## Limitaciones conocidas

- La build web ronda los 93 MB en la última medición; debe evaluarse la carga real antes de optimizar.
- El smoke test headless valida que el plugin se importe y cargue, no que funcione en el navegador real.
- La observación HTTP de tres minutos prueba la entrega local de archivos estáticos, no la estabilidad del servicio Render desplegado.
- No hay pairing real, APK actualizado probado, conexión de extremo a extremo ni escritura remota.
- El plan Render debe permanecer en Free.
