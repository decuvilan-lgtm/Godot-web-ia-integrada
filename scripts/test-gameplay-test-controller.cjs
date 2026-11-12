'use strict';

const assert = require('node:assert/strict');
const { validateTimeline, runGameplayTimeline } = require('./gameplay-test-controller.cjs');

function fakePage(failAt = null) {
  const calls = [];
  let evaluateCount = 0;
  const maybeFail = name => {
    calls.push(name);
    if (failAt === name) throw new Error('synthetic failure');
  };
  return {
    calls,
    evaluate: async () => {
      evaluateCount++;
      return evaluateCount === 1
        ? {
            activeElement: 'BODY',
            activeElementId: null,
            canvases: [{
              index: 0, id: 'game-canvas', tabindex: '2',
              width: 800, height: 600,
              rect: { x: 50, y: 25, width: 800, height: 600 },
              visible: true, parentId: 'tab-game'
            }]
          }
        : {
            focused: true, tagName: 'CANVAS', id: 'game-canvas',
            parentId: 'tab-game',
            rect: { x: 50, y: 25, width: 800, height: 600 },
            activeElement: 'CANVAS', activeElementId: 'game-canvas'
          };
    },
    keyboard: {
      press: async key => maybeFail('press:' + key),
      down: async key => maybeFail('down:' + key),
      up: async key => maybeFail('up:' + key)
    },
    mouse: {
      move: async (x, y) => maybeFail('move:' + x + ':' + y),
      click: async (x, y) => maybeFail('click:' + x + ':' + y),
      down: async () => maybeFail('mouse-down'),
      up: async () => maybeFail('mouse-up')
    },
    context: () => ({
      newCDPSession: async () => ({
        send: async (_method, params) => maybeFail('touch:' + params.type),
        detach: async () => maybeFail('touch-detach')
      })
    }),
    touchscreen: { tap: async (x, y) => maybeFail('tap:' + x + ':' + y) },
    waitForTimeout: ms => new Promise(resolve => setTimeout(resolve, ms))
  };
}

(async () => {
  assert.throws(() => validateTimeline({ duration_ms: 70000 }), /duration_ms/);
  assert.throws(() => validateTimeline({
    duration_ms: 1000,
    actions: [{ at_ms: 0, device: 'keyboard', control: 'A', state: 'execute' }]
  }), /teclado/);
  assert.throws(() => validateTimeline({
    duration_ms: 1000,
    actions: [{ at_ms: 0, device: 'mouse', state: 'click' }]
  }), /coordenadas/);

  const page = fakePage();
  const checkpoints = [];
  const result = await runGameplayTimeline(page, {
    duration_ms: 180,
    capture_interval_ms: 50,
    actions: [
      { at_ms: 0, device: 'keyboard', control: 'ArrowRight', state: 'down' },
      { at_ms: 60, device: 'keyboard', control: 'ArrowRight', state: 'up' },
      { at_ms: 80, device: 'mouse', control: 'primary', state: 'click', x: 120, y: 90 },
      { at_ms: 100, device: 'touch', control: 'tap', state: 'tap', x: 130, y: 100 },
      { at_ms: 110, device: 'touch', control: 'joystick', state: 'down', x: 200, y: 300 },
      { at_ms: 120, device: 'touch', control: 'joystick', state: 'move', x: 250, y: 320 },
      { at_ms: 130, device: 'touch', control: 'joystick', state: 'up', x: 250, y: 320 },
      { at_ms: 140, device: 'mouse', control: 'primary', state: 'click', x: 500, y: 500, coordinate_space: 'normalized' }
    ]
  }, { capture: async detail => { checkpoints.push(detail); } });
  assert.equal(result.actions_sent, 8);
  assert.equal(result.viewport_focus.focused, true);
  assert.equal(result.viewport_focus.target.id, 'game-canvas');
  assert.ok(result.events.some(event => event.type === 'timeline-complete'));
  assert.ok(page.calls.includes('down:ArrowRight'));
  assert.ok(page.calls.includes('up:ArrowRight'));
  assert.ok(page.calls.includes('click:120:90'));
  assert.ok(page.calls.includes('touch:touchStart'));
  assert.ok(page.calls.includes('touch:touchMove'));
  assert.ok(page.calls.includes('touch:touchEnd'));
  assert.ok(page.calls.includes('touch-detach'));
  assert.ok(page.calls.includes('click:450:325'), 'normalized canvas coordinates must map to the visible canvas rectangle');
  assert.equal(checkpoints.filter(item => item.phase === 'before-action').length, 8);
  assert.equal(checkpoints.filter(item => item.phase === 'after-action').length, 8);
  assert.ok(checkpoints.some(item => item.phase === 'after-action' && item.action.control === 'ArrowRight'));

  const failingPage = fakePage('press:Space');
  await assert.rejects(() => runGameplayTimeline(failingPage, {
    duration_ms: 120,
    actions: [
      { at_ms: 0, device: 'keyboard', control: 'A', state: 'down' },
      { at_ms: 5, device: 'touch', control: 'joystick', state: 'down', x: 50, y: 50 },
      { at_ms: 20, device: 'keyboard', control: 'Space', state: 'press' }
    ]
  }), /synthetic failure/);
  assert.ok(failingPage.calls.includes('up:A'), 'held key must be released after failure');
  assert.ok(failingPage.calls.includes('touch:touchEnd'), 'held touch must be released after failure');
  process.stdout.write('Gameplay controller tests passed.\\n');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
