#!/usr/bin/env bash
set -euo pipefail
GODOT="$1"
PROJECT="$2"
PROBE="res://tools/headless_bridge/bridge_probe.gd"
run_probe() {
  "$GODOT" --headless --path "$PROJECT" --script "$PROBE" -- "$@"
}
run_probe project.inspect_resource '{"path":"res://icon.svg"}' | tee artifacts/icon-resource-inspection.log
grep -q '"ok":true' artifacts/icon-resource-inspection.log
run_probe project.list_resources | tee artifacts/project-resources.log
grep -q 'res://main.tscn' artifacts/project-resources.log
echo "FRESH_PROJECT_RESOURCE_INSPECTION_PASS"
run_probe scene.add_node '{"type":"CharacterBody2D","name":"SandboxBody"}'
run_probe scene.add_node '{"type":"CollisionShape2D","name":"SandboxCollision","parent_path":"SandboxBody"}'
run_probe scene.configure_collision_shape '{"node_path":"SandboxBody/SandboxCollision","shape_type":"CircleShape2D","dimensions":{"radius":24.0}}' | tee artifacts/collision-shape-response.log
run_probe scene.get_tree | tee artifacts/collision-scene-inspection.log
grep -q '"SandboxBody"' artifacts/collision-scene-inspection.log
grep -q '"SandboxCollision"' artifacts/collision-scene-inspection.log
grep -q 'CircleShape2D' artifacts/collision-scene-inspection.log
sed -n 's/^BRIDGE_TEST_PASS //p' artifacts/collision-scene-inspection.log | tail -n 1 | jq -e '.result.root.children[] | select(.name == "SandboxNode") | .properties.position.x == 123.0 and .properties.position.y == 45.0' >/dev/null
echo "FRESH_PROJECT_COLLISION_SHAPE_AND_PROPERTY_PASS"
run_probe editor.undo | tee artifacts/undo-bridge-action-response.log
sed -n 's/^BRIDGE_TEST_PASS //p' artifacts/undo-bridge-action-response.log | tail -n 1 | jq -e '.result.direction == "undo" and .result.action_name == "Headless Bridge: Configure collision shape SandboxCollision" and .result.version_after < .result.version_before' >/dev/null
run_probe scene.get_tree | tee artifacts/undo-scene-inspection.log
sed -n 's/^BRIDGE_TEST_PASS //p' artifacts/undo-scene-inspection.log | tail -n 1 | jq -e '.result.root.children[] | select(.name == "SandboxBody") | .children[] | select(.name == "SandboxCollision") | .inspector.properties[] | select(.name == "shape") | .value == null' >/dev/null
echo "FRESH_PROJECT_REAL_UNDO_PASS"
run_probe editor.redo | tee artifacts/redo-bridge-action-response.log
sed -n 's/^BRIDGE_TEST_PASS //p' artifacts/redo-bridge-action-response.log | tail -n 1 | jq -e '.result.direction == "redo" and .result.action_name == "Headless Bridge: Configure collision shape SandboxCollision" and .result.version_after > .result.version_before' >/dev/null
run_probe scene.get_tree | tee artifacts/redo-scene-inspection.log
grep -q 'CircleShape2D' artifacts/redo-scene-inspection.log
echo "FRESH_PROJECT_REAL_REDO_PASS"
run_probe scene.add_node '{"type":"Sprite2D","name":"SandboxSprite"}'
run_probe scene.assign_visual_resource '{"node_path":"SandboxSprite","property":"texture","resource_path":"res://icon.svg"}' | tee artifacts/sprite-texture-assignment.log
grep -q '"resource_type":"CompressedTexture2D"' artifacts/sprite-texture-assignment.log
run_probe scene.get_tree | tee artifacts/sprite-texture-inspection.log
sed -n 's/^BRIDGE_TEST_PASS //p' artifacts/sprite-texture-inspection.log | tail -n 1 | jq -e '.result.root.children[] | select(.name == "SandboxSprite") | .inspector.properties[] | select(.name == "texture") | .value.resource_path == "res://icon.svg"' >/dev/null
echo "FRESH_PROJECT_SPRITE_TEXTURE_ASSIGNMENT_PASS"
# Create and inspect a real SpriteFrames resource with multiple animations.
run_probe scene.create_sprite_frames '{"path":"res://generated/sandbox_walk.tres","animations":[{"name":"walk","speed":6.0,"loop":true,"frames":[{"texture_path":"res://icon.svg","duration":0.5},{"texture_path":"res://icon.svg","duration":0.75}]},{"name":"idle","speed":2.0,"loop":true,"frames":[{"texture_path":"res://icon.svg","duration":1.0}]}]}' | tee artifacts/sprite-frames-create.log
grep -q '"animation_count":2' artifacts/sprite-frames-create.log
grep -q '"frame_count":3' artifacts/sprite-frames-create.log
run_probe project.inspect_resource '{"path":"res://generated/sandbox_walk.tres"}' | tee artifacts/sprite-frames-resource-inspection.log
grep -q '"type":"SpriteFrames"' artifacts/sprite-frames-resource-inspection.log
run_probe scene.add_node '{"type":"AnimatedSprite2D","name":"SandboxAnimatedSprite"}'
run_probe scene.assign_visual_resource '{"node_path":"SandboxAnimatedSprite","property":"sprite_frames","resource_path":"res://generated/sandbox_walk.tres"}' | tee artifacts/sprite-frames-assignment.log
grep -q '"resource_type":"SpriteFrames"' artifacts/sprite-frames-assignment.log
run_probe scene.get_tree | tee artifacts/sprite-frames-scene-inspection.log
sed -n 's/^BRIDGE_TEST_PASS //p' artifacts/sprite-frames-scene-inspection.log | tail -n 1 | jq -e '.result.root.children[] | select(.name == "SandboxAnimatedSprite") | .inspector.properties[] | select(.name == "sprite_frames") | .value.resource_path == "res://generated/sandbox_walk.tres"' >/dev/null
echo "FRESH_PROJECT_SPRITE_FRAMES_CREATE_ASSIGN_PASS"
if run_probe scene.create_sprite_frames '{"path":"res://generated/sandbox_walk.tres","animations":[{"name":"walk","frames":[{"texture_path":"res://icon.svg"}]}]}' > artifacts/duplicate-sprite-frames.log 2>&1; then
  echo "Existing SpriteFrames resource was overwritten" >&2
  exit 1
else
  grep -q 'resource_already_exists' artifacts/duplicate-sprite-frames.log
  echo "FRESH_PROJECT_SPRITE_FRAMES_NO_OVERWRITE_GUARD_PASS"
fi
if run_probe scene.assign_visual_resource '{"node_path":"SandboxAnimatedSprite","property":"sprite_frames","resource_path":"res://icon.svg"}' > artifacts/invalid-sprite-frames-resource.log 2>&1; then
  echo "A texture was accepted as SpriteFrames" >&2
  exit 1
else
  grep -q 'sprite_frames_resource_required' artifacts/invalid-sprite-frames-resource.log
  echo "FRESH_PROJECT_VISUAL_RESOURCE_TYPE_GUARD_PASS"
fi
if run_probe scene.add_node '{"type":"CollisionShape2D","name":"InvalidCollision"}' > artifacts/invalid-collision-parent.log 2>&1; then
  echo "CollisionShape2D invalid parent was accepted" >&2
  exit 1
else
  echo "FRESH_PROJECT_COLLISION_PARENT_GUARD_PASS"
fi
if run_probe scene.add_node '{"type":"OS","name":"InvalidNode"}' > artifacts/invalid-node-type.log 2>&1; then
  echo "Disallowed node type was accepted" >&2
  exit 1
else
  echo "FRESH_PROJECT_NODE_ALLOWLIST_GUARD_PASS"
fi
if run_probe set_node_properties '{"node_path":"SandboxNode","properties":{"unknown_property":1}}' > artifacts/invalid-property.log 2>&1; then
  echo "Unknown node property was accepted" >&2
  exit 1
else
  echo "FRESH_PROJECT_PROPERTY_ALLOWLIST_GUARD_PASS"
fi
if run_probe editor.open_scene '{"path":"res://../outside.tscn"}' > artifacts/invalid-scene-path.log 2>&1; then
  echo "Path traversal scene path was accepted" >&2
  exit 1
else
  echo "FRESH_PROJECT_SCENE_PATH_GUARD_PASS"
fi
run_probe editor.inspect_undo_history | tee artifacts/undo-history-inspection.log
sed -n 's/^BRIDGE_TEST_PASS //p' artifacts/undo-history-inspection.log | tail -n 1 | jq -e '.result.has_undo == true and (.result.current_action_name | startswith("Headless Bridge:"))' >/dev/null
echo "FRESH_PROJECT_EDITOR_UNDO_HISTORY_PASS"
run_probe editor.open_scene '{"path":"res://main.tscn"}' | tee artifacts/open-scene-response.log
grep -q 'BRIDGE_SCENE_OPEN_CONFIRMED res://main.tscn' artifacts/open-scene-response.log
echo "FRESH_PROJECT_OPEN_SCENE_PASS"
run_probe editor.focus_inspector '{"node_path":"SandboxNode","main_screen":"2D"}' | tee artifacts/inspector-focus-response.log
grep -q '"inspector_visible":true' artifacts/inspector-focus-response.log
grep -q '"dock_visible":true' artifacts/inspector-focus-response.log
sed -n 's/^BRIDGE_TEST_PASS //p' artifacts/inspector-focus-response.log | tail -n 1 | jq -e '.result.dock_size.x > 0 and .result.dock_size.y > 0' >/dev/null
sleep 2
run_probe scene.inspect_selection | tee artifacts/inspector-selection-after-focus.log
grep -q '"name":"SandboxNode"' artifacts/inspector-selection-after-focus.log
echo "FRESH_PROJECT_VISIBLE_INSPECTOR_FOCUS_PASS"

# Launch and stop the real game preview through the editor API.
run_probe preview.get_status | tee artifacts/preview-status-before.log
grep -q '"running":false' artifacts/preview-status-before.log
run_probe preview.start '{"scene_path":"res://main.tscn"}' | tee artifacts/preview-start.log
grep -q '"started":true' artifacts/preview-start.log
grep -q '"running":true' artifacts/preview-start.log
run_probe preview.get_status | tee artifacts/preview-status-running.log
grep -q '"running":true' artifacts/preview-status-running.log
run_probe capture.desktop_screenshot | tee artifacts/preview-desktop-capture.log
grep -q '"source":"actual_display"' artifacts/preview-desktop-capture.log
grep -q '"includes_preview_when_visible":true' artifacts/preview-desktop-capture.log
echo "FRESH_PROJECT_PREVIEW_DESKTOP_CAPTURE_PASS"
run_probe preview.stop | tee artifacts/preview-stop.log
grep -q '"stopped":true' artifacts/preview-stop.log
grep -q '"running":false' artifacts/preview-stop.log
run_probe preview.get_status | tee artifacts/preview-status-after.log
grep -q '"running":false' artifacts/preview-status-after.log
echo "FRESH_PROJECT_PREVIEW_LIFECYCLE_PASS"
