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
| [43108334454](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43108334454) | Fallido parcialmente | Las validaciones y capturas de juego pasan; inspección se detiene en el tercer comando |

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


## Nueva corrección en validación (11 de noviembre de 2026)

- Diagnóstico del run [43108334454](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43108334454): el inventario detectó 32 escenas, 58 archivos GDScript y 36 nodos de escena; además exportó 974 propiedades efectivas de ProjectSettings.
- Las escenas raíz Main.tscn y enemy.tscn se abrieron y verificaron. La cola falló en el tercer comando al intentar resolver el hijo directo CollisionShape2D de enemy.tscn.
- El archivo de escena confirma que CollisionShape2D es hijo directo de la raíz Enemy. La hipótesis de trabajo es una condición de sincronización entre la apertura de la escena y la disponibilidad de sus nodos en el árbol del editor; todavía no está demostrada.
- Se actualizó el complemento de prueba para esperar hasta 120 frames a que la raíz solicitada quede activa y hasta 120 frames adicionales para resolver el nodo exacto. Si no aparece, ahora registra ruta, raíz y nombres de hijos antes de fallar.
- Commit de prueba: [b04ccb07c78aea2bd09d4a74b53e2ea267242595](https://github.com/gavilandavid89-pixel/Escondite/commit/b04ccb07c78aea2bd09d4a74b53e2ea267242595).
- Validaciones disparadas por ese commit: [Visual QA run 43110383661](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43110383661) y [Headless source export run 43110383804](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43110383804).
- Estado al documentar: **Pendiente de resultado**. No marcar la selección de nodos hijos como aprobada hasta que Visual QA termine y se compruebe el total de comandos y capturas.


## Resultado de la ejecución y corrección de sintaxis (11 de noviembre de 2026)

- Visual QA [run 43110383661](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43110383661) terminó en fallo. Las etapas de importación, integración, las 7 regresiones y las capturas del juego terminaron correctamente.
- El paso de inspección del editor no llegó a ejecutar el puente: GDScript rechazó la expresión que intentaba usar size()/get() sobre StringName al procesar NodePath. Por tanto, ese run no prueba el comportamiento de la espera de nodos.
- Se corrigió el acceso al último segmento usando NodePath.get_name_count() y NodePath.get_name(). Commit: [5f354c75356d0fc55708e3fab4f061cc79269ff5](https://github.com/gavilandavid89-pixel/Escondite/commit/5f354c75356d0fc55708e3fab4f061cc79269ff5).
- Nueva validación pendiente: [Visual QA run 43110764363](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43110764363) y [Headless export run 43110764430](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43110764430).
- Estado actual: **Pendiente**. No afirmar que la inspección de nodos hijos funciona hasta revisar el nuevo run, el número de comandos verificados y las capturas generadas.


## Resultado verificado: selección visual de nodos hijos (11 de noviembre de 2026)

**Estado: Probado y aprobado en el proyecto Godot de referencia; pendiente de integración en el editor web.**

- Visual QA [run 43119694027](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43119694027): **success**.
- Exportación headless [run 43119694016](https://github.com/gavilandavid89-pixel/Escondite/actions/runs/43119694016): **success**.
- El inspector abre escenas, expande los antecesores en el panel Scene, selecciona el elemento real del árbol y confirma que queda seleccionado antes de tomar la captura.
- Resultado: **36 comandos verificados y 36 capturas de vistas de escena/nodo**.
- La comprobación headless confirma que `enemy.tscn` contiene 2 nodos cargados y que su hijo `CollisionShape2D` está presente. La escena del jugador también conserva sus 2 nodos.
- Causa identificada: la propiedad serializada `collision_mask = 1 | 2` en `enemy.tscn` hacía que Godot 4.7.2 cargara solamente la raíz, aunque el archivo declaraba el hijo. Se sustituyó por el valor entero equivalente `collision_mask = 3`; tras el cambio, la carga reporta 2 nodos y 1 hijo.
- Se añadió una comprobación headless para comparar el contenido declarado del archivo con los nodos realmente cargados, evitando que una futura regresión quede oculta.
- El test de recompensas de combate también se hizo determinista desactivando la evasión aleatoria del enemigo de prueba; no se modificaron los tiempos de espera ni la configuración de Actions.
- Commit de la corrección de la escena: [9c2870ccdbed83b3fb808ec2847cf5e603097bad](https://github.com/gavilandavid89-pixel/Escondite/commit/9c2870ccdbed83b3fb808ec2847cf5e603097bad).

**Límite importante:** estos resultados siguen perteneciendo a `gavilandavid89-pixel/Escondite`, un proyecto de referencia independiente. No demuestran que la automatización ya esté conectada al editor Godot Web de este repositorio ni al servicio Neon. Esa integración continúa pendiente.
