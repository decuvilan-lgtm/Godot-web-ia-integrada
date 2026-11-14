# Godot AI Bridge Sandbox

Proyecto mínimo para el puesto remoto **Godot Web de la IA**. Contiene una escena Node2D de prueba y los complementos propios del sandbox. El controlador semántico de Actions no forma parte del proyecto: el worker lo incorpora temporalmente a la copia ZIP que importa el navegador.

- `godot_command_center`: conexión actual con el Relay de Render y Neon. Para emparejamiento, órdenes de solo lectura y capturas 2D/3D, consulta [su guía](addons/godot_command_center/README.md).
- `godot_project_sync`: sincronización de proyectos compartidos, separada del flujo de observación visual.
- `godot_ai_bridge`: puente WebSocket heredado; no es el flujo actual del Command Center.

El proyecto es seguro para importar como workspace aislado. No reemplaza el proyecto Android del usuario. El Command Center inicia desconectado y no transmite información hasta que se introduce un código temporal de emparejamiento.

La captura actual se limita a los SubViewports 2D y 3D. El complemento es de solo lectura: todavía no dibuja, modifica escenas ni crea animaciones. La captura de la interfaz completa y del preview de juego también sigue pendiente.
