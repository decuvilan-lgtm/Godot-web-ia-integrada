'use strict';

const assert = require('node:assert/strict');
const { parseInputMap } = require('./godot-input-map.cjs');

const source = String.raw`config/name="Generic Sample"

[input]
"move_right"={
"deadzone": 0.2,
"events": [Object(InputEventKey,"resource_local_to_scene":false,"keycode":68,"physical_keycode":68,"unicode":100,"echo":false,"script":null)]
}
"jump"={
"deadzone": 0.5,
"events": [Object(InputEventKey,"keycode":32,"physical_keycode":32), Object(InputEventJoypadButton,"button_index":0)]
}
"pointer_action"={
"deadzone": 0.5,
"events": [Object(InputEventMouseButton,"button_index":1,"pressed":false)]
}

[rendering]
renderer/rendering_method="gl_compatibility"
`;

const result = parseInputMap(source);
assert.equal(result.action_count, 3);
assert.equal(result.actions[0].name, 'move_right');
assert.equal(result.actions[0].deadzone, 0.2);
assert.equal(result.actions[0].events[0].type, 'InputEventKey');
assert.equal(result.actions[0].events[0].properties.physical_keycode, 68);
assert.equal(result.actions[1].events.length, 2);
assert.equal(result.actions[1].events[1].type, 'InputEventJoypadButton');
assert.equal(result.actions[2].events[0].properties.button_index, 1);
assert.equal(result.actions[0].confidence, 'declared');
assert.match(result.interpretation, /no demuestra/);
assert.equal(parseInputMap('[display]\\nwindow/size/viewport_width=1280').action_count, 0);
process.stdout.write('Godot input-map parser tests passed.\\n');
