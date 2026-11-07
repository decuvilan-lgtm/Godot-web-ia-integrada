# Godot AI Bridge Sandbox

A minimal Godot project used to test the editor plugin and remote inspection protocol.

The project intentionally contains only a single Node2D scene. It is safe to import into the web editor without replacing another project.

The editor plugin is enabled in `project.godot`. The bridge starts disconnected and does not transmit project information until a user enters a WSS endpoint and a temporary session token.

For protocol details, see `addons/godot_ai_bridge/README.md`.
