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

Su cometido es ejecutar pruebas automatizadas del Headless Session Bridge y comprobar que puede comunicarse con la instancia del editor real levantada en ese runner. Sirve para verificar el puente, sus protocolos, las operaciones permitidas y la integración CI.

No es el Godot Headless local del agente. No es el entorno cotidiano de autoría. No debe usarse como sustituto del desarrollo local ni asumirse que los archivos que existen en el runner están disponibles automáticamente en el workspace del agente.

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
| Construir niveles y contenido | Principal | No | Inspección |
| Importar y validar el proyecto | Sí | Sí, en su fixture/runner | Puede mostrar estado |
| Ejecutar juego headless | Sí | Sí, para CI | No es su función |
| Ejecutar pruebas automatizadas | Sí | Sí, integración | No |
| Ver composición visual | No | No por sí solo | Principal |
| Probar Headless Session Bridge | No es su objetivo | Principal | Es el editor conectado |
| Verificar conexión con editor real | No | Sí | Es el extremo editor |

## Reglas que no deben romperse

- Nunca describir el Godot de Actions como “mi Godot local”.
- Nunca afirmar que el agente ha ejecutado el juego localmente basándose únicamente en un workflow de Actions.
- Nunca asumir que el éxito de CI demuestra que el nivel se ve bien.
- Nunca asumir que una captura del editor demuestra que las pruebas locales pasaron.
- No usar clics, coordenadas ni automatización de ventanas como método habitual de construcción.
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
