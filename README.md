# Godot Web IA Integrada

Entorno de desarrollo asistido para **proyectos Godot en general**. No está limitado a Dragon Realm ni a un juego, género o repositorio concreto. La idea es poder abrir un proyecto Godot elegido, analizarlo, modificarlo, probarlo y revisar visualmente sus resultados usando herramientas complementarias.

Dragon Realm se ha utilizado como uno de los proyectos de referencia para validar la importación y la inspección. Es solo un caso de prueba; no define el propósito ni la arquitectura del sistema.

## Objetivos

- Trabajar con distintos repositorios y proyectos Godot sin crear una instalación del editor por cada consulta.
- Mantener cada proyecto identificado y separado para evitar mezclar archivos o resultados.
- Desarrollar y validar cambios con Godot Headless cuando sea posible.
- Usar Godot Web para abrir proyectos y realizar comprobaciones visuales en navegador.
- Automatizar pruebas repetibles mediante GitHub Actions.
- Capturar imágenes individuales y secuencias consecutivas para observar el editor y, cuando la prueba lo permita, la ejecución del juego.
- Conservar trazabilidad: repositorio, revisión, parámetros, resultados, logs y capturas.
- Distinguir claramente lo implementado, lo probado y lo que todavía está pendiente.

## Arquitectura general

| Componente | Responsabilidad |
|---|---|
| Repositorio Git | Código fuente, recursos, documentación e historial del proyecto trabajado |
| Godot Headless | Importación, análisis, validaciones, ejecución y pruebas automatizadas sin interfaz |
| Godot Web | Apertura del proyecto en navegador y revisión visual mediante el editor nativo |
| GitHub Actions | Automatización de importaciones, pruebas de navegador, capturas y publicación de artefactos |
| Relay | Entrega controlada de archivos de repositorios públicos al navegador y servicios HTTP auxiliares |
| Render | Alojamiento del editor web y del relay |
| Complementos Godot | Integraciones opcionales para inspección y comunicación entre herramientas |

Estos componentes tienen responsabilidades diferentes. Una prueba correcta en Headless no garantiza que la interfaz o el renderizado web se comporten igual; una captura visual tampoco sustituye las pruebas técnicas.

## Flujo de trabajo recomendado

### 1. Seleccionar un proyecto

Se identifica el repositorio y la rama que se van a trabajar. El sistema debe usar la identidad del repositorio y su revisión, no solamente el nombre visible del proyecto. El importador en código admite repositorios públicos de GitHub, la rama predeterminada o una rama indicada, y una carpeta opcional que contenga `project.godot`. La disponibilidad de los cambios más recientes en Render debe comprobarse por separado.

Enlace de apertura:

```text
https://godot-web-ia-integrada-rt2l.onrender.com/?repo=OWNER/REPOSITORY

# Rama y carpeta opcionales:
https://godot-web-ia-integrada-rt2l.onrender.com/?repo=OWNER/REPOSITORY&branch=master&path=2d/platformer
```

Sustituir `OWNER/REPOSITORY` por el repositorio deseado. El enlace prepara la importación; la finalización todavía utiliza el Project Manager nativo de Godot.

### 2. Recuperar y preparar el proyecto

- Obtener el contenido versionado del repositorio seleccionado.
- Registrar el commit de origen de la copia de trabajo.
- Mantener separados los archivos de proyectos diferentes.
- No incluir el motor Godot ni sus ejecutables dentro del repositorio del juego.
- Recuperar submódulos o dependencias externas por separado cuando sean necesarios.

### 3. Desarrollar y validar

El flujo preferido para cambios de proyecto es trabajar sobre una copia local con Godot Headless:

1. Inspeccionar la estructura y las configuraciones del proyecto.
2. Importar recursos y comprobar errores.
3. Modificar únicamente los archivos necesarios.
4. Ejecutar pruebas automatizadas, validaciones y escenas de prueba pertinentes.
5. Revisar los cambios y comprobar que no se hayan alterado archivos ajenos a la tarea.
6. Publicar en Git los archivos necesarios y registrar el commit resultante.

Para cambios pequeños de documentación o configuración también puede ser conveniente editar directamente el repositorio. Si una edición remota afecta el proyecto ejecutable, debe incorporarse a la copia de trabajo y validarse cuando sea posible.

Consulta [Flujo de desarrollo Headless + GitHub](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md).

### 4. Revisar visualmente en Godot Web

Godot Web permite abrir el proyecto importado en el editor nativo. La revisión visual se utiliza para detectar problemas que una prueba Headless no puede confirmar por sí sola: distribución de la interfaz, escenas visibles, recursos, renderizado y comportamiento del juego.

La importación inicial desde GitHub está implementada para repositorios públicos. La actualización incremental y automática de un proyecto que ya fue importado todavía no debe darse por disponible.

Consulta [Conectar repositorios públicos de GitHub a Godot Web](docs/GITHUB_TO_GODOT_WEB.md).

## Sistema de pruebas y capturas de navegador

El workflow principal es:

[**Importar repositorio en Godot Web — GitHub Actions**](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/workflows/godot-web-import.yml)

Permite ejecutar una prueba de navegador que:

1. Valida que la URL corresponda a un repositorio público de GitHub.
2. Resuelve la rama predeterminada o valida la rama indicada.
3. Abre Godot Web en Chromium bajo Xvfb.
4. Comprueba el aislamiento del navegador y la disponibilidad de `SharedArrayBuffer`.
5. Verifica que el relay entregue el ZIP y que el archivo quede asignado al campo oficial de importación de Godot.
6. Espera a que el Project Manager procese el proyecto.
7. Intenta abrir el proyecto en el editor.
8. Comprueba mediante logs y OCR que el editor y el proyecto esperado estén visibles.
9. Captura una imagen del editor y solicita una secuencia consecutiva.
10. Intenta ejecutar la escena principal con F5 y, si funciona, captura el preview y otra secuencia.

### Parámetros configurables

Al iniciar manualmente el workflow (`workflow_dispatch`) se pueden ajustar:

| Parámetro | Valor predeterminado | Límite |
|---|---:|---:|
| `repository_url` | Repositorio de referencia Dragon Realm | URL HTTPS de GitHub |
| `branch` | Vacío = rama predeterminada | Nombre de rama válido |
| `project_path` | Vacío = raíz | Ruta relativa a la carpeta con `project.godot` |
| `startup_timeout` | 180 s | 60–300 s |
| `editor_frames` | 5 | 1–12 |
| `editor_interval_ms` | 900 ms | 100–5000 ms |
| `game_frames` | 8 | 1–24 |
| `game_interval_ms` | 500 ms | 100–5000 ms |

Los valores fuera de rango se limitan al rango permitido. Las secuencias registran la cantidad solicitada, la cantidad capturada, el intervalo, la duración y los datos básicos de cada imagen.

**Detección dinámica del proyecto:** el workflow valida el repositorio público, resuelve la rama y comprueba `project.godot` en la raíz o en la carpeta indicada. Lee `config/name` desde ese archivo y usa ese nombre en el diálogo nativo de instalación. La apertura se confirma mediante el log `Editing project:` y la ruta real del proyecto bajo `/home/web_user/`.

**Compatibilidad:** el código del Relay admite ramas predeterminadas o explícitas y reempaqueta proyectos de subcarpetas para que `project.godot` quede en la raíz del ZIP. Las pruebas unitarias cubren ambos casos. La activación de estas capacidades en el sitio público depende de que Render despliegue la revisión más reciente.

### Validación de cada imagen

Cada frame de una secuencia se valida antes de considerarlo capturado:

- Debe existir una imagen PNG válida.
- Debe superar el tamaño mínimo de archivo.
- Debe tener dimensiones mínimas de 500 × 300.
- Se registra su índice y metadatos.
- El manifiesto indica si la secuencia está completa.
- Si falta un frame solicitado, la secuencia falla en lugar de presentarse como completa.

La verificación visual usa capturas escalonadas de Playwright, CDP y X11 durante un máximo de 90 segundos. El indicador `rendererResponsive` queda como diagnóstico y no bloquea la prueba por sí solo. Se exige OCR de la interfaz del editor y confirmación de la ruta mediante logs. Después de F5 se vuelve a capturar la vista Game y, cuando se detecta, se obtiene una secuencia independiente.

Los errores de carga de recursos del proyecto (por ejemplo, `Parse Error` o `Failed loading resource`) se registran por separado como advertencias del proyecto. No invalidan por sí solos que el editor haya abierto y sea visible, pero sí impiden describir el proyecto como completamente limpio o listo para ejecutar. La prueba del editor y la salud interna del proyecto son resultados distintos.

### Artefactos de Actions

Los artefactos se publican al terminar el workflow y se conservan durante 14 días. Según las etapas que hayan podido ejecutarse, incluyen:

- `godot-project-manager.png`: Project Manager.
- `godot-editor-open.png`: editor abierto.
- `godot-game-preview.png`: preview del juego, si F5 funciona.
- `editor-sequence-*.png`: frames consecutivos del editor.
- `game-preview-sequence-*.png`: frames consecutivos del preview.
- `editor-sequence-contact-sheet.png`: hoja de contacto del editor.
- `game-preview-sequence-contact-sheet.png`: hoja de contacto del preview.
- `*-sequence.json`: manifiestos con el estado y metadatos de cada secuencia.
- `result.json`: resumen estructurado del resultado.
- `browser-events.json`: eventos de consola, errores y solicitudes fallidas.
- Archivos OCR y capturas de diagnóstico cuando están disponibles.

Una captura individual no demuestra que una secuencia esté completa. Una secuencia completa tampoco demuestra por sí sola que el juego funcione correctamente: debe revisarse junto con el resultado de ejecución, OCR, logs y demás pruebas.

## Inspección dentro del editor Godot

El repositorio contiene un sandbox y complementos experimentales para inspección. Las capacidades documentadas incluyen lectura de estado y archivos, inspección de escenas, apertura de escenas, selección de nodos y captura de vistas 2D/3D.

Estas funciones tienen distintos niveles de madurez. La existencia del código o el éxito de un test aislado no significa que todas estén disponibles en la instancia publicada de Godot Web. Antes de anunciar una capacidad como operativa, revisar su estado y evidencia en:

- [Capacidades de inspección Godot verificadas](docs/VERIFIED_GODOT_INSPECTION_CAPABILITIES.md)
- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Centro de mando](docs/COMMAND_CENTER.md)

La inspección debe permanecer acotada y de solo lectura mientras no exista un flujo seguro de propuestas, diferencias, copias de recuperación y aprobación explícita para cambios remotos.

## Seguridad y protección de proyectos

- No incluir tokens, contraseñas ni claves privadas en el repositorio, capturas o logs.
- No exponer credenciales de GitHub al navegador.
- Validar las URLs antes de descargar repositorios.
- Restringir rutas de archivos y operaciones de inspección al proyecto seleccionado.
- No mezclar archivos, capturas o resultados de proyectos distintos.
- No sobrescribir cambios locales sin detectar y preservar las modificaciones.
- No habilitar shell remoto ni ejecución arbitraria como parte de una inspección.
- Mantener separada la copia de trabajo de cualquier copia que el usuario considere aceptada.
- Las operaciones de escritura futuras deben contar con diff, revisión base, respaldo y aprobación explícita.

## Servicios desplegados

- **Editor Godot Web:** https://godot-web-ia-integrada-rt2l.onrender.com/
- **Relay:** https://godot-web-ia-relay.onrender.com/
- **Salud del relay:** https://godot-web-ia-relay.onrender.com/health
- **Repositorio de este sistema:** https://github.com/decuvilan-lgtm/Godot-web-ia-integrada

Los servicios Render deben permanecer en el plan Free. El relay puede suspenderse por inactividad; no debe tratarse como almacenamiento persistente.

## Estado actual resumido

| Área | Estado |
|---|---|
| Editor Godot Web 4.7.2 publicado | Implementado |
| Inicio del Project Manager en navegador | Implementado; revisar en ejecución real |
| Importación inicial desde repositorio público | Implementada en código; despliegue actualizado pendiente de verificar |
| URL, rama y subcarpeta configurables en Actions | Implementadas en código y cubiertas por pruebas |
| Apertura de proyecto en Godot Web | Probada: ruta confirmada y editor visible |
| Captura individual del editor | Probada con Playwright/CDP; secuencia completa 5/5 |
| Secuencias configurables de capturas | Probadas: editor 5/5 y juego 8/8; dimensiones PNG verificadas |
| Advertencias de carga del proyecto | Se separan de la verificación de apertura; requieren revisar los recursos del proyecto objetivo |
| Validación de PNG y manifiestos | Implementada en el workflow |
| Hojas de contacto | Implementadas en el workflow; validar en la siguiente ejecución |
| Captura del preview F5 | Probada: se abrió el menú inicial y se capturaron 8/8 frames |
| Detección dinámica de nombre/ruta del proyecto en repositorios compatibles | Implementada; validación visual del proyecto de referencia pendiente de corregir |
| Compatibilidad con ramas distintas de `main` o proyectos en subcarpetas | Implementada en código y con pruebas unitarias; E2E y despliegue público pendientes |
| Actualización incremental del proyecto ya importado | Pendiente |
| Captura de interfaz completa, zoom arbitrario y vistas adicionales | Pendiente de backend/validación |
| Prueba integral de todas las capacidades del sandbox en la instancia publicada | Pendiente |

**Evidencia visual:** la ejecución [43158048268](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43158048268) abrió el editor y el juego de referencia. El editor produjo 5/5 capturas y el menú del juego 8/8. El estado fue `passed-with-project-warnings` porque Godot informó `Parse Error: Busy` al cargar `res://scenes/ui/hud.tscn`; ese error pertenece al proyecto de referencia y no impidió mostrar su menú inicial. La ejecución 43158048268 también detectó un defecto en el manifiesto de dimensiones de la secuencia Playwright; el parseo se corrigió en el commit `1e65b78`, cuya validación posterior debe confirmar que los campos ancho/alto ya no aparecen nulos.\n\n**Despliegue:** Render informa que el servicio Relay tiene auto-deploy habilitado, pero su último despliegue visible sigue apuntando a una revisión anterior. Por ello, las mejoras de rama/subcarpeta y la versión más reciente del shell están documentadas como implementadas en el repositorio, no como ya activas en producción. La verificación final requiere que Render registre un despliegue nuevo y repetir la prueba con un proyecto en subcarpeta.

## Documentación técnica

- [Arquitectura técnica](docs/ARCHITECTURE.md)
- [Flujo de desarrollo Headless + GitHub](docs/HEADLESS_DEVELOPMENT_WORKFLOW.md)
- [Importación GitHub → Godot Web](docs/GITHUB_TO_GODOT_WEB.md)
- [Capacidades de inspección verificadas](docs/VERIFIED_GODOT_INSPECTION_CAPABILITIES.md)
- [Observación visual](docs/VISUAL_OBSERVATION.md)
- [Contrato de comandos visuales](docs/VISUAL_COMMANDS.md)
- [Centro de mando](docs/COMMAND_CENTER.md)
- [Relay y variables de entorno](relay/README.md)
- [Sandbox de integración](examples/bridge-sandbox/project.godot)

## Principios para continuar el desarrollo

1. El sistema es una herramienta general para proyectos Godot, no una herramienta exclusiva de Dragon Realm.
2. Cada prueba debe recibir explícitamente el repositorio o proyecto objetivo.
3. Los nombres de proyecto, rutas, escenas y recursos deben descubrirse dinámicamente siempre que sea posible.
4. Las pruebas Headless y las pruebas visuales deben complementarse.
5. Cada ejecución debe producir evidencia identificada y aislada.
6. Las secuencias deben capturar exactamente la cantidad solicitada o marcarse como incompletas.
7. Las capacidades no verificadas deben figurar como pendientes, sin presentarlas como terminadas.
8. Las mejoras deben integrarse al flujo general y reutilizarse entre proyectos, evitando soluciones especiales para un solo juego.
