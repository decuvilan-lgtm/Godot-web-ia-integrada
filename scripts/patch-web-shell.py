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

entry.write_text(html, encoding="utf-8")
print("Mobile viewport metadata: OK")
