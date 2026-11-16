# Flujo de desarrollo: Godot Headless Linux + editor visual

## Principio de trabajo

**Godot Headless Linux es el entorno principal de construcción y prueba.** El agente trabaja sobre una copia aislada del proyecto mediante archivos, escenas .tscn, recursos, scripts y configuraciones. No necesita manejar la interfaz para crear contenido ni depende de coordenadas, clics o automatización de ventanas para programar el juego.

**Godot Editor real es la estación de inspección visual.** Se utiliza después de que Headless haya importado y validado el proyecto para comprobar cómo se ven las escenas, la jerarquía, el Inspector, los recursos y el juego en ejecución. El Headless Session Bridge permite consultar el estado del editor y solicitar operaciones acotadas desde el proceso operador; no convierte la interfaz en el mecanismo principal de autoría.

El proyecto es la unidad de trabajo. No se depende de un repositorio de juego predeterminado: el usuario elige el proyecto y el sistema crea una copia de trabajo aislada.

## Ciclo de desarrollo obligatorio

1. **Seleccionar y aislar el proyecto.** Registrar origen/commit cuando exista y crear una copia de trabajo sin modificar el original.
2. **Construir desde Linux Headless.** Crear y editar scripts GDScript, escenas .tscn, recursos, datos y configuraciones directamente en la copia de trabajo. Mantener cambios pequeños, organizados y reutilizables.
3. **Importar y validar.** Ejecutar Godot con --headless --editor --path <proyecto> --quit para importar recursos y detectar errores de parseo/importación. Revisar el código de salida y los logs; no basta con que el proceso se haya iniciado.
4. **Probar comportamiento.** Ejecutar pruebas automatizadas y el juego con --headless --path <proyecto> (con límite de tiempo cuando corresponda). Añadir pruebas reproducibles para mecánicas, escenas, datos y regresiones.
5. **Revisar visualmente en el editor real.** Abrir la misma copia de trabajo en Godot Editor. Consultar la escena activa, árbol de nodos, selección, Inspector, recursos y preview mediante el puente. Capturar evidencia visual cuando ayude.
6. **Corregir y repetir.** Si la inspección visual revela problemas, corregir los archivos desde el flujo Headless, volver a importar y ejecutar pruebas; después repetir la inspección. No resolver problemas de diseño a base de hacer clics a ciegas.
7. **Revisar el diff.** Confirmar exactamente qué archivos cambiaron y que pertenecen al proyecto seleccionado.
8. **Sincronizar/publicar solo con aprobación.** Reflejar los archivos probados en la rama de trabajo correspondiente. El original permanece intacto; exportar o publicar cambios requiere revisión explícita.

## Responsabilidades separadas

| Componente | Responsabilidad principal |
|---|---|
| Godot Headless Linux | Autoría por archivos, importación, parseo, ejecución y pruebas automatizadas |
| Copia de trabajo local | Fuente de verdad durante el ciclo de desarrollo |
| Godot Editor real | Inspección visual de escenas, nodos, Inspector, recursos y preview |
| Headless Session Bridge | Consultas y operaciones acotadas sobre la instancia del editor; nunca automatización por coordenadas |
| Integración GitHub | Sincronizar archivos y commits de forma controlada |
| Godot Web/Chromium | Revisión visual/sincronización web cuando sea necesario; no reemplaza Headless |

## Reglas de automatización

- No usar clics, coordenadas ni automatización de ventanas como método normal para crear niveles o programar.
- No exigir que la IA manipule manualmente cada nodo desde el editor cuando el archivo de escena puede generarse y validarse de forma determinista.
- No asumir que un proyecto headless válido se ve bien: la revisión visual sigue siendo obligatoria para cambios de presentación.
- No afirmar que una prueba visual se realizó si solo se ejecutó Headless.
- No afirmar que una prueba Headless se realizó si el ejecutable no estaba disponible.
- No instalar el puente en el proyecto original: solo en una copia aislada y cuando se necesite inspección desde el editor.
- No ejecutar GDScript arbitrario recibido como comando del puente. La autoría de scripts ocurre como cambios de archivos en el workspace aislado y se valida con el runtime Godot.
- No publicar automáticamente ni modificar main.

## Disponibilidad del runtime

Antes de iniciar una tarea, comprobar que existe un ejecutable Godot compatible y registrar su versión. Si no está instalado en el entorno de trabajo, no fingir que las pruebas locales se ejecutaron: preparar los cambios y usar el workflow Linux de CI como validación temporal, o detener la fase de ejecución hasta disponer del runtime. La inspección del editor real es una etapa distinta y no sustituye esa validación.

El entorno Linux de trabajo puede no tener salida directa a Internet. En ese caso, recuperar los archivos mediante la integración GitHub de ChatGPT y no crear relays, proxies o servicios nuevos para sortear esa limitación.

## Pruebas y reporte

Cada iteración debe dejar evidencia verificable de:
- versión y ruta del ejecutable Godot utilizado;
- importación/parseo y código de salida;
- pruebas ejecutadas y sus resultados;
- logs y errores relevantes;
- inspección visual realizada en el editor real, si se hizo;
- diff exacto de archivos.

Al terminar, informar qué se construyó, qué se probó en Headless, qué se inspeccionó visualmente y qué limitaciones quedaron pendientes.

## Sincronización con GitHub

Para transferencias iniciales o amplias se puede usar .github/workflows/export-headless-workspace.yml y verificar commit/SHA-256. Para cambios pequeños, recuperar y actualizar solo los archivos necesarios. Como el entorno Linux puede no tener salida a Internet, las operaciones remotas se realizan mediante la integración GitHub disponible en ChatGPT. Nunca sobrescribir cambios remotos sin leer la versión actual y respetar SHA/concurrencia.

**Principio clave:** construir y probar primero en Godot Headless; inspeccionar después en el editor real; corregir desde el workspace sin depender de clics; sincronizar únicamente los cambios revisados.
