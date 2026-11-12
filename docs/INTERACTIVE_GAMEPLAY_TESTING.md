# Pruebas interactivas y escenas temporales de Godot

## Propósito

Este documento define cómo el entorno debe probar proyectos Godot de forma visual e interactiva, sin quedar acoplado a un juego, género, repositorio, personaje o conjunto de controles concreto.

Los proyectos usados como referencias durante el desarrollo (incluidos Dragon Realm y Escondite) son casos de validación intercambiables. No son dependencias, valores fijos, nombres especiales ni requisitos del sistema. Toda selección de proyecto, rama, ruta, escena, acción y duración debe ser configurable o descubrirse desde el proyecto.

## Objetivos

1. Abrir cualquier proyecto Godot compatible mediante el flujo de importación existente.
2. Ejecutar el juego y manejarlo mediante entradas reales del navegador: teclado, ratón y eventos táctiles.
3. Observar su comportamiento durante una ventana de prueba configurable; el valor inicial recomendado es 10 segundos.
4. Comparar el comportamiento observado con instrucciones y resultados esperados.
5. Solo después de demostrar que el control del juego en ejecución funciona de forma fiable, habilitar escenarios temporales dentro del proyecto seleccionado. Estos escenarios podrán cubrir cualquier mecánica, interacción, interfaz, sistema o estado.
6. Publicar temporalmente los archivos del escenario en la rama principal del repositorio seleccionado, sincronizar la revisión exacta y limpiar los cambios temporales al finalizar.

## Principios no negociables

- **Agnóstico al proyecto:** no codificar rutas, nombres, escenas principales, controles, recursos ni mecánicas de un proyecto de referencia.
- **No asumir controles:** leer la configuración del adaptador/manifest o inspeccionar el proyecto. Si no se conoce el mapeo, informar qué falta; no inventar teclas ni botones.
- **Entradas reales:** Playwright debe enviar eventos de teclado, ratón o puntero/touch al juego que se está ejecutando. No reemplazar el juego por una simulación de sus resultados.
- **Temporalidad controlada:** el escenario se publica temporalmente en la rama principal, como autorizó el usuario, y se elimina al terminar. Registrar el commit base, cada archivo creado/modificado y los commits propios de la prueba. No sobrescribir ni descartar cambios ajenos.
- **No borrar trabajo del usuario:** la limpieza solo puede retirar los archivos temporales identificados por el manifiesto y creados por esta ejecución.
- **Evidencia:** separar observación visual, telemetría funcional, errores del motor y resultado de Actions. Una captura por sí sola no demuestra una mecánica interna.
- **No declarar éxito prematuramente:** el resultado debe distinguir entre importación, apertura, entrada enviada, reacción visual y aserciones funcionales.

## Flujo A: prueba interactiva genérica de 10 segundos

1. Importar el repositorio, rama y subcarpeta seleccionados.
2. Confirmar que el proyecto se instaló y que Godot abrió la revisión esperada.
3. Ejecutar la escena principal o la escena indicada por la configuración.
4. Detectar el viewport del juego y comprobar que recibe foco.
5. Ejecutar una secuencia de acciones configurada. Cada acción especifica dispositivo, control, estado (presionar/soltar), duración y pausa posterior.
6. Liberar siempre todas las teclas y botones al terminar una acción, al ocurrir un error y al cerrar el navegador.
7. Mantener la sesión de observación hasta completar la duración total (10 segundos por defecto).
8. Capturar frames en momentos configurables, preferentemente antes, durante y después de acciones relevantes.
9. Guardar un timeline con marcas de tiempo, acciones enviadas, foco, capturas, eventos de consola y errores disponibles.
10. Emitir un resultado estructurado y conservarlo junto a los artefactos del workflow.

### Controles del controlador inicial

- Teclado: key down, key up y pulsaciones cortas.
- Ratón: movimiento, click y mantener/soltar botones.
- Táctil: toque puntual (tap) mediante el dispositivo táctil de Playwright.
- Los gestos táctiles continuos, arrastre táctil y doble click quedan como ampliaciones pendientes.
- Secuencias combinadas y esperas.
- Duración total y duración de cada acción configurables.

La capa de automatización no debe depender de un mapeo universal de teclas. Los nombres de acciones del juego se traducen a entradas concretas mediante el adaptador del proyecto. Si solo se dispone de controles visuales, se pueden localizar e interactuar con ellos mediante sus coordenadas/elementos, registrando el método usado.

### Ejemplo conceptual de timeline

```json
{
  "duration_ms": 10000,
  "capture_interval_ms": 500,
  "actions": [
    { "at_ms": 500, "device": "keyboard", "control": "move_right", "state": "press", "duration_ms": 1200 },
    { "at_ms": 2200, "device": "keyboard", "control": "jump", "state": "tap" },
    { "at_ms": 4000, "device": "pointer", "control": "attack_button", "state": "press", "duration_ms": 350 },
    { "at_ms": 5000, "device": "pointer", "control": "attack_button", "state": "release" }
  ]
}
```

Es un formato ilustrativo: los controles simbólicos se resuelven mediante la configuración específica del proyecto. No deben enviarse literalmente como teclas si el adaptador no los ha traducido.

## Flujo B (fase posterior): crear un escenario temporal dentro del repositorio

**Este bloque queda expresamente pospuesto.** No se debe comenzar a crear, publicar ni limpiar escenarios temporales hasta que el sistema pueda controlar de forma demostrable el juego ya ejecutándose, con entradas reales, foco correcto y reacción observable. La prioridad inmediata es completar y validar el Flujo A. Una vez superada esa etapa, se habilitará este flujo.

Esta es la vía preferida cuando la mecánica está demasiado avanzada para alcanzarla desde el inicio normal del juego.

1. Registrar repositorio, commit base, rama, subcarpeta y estado inicial.
2. Registrar el SHA exacto de `main` y comprobar que no haya otra prueba temporal activa. Crear un manifiesto de ejecución con un identificador único y una lista de archivos reservados para esta prueba.
3. Descargar/importar el proyecto en el entorno de trabajo.
4. Inspeccionar sus escenas, scripts, recursos, autoloads, configuración de entrada y dependencias.
5. Crear dentro del proyecto una escena temporal que reutilice los sistemas y recursos reales necesarios. Añadir scripts auxiliares mínimos solo cuando hagan falta para preparar el estado inicial o exponer resultados.
6. Añadir un manifiesto que identifique inequívocamente todos los archivos creados para esta prueba.
7. Configurar la escena como punto de entrada temporal mediante un override de ejecución o una configuración de prueba; no cambiar permanentemente la escena principal del usuario.
8. Publicar los archivos temporales en `main` mediante commits identificables. Esperar a que Render publique la revisión correspondiente y comprobar el estado del despliegue. Importar en Godot Web el commit exacto que contiene el escenario.
9. Abrir el proyecto, ejecutar la escena temporal y realizar la prueba interactiva.
10. Evaluar capturas y aserciones; si falla, conservar evidencia y corregir/repetir en la misma rama temporal.
11. Al terminar, eliminar únicamente los archivos creados por la prueba y restaurar exactamente los archivos preexistentes que se hayan modificado, usando commits normales en `main`. No usar force-push, reset ni revertir commits ajenos.
12. Verificar que `main` vuelve a contener el contenido funcional previo a la prueba, que los cambios ajenos siguen intactos y que Render vuelve a desplegar la revisión limpia.

El escenario temporal vive **dentro del proyecto Godot real**, por lo que puede reutilizar scripts, recursos, autoloads y sistemas auténticos. No es una maqueta externa ni una simulación independiente del juego. La rama principal puede mostrar temporalmente esos archivos en la web; la limpieza posterior los retira mediante commits auditables.

### Qué puede contener un escenario temporal

- El jugador/personaje real y su configuración.
- Enemigos, NPC u objetos necesarios.
- Terreno, cámara, iluminación y límites mínimos.
- Recursos y habilidades requeridos.
- Estado inicial preparado (vida, energía, inventario, progreso, etc.).
- Señales o instrumentación de prueba para registrar resultados.
- Instrucciones de ejecución y condiciones de aceptación.

Debe incluir solo lo necesario para la prueba, evitando cargar mundos o sistemas ajenos al objetivo. Cuando la mecánica dependa de servicios o progresión reales, la escena debe inicializar esos sistemas de manera controlada, no reemplazarlos por versiones falsas.

## Contrato de configuración por proyecto

Cada proyecto puede ofrecer un adaptador de pruebas opcional. El sistema genérico funciona sin él en modo exploratorio, pero las comprobaciones semánticas profundas requieren configuración explícita.

Ubicación sugerida: `godot-web-test.json` en la raíz del proyecto, o en una ruta configurable.

Ejemplo ilustrativo:

```json
{
  "schema_version": 1,
  "project": {
    "display_name": "Nombre del proyecto",
    "main_scene": "res://scenes/main.tscn"
  },
  "controls": {
    "move_right": { "type": "key", "value": "D" },
    "jump": { "type": "key", "value": "Space" },
    "attack": { "type": "pointer", "target": "attack_button" }
  },
  "scenarios": [
    {
      "id": "combat-basic",
      "scene": "res://__test__/combat_basic.tscn",
      "duration_ms": 10000,
      "instructions": [
        "Observar el estado inicial del jugador y el objetivo",
        "Ejecutar ataque",
        "Comprobar la reacción del objetivo"
      ],
      "expected": [
        { "kind": "visual", "description": "La animación de ataque aparece" },
        { "kind": "state", "path": "target.health", "operator": "less_than", "value": 100 }
      ]
    }
  ],
  "temporary_files": [
    "res://__test__/combat_basic.tscn",
    "res://__test__/combat_basic.gd"
  ]
}
```

El ejemplo define una forma de contrato, no una API ya implementada. El esquema definitivo deberá validar rutas, tipos, acciones, límites de tiempo y archivos temporales. No se deben ejecutar rutas arbitrarias ni scripts no confiables sin las protecciones correspondientes.

## Observabilidad y resultados

Cada ejecución debe producir un informe con, como mínimo:

- Identidad del proyecto: URL, rama, commit, subcarpeta y revisión temporal.
- Escena iniciada y método usado para iniciarla.
- Duración solicitada y duración efectiva.
- Timeline de acciones: entrada, instante, duración, foco y confirmación de envío.
- Capturas con marca de tiempo y hoja de contacto.
- Errores y advertencias de consola/navegador/Godot que estén disponibles.
- Aserciones visuales y funcionales, cada una con estado y evidencia.
- Lista exacta de archivos temporales creados y resultado de limpieza.

Estados recomendados por aserción: `passed`, `failed`, `not_observable`, `not_configured`. El estado global debe distinguir entre prueba completa, parcial, advertencias del proyecto y fallo de infraestructura.

### Dos canales de validación

**Visual:** lo que se ve en pantalla: movimiento, animaciones, UI, cambios de escena, reacción de objetos y presentación.

**Funcional:** valores y eventos internos, solo cuando el proyecto proporcione una interfaz de prueba fiable (por ejemplo, señales, estado serializado o un adaptador). No inferir valores internos a partir de píxeles.

## Sincronización con Godot Web

La revisión temporal debe identificarse por commit y rama, no por el nombre del juego. Después de publicar la escena temporal, el importador debe descargar esa revisión exacta y comprobar su SHA/identidad antes de abrirla. La sincronización debe ser explícita y verificable; no asumir que una pestaña ya abierta se actualiza sola.

Si el editor ya contiene una copia importada, el sistema debe detectar si corresponde a la revisión esperada. Si no coincide, debe volver a importar o actualizar de forma controlada antes de ejecutar la prueba.

## Limpieza segura

- Mantener una lista allowlist de archivos temporales creados por la ejecución.
- No eliminar archivos preexistentes ni modificar recursos del proyecto que no sean temporales.
- Si se modifica un archivo existente para habilitar el escenario, registrar el diff y restaurarlo exactamente al finalizar.
- La publicación temporal en `main` requiere autorización explícita (concedida para este flujo), registro del SHA base y serialización de pruebas para evitar solapamientos.
- Nunca usar force-push, reset --hard ni operaciones que eliminen commits de terceros.
- Antes de limpiar, comparar el HEAD actual con los commits propios de la prueba. Si hay commits ajenos posteriores o cambios inesperados, detener la limpieza automática y preservar el estado para revisión.
- Borrar solo rutas nuevas enumeradas en el manifiesto; restaurar archivos existentes desde su contenido/SHA original.
- La limpieza se ejecuta tanto después del éxito como del fallo, salvo que el usuario solicite conservar el entorno de diagnóstico.
- Antes de borrar, verificar que el commit/branch objetivo es el temporal creado por esta ejecución.
- Publicar evidencia de limpieza: archivos retirados, rama eliminada y commit base intacto.

## Seguridad y límites

- Tratar repositorios y scripts importados como código no confiable.
- Ejecutar las pruebas en un entorno aislado y con permisos mínimos.
- No exponer secretos, credenciales ni variables del entorno al proyecto.
- Limitar duración, consumo de recursos, tamaño del proyecto y número de acciones.
- Validar rutas para impedir traversal y limitar las operaciones de escritura a la copia temporal.
- No ejecutar comandos externos sugeridos por el proyecto sin revisión.
- Si el proyecto no tiene controles accesibles, adaptador o escena ejecutable, informar la limitación en lugar de fingir una prueba.

## Estado de implementación

La prueba E2E actual ya demuestra: importación del ZIP, selección explícita de rama, apertura del proyecto en Godot Web, detección del editor, ejecución F5 y captura de secuencias del editor y del juego. También comprueba el Relay con un fixture en subcarpeta.

El controlador base de teclado, ratón y toque táctil, la validación del timeline y la liberación segura de teclas están implementados. Sus pruebas unitarias pasaron en Actions (ejecución 43278159189). La integración del workflow terminó correctamente en Actions (ejecución 43278226182), incluyendo el test unitario del controlador y el timeline de observación. Sin embargo, esa ejecución usó una lista de acciones vacía (`[]`): **no demuestra que el juego haya recibido controles ni que haya reaccionado**.

### Prioridad inmediata: conseguir control real del juego en ejecución

1. Detectar con fiabilidad el viewport/iframe/canvas del juego y darle foco.
2. Determinar cómo se enrutan las entradas en la versión de Godot Web utilizada (teclado, ratón y táctil).
3. Enviar acciones conocidas y registrar confirmación de envío, foco y eventos observables.
4. Verificar reacción real en pantalla; distinguir entrada enviada de acción procesada por el juego.
5. Probar secuencias de movimiento y acciones sostenidas, liberación de controles y recuperación ante errores.
6. Ejecutar una sesión de 10 segundos con acciones reales y guardar capturas/timeline reproducibles.
7. Ampliar a gestos táctiles continuos, arrastre y doble click.

### Fase posterior (bloqueada hasta superar la prioridad inmediata)

- Adaptadores por proyecto para mapear controles y aserciones funcionales.
- Creación de escenarios temporales de cualquier mecánica/interacción.
- Publicación temporal en `main`, importación de commit exacto y limpieza auditable.
- Informe combinado visual + funcional.

No iniciar el bloque de escenarios temporales antes de validar el control interactivo real.

No describir estas capacidades pendientes como ya disponibles hasta que existan pruebas automatizadas y artefactos que lo demuestren.
