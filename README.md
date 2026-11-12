# Godot Web IA Integrada

Flujo de desarrollo acordado:

- **GitHub `main`:** única fuente oficial de los proyectos seleccionados.
- **ChatGPT + Godot Headless:** clonan el repositorio completo, desarrollan, prueban y publican cambios directamente en `main`. Headless no necesita Project Manager.
- **Godot Web:** conserva su Project Manager nativo y sirve para abrir, ejecutar e inspeccionar visualmente la revisión publicada en GitHub.
- **Android:** conserva su mecanismo de importación desde repositorios públicos; se auditará para reutilizar su lógica donde sea compatible.

Godot Web inicia automáticamente y presenta el Project Manager. El shell incluye el preloader de repositorios públicos desde `main`; el build se publicó correctamente en Render. Falta la prueba de interacción real en navegador. La actualización incremental GitHub → proyecto ya importado y las pruebas visuales de extremo a extremo siguen pendientes.

**Nota de transición:** las secciones posteriores que describen dos puestos emparejados, Neon como fuente de verdad del proyecto, propuestas hacia Android y sincronización entre editores documentan una arquitectura anterior. Se conservan temporalmente como inventario técnico, pero no son la dirección vigente y deben auditarse antes de retirar sus componentes.
> **Estado real (10 nov 2026):** editor Godot Web 4.7.2 publicado; Relay conectado a Neon en Render; credencial de Object Storage limitada a `storage:read` y `storage:write` configurada como secreto; bucket privado `godot-visual-captures`; capturas `editor_2d` y `editor_3d` habilitadas en la API y cliente Godot; secuencias realtime disponibles. CI de relay y smoke test Godot pasan. **Todavía falta emparejar el editor web y demostrar una captura real almacenada y recuperada**. El commit `48034bc` añade además un servidor MCP remoto autenticado; CI pasó, pero su despliegue Render aún debe confirmarse. Captura de UI completa, game preview y zoom siguen fuera de servicio. No hay escritura remota habilitada.

## Conexión GitHub → Godot Web

El shell incluye el botón **Conectar GitHub** y un preloader para repositorios públicos de la rama `main`. El Relay sirve el ZIP de forma acotada sin exponer credenciales. Consulta [docs/GITHUB_TO_GODOT_WEB.md](docs/GITHUB_TO_GODOT_WEB.md). La importación inicial utiliza el diálogo nativo del Project Manager; la actualización automática de proyectos ya importados aún no está disponible.

## Acceso

- **Editor web de la IA:** https://godot-web-ia-integrada-rt2l.onrender.com
- **Relay:** https://godot-web-ia-relay.onrender.com
- **Salud del relay:** https://godot-web-ia-relay.onrender.com/health
- [Repositorio de integración IA](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada)
- [Repositorio Godot Android modificado](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado)
- [Centro de mando Neon](https://console.neon.tech/app/projects/aged-dew-94732514)

**Infraestructura:** los servicios Render existentes deben permanecer en el plan `free`. No crear ni cambiar recursos a planes pagos. El relay puede suspenderse y reiniciarse; por eso no se considera almacenamiento persistente.

## Separación de puestos

| Función | IA | Usuario |
|---|---|---|
| Editor | Godot Web desplegado | Godot Android |
| Workspace | Copia remota aislada | Proyecto aceptado |
| Inspección | Permitida mediante comandos autorizados | Local |
| Preparar cambios | En su workspace | No aplica |
| Aceptar cambios | No puede autoaprobar | Aprobación explícita |
| Aplicar al proyecto aceptado | Prohibido sin aprobación | Solo tras revisión |

La versión web no es una interfaz móvil alternativa para el usuario. Las comprobaciones de viewport móvil solo verifican que la página no se rompa en pantallas pequeñas; no cambian la asignación de puestos.

## Godot Android: fuente correcta

El repositorio que debemos tomar como referencia para el editor Android es **Godot-engine4-v4.7.2-stable-difusion-modificado**.

Ese repositorio no almacena el árbol completo del motor. Su workflow descarga temporalmente `godotengine/godot` en el tag `4.7.2-stable`, aplica el parche mantenido en `scripts/apply_github_import_patch.py` y compila el APK. Las modificaciones propias deben incorporarse como cambios reproducibles al parche/build, no a una copia efímera del motor.

- [Repositorio y documentación del editor Android](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado)
- [Workflow de compilación Android](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/blob/main/.github/workflows/build-godot-android-source.yml)

El submódulo `engine/godot` de este repositorio es una referencia upstream fijada a 4.7.2-stable; no sustituye al flujo modificado del editor Android.

## Cliente Godot Web del Command Center

El proyecto de prueba `examples/bridge-sandbox` incluye el complemento `godot_command_center`, habilitado como plugin del proyecto:

- Empareja el puesto web con un código de un solo uso.
- Usa el rol `web_editor` confirmado por el servidor.
- Mantiene la credencial Bearer solo en memoria.
- Consulta la cola durable de Neon y confirma resultados.
- Solo permite `ping`, `project.get_state`, `project.list_files`, `scene.inspect` y `script.read`.
- Limita rutas, cantidad de archivos, profundidad de escena y tamaño de scripts.
- No permite escritura, shell ni ejecución de procesos.

El ZIP sandbox se importa/abre dentro del editor web para cargar este complemento. **Añadirlo al sandbox no significa que el editor web publicado ya esté emparejado ni que el agente pueda controlarlo automáticamente.** Falta la conexión real con Neon, el controlador de órdenes del agente y la prueba funcional dentro del navegador web.

El complemento WebSocket anterior se conserva como referencia, pero el sandbox activa el nuevo cliente HTTP del Command Center para evitar confundir los dos protocolos.

## Cliente Godot Android

El PR #3 del repositorio Android incorpora un cliente experimental al addon Live Link existente:

- [PR #3 — adaptador Android](https://github.com/decuvilan-lgtm/Godot-engine4-v4.7.2-stable-difusion-modificado/pull/3)
- Emparejamiento de un solo uso y credencial en memoria.
- Polling de órdenes para el rol `android_editor`.
- Mismas cinco acciones de solo lectura.
- No modifica archivos del proyecto ni ejecuta comandos del sistema.

Todavía no se ha generado y probado un APK nuevo ni se ha realizado una prueba en el teléfono físico.

## Relay y Neon

El PR #1 añade al relay FastAPI existente:

- API autenticada bajo `/v1/command-center`.
- Códigos temporales de emparejamiento y tokens de dispositivo almacenados como hashes.
- Cola durable con leases, idempotencia, resultados y eventos.
- CORS restringido al origen del editor web.
- Respuestas no-cache y reconexión Neon acotada.
- Página administrativa de emparejamiento en `/command-center/admin`.

La API falla de forma cerrada si Neon no está configurado. Las migraciones 001–007 están instaladas/verificadas en Neon. Render conserva los secretos de Postgres y del bucket privado. La API acepta capturas `editor_2d`/`editor_3d`; WebP, hojas de contacto, captura de UI, preview y zoom siguen rechazados. Todavía falta demostrar una sesión real del editor web y recuperar una captura. El control del repositorio se realiza mediante la integración GitHub; la sincronización y observación del editor usan el Command Center HTTP existente. No hay un servidor de protocolo personalizado ni un runtime de ChatGPT conectado directamente a la cola.

## Servidor MCP remoto

El endpoint MCP previsto es `https://godot-web-ia-relay.onrender.com/mcp`. Acepta solo credenciales Bearer emparejadas como `agent_controller`; el destino de sus órdenes está fijado al puesto aislado `web_editor`. Las herramientas exponen estado del workspace, encolado idempotente y consulta de resultados. No hay escritura de archivos ni shell. Consulta [docs/MCP_SERVER.md](docs/MCP_SERVER.md) para el contrato y límites.

## Proyecto persistente y consultas múltiples

El workspace de Neon conserva el contexto del proyecto Godot Web de la IA. Cada consulta crea solo una orden independiente; no crea un proyecto, workspace ni sesión. Se pueden encolar varias consultas sobre el mismo proyecto: cada una tiene su ID e idempotency key, y el editor las procesa en cola, una por una. Las órdenes pendientes tienen una ventana de expiración de 10 minutos. Las repeticiones de una misma consulta reutilizan su clave; las consultas nuevas usan claves nuevas, pero mantienen el mismo workspace. La selección/creación de otros proyectos será una acción explícita futura, nunca un efecto secundario de consultar.

## Verificaciones y límites

- Los tests del relay y el smoke test de Godot 4.7.2 para el sandbox han pasado en CI para el último commit validado.
- La compilación del editor web y la observación HTTP local de tres minutos están en ejecución para el commit que incorpora el nuevo cliente web.
- La observación HTTP local valida entrega de archivos estáticos; no equivale a una prueba de interacción real con el editor web desplegado.
- No hay pairing Android/Web de extremo a extremo, APK actualizado probado, controlador IA operativo ni escritura remota.
- El paquete publicado del editor web ronda los 93 MB en la última medición; debe revisarse la carga real en navegador y dispositivos antes de optimizar.

## Próximas etapas

1. Importar y abrir `examples/bridge-sandbox` en el Godot Web publicado; confirmar el dock Command Center.
2. Emparejar únicamente `web_editor` en workspace `default` y probar `ping`, estado, escena y lectura.
3. Ejecutar una captura real `editor_2d` y verificar almacenamiento, metadatos, hash y recuperación.
4. Probar captura `editor_3d` y una secuencia breve; comprobar fallos parciales y limpieza.
5. Resolver una vía nativa y compatible para que ChatGPT use la API HTTP del Command Center; no añadir un servidor de protocolo personalizado ni asumir que el rol `agent_controller` ya conecta esta conversación.
6. Mantener la copia web aislada; implementar propuestas, diffs, snapshots, validación y aprobación explícita antes de aplicar cambios al proyecto Android.

## Observación visual (en desarrollo)

El protocolo visual está definido en [docs/VISUAL_OBSERVATION.md](docs/VISUAL_OBSERVATION.md) y su contrato estricto de comandos en [docs/VISUAL_COMMANDS.md](docs/VISUAL_COMMANDS.md). En producción solo están habilitados los objetivos `editor_2d` y `editor_3d`. `editor_ui`, `game_preview` y `visual.zoom_to` están documentados, pero rechazados hasta implementar sus backends y restauración de vista. Las secuencias indican cantidad e intervalo; no se permite adivinar objetivos ni sustituir una fuente por otra.

Neon Object Storage tiene el bucket privado `godot-visual-captures`; el Relay tiene credenciales de almacenamiento con alcance `storage:read`/`storage:write`, transferencia binaria autenticada a través del Relay y validación de imagen/metadatos. La API permite `editor_2d` y `editor_3d`, además de secuencias realtime. **El código está habilitado, pero la operación real sigue pendiente de emparejar el editor web y validar el ciclo captura → almacenamiento → recuperación**. `editor_ui`, `game_preview` y `visual.zoom_to` no se consideran disponibles.

## Capacidades de inspección Godot verificadas

Se mantiene un registro de técnicas probadas en CI con Godot 4.7.2: ejecución headless, regresiones, capturas Xvfb y navegación/selección de escenas. La prueba de referencia es externa a este repositorio; no implica que el editor web ya tenga esas funciones integradas. El último intento también detectó un límite pendiente al seleccionar un nodo hijo. Consulta [capacidades verificadas, evidencias y límites](docs/VERIFIED_GODOT_INSPECTION_CAPABILITIES.md) antes de reutilizar o anunciar estas funciones.

## Flujo de desarrollo Headless + GitHub

El trabajo técnico se realiza primero en el proyecto local de Linux con Godot Headless. Después se reflejan en GitHub los archivos locales necesarios o, cuando conviene, se editan directamente los archivos del repositorio. Linux no necesita ni tiene que conectarse a Internet; nunca se sube el motor Headless. Consulta el [flujo de desarrollo detallado](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md).

## Desarrollo

- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Centro de mando](docs/COMMAND_CENTER.md)
- [Protocolo WebSocket anterior](docs/BRIDGE_PROTOCOL.md)
- [Relay](relay/README.md)
- [Complemento Web Command Center](examples/bridge-sandbox/addons/godot_command_center/plugin.gd)
- [Sandbox del editor web](examples/bridge-sandbox/project.godot)

## Shared projects: Godot Web and Android

The project-sync layer lets the two editors work with the same selected project while keeping separate local copies. It uses a workspace-scoped project catalog, per-file SHA-256 manifests, revisions and conflict checks. File bytes pass through the authenticated Render relay to private Neon Object Storage.

- The web editor shows a **Compartir proyectos** launcher to download the connector ZIP; importing and opening that sandbox enables the **Shared Projects** dock.
- The modified Android editor source includes the **Shared Sync** Project Manager installer, which installs and enables the same project add-on in a selected project.
- Pair both editors separately into the same workspace, then select the same shared project.
- Analyze is read-only; Sync is manual, incremental and conflict-blocking. The Web sandbox can clone the Android-seeded remote project after explicit confirmation, with rescue copies. Local files are rescued before remote overwrites or deletions.
- See [docs/SHARED_PROJECT_SYNC.md](docs/SHARED_PROJECT_SYNC.md) for the API, limits and setup.

The shared-project schema migration is applied to production Neon. The new relay code and Android editor installer still require CI, deployment/build and a real two-editor transfer test before end-to-end readiness can be claimed.

