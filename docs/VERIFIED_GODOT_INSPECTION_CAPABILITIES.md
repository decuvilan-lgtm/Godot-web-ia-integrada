# Capacidades de inspección Godot verificadas

Este documento registra capacidades que ya se ejecutaron y observaron en CI usando Godot 4.7.2 sobre Linux/Xvfb. La implementación de referencia está en el repositorio de pruebas `gavilandavid89-pixel/Escondite`; **no significa que estas funciones estén conectadas automáticamente al editor web desplegado ni al Command Center de este repositorio**. Se documentan aquí como capacidades reutilizables para el agente de desarrollo.

## Evidencia confirmada

### Ejecución headless y validación de proyecto
- Descarga de una versión fijada de Godot 4.7.2 y comprobación SHA-512 del paquete.
- Importación del proyecto y validación de scripts con Godot en modo editor/headless.
- Ejecución de pruebas de integración del mundo y de carreras/habilidades.
- Ejecución de una suite de siete regresiones: razas, combate de habilidades, progresión, barrera de selección, estadísticas, balance de mobs e integración VFX.
- En la ejecución visual correcta indicada abajo, todos esos pasos terminaron en estado `success`.

### Capturas visuales automatizadas
- Arranque del editor Godot en una pantalla virtual Xvfb (display :99).
- Capturas de menú y vistas de juego/mapas.
- Captura del editor, workspace 2D, scripts y modos de presentación del juego.
- Captura del juego en ventana sobre el editor y captura del juego a pantalla completa.
- Las imágenes y logs se empaquetan como artefacto de Actions con retención de 14 días.

### Navegación e inspección de escenas
- Un complemento EditorPlugin recibe comandos externos desde archivos JSON.
- Abre una escena mediante EditorInterface, espera al árbol de escena y verifica que la raíz editada corresponde a la ruta solicitada.
- Selecciona la raíz o un nodo solicitado y comprueba que la selección aparece en EditorInterface.get_selection().
- Una ejecución CI completó **32 de 32 comandos** y guardó **32 capturas** de vistas de escena/nodo.
- El flujo usa Xvfb y capturas de pantalla reales del escritorio del editor; no son imágenes duplicadas generadas desde el inventario.

## Ejecuciones de referencia

| Run | Resultado | Evidencia |
|---|---|---|
| [43106936057](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43106936057) | Correcto | 32 comandos verificados; 32 vistas capturadas; ventana y pantalla completa |
| [43107522110](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43107522110) | Correcto | Suite headless/regresión, capturas y 32 inspecciones completadas |
| [43108334454](https://github.com/gavilandavid-pixel/Escondite/actions/runs/43108334454) | Fallido parcialmente | Las validaciones y capturas de juego pasan; inspección se detiene en el tercer comando |

## Fallo conocido y límites actuales

La última ejecución, [43108334454](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43108334454), terminó con:
- Importación, validación, integración, prueba de razas/habilidades y siete regresiones: correctas.
- Capturas de menú y juego: correctas.
- Editor: abre y verifica `Main.tscn` y la raíz de `scenes/enemies/enemy.tscn`.
- Falla al seleccionar `CollisionShape2D` en `enemy.tscn`: `node_not_found`.

Por tanto, la selección de raíces de escenas está probada; la selección de todos los nodos hijos todavía no. No afirmar que la navegación completa del árbol esté resuelta.

La inspección del editor aún no demuestra:
- Captura exhaustiva de todas las páginas del Inspector y Project Settings.
- Lectura y exportación de logs útiles del debugger durante una sesión ejecutada desde el propio editor.
- Inspección completa de pestañas superiores, docks y opciones de cada panel.
- Captura UI/preview/zoom integrada con el servicio Neon del editor web.
- Control remoto de escritura o ejecución arbitraria.

## Cómo reutilizarlo en este proyecto

1. Mantener el Command Center como canal autenticado y limitado; no introducir shell remoto ni escritura implícita.
2. Adaptar la inspección como acciones explícitas y auditables del rol `web_editor`, con límites de rutas, profundidad, tamaño y tiempo.
3. Separar resultado de comando, verificación observable y captura asociada.
4. Conservar el principio de solo lectura hasta que exista un sistema separado de propuestas, diff, snapshot y aprobación explícita.
5. Antes de marcar una capacidad como integrada, probarla dentro del editor Godot Web publicado; una prueba en Escondite solo demuestra que la técnica funciona en un proyecto Godot de referencia.

## Regla de documentación

Cada capacidad futura debe etiquetarse como **Implementada**, **Probada**, **Aprobada** o **Pendiente**. La presencia de código no equivale a funcionamiento. Añadir siempre el enlace de CI, el resultado, el número de elementos procesados y cualquier limitación observada.
