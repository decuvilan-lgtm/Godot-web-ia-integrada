# Anfitrión persistente para Godot nativo

## Estado

Diseño de despliegue; todavía no está aprovisionado ni conectado al Relay. No ejecutar ni registrar un runner en un equipo hasta que su propietario lo autorice.

La sesión persistente de Godot nativo debe vivir en un host con escritorio gráfico real. El Relay Chromium no es ese host, y el runner efímero estándar de GitHub Actions tampoco.

## Arquitectura objetivo

```
Operador (GitHub Actions, trabajo corto)
       |  orden firmada / ejecución autorizada
       v
Command Center (Relay HTTPS + Neon, cola durable)
       |
       v
Agente anfitrión (self-hosted runner / servicio local)
       |-- Godot Editor GUI (un único proceso por workspace)
       |-- Headless Session Bridge (127.0.0.1)
       |-- session_watcher.gd (heartbeat + reconexión)
       |-- workspace aislado + snapshots
       v
Evidencias -> Neon Object Storage + resultado en Command Center
```

El agente local nunca debe abrir un puerto público. El único canal remoto es HTTPS saliente hacia el Relay. El bridge TCP existente permanece ligado a localhost y conserva su token aleatorio y fingerprint de proyecto.

## Requisitos del host

- Linux x86_64 con sesión gráfica persistente (Xorg o Wayland/XWayland), no solo Xvfb.
- Godot 4.7.2 exacto, editor y runtime headless instalados y verificados.
- GPU/driver que exponga las extensiones Vulkan necesarias, más Vulkan loader/ICD. OpenGL software es un fallback de diagnóstico, no una validación Vulkan.
- Usuario de sistema dedicado, sin privilegios administrativos para el proceso Godot.
- Runner GitHub self-hosted con etiqueta dedicada `godot-native`, instalado como servicio y limitado a este repositorio.
- Almacenamiento persistente para workspace y logs; snapshots antes de cualquier modificación.
- Supervisión de memoria, disco, temperatura y reinicios. Un proceso vivo no equivale a una sesión sana.

No se debe usar un portátil personal como host desatendido sin consentimiento y configuración explícita del propietario. No almacenar secretos de GitHub ni credenciales de Relay dentro del proyecto Godot.

## Ciclo de vida

1. Aprovisionar host y runner por separado; nunca registrar un runner en una máquina ajena sin autorización.
2. Crear un workspace por sesión a partir de un SHA inmutable del proyecto elegido. No editar el repositorio original.
3. Arrancar el editor gráfico una sola vez para ese workspace y verificar que el plugin `headless_session_bridge` publica `user://headless_bridge.json`.
4. Arrancar `session_watcher.gd` como proceso supervisado. Debe reconectar si el editor se reinicia, sin lanzar una segunda instancia del editor.
5. Registrar en el Command Center el `session_id`, proyecto, SHA, PID del editor, versión del protocolo y estado del host. No enviar el token local del bridge al Relay.
6. Los operadores insertan órdenes con clave idempotente. El agente reclama una orden, valida su esquema/allowlist, ejecuta un probe local y publica resultado/evidencia.
7. El proceso editor y el watcher sobreviven al fin del operador. Solo una orden explícita de cierre o una política de mantenimiento puede detenerlos.
8. En cada reinicio del host, el agente marca la sesión como interrumpida, recupera el último snapshot y solicita una nueva inspección antes de reanudar trabajo.

## Contrato de órdenes

La primera versión remota debe limitarse a operaciones de QA de solo lectura:

- `ping`: confirmar proceso, proyecto y protocolo.
- `editor.get_state`: editor/escena activa.
- `scene.get_tree`: árbol acotado.
- `project.list_resources`: inventario acotado.
- `capture.editor_screenshot` y `capture.desktop_screenshot`: evidencia.

No exponer inicialmente operaciones que modifiquen escenas, scripts o recursos. Para habilitarlas más adelante, exigir workspace aislado, snapshot previo, diff, validación Headless y aprobación explícita. Nunca admitir shell arbitrario, GDScript arbitrario, `eval`, rutas fuera del workspace ni argumentos no validados.

Cada orden debe incluir `session_id`, `sequence`, `idempotency_key`, `issued_at`, `expires_at`, `action` y `args`. El host debe rechazar secuencias repetidas, expiradas o de otra sesión. Un timeout debe producir estado `unknown` hasta reconciliar el resultado; no repetir una mutación automáticamente.

## Seguridad del runner

- Etiquetas dedicadas; no usar `self-hosted` genérico compartido con otros repositorios.
- No aceptar workflows de pull requests no confiables en el runner persistente.
- Permisos mínimos, ejecución bajo usuario no administrador y firewall de entrada cerrado.
- OIDC/credenciales de dispositivo con alcance mínimo y rotación/revocación.
- Nunca imprimir tokens, pairing codes, cabeceras Authorization o contenido de secretos en logs.
- Aislar cada proyecto y borrar workspaces solo después de confirmar snapshot y exportación.
- Un runner self-hosted ejecuta código del repositorio: solo debe procesar ramas y commits confiables aprobados.

## Por qué no activar todavía

El Relay actual ya dispone de Command Center con Neon y cola durable, pero sus acciones permitidas están orientadas a los adaptadores Web/Android y no incluyen aún un dispositivo `native_editor`. No se debe fingir que el flujo actual ya puede controlar el editor nativo remoto.

Antes de activar el anfitrión hay que implementar y probar, en este orden:

1. Tipo de dispositivo `native_editor` y pairing/revocación dedicados.
2. Cola de órdenes nativas con lease, secuencia, expiración, idempotencia y recuperación.
3. Agente local que traduzca solo acciones allowlisted al `bridge_probe.gd`.
4. Registro de heartbeat/estado y captura de evidencias.
5. Tests de reinicio del editor, reinicio del host, pérdida de red, orden duplicada y timeout.
6. Prueba de Vulkan real en hardware/driver compatible.

Hasta que esos pasos estén aprobados, el workflow de benchmark de Actions sigue siendo una prueba efímera y el bridge nativo sigue siendo local. No se despliega ni se mezcla esta arquitectura en `main` automáticamente.
