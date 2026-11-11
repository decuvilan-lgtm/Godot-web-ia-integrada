# Remote Godot execution

## Provider priority

The repository supports fixed, allowlisted Godot validation tasks through its CI providers:

1. **GitHub Actions — standard path.** Manually dispatched from the repository Actions page.
2. **CircleCI — optional path.** Triggered manually from the connected CircleCI project.

Both providers run the same version-pinned Godot binary and the same repository script. They do not accept arbitrary shell commands or paths.

## Fixed task profiles

- `engine_smoke`: verifies the pinned Godot 4.7.2 Linux binary, imports the isolated bridge sandbox, and fails on script/parse errors.
- `scene_audit_3d`: performs the same import check and runs a structured scene audit. The JSON report records scene hierarchy, world transforms and basis vectors, mesh bounds and surfaces, materials, cameras, lights/shadows, collision shapes/layers, rigid and character body settings, skeleton bone names, and AnimationPlayer tracks with sampled key values. The same profile launches a separate Mesa software-rendered Godot process under Xvfb and saves eight camera views per scene containing meshes, with camera coordinates and image dimensions in a manifest.

The current audit target is deliberately fixed to `examples/bridge-sandbox`, which includes a synthetic 3D fixture (mesh, material, camera, directional light, static and character physics bodies with box/capsule collision shapes, and a keyed AnimationPlayer track) so the audit proves it can read non-zero spatial, physics, and animation data. It is an infrastructure validation target, not yet the user's actual game workspace. The next integration step is to transfer a versioned project snapshot into an isolated runner workspace and run these profiles against that snapshot.

## Manual dispatch

For GitHub Actions, open the repository's `Actions` tab, choose `Remote Godot task`, select one fixed profile, provide a correlation ID, and run the workflow. The workflow checks out `main`, executes the pinned Godot task script, and uploads the evidence artifact. No Relay token or custom controller service is involved.

## CircleCI setup

1. Sign in to CircleCI and connect the GitHub repository `decuvilan-lgtm/Godot-web-ia-integrada`.
2. Confirm the repository uses `.circleci/config.yml` from the `main` branch.
3. Add the CircleCI project slug and API token to Render's Relay environment.
4. Keep the account on the Free plan and do not add a paid credit package.
5. Run the CircleCI pipeline manually when needed; the Relay does not dispatch it.

The Relay exposes authenticated MCP tools `godot_execution_providers`, `godot_start_task`, and `godot_task_status`. The provider status tool reveals only whether the required variables are configured and their non-secret project/repository identifiers; it never returns token values. Status responses include available job artifacts and their metadata. A paired `agent_controller` is required. The status tool only reads executions from the configured provider project/repository.

## 3D evidence and precision

A single screenshot is not sufficient to assess a 3D project. The scene audit preserves structural evidence that can be checked independently of appearance: node hierarchy, world transforms, basis vectors, camera projection/FOV/near/far planes, mesh AABBs and surfaces, material parameters, light energy and shadow state, skeletons, and animation names.

This is not a guarantee of "total precision". Visual fidelity still requires real rendered frames from multiple viewpoints, animation frame sequences, collision/physics checks, and comparison against the intended reference. The current CI audit and eight-view capture are deterministic infrastructure evidence for the fixed sandbox. They do not yet mean the user's real game project has been transferred or inspected; versioned project snapshot transfer remains a separate integration step.
