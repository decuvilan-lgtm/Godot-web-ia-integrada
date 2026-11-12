'use strict';

const MAX_DURATION_MS = 60000;
const MAX_ACTIONS = 200;
const MAX_COORDINATE = 10000;

function integer(value, name, min, max) {
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new TypeError(`${name} debe ser un entero entre ${min} y ${max}.`);
  }
  return value;
}

function validateTimeline(config) {
  if (!config || typeof config !== 'object' || Array.isArray(config)) {
    throw new TypeError('La configuración del timeline debe ser un objeto.');
  }
  const durationMs = integer(config.duration_ms ?? 10000, 'duration_ms', 100, MAX_DURATION_MS);
  const captureIntervalMs = integer(config.capture_interval_ms ?? 500, 'capture_interval_ms', 50, 10000);
  const actions = config.actions ?? [];
  if (!Array.isArray(actions) || actions.length > MAX_ACTIONS) {
    throw new TypeError(`actions debe ser una lista de hasta ${MAX_ACTIONS} elementos.`);
  }
  const normalized = actions.map((item, index) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      throw new TypeError(`La acción ${index} no es válida.`);
    }
    const atMs = integer(item.at_ms ?? 0, `actions[${index}].at_ms`, 0, durationMs);
    const device = item.device;
    const control = String(item.control ?? '');
    const state = item.state;
    if (!['keyboard', 'mouse', 'touch'].includes(device)) {
      throw new TypeError(`Dispositivo no admitido en la acción ${index}.`);
    }
    if (device === 'keyboard') {
      if (!control || control.length > 40 || !['press', 'down', 'up'].includes(state)) {
        throw new TypeError(`Acción de teclado no válida en el índice ${index}.`);
      }
    } else if (device === 'mouse') {
      if (!['move', 'click', 'down', 'up'].includes(state)) {
        throw new TypeError(`Acción de ratón no válida en el índice ${index}.`);
      }
    } else if (state !== 'tap') {
      throw new TypeError(`La acción táctil debe ser tap (índice ${index}).`);
    }
    const x = item.x == null ? null : integer(item.x, `actions[${index}].x`, 0, MAX_COORDINATE);
    const y = item.y == null ? null : integer(item.y, `actions[${index}].y`, 0, MAX_COORDINATE);
    if ((device === 'mouse' || device === 'touch') && (x === null || y === null)) {
      throw new TypeError(`La acción ${index} necesita coordenadas x e y.`);
    }
    return { at_ms: atMs, device, control, state, x, y, button: item.button || 'left' };
  }).sort((a, b) => a.at_ms - b.at_ms);
  return { duration_ms: durationMs, capture_interval_ms: captureIntervalMs, actions: normalized };
}

async function focusGameViewport(page) {
  const before = await page.evaluate(() => ({
    activeElement: document.activeElement?.tagName || null,
    activeElementId: document.activeElement?.id || null,
    canvases: [...document.querySelectorAll('canvas')].map((canvas, index) => {
      const rect = canvas.getBoundingClientRect();
      const style = getComputedStyle(canvas);
      return {
        index, id: canvas.id || null, tabindex: canvas.getAttribute('tabindex'),
        width: canvas.width, height: canvas.height,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        visible: rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden',
        parentId: canvas.parentElement?.id || null
      };
    })
  }));
  const chosen = await page.evaluate(() => {
    const visible = canvas => {
      const r = canvas.getBoundingClientRect();
      const s = getComputedStyle(canvas);
      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
    };
    const candidates = [
      document.querySelector('#tab-game canvas'),
      document.querySelector('#game-canvas'),
      document.querySelector('#gameCanvas'),
      ...document.querySelectorAll('canvas')
    ].filter((canvas, index, all) => canvas && all.indexOf(canvas) === index && visible(canvas));
    const canvas = candidates[0];
    if (!canvas) return { focused: false, reason: 'No se encontró un canvas visible.' };
    canvas.setAttribute('tabindex', canvas.getAttribute('tabindex') || '0');
    canvas.focus({ preventScroll: true });
    const r = canvas.getBoundingClientRect();
    return {
      focused: document.activeElement === canvas,
      tagName: canvas.tagName,
      id: canvas.id || null,
      parentId: canvas.parentElement?.id || null,
      rect: { x: r.x, y: r.y, width: r.width, height: r.height },
      activeElement: document.activeElement?.tagName || null,
      activeElementId: document.activeElement?.id || null
    };
  });
  return { before, target: chosen, focused: Boolean(chosen.focused) };
}

async function runGameplayTimeline(page, input, options = {}) {
  const config = validateTimeline(input);
  const started = Date.now();
  const events = [];
  const heldKeys = new Set();
  const heldButtons = new Set();
  let nextCapture = 0;
  let actionIndex = 0;
  const capture = typeof options.capture === 'function' ? options.capture : null;
  const log = (type, detail = {}) => events.push({ at_ms: Date.now() - started, type, ...detail });
  const waitUntil = async target => {
    while (Date.now() - started < target) {
      const remaining = target - (Date.now() - started);
      await page.waitForTimeout(Math.min(remaining, 100));
    }
  };
  const perform = async action => {
    if (action.device === 'keyboard') {
      if (action.state === 'press') {
        await page.keyboard.press(action.control);
      } else if (action.state === 'down') {
        await page.keyboard.down(action.control);
        heldKeys.add(action.control);
      } else {
        await page.keyboard.up(action.control);
        heldKeys.delete(action.control);
      }
    } else if (action.device === 'mouse') {
      await page.mouse.move(action.x ?? 0, action.y ?? 0);
      if (action.state === 'click') {
        await page.mouse.click(action.x, action.y, { button: action.button });
      } else if (action.state === 'down') {
        await page.mouse.down({ button: action.button });
        heldButtons.add(action.button);
      } else if (action.state === 'up') {
        await page.mouse.up({ button: action.button });
        heldButtons.delete(action.button);
      }
    } else {
      await page.touchscreen.tap(action.x, action.y);
    }
    log('input', { device: action.device, control: action.control, state: action.state, x: action.x, y: action.y });
  };

  try {
    while (Date.now() - started < config.duration_ms) {
      const elapsed = Date.now() - started;
      while (actionIndex < config.actions.length && config.actions[actionIndex].at_ms <= elapsed) {
        await perform(config.actions[actionIndex++]);
      }
      if (capture && elapsed >= nextCapture) {
        await capture({ at_ms: elapsed, index: events.filter(e => e.type === 'capture').length });
        log('capture');
        nextCapture += config.capture_interval_ms;
      }
      const nextActionAt = actionIndex < config.actions.length ? config.actions[actionIndex].at_ms : config.duration_ms;
      const nextCaptureAt = capture ? nextCapture : config.duration_ms;
      await waitUntil(Math.min(config.duration_ms, Math.max(elapsed + 10, Math.min(nextActionAt, nextCaptureAt))));
    }
    while (actionIndex < config.actions.length && config.actions[actionIndex].at_ms <= config.duration_ms) {
      await perform(config.actions[actionIndex++]);
    }
    log('timeline-complete', { duration_ms: Date.now() - started });
  } catch (error) {
    log('timeline-error', { message: String(error?.message || error) });
    throw error;
  } finally {
    for (const key of heldKeys) {
      try { await page.keyboard.up(key); log('auto-release', { device: 'keyboard', control: key }); } catch {}
    }
    for (const button of heldButtons) {
      try { await page.mouse.up({ button }); log('auto-release', { device: 'mouse', button }); } catch {}
    }
  }
  return { requested_duration_ms: config.duration_ms, elapsed_ms: Date.now() - started, actions_requested: config.actions.length, actions_sent: actionIndex, viewport_focus: viewportFocus, events };
}

module.exports = { validateTimeline, focusGameViewport, runGameplayTimeline, MAX_DURATION_MS, MAX_ACTIONS };
