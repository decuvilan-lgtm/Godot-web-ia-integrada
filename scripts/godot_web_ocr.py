#!/usr/bin/env python3
"""OCR helper for locating Godot Web Project Manager buttons in CI screenshots."""
from __future__ import annotations
import json
import sys
from pathlib import Path
import pytesseract
from PIL import Image

def scan(path: Path) -> dict:
    image = Image.open(path).convert('RGB')
    data = pytesseract.image_to_data(image, config='--psm 11', output_type=pytesseract.Output.DICT)
    grouped = {}
    for i, raw in enumerate(data['text']):
        if raw.strip():
            key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
            grouped.setdefault(key, []).append(i)
    lines = []
    for indices in grouped.values():
        words = [data['text'][i].strip() for i in indices if data['text'][i].strip()]
        if not words: continue
        x0 = min(data['left'][i] for i in indices)
        y0 = min(data['top'][i] for i in indices)
        x1 = max(data['left'][i] + data['width'][i] for i in indices)
        y1 = max(data['top'][i] + data['height'][i] for i in indices)
        lines.append({'text': ' '.join(words), 'x': (x0+x1)//2, 'y': (y0+y1)//2, 'box': [x0,y0,x1-x0,y1-y0]})
    lines.sort(key=lambda item: (item['y'], item['x']))
    return {'image': str(path), 'text': '\\n'.join(item['text'] for item in lines), 'lines': lines}

if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('usage: godot_web_ocr.py screenshot.png')
    print(json.dumps(scan(Path(sys.argv[1])), ensure_ascii=False))
