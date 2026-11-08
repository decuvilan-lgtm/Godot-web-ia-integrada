"""Same-origin, ephemeral administrator page for device pairing codes."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

router = APIRouter(tags=["command-center-admin"])

_PAGE = """<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>Godot Command Center · Emparejamiento</title>
  <style>
    :root{color-scheme:dark;font-family:system-ui,sans-serif;background:#10151d;color:#e8edf5}
    *{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:20px}
    main{width:min(100%,560px);background:#192230;border:1px solid #334155;border-radius:18px;padding:24px}
    h1{font-size:1.35rem;margin:0 0 8px}p{color:#aebbd0;line-height:1.5}
    label{display:block;margin:18px 0 7px;font-weight:600}
    input,select,button{width:100%;font:inherit;border-radius:10px;padding:12px;border:1px solid #43536b;background:#101923;color:#f5f7fb}
    button{margin-top:18px;background:#2563eb;border:0;font-weight:700;cursor:pointer}
    button:disabled{opacity:.55;cursor:wait}.hint{font-size:.88rem}
    #result{margin-top:20px;padding:16px;border:1px solid #43536b;border-radius:12px}
    #code{display:block;overflow-wrap:anywhere;font:600 1.05rem ui-monospace,monospace;margin:12px 0}
    #copy{background:#334155}#status{min-height:1.5em;margin-top:14px}
    [hidden]{display:none!important}
  </style>
</head>
<body>
<main>
  <h1>Godot Command Center</h1>
  <p>Genera un código temporal para vincular un editor o el agente. El código se muestra una sola vez y caduca en dos minutos.</p>
  <form id="pairing-form">
    <label for="admin-token">Credencial administrativa</label>
    <input id="admin-token" type="password" autocomplete="off" spellcheck="false" required>
    <label for="workspace">Espacio de trabajo</label>
    <input id="workspace" value="default" maxlength="80" required>
    <label for="device-kind">Tipo de dispositivo</label>
    <select id="device-kind">
      <option value="android_editor">Godot Android</option>
      <option value="web_editor">Godot Web</option>
      <option value="agent_controller">Agente controlador</option>
    </select>
    <button id="generate" type="submit">Generar código de emparejamiento</button>
  </form>
  <section id="result" hidden aria-live="polite">
    <strong>Código temporal</strong>
    <code id="code"></code>
    <p id="expiry" class="hint"></p>
    <button id="copy" type="button">Copiar código</button>
  </section>
  <p id="status" role="status" aria-live="polite"></p>
  <p class="hint">Esta página no guarda la credencial ni el código en el navegador. Cierra la página al terminar y no compartas el código con otras personas.</p>
</main>
<script src="/command-center/admin.js" defer></script>
</body>
</html>"""

_SCRIPT = """(() => {
  const form = document.getElementById('pairing-form');
  const token = document.getElementById('admin-token');
  const workspace = document.getElementById('workspace');
  const kind = document.getElementById('device-kind');
  const button = document.getElementById('generate');
  const result = document.getElementById('result');
  const code = document.getElementById('code');
  const expiry = document.getElementById('expiry');
  const status = document.getElementById('status');
  const copy = document.getElementById('copy');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    result.hidden = true;
    code.textContent = '';
    status.textContent = 'Generando código…';
    button.disabled = true;
    const secret = token.value;
    token.value = '';
    try {
      const response = await fetch('/v1/command-center/pairing-codes', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Command-Center-Admin': secret
        },
        body: JSON.stringify({device_kind: kind.value, workspace: workspace.value.trim()})
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || 'No se pudo generar el código.');
      }
      code.textContent = payload.pairing_code;
      expiry.textContent = 'Caduca en ' + payload.expires_in_seconds + ' segundos. Úsalo inmediatamente en el editor correspondiente.';
      result.hidden = false;
      status.textContent = 'Código generado. La credencial administrativa se ha limpiado del campo.';
    } catch (error) {
      status.textContent = error.message || 'Error de conexión.';
    } finally {
      button.disabled = false;
    }
  });

  copy.addEventListener('click', async () => {
    const value = code.textContent;
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      status.textContent = 'Código copiado.';
    } catch (_) {
      status.textContent = 'No se pudo copiar automáticamente. Selecciona y copia el código manualmente.';
    }
  });
})();"""

@router.get("/command-center/admin", response_class=HTMLResponse, include_in_schema=False)
async def command_center_admin_page():
    return HTMLResponse(
        _PAGE,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        },
    )

@router.get("/command-center/admin.js", include_in_schema=False)
async def command_center_admin_script():
    return Response(
        _SCRIPT,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )
