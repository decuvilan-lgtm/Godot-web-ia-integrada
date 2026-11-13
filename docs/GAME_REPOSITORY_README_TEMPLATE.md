# Plantilla de README para repositorios de juegos Godot

Este documento define la información que cada repositorio de juego debe ofrecer para que una persona o un agente pueda entenderlo, abrirlo y probarlo sin adivinar controles ni mecánicas.

El README es la guía humana del proyecto. Las acciones automatizables y validadas pertenecen a `godot-lab/lab-manifest.json`, `godot-lab/control-profile.json` y `godot-lab/commands/*.json`. Ambos deben describir el mismo comportamiento. El README por sí solo no autoriza la ejecución automática de scripts.

Copia esta estructura en el README del juego y sustituye todos los campos de ejemplo por datos reales. Elimina cualquier sección que no aplique, pero no inventes información.

---

## 1. Identidad y estado del proyecto

- **Nombre del juego:**
- **Versión/revisión del proyecto:**
- **Motor y versión exacta de Godot:**
- **Tipo de juego / género:**
- **Estado:** prototipo, demo, alpha, beta, etc.
- **Plataformas objetivo:**
- **Orientación y relación de aspecto:**
- **Ruta del proyecto:** carpeta que contiene `project.godot`.
- **Escena principal:** ruta exacta de la escena inicial.
- **Cómo abrirlo:** pasos mínimos desde Project Manager.
- **Cómo iniciar la partida:** acción exacta dentro del editor o menú.

## 2. Descripción jugable

Explica de forma concreta:

- Qué controla el jugador.
- Qué intenta conseguir.
- Cuál es el ciclo principal de juego.
- Qué puede hacer y qué no puede hacer.
- Qué significa ganar, perder, completar o reiniciar.
- Qué sistemas están implementados y cuáles son solo placeholders.

Evita frases generales como “juego de aventura”. Describe qué ocurre en pantalla y qué acciones lo provocan.

## 3. Controles completos

Incluye controles de teclado, ratón, mando y táctil por separado. No confundas el nombre de una acción de Godot en Input Map con la tecla física que la activa.

| Acción jugable | Input Map de Godot | Teclado físico | Ratón/mando/táctil | ¿Mantener o pulsar? | Contexto |
|---|---|---|---|---|---|
| Mover izquierda | `move_left` | Flecha izquierda / A | Joystick hacia izquierda | Mantener | Durante juego |
| Mover derecha | `move_right` | Flecha derecha / D | Joystick hacia derecha | Mantener | Durante juego |
| Saltar | `jump` | Espacio | Botón A / botón táctil | Pulsación | En suelo |
| Acción principal | `primary_action` | X | Botón de acción | Pulsación o mantener, especificar | Cerca de objetivo |

Para cada control real, documenta:

- Nombre exacto de la acción en Project Settings → Input Map.
- Tecla o botón físico asignado.
- Si responde al presionar, mantener, repetir o soltar.
- Si solo funciona en una escena, menú, estado o rango de distancia.
- Si hay controles alternativos.
- Si el juego captura el ratón o necesita que se haga clic primero dentro del viewport.
- Si existe soporte táctil, dónde aparece el control y cómo se comporta al arrastrar.

Sustituye los ejemplos por los controles reales. Si no existe mando o táctil, indícalo explícitamente.

## 4. Menús y navegación

Documenta cada pantalla/menú:

| Pantalla | Cómo llegar | Elementos visibles | Acción | Resultado esperado |
|---|---|---|---|---|
| Menú principal | Al iniciar | Jugar, Opciones, Salir | Pulsar Jugar | Abre la escena de juego |
| Pausa | Durante partida | Continuar, Reiniciar | Pulsar Continuar | Regresa al juego |

Incluye rutas de escenas cuando se conozcan y explica cómo regresar, pausar, reiniciar y salir. Si hay botones sin implementar, márcalos como pendientes.

## 5. Escenas, nodos y sistemas importantes

Lista solo rutas que existan en el repositorio:

- Escena principal:
- Escenas de menú:
- Escenas de gameplay:
- Escenas de jugador/personajes:
- Escenas de enemigos:
- HUD e interfaz:
- Autoloads / singletons:
- Sistemas de inventario, combate, guardado, misiones, red, etc.

Para cada sistema explica su responsabilidad, qué escena lo utiliza y qué señal visible permite saber que está funcionando. No publiques rutas hipotéticas como si existieran.

## 6. Reglas y comportamiento del juego

Describe los comportamientos observables:

- Movimiento, gravedad, salto, vuelo y colisiones.
- Cámara, seguimiento, límites y desplazamiento del mundo.
- Combate: objetivo válido, alcance, daño, enfriamiento, animación y reacción del enemigo.
- Vida, energía, recursos y condiciones de derrota.
- Inventario, equipamiento, objetos y persistencia.
- IA de enemigos: detección, persecución, ataque, retorno y derrota.
- Multijugador/red, si existe: roles, conexión y límites conocidos.
- Guardado/carga, puntos de control y reinicio.

No hace falta revelar cada fórmula interna, pero sí explicar qué debe verse al probar una acción.

## 7. Referencias visuales y feedback esperado

Describe elementos que ayudan a reconocer estados:

- Apariencia o ubicación del jugador.
- Barras de vida/energía y cómo cambian.
- Indicadores de daño, mensajes, partículas y animaciones.
- Cambios de escena, overlays, diálogos y notificaciones.
- Diferencias visuales entre estado normal, daño, victoria, derrota y pausa.

Incluye capturas de pantalla propias cuando aporten claridad y mantenlas actualizadas con la revisión actual. No uses imágenes de otra versión como evidencia de comportamiento actual.

## 8. Viewport, rendimiento y dispositivos

- Resolución base del proyecto:
- Modo de stretch y aspecto:
- Orientación permitida:
- Tamaños mínimos probados:
- Android / escritorio / navegador:
- FPS objetivo:
- Requisitos de GPU/WebGL:
- Limitaciones de Godot Web:
- Problemas conocidos de escalado, input o rendimiento:

Aclara si el juego está diseñado para horizontal o vertical. Describe cómo se adapta el HUD y si hay botones que cambian de posición o tamaño.

## 9. Escenarios reproducibles de prueba

Cada escenario debe poder repetirse desde un estado inicial claro.

| ID | Preparación | Pasos | Resultado esperado | Evidencia |
|---|---|---|---|---|
| T-001 | Abrir el juego desde el menú | Iniciar partida | Aparece el personaje y el HUD | Captura de gameplay |
| T-002 | Personaje en zona segura | Mantener movimiento derecha 1 s | El personaje cambia de posición | Capturas antes/después |
| T-003 | Enemigo visible y dentro de alcance | Ejecutar ataque | Enemigo reacciona y su vida disminuye | Mensaje/HP/animación |

Para cada escenario añade:

1. Escena y estado inicial requeridos.
2. Controles exactos y duración aproximada.
3. Condiciones previas (por ejemplo, esperar a que termine una animación).
4. Resultado visual esperado.
5. Resultado funcional esperado, si puede observarse.
6. Qué invalida la prueba.
7. Cómo volver de forma segura al estado inicial.

No describas como “verificado” un escenario que solo se ha escrito. La verificación real debe registrar evidencia y el SHA exacto del commit en el manifiesto del laboratorio.

## 10. Manifiesto automatizable del laboratorio

Indica dónde se encuentran los comandos declarativos:

- Manifiesto: `godot-lab/lab-manifest.json`.
- Perfil de controles: `godot-lab/control-profile.json`.
- Comandos: `godot-lab/commands/*.json`.
- Comando básico, si existe: `smoke-test`.
- Estado de verificación: `pending`, `verified` u `obsolete`.
- SHA exacto verificado:

El manifiesto es la fuente de verdad para los pasos que el Relay puede ejecutar. Los controles no se copian de otros juegos. Los comandos deben usar solo las operaciones permitidas por el Relay; no se admiten scripts shell, Python, JavaScript ni ejecución arbitraria.

## 11. Limitaciones y problemas conocidos

Mantén una lista honesta:

- Errores actuales de consola o importación.
- Recursos que no cargan.
- Botones o escenas incompletos.
- Sistemas que funcionan solo en escritorio o solo en Android.
- Problemas de rendimiento.
- Características planeadas que todavía no existen.

Incluye una fecha/revisión para saber cuándo se comprobó por última vez.

## 12. Seguridad y datos

- No incluir tokens, contraseñas, claves privadas ni datos personales.
- No documentar credenciales de servicios externos.
- No incluir comandos destructivos como pasos normales de prueba.
- No borrar partidas, archivos ni datos persistentes sin una preparación y autorización explícitas.
- Indicar si el proyecto realiza conexiones externas o guarda datos del usuario.

## 13. Historial de verificación

| Fecha | Commit SHA | Escena/escenario | Resultado | Evidencia | Observaciones |
|---|---|---|---|---|---|
| AAAA-MM-DD | SHA completo | T-001 | Pendiente | Ruta/ID | Descripción |

Actualiza el historial después de una prueba real. Si cambia el comportamiento o se modifica un control, vuelve a poner el perfil/comando en `pending` hasta repetir la verificación.

---

## Reglas de calidad del README

1. Todo control debe tener una descripción inequívoca y coincidir con Input Map.
2. Todo escenario debe indicar preparación, acción y resultado observable.
3. Las rutas de escenas y nodos deben existir en el commit descrito.
4. Separar lo implementado, lo parcial y lo planeado.
5. Anotar el SHA o versión a la que corresponde la información.
6. No usar el README como sustituto del manifiesto JSON automatizable.
7. No marcar controles ni comandos como verificados sin probarlos en el editor real.
