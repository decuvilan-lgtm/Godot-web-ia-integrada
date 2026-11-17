# Tres entornos Godot: desarrollo local, Actions y editor visual

## Distinción obligatoria: son tres instancias diferentes

Este proyecto utiliza tres entornos separados. No deben confundirse ni sustituirse entre sí.

### A. Godot Headless local del agente — entorno principal de desarrollo

Es una instalación Linux de Godot que debe ejecutarse directamente en el entorno de trabajo del agente (no dentro de GitHub Actions y no en el editor real).

Aquí se realiza el trabajo cotidiano:
- Crear y editar scripts GDScript, escenas .tscn, recursos y configuraciones mediante archivos.
- Importar recursos y validar proyectos.
- Ejecutar el juego en modo headless.
- Ejecutar pruebas automatizadas, revisar logs, localizar fallos y corregirlos.
- Construir niveles y prototipos completos sin manejar la interfaz gráfica.

Esta instancia trabaja sobre una copia aislada del proyecto que el usuario haya elegido. Es la fuente principal para autoría y validación técnica.

**Requisito operativo:** antes de declarar una prueba local, comprobar que el binario existe en el entorno del agente, registrar su ruta y versión, y ejecutar realmente los comandos. Si no existe, la etapa local todavía no está disponible: no se debe fingir que Actions equivale a ella.

### B. Godot Headless de GitHub Actions — integración del editor real

Es otra instalación, dentro de los runners de GitHub Actions. Pertenece al pipeline de integración del repositorio.

Su cometido es ejecutar pruebas automatizadas del Headless Session Bridge y operar semánticamente el editor real levantado en ese runner. A y B comparten la misma sesión de Chromium: A abre el proyecto y mantiene la sesión; B inspecciona y edita mediante el agente nativo integrado, sin depender de arrastres del ratón para autoría.

Capacidades verificadas o en aceptación:
- Consultar estado, árbol de escena y propiedades visibles del Inspector.
- Crear nodos de clases allowlisted y configurar propiedades tipadas mediante Undo/Redo.
- Construir jerarquías acotadas y leer de vuelta el árbol/Inspector para verificar los cambios.
- Ejecutar la escena con F6, abrir Game, detectar el canvas, hacer clic y enviar entradas de teclado con liberación controlada.
- Capturar la interfaz o la vista previa durante la misma sesión.

B no es un Godot Headless local ni un editor general de archivos. No sustituye el trabajo local de scripts, recursos y automatizaciones de proyecto; tampoco permite ejecutar GDScript arbitrario ni acceder libremente al filesystem. La sesión A/B se configura entre 60 y 3600 segundos (30 minutos por defecto) y puede cerrarse antes mediante `stop`.

### C. Godot Editor real — inspección visual

Es la instancia gráfica del editor, normalmente abierta sobre la misma copia de trabajo o sobre una copia de inspección sincronizada.

Se usa principalmente para:
- Ver la composición visual del nivel y las escenas.
- Revisar árbol de nodos, Inspector, recursos, animaciones y preview.
- Capturar imágenes o vídeo para evaluar presentación.
- Confirmar visualmente que lo construido por archivos se representa correctamente.

No debe ser necesario colocar manualmente cada plataforma, nodo o recurso haciendo clics. El agente construye desde Headless local y después inspecciona el resultado en el editor. El puente puede consultar y operar sobre el editor para las pruebas de integración, pero no convierte la automatización de coordenadas en el método de autoría.

## Flujo correcto de trabajo

1. El usuario selecciona el proyecto; nunca se presupone un repositorio de juego.
2. Crear una copia de trabajo aislada, manteniendo intacto el original.
3. El agente desarrolla en esa copia usando **su Godot Headless local**.
4. Importar, ejecutar el juego y correr pruebas locales; corregir los fallos.
5. Sincronizar la copia validada con el entorno de inspección visual.
6. Abrirla en **Godot Editor real** y revisar composición, jerarquía, recursos y comportamiento visual.
7. Si aparece un defecto visual, corregir los archivos en el entorno local y repetir el ciclo.
8. En paralelo, **GitHub Actions** ejecuta sus propias pruebas con su propio Godot Headless para verificar el puente y la integración del editor.
9. Revisar el diff y publicar únicamente con aprobación explícita.

## Matriz de responsabilidades

| Capacidad | Headless local del agente | Headless de Actions | Editor real |
|---|---:|---:|---:|
| Crear scripts y escenas por archivos | Principal | Solo fixtures de pruebas | No como método normal |
| Construir niveles y contenido por archivos | Principal | No es su método principal | Inspección |
| Crear jerarquías de nodos y configurar propiedades | Sí | Sí, mediante operaciones semánticas acotadas | Inspección |
| Importar y validar el proyecto | Sí | Sí, en su fixture/runner | Puede mostrar estado |
| Ejecutar juego headless | Sí | Sí, para CI | No es su función |
| Ejecutar pruebas automatizadas | Sí | Sí, integración | No |
| Ejecutar y controlar la vista previa | No por sí solo | Sí, mediante Game canvas y entradas acotadas | Principal |
| Ver composición visual | No | Sí, con capturas del editor/preview | Principal |
| Probar Headless Session Bridge | No es su objetivo | Principal | Es el editor conectado |
| Verificar conexión con editor real | No | Sí | Es el extremo editor |

## Reglas que no deben romperse

- Nunca describir el Godot de Actions como “mi Godot local”.
- Nunca afirmar que el agente ha ejecutado el juego localmente basándose únicamente en un workflow de Actions.
- Nunca asumir que el éxito de CI demuestra que el nivel se ve bien.
- Nunca asumir que una captura del editor demuestra que las pruebas locales pasaron.
- No usar clics, coordenadas ni automatización de ventanas como método habitual de construcción; la autoría usa operaciones semánticas. Las entradas normalizadas se reservan para probar el juego en ejecución.
- No instalar el puente en el proyecto original; solo en una copia aislada.
- No ejecutar GDScript arbitrario recibido como comando del puente.
- No publicar automáticamente ni modificar main.
- No vincular el sistema a un repositorio de juego fijo: el usuario elige el proyecto de cada sesión.

## Disponibilidad del Headless local

En cada sesión, comprobar la presencia del binario Godot local con la ruta disponible y registrar su versión. Si no está instalado, informar claramente que el entorno local aún no está listo. El workflow de Actions puede seguir validando la integración, pero es una validación separada y no reemplaza el requisito local. No crear relays, servidores o proxies para confundir o fusionar los entornos.

## Evidencia por iteración

Registrar por separado:
- **Local:** ruta/versión del Godot Headless del agente, comandos ejecutados, código de salida, pruebas y logs.
- **Visual:** editor abierto, proyecto inspeccionado, escenas revisadas y capturas.
- **Actions:** URL del workflow, SHA probado, resultado de bridge/integración y artefactos.
- Archivos modificados y diff final.

**Principio clave:** el agente construye y prueba con su Godot Headless local; el editor real permite mirar y revisar visualmente; el Godot Headless de Actions verifica por separado la integración del puente con ese editor.
