# Flujo de desarrollo: Godot Headless Linux + GitHub

## Regla general

El desarrollo y las pruebas se realizan en el entorno Linux disponible para ChatGPT, usando el ejecutable Godot Headless ya instalado. Ese entorno no tiene salida directa a Internet. No se debe intentar resolver esta limitación creando otro relay, servidor o servicio, ni trasladando el motor Godot a GitHub.

El proyecto es la unidad de trabajo. El motor Headless es únicamente la herramienta local para editar, importar, validar y ejecutar el proyecto.

## Flujo de trabajo obligatorio

1. **Trabajar en el proyecto local de Linux.** Abrir y modificar directamente la copia de trabajo del proyecto con las herramientas disponibles y el Godot Headless instalado.
2. **Probar antes de publicar.** Ejecutar importación, validaciones, pruebas automatizadas y ejecuciones headless que correspondan al cambio. Corregir los errores detectados antes de actualizar GitHub, siempre que sea posible verificarlos localmente.
3. **Identificar el conjunto real de cambios.** Determinar qué archivos fueron creados, modificados o eliminados y revisar su contenido. No reconstruir cambios de memoria ni subir archivos que no formen parte del trabajo.
4. **Actualizar GitHub usando la conexión de GitHub de ChatGPT.** Como Linux no tiene salida a Internet, las operaciones remotas se hacen mediante la integración de GitHub disponible en ChatGPT.
5. **Elegir la vía adecuada según el tipo de cambio.** No existe una única operación obligatoria:
   - **Subir/crear/reemplazar archivos:** cuando el trabajo local produjo escenas, scripts, recursos, configuraciones u otros archivos que deben incorporarse al repositorio. Crear los archivos nuevos y reemplazar los existentes necesarios, conservando el resto del repositorio.
   - **Modificar directamente el repositorio:** cuando el cambio es documental, de configuración o de código que conviene editar directamente en GitHub y no requiere transferir un archivo generado/probado localmente. Leer primero la versión actual y actualizarla sin sobrescribir cambios ajenos.
   - **Combinar ambas vías:** cuando una tarea incluye archivos desarrollados localmente y ajustes adicionales que tienen más sentido como edición directa del repositorio.
6. **Mantener el repositorio coherente con lo probado.** Los archivos transferidos deben ser los mismos que se trabajaron y probaron en Linux. Si se hace una modificación directa en GitHub que afecta el proyecto ejecutable, incorporar luego esa modificación a la copia local y validarla en Headless cuando sea posible.
7. **Dejar Godot Web para la revisión visual/sincronización posterior.** Una vez que los cambios estén en GitHub, el proyecto podrá sincronizarse desde Godot Web para inspección visual. Godot Web no reemplaza las pruebas headless y una prueba headless correcta no garantiza por sí sola que la presentación web sea correcta.

## Qué NO se debe hacer

- No subir el ejecutable, la distribución, el archivo comprimido ni el entorno completo de Godot Headless.
- No generar un ZIP del motor o del proyecto como paso rutinario.
- No crear un proyecto nuevo para cada consulta o cambio.
- No intentar conectar Linux directamente a GitHub, Render u otros servicios externos: el entorno de ejecución no tiene salida a Internet.
- No crear un relay, proxy o servicio adicional para evitar esa limitación.
- No reemplazar todo el repositorio cuando solo hacen falta unos pocos archivos.
- No afirmar que algo fue probado si solo se editó o se subió.
- No sobrescribir cambios remotos sin leer la versión actual y respetar el SHA/concurrencia que exija la operación de GitHub.

## Separación de responsabilidades

| Componente | Responsabilidad |
|---|---|
| Godot Headless en Linux | Desarrollo local, importación, ejecución y pruebas técnicas |
| Proyecto local | Copia de trabajo donde se hacen los cambios y se verifica su comportamiento |
| Integración GitHub de ChatGPT | Crear, añadir o reemplazar únicamente los archivos necesarios; editar directamente archivos del repo cuando corresponda |
| Repositorio GitHub | Historial y versión compartida de los cambios terminados |
| Godot Web | Sincronización y revisión visual posterior del proyecto |

## Informe al terminar cada tarea

El resumen debe indicar, de forma breve y verificable:

- Qué se cambió.
- Qué pruebas se ejecutaron y cuáles fueron sus resultados.
- Qué archivos se añadieron, reemplazaron o editaron directamente en GitHub.
- Si quedó algo pendiente de revisar en Godot Web.
- Cualquier limitación que haya impedido probar una parte.

**Principio clave:** primero se desarrolla y se prueba en el proyecto local con Godot Headless; después se refleja el resultado en GitHub usando la operación que corresponda. Se transfieren los archivos del proyecto cuando hace falta, no el motor Headless.
