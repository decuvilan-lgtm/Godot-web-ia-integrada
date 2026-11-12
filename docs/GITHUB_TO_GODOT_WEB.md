# Conectar repositorios públicos de GitHub a Godot Web

## Objetivo

Importar proyectos Godot públicos desde GitHub mediante el importador ZIP oficial de Godot Web. El Project Manager nativo sigue siendo la interfaz de gestión; no se sustituye por otro administrador.

## Flujo

1. Godot Web inicia el Project Manager.
2. El botón **Conectar GitHub** permite introducir `owner/repository`, una rama opcional y una carpeta opcional.
3. Si la rama queda vacía, el Relay resuelve la rama predeterminada del repositorio mediante la API pública de GitHub.
4. Si la ruta queda vacía, se espera `project.godot` en la raíz. Si se indica una ruta, el Relay valida esa carpeta y genera un ZIP cuyo `project.godot` queda en la raíz del archivo.
5. El navegador solicita el ZIP al Relay, lo asigna al campo oficial `Preload project ZIP` y activa el inicio del editor.
6. Godot procesa el archivo con su Project Manager. La instalación final usa el diálogo nativo de Godot.

También se admiten enlaces directos:

```text
https://godot-web-ia-integrada-rt2l.onrender.com/?repo=OWNER/REPOSITORY
https://godot-web-ia-integrada-rt2l.onrender.com/?repo=OWNER/REPOSITORY&branch=develop
https://godot-web-ia-integrada-rt2l.onrender.com/?repo=OWNER/REPOSITORY&branch=master&path=2d/platformer
```

Los parámetros `branch` y `path` son opcionales. Los valores se codifican como parámetros URL normales.

## Relay

Endpoint:

```text
GET /v1/github/{owner}/{repository}/archive?branch=BRANCH&path=PROJECT_PATH
```

Contrato de seguridad y límites:

- Solo repositorios públicos; no se envían tokens GitHub al navegador.
- La rama se valida antes de construir la URL de codeload. Si no se especifica, se consulta `default_branch` en la API de GitHub.
- El host upstream está fijado a `codeload.github.com`; se valida el host final de las redirecciones.
- La ruta del proyecto no admite rutas absolutas, segmentos `.` o `..`, barras invertidas ni caracteres de control.
- El ZIP comprimido está limitado a 128 MiB; el proyecto seleccionado se limita a 256 MiB descomprimidos.
- Para proyectos en subcarpetas, el Relay extrae de forma segura solo esa carpeta y la vuelve a empaquetar con `project.godot` en la raíz.
- La descarga tiene timeout y concurrencia limitada; se usa almacenamiento temporal con memoria acotada.
- La respuesta identifica repositorio y rama mediante cabeceras; `X-GitHub-Ref` está expuesta a CORS para que el navegador pueda nombrar el ZIP correctamente.
- Las respuestas no se almacenan en caché.

Los repositorios privados no están habilitados. No se debe añadir un token GitHub al JavaScript del navegador.

## Pruebas

Las pruebas unitarias del Relay cubren:
- Resolución de la rama predeterminada.
- Ramas con subdirectorios, como `release/2.0`.
- Validación de nombres de rama y rutas.
- Selección y reempaquetado de proyectos en subcarpetas.
- Rechazo cuando falta `project.godot`.
- Límite de tamaño y cabeceras CORS.

La importación visual del proyecto de referencia confirmó:
- ZIP precargado y apertura de la ruta del proyecto.
- Editor visible con 5/5 capturas consecutivas.
- F5 abre el menú del juego y permite 8/8 capturas consecutivas.
- Las imágenes PNG se validan y sus manifiestos registran dimensiones, tiempos y tamaños.

La ejecución también registró una advertencia del proyecto de referencia: `Parse Error: Busy` al cargar `res://scenes/ui/hud.tscn`. No impidió abrir el editor ni mostrar el menú inicial, pero requiere revisar el proyecto por separado.

## Límites y estado de despliegue

- El flujo de importación inicial no hace `git pull` sobre un proyecto ya importado.
- No reemplaza automáticamente archivos locales; una actualización futura debe preservar cambios del usuario y ofrecer comparación.
- Todavía no registra el SHA del commit importado como metadato del proyecto.
- La importación inicial termina en el diálogo nativo de Godot; no automatiza controles internos del canvas que no formen parte del shell web.
- El código de rama predeterminada y subcarpetas está implementado y cubierto por pruebas del repositorio. Su disponibilidad en el sitio público depende de que Render despliegue los commits más recientes. La última consulta de despliegues aún mostraba una revisión anterior, por lo que no se debe dar esa parte por activa en producción hasta comprobar el nuevo deploy.

## Responsabilidad del asistente

ChatGPT puede preparar el enlace y revisar los resultados de una ejecución de GitHub Actions. La navegación y el trabajo en la pestaña Godot Web ocurren en el navegador; esta conversación no controla automáticamente una pestaña abierta por el usuario.
