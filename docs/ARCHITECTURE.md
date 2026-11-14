# Arquitectura técnica

## Decisiones acordadas: GitHub como origen y Godot Web como inspector visual

Esta sección registra la dirección acordada para el flujo de desarrollo asistido. Es una decisión de arquitectura; no implica que todo esté implementado o probado. Las secciones posteriores de este documento contienen componentes y decisiones de una arquitectura anterior (puestos emparejados, propuestas hacia Android y sincronización Neon); deben tratarse como legado pendiente de auditoría, no como requisitos que contradigan esta dirección nueva.

- **GitHub, rama `main`:** única fuente oficial y única rama de trabajo para este flujo.
- **ChatGPT + Godot Headless:** obtienen el repositorio completo, lo inspeccionan, desarrollan, ejecutan pruebas y publican commits directamente en `main`. Headless no necesita Project Manager: trabaja sobre el repositorio clonado y su `project.godot`.
- **Godot Web:** recibe/actualiza únicamente la copia asociada al repositorio seleccionado y sirve para abrir, ejecutar e inspeccionar visualmente el proyecto.
- **Project Manager:** se conserva el Project Manager nativo de Godot Web. No se construye un administrador paralelo.
- **Android:** su importador desde repositorios públicos se auditará como referencia antes de duplicar mecanismos.

Flujo: Headless clona y registra el SHA base → desarrolla y prueba → verifica que `main` no haya avanzado externamente → publica en `main` → Godot Web actualiza el proyecto asociado → se verifica visualmente el mismo SHA. Si la inspección detecta defectos, se corrigen desde Headless y se publica otro commit en `main`.

### Control semántico del editor Chromium

El puesto visual de Godot Web continúa siendo el Chromium de GitHub Actions. Se incorpora una extensión ligera que recibe órdenes semánticas del worker y las entrega a un adaptador del editor; no es otro Godot Headless, no abre un segundo navegador y no sustituye la inspección visual.

El worker usa un contexto persistente de Playwright con el canal Chromium que admite extensiones en modo headless. La extensión y el cliente Python se encuentran documentados en [Chromium Godot Controller](CHROMIUM_GODOT_CONTROLLER.md). Las órdenes nuevas deben identificar escenas, nodos y paneles mediante nombres/rutas estables, nunca mediante coordenadas o clics simulados.

La extensión y el despacho semántico están integrados en el worker. El adaptador EditorPlugin, propiedad de este laboratorio, se inyecta temporalmente en el ZIP seleccionado en memoria antes de que Godot lo importe; ni el ZIP de origen ni el repositorio del juego se modifican. El overlay tiene un smoke test local satisfactorio, pero la primera ejecución de Actions (issue #50) devolvió GODOT_ADAPTER_UNAVAILABLE: el complemento no quedó activo en el editor. La issue #51 añade diagnósticos para determinar si el ZIP transformado llegó al importador y si el adaptador se inicializó. Hasta resolverlo, el control del editor sigue siendo experimental. Las capturas, vídeo, consola y evidencias siguen perteneciendo al Chromium existente.

### Project Manager y entrada automática

La distribución oficial 4.7.2 presenta una página inicial con el botón **Start Godot Editor**. Ese botón llama a `startEditor()`, que crea el motor web y lo inicia con los argumentos `--project-manager --single-window`. Por tanto, el Project Manager nativo ya está incluido: el paso extra es iniciar el motor.

La experiencia deseada para nuestra web es iniciar Godot automáticamente al cargar la página y mostrar el Project Manager al terminar la carga, sin requerir que el usuario pulse manualmente Start Godot Editor. Se debe conservar el aviso de incompatibilidad cuando falten funciones requeridas (por ejemplo, aislamiento de origen/SharedArrayBuffer): en ese caso no se debe forzar el inicio. El estado de carga y los errores deben seguir visibles. El usuario debe poder volver al Project Manager y elegir entre los proyectos importados.

Godot Web guarda proyectos en IndexedDB. La carpeta debe estar bajo `/home/web_user/` para conservarse según la documentación. El Project Manager no implementa por sí mismo la sincronización con GitHub; esa actualización es una función independiente.

Referencias:
- https://docs.godotengine.org/en/4.7/tutorials/editor/using_the_web_editor.html
- https://github.com/godotengine/godot/blob/4.7.2-stable/misc/dist/html/editor.html

### Conexión de repositorios GitHub

El mecanismo inicial de conexión está descrito en [Conectar repositorios públicos de GitHub a Godot Web](GITHUB_TO_GODOT_WEB.md). ChatGPT puede preparar un enlace ?repo=owner/repository; el shell web solicita el ZIP público de main al Relay, lo precarga en el campo ZIP oficial y deja que el Project Manager nativo realice la importación. No se exponen tokens GitHub al navegador. La importación final aún utiliza el diálogo nativo. La actualización automática de un proyecto ya importado y la trazabilidad del SHA todavía no están implementadas.

### Aislamiento de proyectos

- Cada proyecto conserva su identidad y directorio propio en el almacenamiento web.
- Un commit solo puede actualizar el proyecto asociado a su URL de repositorio; nunca otro proyecto por coincidencia de nombre.
- Registrar URL, rama `main`, SHA remoto y SHA actualmente cargado.
- No sobrescribir silenciosamente modificaciones locales. Antes de actualizar, detectar cambios locales y preservar o respaldar la copia.
- Si la descarga/importación falla, conservar la última copia válida.
- No exponer credenciales privadas en el navegador. La primera prueba puede usar un repositorio público.
- El editor Android y Godot Web no deben sincronizarse entre sí: ambos consumen la fuente GitHub según sus responsabilidades.

### Pruebas de aceptación

1. Entrar en la web limpia y comprobar que Godot inicia automáticamente y presenta el Project Manager.
2. Confirmar que el aviso de incompatibilidad bloquea el inicio cuando faltan requisitos del navegador.
3. Confirmar que el progreso/errores de carga siguen visibles y no hay doble inicialización.
4. Importar un repositorio público y verificar que aparece en el Project Manager.
5. Recargar la página y confirmar que la lista de proyectos persiste.
6. Publicar un commit en `main` y comprobar que solo se actualiza el proyecto vinculado.
7. Confirmar que el SHA cargado coincide con GitHub y que otros proyectos permanecen intactos.
8. Probar cambios locales no publicados y fallos de descarga sin perder la copia anterior.
9. Auditar el importador del editor Android para identificar lógica reutilizable.

**Estado:** Project Manager nativo confirmado en el código oficial 4.7.2. El autoarranque y el preloader de repositorios públicos están publicados en Render; el build web pasó las pruebas del parche. Falta probar la interacción real en navegador. La actualización incremental de proyectos ya importados y la identificación del SHA siguen pendientes.

### Artefactos de ejecución visual: Output y Debugger

Cada ejecución del juego dentro de Godot Web debe producir artefactos descargables asociados a esa ejecución concreta. La salida de Headless no sustituye los datos de la ejecución visual: esta puede revelar problemas de renderizado, interacción, escenas, recursos, audio, entradas y comportamiento del navegador.

Recopilar, como mínimo:
- **Output:** salida disponible de la consola de ejecución, con mensajes informativos, advertencias, errores y trazas.
- **Debugger:** errores y datos de depuración que realmente estén disponibles en la build web.
- **Metadatos:** URL del repositorio, rama `main`, SHA cargado, proyecto, escena inicial si se conoce, fecha/hora, ID de ejecución, duración y estado (finalizada, detenida, fallida o interrumpida).
- **Capturas:** imágenes relevantes y marca temporal, si existen.

Los artefactos deben poder descargarse individualmente y en un paquete ZIP con manifiesto. Cada paquete debe identificar el SHA y el ID de ejecución; nunca se deben mezclar logs de ejecuciones distintas. La captura debe ocurrir antes de cerrar o reiniciar el editor. Si una categoría no está disponible, el paquete debe marcarla como parcial/no disponible en vez de fingir que está completa. No incluir secretos ni credenciales.

**Limitación confirmada:** la documentación oficial del Godot Web Editor 4.x declara que no ofrece depuración/profiling de GDScript ni funciones que dependen del protocolo del debugger. Por eso no se puede prometer la exportación del Debugger de escritorio desde la build web. Hay que investigar qué Output y errores de ejecución se pueden extraer mediante interfaces estables del editor y qué información adicional puede obtenerse desde la consola del navegador.

Prueba de aceptación: ejecutar un proyecto de prueba que emita mensajes de salida y un error controlado; descargar los artefactos y comprobar Output disponible, datos de depuración disponibles/no disponibles, SHA, metadatos y aislamiento entre ejecuciones. Comparar con Headless y documentar qué información solo existe en el entorno visual.

**Estado:** requisito acordado; extracción y empaquetado pendientes de investigación e implementación.

---

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
- Acciones de consulta: `ping`, `project.get_state`, `project.list_files`, `scene.inspect`, `script.read`.
- Navegación de interfaz acotada: `scene.open` y `scene.select_node`; permiten abrir una escena y seleccionar un nodo en el panel Scene sin modificar archivos ni contenido del proyecto.
- Límites de archivos, nodos, profundidad y tamaño de scripts.
- Sin escritura arbitraria, shell ni ejecución de procesos. La navegación de escenas solo cambia la escena activa y la selección del editor.

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
