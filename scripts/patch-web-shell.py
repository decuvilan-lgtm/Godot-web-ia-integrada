#!/usr/bin/env python3
"""Patch the official Godot Web shell without replacing its editor UI."""
from pathlib import Path
import re


RELAY_URL = "https://godot-web-ia-relay.onrender.com"
def patch_html(html: str) -> str:
    """Apply mobile metadata and connector; validate structure, not private Godot APIs."""
    if not re.search(r"<html\b", html, flags=re.I):
        raise SystemExit("ERROR: input is not an HTML document (missing <html>)")
    if not re.search(r"<head\b", html, flags=re.I):
        raise SystemExit("ERROR: HTML document has no <head>")
    if not re.search(r"<body\b", html, flags=re.I) or not re.search(r"</body\s*>", html, flags=re.I):
        raise SystemExit("ERROR: HTML document has no complete <body>")

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

    connector = r"""
<script id="godot-github-connector" data-version="commit-pinned-v3">
(function () {
  "use strict";
  const relay = "__RELAY_URL__";
  const repoPattern = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$/;
  const branchPattern = /^[A-Za-z0-9._/-]{1,128}$/;
  const commitShaPattern = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/i;

  function validBranch(value) {
    return !value || (
      branchPattern.test(value) && !value.startsWith("/") && !value.endsWith("/") &&
      !value.includes("//") && !value.includes("..") && !value.endsWith(".") &&
      !value.includes("@{") && !["~", "^", ":", "?", "*", "[", "]", "\\", " "].some(char => value.includes(char)) &&
      value.split("/").every(part => part && part !== "." && part !== "..")
    );
  }

  function validCommitSha(value) {
    return !value || commitShaPattern.test(value);
  }

  function validProjectPath(value) {
    return !value || (
      value.length <= 240 && !value.startsWith("/") && !value.endsWith("/") &&
      !value.includes("\\") && value.split("/").every(part => part && part !== "." && part !== "..")
    );
  }

  function connectRepository() {
    const value = window.prompt("Repositorio público de GitHub (owner/repository):");
    if (!value) return;
    const repo = value.trim();
    if (!repoPattern.test(repo)) {
      window.alert("Formato no válido. Escribe owner/repository, sin URL.");
      return;
    }
    const branch = (window.prompt("Rama de GitHub (vacío = rama predeterminada):", "") || "").trim();
    if (!validBranch(branch)) {
      window.alert("Nombre de rama no válido.");
      return;
    }
    const commitSha = (window.prompt("Commit SHA exacto (vacío = último commit de la rama):", "") || "").trim().toLowerCase();
    if (!validCommitSha(commitSha)) {
      window.alert("El SHA debe tener 40 o 64 caracteres hexadecimales.");
      return;
    }
    const projectPath = (window.prompt("Carpeta que contiene project.godot (vacío = raíz):", "") || "").trim();
    if (!validProjectPath(projectPath)) {
      window.alert("Ruta de proyecto no válida. Usa carpetas separadas por /.");
      return;
    }
    const description = repo + (branch ? " · " + branch : " · rama predeterminada") + (commitSha ? " · SHA " + commitSha : " · último commit") + (projectPath ? " · " + projectPath : " · raíz");
    if (!window.confirm("Se recargará Godot Web para precargar " + description + ". Guarda antes cualquier cambio local no publicado. ¿Continuar?")) return;
    const target = new URL(window.location.href);
    target.searchParams.set("repo", repo);
    if (branch) target.searchParams.set("branch", branch);
    else target.searchParams.delete("branch");
    if (commitSha) target.searchParams.set("sha", commitSha);
    else target.searchParams.delete("sha");
    if (projectPath) target.searchParams.set("path", projectPath);
    else target.searchParams.delete("path");
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
    button.title = "Precargar un repositorio público, una rama y una carpeta Godot";
    button.addEventListener("click", connectRepository);
    bar.appendChild(button);
  });

  async function waitForElement(selector, predicate, timeoutMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const element = document.querySelector(selector);
      if (element && (!predicate || predicate(element))) return element;
      await new Promise(resolve => window.setTimeout(resolve, 150));
    }
    throw new Error("Tiempo agotado esperando " + selector + ".");
  }

  async function startGodotWeb() {
    const startButton = await waitForElement("#startButton", null, 45000);
    const input = await waitForElement("#zip-file", null, 45000);
    const params = new URLSearchParams(window.location.search);
    const repo = params.get("repo");

    window.__godotGithubConnectorStatus = { phase: "initializing", repo: repo || null };

    if (repo) {
      const branch = (params.get("branch") || "").trim();
      const projectPath = (params.get("path") || "").trim();
      const commitSha = (params.get("sha") || "").trim().toLowerCase();
      if (!repoPattern.test(repo) || !validBranch(branch) || !validCommitSha(commitSha) || !validProjectPath(projectPath)) {
        window.__godotGithubConnectorStatus = { phase: "invalid-parameters", repo };
        throw new Error("Revisa owner/repository, rama y carpeta del proyecto.");
      }

      const [owner, repository] = repo.split("/");
      try {
        window.__godotGithubConnectorStatus.phase = "downloading";
        const archiveUrl = new URL(
          relay + "/v1/github/" + encodeURIComponent(owner) + "/" + encodeURIComponent(repository) + "/archive"
        );
        if (branch) archiveUrl.searchParams.set("branch", branch);
        if (commitSha) archiveUrl.searchParams.set("sha", commitSha);
        if (projectPath) archiveUrl.searchParams.set("path", projectPath);

        const response = await fetch(archiveUrl.toString(), {
          method: "GET",
          mode: "cors",
          credentials: "omit",
          cache: "no-store",
          referrerPolicy: "no-referrer"
        });
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
        if (typeof DataTransfer === "undefined") {
          throw new Error("Este navegador no permite precargar el ZIP automáticamente.");
        }

        const selectedRef = response.headers.get("X-GitHub-Ref") || commitSha || branch || "default";
        const selectedCommitSha = response.headers.get("X-GitHub-Commit-SHA") || (commitSha || null);
        if (commitSha && selectedCommitSha !== commitSha) throw new Error("El Relay no confirmó el SHA solicitado.");
        const refFile = selectedRef.replace(/[^A-Za-z0-9._-]+/g, "-");
        const filename = owner + "-" + repository + "-" + refFile + ".zip";
        const transfer = new DataTransfer();
        transfer.items.add(new File([blob], filename, { type: "application/zip" }));
        input.files = transfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));

        if (input.files.length !== 1 || input.files[0].name !== filename) {
          throw new Error("El navegador no conservó el ZIP en el control oficial de Godot.");
        }
        window.__godotGithubConnectorStatus = {
          phase: "zip-assigned",
          repo,
          filename,
          bytes: blob.size,
          branch,
          commitSha: selectedCommitSha,
          selectedRef
        };

        const cleanUrl = new URL(window.location.href);
        cleanUrl.searchParams.delete("repo");
        cleanUrl.searchParams.delete("branch");
        cleanUrl.searchParams.delete("path");
        cleanUrl.searchParams.delete("sha");
        window.history.replaceState(null, "", cleanUrl.toString());
      } catch (error) {
        window.__godotGithubConnectorStatus = {
          phase: "failed",
          repo,
          error: String(error.message || error)
        };
        window.alert("No se pudo descargar " + repo + ": " + String(error.message || error));
        return;
      }
    }

    // Godot puede mantener Start deshabilitado mientras termina su inicialización.
    // No abortar la importación: esperar a que el botón esté listo.
    await waitForElement("#startButton", element => !element.disabled, 90000);
    if (typeof closeWelcomeModal === "function") closeWelcomeModal(false);
    window.__godotGithubConnectorStatus = {
      ...(window.__godotGithubConnectorStatus || {}),
      phase: "starting"
    };
    startButton.click();
    window.__godotGithubConnectorStatus = {
      ...(window.__godotGithubConnectorStatus || {}),
      phase: "started"
    };
  }

  function scheduleGodotStart() {
    // The acceptance harness can drive the official Project Manager manually.
    if (new URLSearchParams(window.location.search).get("manual") === "1") return;
    startGodotWeb().catch(error => {
      window.__godotGithubConnectorStatus = {
        ...(window.__godotGithubConnectorStatus || {}),
        phase: "failed",
        error: String(error.message || error)
      };
      console.error("[Godot GitHub connector]", error);
      window.alert("No se pudo iniciar Godot Web: " + String(error.message || error));
    });
  }

  // No depender exclusivamente del evento load: el script puede ejecutarse
  // después de ese evento en navegaciones/restauraciones del navegador.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleGodotStart, { once: true });
  } else {
    scheduleGodotStart();
  }
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
