# Godot Web IA Integrada

Entorno de desarrollo basado en Godot Web, con una capa propia de automatización para que un agente pueda inspeccionar y editar proyectos sin sustituir el editor real.

> Estado: **fundación inicial**. Esta rama prepara el editor web oficial y define la arquitectura del puente. No afirma todavía que exista una sesión remota persistente ni que la IA pueda operar el editor de extremo a extremo.

## Objetivos

- Ejecutar el editor Godot Web desde navegador, también en Android.
- Mantener los proyectos del usuario separados de los cambios experimentales del agente.
- Exponer operaciones estructuradas para inspeccionar proyectos, escenas, nodos, recursos y scripts.
- Permitir que el agente proponga cambios, los valide y los aplique de forma explícita.
- Ejecutar pruebas y devolver resultados observables, capturas y registros.
- Sincronizar el mismo proyecto entre la sesión de trabajo remota y el navegador del usuario.

## Base del motor

La primera versión usa el paquete web oficial **Godot 4.7.2-stable** publicado por el proyecto Godot. El script de compilación descarga el archivo oficial y verifica su SHA-256 antes de publicarlo. El código fuente del motor se incorporará como submódulo en una fase posterior para mantener los cambios propios separados del upstream.

- Motor: https://github.com/godotengine/godot
- Versión fijada: 4.7.2-stable
- Paquete web: Godot_v4.7.2-stable_web_editor.zip
- Licencia del motor: MIT; consultar los avisos oficiales incluidos en la distribución.

## Despliegue

Render Static Site:
- Build command: `bash scripts/build-web.sh`
- Publish directory: `public`
- Los encabezados COOP/COEP están declarados en `render.yaml` para habilitar aislamiento de origen cuando el navegador y el paquete lo requieran.

## Arquitectura prevista

1. **Web Editor**: distribución web oficial del editor Godot.
2. **AI Bridge**: API local/remota con permisos limitados y operaciones tipadas.
3. **Project Workspace**: almacenamiento versionado de proyectos y snapshots.
4. **Scene & Script Controllers**: lectura, edición y validación de escenas y scripts.
5. **Test Runner**: ejecución aislada de pruebas y recolección de logs.
6. **Visual Observer**: capturas de pantalla y estado visual del editor/juego.
7. **Sync Manager**: sincronización entre la sesión remota y el navegador Android.

## Seguridad y límites

- No se deben exponer tokens ni secretos en el navegador o en Git.
- El puente no debe aceptar comandos de shell arbitrarios desde el cliente.
- Las operaciones destructivas deben requerir confirmación y generar snapshot previo.
- El agente trabaja primero en una copia/sandbox; el proyecto del usuario solo cambia al aceptar.
- El editor web no equivale al editor nativo: depuración, exportación y funciones de plataforma se evaluarán por separado.

## Desarrollo

Consulta [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) para el diseño técnico y las etapas de implementación.
