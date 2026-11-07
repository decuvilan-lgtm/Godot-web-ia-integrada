# Godot Web IA Integrada

Entorno de desarrollo con **dos puestos de trabajo separados** que comparten un proyecto sin pisarse:

- **Puesto de la IA: Godot Web desplegado en Render.** Este es el editor remoto que utiliza el agente para inspeccionar y preparar trabajo en un workspace aislado.
- **Puesto del usuario: Godot Android.** Es el editor del usuario en su teléfono. No se sustituye por la web ni se le pide que use el editor web móvil.
- **Centro de mando: Neon Postgres + relay Render Free.** Mantiene identidades, emparejamientos, órdenes, resultados, revisiones, snapshots y propuestas. Postgres es la fuente de verdad; Render es transporte.

La regla central es que el agente trabaja en su copia web. Nunca sobrescribe directamente el proyecto aceptado en Android. Los cambios futuros se presentarán como propuestas con diff, validación y snapshot; solo se aplicarán tras aprobación explícita.

> **Estado real:** editor Godot Web 4.7.2 publicado; cliente experimental del Command Center añadido al proyecto sandbox web y validado con Godot headless; cliente Android experimental en PR #3; API FastAPI del relay implementada en PR #1. Aún no hay conexión Neon real, dispositivos emparejados ni operación de extremo a extremo. No hay escritura remota habilitada.

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

La API falla de forma cerrada si Neon no está configurado. Las migraciones 001–004 están instaladas/verificadas en Neon, incluido el esquema de metadatos de observación visual. El servicio Render aún no tiene configurados los secretos necesarios. No se ha desplegado esta versión ni se ha hecho una solicitud real contra la base de datos.

## Verificaciones y límites

- Los tests del relay y el smoke test de Godot 4.7.2 para el sandbox han pasado en CI para el último commit validado.
- La compilación del editor web y la observación HTTP local de tres minutos están en ejecución para el commit que incorpora el nuevo cliente web.
- La observación HTTP local valida entrega de archivos estáticos; no equivale a una prueba de interacción real con el editor web desplegado.
- No hay pairing Android/Web de extremo a extremo, APK actualizado probado, controlador IA operativo ni escritura remota.
- El paquete publicado del editor web ronda los 93 MB en la última medición; debe revisarse la carga real en navegador y dispositivos antes de optimizar.

## Próximas etapas

1. Terminar CI del cliente web y corregir cualquier error de plugin.
2. Revisar el sandbox dentro del editor Godot Web real y confirmar que el plugin puede ejecutarse allí.
3. Configurar Neon URL y secreto administrativo en Render, después de revisión; desplegar solo cuando esté preparado.
4. Emparejar el editor web como `web_editor` y Android como `android_editor`.
5. Probar primero `ping`, estado, listado, escena y lectura de scripts.
6. Conectar un controlador IA autenticado que pueda encolar órdenes para el puesto web.
7. Implementar propuestas, diffs, snapshots, validación y aprobación explícita antes de cualquier aplicación al proyecto Android.

## Observación visual (en desarrollo)

El protocolo visual está definido en [docs/VISUAL_OBSERVATION.md](docs/VISUAL_OBSERVATION.md) y su contrato estricto de comandos en [docs/VISUAL_COMMANDS.md](docs/VISUAL_COMMANDS.md). Cada solicitud debe indicar un objetivo exacto (`editor_ui`, `editor_2d`, `editor_3d` o `game_preview`); las secuencias indican cantidad e intervalo, y el zoom declara el sistema de coordenadas. No se permite adivinar el objetivo ni sustituir una fuente por otra.

Neon Object Storage tiene el bucket privado `godot-visual-captures` y la migración 004 ya está aplicada y verificada en producción. La migración 005, necesaria para guardar secuencias de capturas de `editor_ui`, está preparada y probada en una rama temporal, pendiente de autorización para producción. Falta implementar endpoints firmados de transferencia, capturadores reales y la inspección de imágenes por el agente. Por tanto, **la captura visual aún no está operativa**.

## Desarrollo

- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Centro de mando](docs/COMMAND_CENTER.md)
- [Protocolo WebSocket anterior](docs/BRIDGE_PROTOCOL.md)
- [Relay](relay/README.md)
- [Complemento Web Command Center](examples/bridge-sandbox/addons/godot_command_center/plugin.gd)
- [Sandbox del editor web](examples/bridge-sandbox/project.godot)
