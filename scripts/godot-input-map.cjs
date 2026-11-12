'use strict';

const fs = require('node:fs');

function splitTopLevel(source) {
  const parts = [];
  let start = 0, depth = 0, quoted = false, escaped = false;
  for (let i = 0; i < source.length; i++) {
    const ch = source[i];
    if (quoted) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === '"') quoted = false;
      continue;
    }
    if (ch === '"') quoted = true;
    else if (ch === '{' || ch === '[' || ch === '(') depth++;
    else if (ch === '}' || ch === ']' || ch === ')') depth = Math.max(0, depth - 1);
    else if (ch === ',' && depth === 0) {
      parts.push(source.slice(start, i).trim());
      start = i + 1;
    }
  }
  if (source.slice(start).trim()) parts.push(source.slice(start).trim());
  return parts;
}

function parseFields(source) {
  const fields = {};
  for (const part of splitTopLevel(source)) {
    const match = part.match(/^"((?:[^"\\]|\\.)+)"\s*:\s*(.*)$/s);
    if (!match) continue;
    let value = match[2].trim();
    if (value === 'true') value = true;
    else if (value === 'false') value = false;
    else if (value === 'null') value = null;
    else if (/^-?\d+$/.test(value)) value = Number(value);
    else if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, '\\');
    fields[match[1]] = value;
  }
  return fields;
}

function extractObjects(value) {
  const events = [];
  const pattern = /Object\((InputEvent[A-Za-z0-9_]+)\s*,/g;
  let match;
  while ((match = pattern.exec(value))) {
    let start = pattern.lastIndex, depth = 1, quoted = false, escaped = false, end = start;
    for (; end < value.length; end++) {
      const ch = value[end];
      if (quoted) {
        if (escaped) escaped = false;
        else if (ch === '\\') escaped = true;
        else if (ch === '"') quoted = false;
        continue;
      }
      if (ch === '"') quoted = true;
      else if (ch === '(') depth++;
      else if (ch === ')') {
        depth--;
        if (depth === 0) break;
      }
    }
    const fields = parseFields(value.slice(start, end));
    events.push({ type: match[1], properties: fields, descriptor: describeEvent(match[1], fields) });
    pattern.lastIndex = end + 1;
  }
  return events;
}


const SPECIAL_KEYS = new Map([
  [4194305, 'Escape'], [4194306, 'Tab'], [4194308, 'Backspace'],
  [4194309, 'Enter'], [4194311, 'Insert'], [4194312, 'Delete'],
  [4194315, 'Home'], [4194316, 'End'], [4194319, 'ArrowLeft'],
  [4194320, 'ArrowUp'], [4194321, 'ArrowRight'], [4194322, 'ArrowDown'],
  [4194323, 'PageUp'], [4194324, 'PageDown']
]);

function describeEvent(type, properties) {
  if (type === 'InputEventKey') {
    const code = properties.physical_keycode || properties.keycode || properties.key_label || 0;
    let label = SPECIAL_KEYS.get(code);
    if (!label && code >= 32 && code <= 126) label = String.fromCharCode(code).toUpperCase();
    return { device: 'keyboard', control: label || 'keycode:' + code, raw_code: code };
  }
  if (type === 'InputEventMouseButton') {
    const buttons = { 1: 'LeftClick', 2: 'RightClick', 3: 'MiddleClick', 4: 'WheelUp', 5: 'WheelDown' };
    const code = properties.button_index;
    return { device: 'mouse', control: buttons[code] || 'mouse_button:' + code, raw_code: code };
  }
  if (type === 'InputEventJoypadButton') {
    return { device: 'gamepad', control: 'button:' + properties.button_index, raw_code: properties.button_index };
  }
  if (type === 'InputEventJoypadMotion') {
    return { device: 'gamepad', control: 'axis:' + properties.axis + ':' + properties.axis_value, raw_code: properties.axis };
  }
  if (type === 'InputEventScreenTouch') return { device: 'touch', control: 'screen_touch', raw_code: properties.index };
  if (type === 'InputEventScreenDrag') return { device: 'touch', control: 'screen_drag', raw_code: properties.index };
  return { device: 'other', control: type, raw_code: null };
}

function parseInputMap(text) {
  if (typeof text !== 'string') throw new TypeError('project.godot debe ser texto.');
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const actions = [];
  let inInput = false, current = null, collecting = false, buffer = '', depth = 0;
  const flush = () => {
    if (!current) return;
    const events = extractObjects(buffer);
    actions.push({
      name: current.name,
      deadzone: current.deadzone,
      events,
      declared_event_count: events.length,
      source: 'project.godot [input]',
      confidence: 'declared'
    });
    current = null; collecting = false; buffer = ''; depth = 0;
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (/^\[[^\]]+\]$/.test(line)) {
      flush();
      inInput = line === '[input]';
      continue;
    }
    if (!inInput || !line || line.startsWith(';') || line.startsWith('#')) continue;
    if (!collecting) {
      const match = line.match(/^(?:"((?:[^"\\]|\\.)+)"|([A-Za-z0-9_./-]+))\s*=\s*\{(.*)$/);
      if (!match) continue;
      current = { name: (match[1] || match[2]).replace(/\\"/g, '"'), deadzone: null };
      buffer = match[3];
      collecting = true;
      depth = 1 + (([...buffer.matchAll(/\{/g)].length) - ([...buffer.matchAll(/\}/g)].length));
    } else {
      buffer += '\n' + line;
      depth += [...line.matchAll(/\{/g)].length - [...line.matchAll(/\}/g)].length;
    }
    const deadzone = buffer.match(/"deadzone"\s*:\s*([0-9.]+)/);
    if (deadzone) current.deadzone = Number(deadzone[1]);
    if (depth <= 0) flush();
  }
  flush();
  return {
    format: 'godot-project-input-map',
    version: 1,
    action_count: actions.length,
    actions,
    interpretation: 'Los eventos se extraen literalmente de project.godot. El nombre de una acción no demuestra por sí solo su función dentro del juego.'
  };
}

if (require.main === module) {
  const path = process.argv[2];
  if (!path) throw new Error('Uso: node godot-input-map.cjs <project.godot>');
  const result = parseInputMap(fs.readFileSync(path, 'utf8'));
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}

module.exports = { parseInputMap, extractObjects, splitTopLevel, describeEvent };
