# Conectar repositorios públicos de GitHub a Godot Web

## Objetivo

Permitir que ChatGPT prepare la conexión de un repositorio de juego y que Godot Web lo reciba mediante su importador ZIP oficial. El Project Manager nativo sigue siendo la interfaz de gestión; no se crea otro administrador.

## Flujo actual implementado

1. El usuario abre Godot Web y el editor inicia el Project Manager automáticamente.
2. El botón **Conectar GitHub** está en la barra superior del shell web.
3. Al introducir owner/repository, el shell valida el formato y solicita confirmación antes de recargar la página.
4. La URL se recarga con el parámetro ?repo=owner/repository.
5. El shell solicita el ZIP al Relay, que lo obtiene de codeload.github.com desde la rama main.
6. El navegador convierte la respuesta en un File, lo asigna al campo oficial Preload project ZIP y pulsa el botón oficial Start Godot Editor.
7. Godot inicia su Project Manager y procesa el ZIP mediante su flujo de importación normal. El usuario termina la importación con los controles nativos de Godot (nombre/carpeta e Install & Edit, según el diálogo que presente esa versión).

También se puede construir un enlace directo a la página con ?repo=owner/repository. Esto permite que el asistente prepare un enlace exacto para el repositorio solicitado sin que el usuario tenga que descargar ni seleccionar un ZIP.

## Relay

Endpoint:

GET /v1/github/{owner}/{repository}/archive

Contrato:
- Solo repositorios públicos.
- Rama fija main; no se acepta una rama o URL arbitraria.
- El host upstream está fijado a https://codeload.github.com.
- Owner y nombre del repositorio se validan mediante expresiones permitidas.
- El host final de cualquier redirección se comprueba.
- Tamaño máximo del ZIP: 128 MiB.
- Descarga con timeout y concurrencia limitada; se usa un archivo temporal con memoria acotada.
- El navegador no recibe credenciales GitHub, Neon ni S3.
- Respuestas sin caché, con tipo ZIP y cabeceras que identifican repositorio y rama.

Los repositorios privados no están habilitados. No se debe añadir un token GitHub al JavaScript del navegador. El soporte privado requeriría una autorización de servidor con alcance mínimo.

## Responsabilidad del asistente

Cuando el usuario indique un repositorio público, ChatGPT puede preparar el enlace de conexión usando owner/repository y la rama main. La navegación real ocurre en el navegador del usuario: esta conversación no controla automáticamente una pestaña Godot Web que el usuario tenga abierta. El botón del shell también permite introducir el repositorio desde la propia página.

## Límites actuales

- La conexión precarga el ZIP oficial; no implementa todavía un git pull dentro del sistema de archivos IndexedDB.
- La importación inicial utiliza el diálogo nativo de Godot. No se automatizan los botones internos dibujados en el canvas.
- Una nueva versión de main no reemplaza todavía de forma automática un proyecto ya importado. Ese paso requiere una estrategia de actualización segura que preserve la última copia válida y los cambios locales.
- El SHA del commit aún no se registra en metadatos del proyecto importado. La API actual descarga el snapshot de main, pero no resuelve ni presenta el SHA.
- El importador requiere un navegador compatible con Godot Web y el mecanismo DataTransfer para precargar el ZIP.

## Pruebas de aceptación

1. Abrir Godot Web sin parámetros: debe iniciar el Project Manager nativo.
2. Abrir con ?repo=owner/repository: el Relay debe descargar el ZIP de main, el shell debe precargarlo y el Project Manager debe presentar la importación.
3. Confirmar que el navegador no envía tokens GitHub ni credenciales de almacenamiento.
4. Probar repositorio inexistente/privado, nombre inválido, timeout y ZIP superior a 128 MiB.
5. Verificar que un error de descarga no impide abrir el Project Manager sin ZIP.
6. Importar dos repositorios distintos y comprobar que quedan como proyectos independientes en el Project Manager.
7. Recargar la web y comprobar que los proyectos importados persisten en IndexedDB.
8. Confirmar que no se sobrescribe ningún proyecto ya importado al conectar otro repositorio.

**Estado:** el proxy y el preloader están implementados en main. El despliegue del Relay y del shell, junto con las pruebas reales en navegador, siguen pendientes de confirmación. La actualización automática de proyectos ya importados y la trazabilidad SHA siguen siendo trabajo futuro.
