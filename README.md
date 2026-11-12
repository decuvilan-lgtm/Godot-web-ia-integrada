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

Se identifica el repositorio y la rama que se van a trabajar. El sistema debe usar la identidad del repositorio y su revisión, no solamente el nombre visible del proyecto. El importador web actual admite repositorios públicos de GitHub desde la rama `main`.

Enlace de apertura:

```text
https://godot-web-ia-integrada-rt2l.onrender.com/?repo=OWNER/REPOSITORY
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
2. Comprueba que exista la rama `main`.
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
| `startup_timeout` | 180 s | 60–300 s |
| `editor_frames` | 5 | 1–12 |
| `editor_interval_ms` | 900 ms | 100–5000 ms |
| `game_frames` | 8 | 1–24 |
| `game_interval_ms` | 500 ms | 100–5000 ms |

Los valores fuera de rango se limitan al rango permitido. Las secuencias registran la cantidad solicitada, la cantidad capturada, el intervalo, la duración y los datos básicos de cada imagen.

**Detección dinámica del proyecto:** el workflow valida el repositorio público seleccionado, comprueba que exista `project.godot` en la raíz de `main`, lee `config/name` desde ese archivo y usa ese nombre en el diálogo nativo de instalación y en la verificación OCR. La apertura se confirma leyendo la ruta real `Editing project:` emitida por Godot bajo `/home/web_user/`; ya no depende del nombre Dragon Realm ni de una carpeta fija. El nombre del repositorio se usa como alternativa si `config/name` no está definido.

**Límites actuales:** el relay y el workflow siguen descargando exclusivamente la rama `main`, y el proyecto Godot debe tener `project.godot` en la raíz del repositorio. Los proyectos alojados en subcarpetas o cuya rama principal tenga otro nombre requieren ampliar el importador antes de considerarlos compatibles.

### Validación de cada imagen

Cada frame de una secuencia se valida antes de considerarlo capturado:

- Debe existir una imagen PNG válida.
- Debe superar el tamaño mínimo de archivo.
- Debe tener dimensiones mínimas de 500 × 300.
- Se registra su índice y metadatos.
- El manifiesto indica si la secuencia está completa.
- Si falta un frame solicitado, la secuencia falla en lugar de presentarse como completa.

La captura utiliza Chrome DevTools Protocol para reducir la dependencia de la ejecución de JavaScript dentro de Godot Web, cuyo hilo principal puede quedar ocupado durante la inicialización del editor.

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
| Importación inicial desde repositorio público `main` | Implementada |
| URL de repositorio configurable en Actions | Implementada |
| Apertura de proyecto en Godot Web | Prueba anterior aprobada; las ejecuciones genéricas recientes confirman la ruta en logs, pero fallan la verificación visual del editor |
| Captura individual del editor mediante CDP | Probada con el proyecto de referencia |
| Secuencias configurables de capturas | Implementadas en el workflow; falta validar el último cambio con una ejecución completa |
| Validación de PNG y manifiestos | Implementada en el workflow |
| Hojas de contacto | Implementadas en el workflow; validar en la siguiente ejecución |
| Captura del preview F5 | Probada con el proyecto de referencia; opcional y sujeta a que el proyecto pueda ejecutarse |
| Detección dinámica de nombre/ruta del proyecto en repositorios compatibles | Implementada; validación visual del proyecto de referencia pendiente de corregir |
| Compatibilidad con ramas distintas de `main` o proyectos en subcarpetas | Pendiente |
| Actualización incremental del proyecto ya importado | Pendiente |
| Captura de interfaz completa, zoom arbitrario y vistas adicionales | Pendiente de backend/validación |
| Prueba integral de todas las capacidades del sandbox en la instancia publicada | Pendiente |

**No confundir estados:** “Implementado” significa que existe código; “Probado” significa que se ejecutó una prueba concreta; “Pendiente” significa que no hay evidencia suficiente para darlo por funcional.

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
