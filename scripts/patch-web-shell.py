#!/usr/bin/env python3
"""Patch the official Godot Web shell without replacing its editor UI."""
from pathlib import Path
import re


RELAY_URL = "https://godot-web-ia-relay.onrender.com"
STARTUP_CONTRACT = (
    'id="startButton"',
    'id="zip-file"',
    "function startEditor(zip)",
    "'--project-manager'",
)


def patch_html(html: str) -> str:
    """Apply idempotent mobile metadata and the GitHub-to-Project-Manager bridge."""
    viewport = '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    viewport_pattern = r"""<meta[^>]+name=["']viewport["']"""
    if re.search(viewport_pattern, html, flags=re.I):
        html = re.sub(
            r"""<meta([^>]+name=["']viewport["'][^>]*)>""",
            lambda match: '<meta' + re.sub(
                r"""content=["'][^"']*["']""",
                'content="width=device-width, initial-scale=1, viewport-fit=cover"',
                match.group(1),
                flags=re.I,
            ) + '>',
            html,
            count=1,
            flags=re.I,
        )
    else:
        html = re.sub(
            r"(<head[^>]*>)",
            lambda match: match.group(1) + chr(10) + "  " + viewport,
            html,
            count=1,
            flags=re.I,
        )

    if not re.search(viewport_pattern, html, flags=re.I):
        raise SystemExit("ERROR: could not install mobile viewport metadata")

    if not re.search(r"<title[^>]*>", html, flags=re.I):
        html = re.sub(
            r"</head>",
            "<title>Godot Web IA Integrada</title>" + chr(10) + "</head>",
            html,
            count=1,
            flags=re.I,
        )

    missing = [token for token in STARTUP_CONTRACT if token not in html]
    if missing:
        raise SystemExit("ERROR: official Godot Web startup contract changed: " + ", ".join(missing))

    connector = r"""
<script id="godot-github-connector">
(function () {
  "use strict";
  const relay = "__RELAY_URL__";
  const repoPattern = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$/;

  function connectRepository() {
    const value = window.prompt("Repositorio público de GitHub (owner/repository). Se usará exclusivamente main:");
    if (!value) return;
    const repo = value.trim();
    if (!repoPattern.test(repo)) {
      window.alert("Formato no válido. Escribe owner/repository, sin URL.");
      return;
    }
    if (!window.confirm("Se recargará Godot Web para precargar " + repo + " (main). Guarda antes cualquier cambio local no publicado. ¿Continuar?")) return;
    const target = new URL(window.location.href);
    target.searchParams.set("repo", repo);
    window.location.assign(target.toString());
  }

  window.addEventListener("DOMContentLoaded", function () {
    const bar = document.getElementById("tabs-buttons");
    if (!bar || document.getElementById("godot-connect-github")) return;
    const button = document.createElement("button");
    button.id = "godot-connect-github";
    button.type = "button";
    button.className = "btn tab-btn";
    button.textContent = "Conectar GitHub";
    button.title = "Precargar un repositorio público desde la rama main";
    button.addEventListener("click", connectRepository);
    bar.appendChild(button);
  });

  window.addEventListener("load", async function () {
    const startButton = document.getElementById("startButton");
    if (!startButton || startButton.disabled) return;

    const repo = new URLSearchParams(window.location.search).get("repo");
    if (repo) {
      if (!repoPattern.test(repo)) {
        window.alert("No se pudo conectar el repositorio: usa owner/repository.");
      } else {
        const [owner, repository] = repo.split("/");
        try {
          const response = await fetch(
            relay + "/v1/github/" + encodeURIComponent(owner) + "/" + encodeURIComponent(repository) + "/archive",
            { method: "GET", mode: "cors", credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer" }
          );
          if (!response.ok) {
            let detail = "HTTP " + response.status;
            try {
              const payload = await response.json();
              if (payload && payload.detail) detail = payload.detail;
            } catch (_error) {}
            throw new Error(detail);
          }
          const blob = await response.blob();
          if (!blob.size || blob.size > 128 * 1024 * 1024) {
            throw new Error("El ZIP está vacío o supera el límite de 128 MiB.");
          }
          const input = document.getElementById("zip-file");
          if (!input || typeof DataTransfer === "undefined") {
            throw new Error("Este navegador no permite precargar el ZIP automáticamente.");
          }
          const transfer = new DataTransfer();
          transfer.items.add(new File([blob], owner + "-" + repository + "-main.zip", { type: "application/zip" }));
          input.files = transfer.files;
          input.dispatchEvent(new Event("change", { bubbles: true }));
          const cleanUrl = new URL(window.location.href);
          cleanUrl.searchParams.delete("repo");
          window.history.replaceState(null, "", cleanUrl.toString());
        } catch (error) {
          window.alert("No se pudo descargar " + repo + " desde main: " + String(error.message || error));
        }
      }
    }

    if (typeof closeWelcomeModal === "function") closeWelcomeModal(false);
    startButton.click();
  }, { once: true });
})();
</script>
""".replace("__RELAY_URL__", RELAY_URL)

    if 'id="godot-github-connector"' not in html:
        html = re.sub(
            r"</body\s*>",
            lambda match: connector + chr(10) + match.group(0),
            html,
            count=1,
            flags=re.I,
        )
        if 'id="godot-github-connector"' not in html:
            raise SystemExit("ERROR: could not install GitHub connector")

    return html


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "public"
    entry = root / "index.html"
    if not entry.is_file():
        raise SystemExit("ERROR: public/index.html not found")
    html = patch_html(entry.read_text(encoding="utf-8"))
    entry.write_text(html, encoding="utf-8")
    print("Mobile viewport metadata: OK")
    print("Godot Project Manager auto-start: OK")
    print("Public GitHub repository preloader: OK")


if __name__ == "__main__":
    main()
