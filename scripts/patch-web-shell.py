#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1] / "public"
entry = root / "index.html"
if not entry.is_file():
    raise SystemExit("ERROR: public/index.html not found")

html = entry.read_text(encoding="utf-8")
viewport = '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
if re.search(r'<meta[^>]+name=["\']viewport["\']', html, flags=re.I):
    html = re.sub(
        r'<meta([^>]+name=["\']viewport["\'][^>]*)>',
        lambda m: '<meta' + re.sub(r'content=["\'][^"\']*["\']', 'content="width=device-width, initial-scale=1, viewport-fit=cover"', m.group(1), flags=re.I) + '>',
        html,
        count=1,
        flags=re.I,
    )
else:
    html = re.sub(r'(<head[^>]*>)', r'\1\n  ' + viewport, html, count=1, flags=re.I)

if not re.search(r'<meta[^>]+name=["\']viewport["\']', html, flags=re.I):
    raise SystemExit("ERROR: could not install mobile viewport metadata")

if not re.search(r'<title[^>]*>', html, flags=re.I):
    html = re.sub(r'</head>', '<title>Godot Web IA Integrada</title>\n</head>', html, count=1, flags=re.I)


# Keep the shared-project connector discoverable without replacing or covering the editor UI.
if 'id="shared-project-sync-launcher"' not in html:
    connector_ui = r"""
<style>
#shared-project-sync-launcher{position:fixed;right:12px;top:12px;z-index:2147483000;font:13px/1.4 system-ui,sans-serif;color:#f5f7fb}
#shared-project-sync-launcher button{border:1px solid #596579;border-radius:999px;background:#202938;color:inherit;padding:9px 13px;font:inherit;box-shadow:0 2px 12px #0005}
#shared-project-sync-panel{display:none;width:min(290px,calc(100vw - 24px));margin-top:8px;padding:13px;border:1px solid #596579;border-radius:12px;background:#18212e;box-shadow:0 8px 28px #0008}
#shared-project-sync-panel[data-open="true"]{display:block}
#shared-project-sync-panel p{margin:0 0 10px}
#shared-project-sync-panel a{display:block;margin-top:8px;border-radius:8px;background:#34465e;color:#fff;padding:9px 10px;text-decoration:none}
#shared-project-sync-panel a:focus-visible,#shared-project-sync-launcher button:focus-visible{outline:2px solid #9dc4ff;outline-offset:2px}
</style>
<div id="shared-project-sync-launcher">
  <button type="button" id="shared-project-sync-toggle" aria-expanded="false" aria-controls="shared-project-sync-panel">Compartir proyectos</button>
  <div id="shared-project-sync-panel" data-open="false">
    <p><strong>Conectar Godot Web y Android</strong></p>
    <p>Importa y abre este proyecto conector para empezar a compartirlo. Para un proyecto Web existente, instala también los tres add-ons de integración en su carpeta addons y actívalos en Project Settings > Plugins. Empareja ambos editores en el mismo workspace y selecciona el mismo proyecto compartido.</p>
    <a href="./bridge-sandbox.zip" download="godot-shared-project-connector.zip">Descargar proyecto conector</a>
    <a href="https://github.com/decuvilan-lgtm/Godot-web-ia-integrada/blob/main/docs/SHARED_PROJECT_SYNC.md" target="_blank" rel="noopener noreferrer">Abrir guía de sincronización</a>
  </div>
</div>
<script>
(function(){
  var toggle=document.getElementById("shared-project-sync-toggle");
  var panel=document.getElementById("shared-project-sync-panel");
  if(!toggle||!panel)return;
  toggle.addEventListener("click",function(){
    var open=panel.getAttribute("data-open")!=="true";
    panel.setAttribute("data-open",open?"true":"false");
    toggle.setAttribute("aria-expanded",open?"true":"false");
  });
})();
</script>
"""
    html = re.sub(r"</body\s*>", connector_ui + "\n</body>", html, count=1, flags=re.I)
    if 'id="shared-project-sync-launcher"' not in html:
        raise SystemExit("ERROR: could not add the shared-project connector entry point")

# Fail the build if the upstream HTML changes the startup contract.
if 'id="startButton"' not in html or "function startEditor(zip)" not in html or "'--project-manager'" not in html:
    raise SystemExit("ERROR: official Godot Web Project Manager startup contract changed")

# Start the official Project Manager automatically after the page is fully loaded.
# The official start button already performs the supported initialization path.
auto_start = r"""
<script id="godot-auto-start">
window.addEventListener("load", function () {
  const startButton = document.getElementById("startButton");
  // Keep Godot's own missing-feature checks authoritative (e.g. SharedArrayBuffer).
  if (!startButton || startButton.disabled) return;
  if (typeof closeWelcomeModal === "function") closeWelcomeModal(false);
  startButton.click();
}, { once: true });
</script>
"""
if 'id="godot-auto-start"' not in html:
    html = re.sub(r"</body\s*>", auto_start + "\n</body>", html, count=1, flags=re.I)
    if 'id="godot-auto-start"' not in html:
        raise SystemExit("ERROR: could not install automatic Godot Project Manager startup")

entry.write_text(html, encoding="utf-8")
print("Mobile viewport metadata: OK")
print("Godot Project Manager auto-start: OK")
