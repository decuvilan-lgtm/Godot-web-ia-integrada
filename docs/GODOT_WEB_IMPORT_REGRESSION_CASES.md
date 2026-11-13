# Casos de regresión: importación Godot Web

Este registro conserva fallos reales del flujo GitHub → Relay → navegador → Godot Web y las barreras que evitan repetirlos. Cada caso debe incluir síntoma, causa comprobada, corrección y una prueba reproducible.

## GWI-001 — El ZIP nunca llega al control de archivos

- **Detectado:** 2026-11-12, al importar `gavilandavid89-pixel/Ajedrez-2c2`, rama `main`, carpeta `ajedrez_2c2_v161`.
- **Ejecución fallida:** [GitHub Actions #43347432516](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43347432516).
- **Síntoma:** Godot Web muestra Project Manager vacío; `#zip-file` permanece con `files.length === 0` y la automatización agota el timeout.
- **Qué sí se comprobó:** la página del editor responde; el Relay entrega HTTP 200 para su fixture y reempaqueta correctamente un proyecto de subcarpeta. Eso no prueba que el conector de navegador haya descargado ni asignado el ZIP del proyecto objetivo.
- **Causa probable identificada por inspección estática (pendiente de confirmar con la versión desplegada):** el conector original ejecutaba su trabajo dentro de un listener de `window.load` y hacía `if (!startButton || startButton.disabled) return;`. Si Godot todavía mantenía Start deshabilitado al dispararse el evento, el listener terminaba sin descargar el ZIP y sin dejar una señal de error estructurada. Además, depender solo de `load` no cubría restauraciones donde el script pudiera ejecutarse después de ese evento. La ejecución posterior #43348575005 siguió usando el conector publicado `branch-path-v1`, por lo que no pudo validar ni refutar el parche `branch-path-v2`.
- **Corrección introducida en la rama de prueba:** el conector espera explícitamente a que existan `#startButton` y `#zip-file`; realiza la descarga antes de arrancar Godot; verifica que el navegador conserve exactamente un archivo con el nombre esperado; registra fases en `window.__godotGithubConnectorStatus`; y espera a que Start esté habilitado en lugar de abandonar la importación. El arranque se programa según `document.readyState`, cubriendo tanto DOM aún cargando como DOM ya preparado.
- **Prevención:** la prueba E2E ahora termina con el error real del conector si este informa `phase: failed`, en vez de ocultarlo detrás de un timeout genérico. Las pruebas unitarias del parche comprueban que no vuelva a existir el retorno prematuro por `startButton.disabled`.
- **Estado:** corrección y pruebas añadidas a `test/ajedrez-2c2-readonly`; pendiente validar el despliegue de esa versión en el editor publicado y completar una importación E2E. No declarar resuelto hasta que el artefacto confirme nombre del ZIP, rama, ruta y proyecto abierto.

### Criterios obligatorios para cerrar GWI-001

1. Las pruebas unitarias del parche web pasan.
2. La importación E2E observa `#zip-file.files.length === 1`.
3. El nombre del ZIP coincide con repositorio y rama solicitados.
4. El Relay confirma la rama y la carpeta seleccionadas, y el ZIP tiene `project.godot` en la raíz.
5. Godot registra la apertura del proyecto objetivo y una captura visual/OCR identifica el proyecto esperado.
6. El resultado conserva la fase del conector, la URL de entrada y el diagnóstico en artefactos.

## GWI-002 — La prueba E2E ejecuta una versión antigua del editor publicado

- **Detectado:** 2026-11-12, al validar el parche GWI-001.
- **Ejecución:** [GitHub Actions #43348575005](https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/actions/runs/43348575005).
- **Síntoma:** las pruebas unitarias pasan, pero la importación E2E vuelve a esperar 180 segundos y el ZIP nunca aparece.
- **Causa comprobada:** el workflow del repositorio de pruebas carga el editor alojado en Render, que todavía sirve el conector `branch-path-v1`. El parche `branch-path-v2` existe únicamente en la rama `test/ajedrez-2c2-readonly`; cambiar una rama GitHub no actualiza por sí solo el servicio publicado. Por eso esa ejecución no estaba probando el código recién corregido.
- **Corrección preventiva:** el workflow consulta `#godot-github-connector[data-version]` al abrir el editor y exige `branch-path-v2`. Si Render sirve otra versión, falla inmediatamente con un mensaje claro, sin consumir el timeout de tres minutos.
- **Estado:** precondición de versión añadida a la rama de prueba. Para la validación E2E real, el editor publicado debe recibir primero el parche de la rama correspondiente mediante el proceso de despliegue autorizado.

### Criterios para cerrar GWI-002

1. El editor publicado informa `data-version="branch-path-v2"`.
2. El workflow supera la comprobación de versión antes de esperar el ZIP.
3. Si el servicio vuelve a una versión anterior, la prueba falla en preflight y registra la versión detectada.

## Reglas para nuevos casos

- No atribuir un fallo al Relay solo porque Godot muestre el Project Manager vacío: separar respuesta HTTP, contenido ZIP, asignación al input, inicio del motor e identidad del proyecto.
- No interpretar HTTP 200 de un fixture como prueba de descarga del repositorio objetivo.
- No cambiar un timeout para esconder una condición de carrera; registrar primero la fase exacta donde se detuvo el flujo.
- No marcar una importación como exitosa solo porque se hizo clic en Start. Exigir evidencia de proyecto abierto e identidad verificada.
- Mantener los repositorios objetivo en solo lectura salvo autorización explícita y separada.
