# Remote Godot execution

## Provider priority

The Relay dispatches fixed, allowlisted Godot tasks in this order:

1. **CircleCI — primary executor.** Triggered directly through the CircleCI API.
2. **GitHub Actions — fallback executor.** Used when CircleCI is not configured or its dispatch API is unavailable.

Both providers run the same version-pinned Godot binary and the same repository script. They do not run arbitrary shell commands supplied by MCP.

## Fixed task profiles

- `engine_smoke`: verifies the pinned Godot 4.7.2 Linux binary, imports the isolated bridge sandbox, and fails on script/parse errors.
- `scene_audit_3d`: performs the same import check and runs a structured scene audit. The JSON report records scene hierarchy, world transforms and basis vectors, mesh bounds and surfaces, materials, cameras, lights/shadows, collision shapes/layers, rigid and character body settings, skeleton bone names, and AnimationPlayer tracks with sampled key values. The same profile launches a separate Mesa software-rendered Godot process under Xvfb and saves eight camera views per scene containing meshes, with camera coordinates and image dimensions in a manifest.

The current audit target is deliberately fixed to `examples/bridge-sandbox`, which includes a synthetic 3D fixture (mesh, material, camera, directional light, static and character physics bodies with box/capsule collision shapes, and a keyed AnimationPlayer track) so the audit proves it can read non-zero spatial, physics, and animation data. It is an infrastructure validation target, not yet the user's actual game workspace. The next integration step is to transfer a versioned project snapshot into an isolated runner workspace and run these profiles against that snapshot.

## Required Render environment variables

Set these as encrypted environment variables on the existing Relay service only after creating/configuring the CircleCI project:

- `CIRCLECI_TOKEN`: CircleCI personal/API token with access only to this project.
- `CIRCLECI_PROJECT_SLUG`: e.g. `gh/organization/repository`.

Fallback variables:

- `GITHUB_ACTIONS_TOKEN`: fine-grained GitHub token restricted to this repository, with Actions read/write and Contents read permissions.
- `GITHUB_ACTIONS_REPOSITORY`: optional; defaults to `decuvilan-lgtm/Godot-web-ia-integrada`.

Never commit tokens or put them in pipeline parameters. No automatic credit refill or paid upgrade should be enabled. CircleCI Free currently has a monthly credit allowance; when it is exhausted, tasks stop until the next reset. GitHub Actions remains the secondary provider and is also subject to its plan limits.

## CircleCI setup

1. Sign in to CircleCI and connect the GitHub repository `decuvilan-lgtm/Godot-web-ia-integrada`.
2. Confirm the repository uses `.circleci/config.yml` from the `main` branch.
3. Add the CircleCI project slug and API token to Render's Relay environment.
4. Keep the account on the Free plan and do not add a paid credit package.
5. Deploy the Relay after the secrets are configured.

The Relay exposes authenticated MCP tools `godot_execution_providers`, `godot_start_task`, and `godot_task_status`. The provider status tool reveals only whether the required variables are configured and their non-secret project/repository identifiers; it never returns token values. Status responses include available job artifacts and their metadata. A paired `agent_controller` is required. The status tool only reads executions from the configured provider project/repository.

## 3D evidence and precision

A single screenshot is not sufficient to assess a 3D project. The scene audit preserves structural evidence that can be checked independently of appearance: node hierarchy, world transforms, basis vectors, camera projection/FOV/near/far planes, mesh AABBs and surfaces, material parameters, light energy and shadow state, skeletons, and animation names.

This is not a guarantee of "total precision". Visual fidelity still requires real rendered frames from multiple viewpoints, animation frame sequences, collision/physics checks, and comparison against the intended reference. The current CI audit and eight-view capture are deterministic infrastructure evidence for the fixed sandbox. They do not yet mean the user's real game project has been transferred or inspected; versioned project snapshot transfer remains a separate integration step.
