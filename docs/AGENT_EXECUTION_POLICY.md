# Agent execution policy: observe, operate, verify

This policy governs every user-issued task that uses the persistent Godot browser session (A) and the command bridge (B).

## Roles

- **ChatGPT is the operator and decision-maker.** It interprets the user's request, inspects observations, chooses the next action, sends the requested command, evaluates the returned result, and decides whether another action is needed.
- **A is the persistent browser host.** A owns the real Chromium/Godot editor session, executes received browser/editor commands, and returns observable state, screenshots, logs, and command results.
- **B is a transport bridge only.** B forwards the operator's explicit request to A and returns A's response to the operator. B must not interpret the task, choose actions, plan steps, perform semantic inspection on its own, run benchmarks autonomously, or decide when work is complete.

## Required procedure for each user order

1. Start or reuse the authorized A session for the requested task. Do not treat a workflow's `queued`, `in_progress`, or successful startup status as task completion.
2. Observe A for **10 full minutes** before issuing the first task-specific B request. During that period, inspect the available state/evidence at reasonable intervals and record meaningful changes, errors, readiness, and whether the same browser session remains alive.
3. After the observation period, ChatGPT determines the next action from the user's request and the evidence. It sends that explicit action through one B request. **Each B invocation carries exactly one command**; do not batch future decisions or follow-up actions into the same request. B transports the command without changing its meaning.
4. Wait for the actual A-side command result. Acknowledgement that a command was enqueued or claimed is not execution evidence.
5. After **each B request has been executed**, observe A for another **10 full minutes** before deciding on the next B request. Repeat this cycle for every additional B request.
6. ChatGPT verifies the requested outcome using returned state, screenshots, editor/project evidence, and any relevant tests. If verification fails, diagnose and issue another explicit B request, followed by another 10-minute observation period.
7. Report completion only when the requested outcome is actually present and independently verified. If a workflow fails, times out, loses its session, or cannot provide evidence, report the exact blocker and classify the task as incomplete.

## Timing and truthful reporting

- The required observation window is 10 minutes, not 1 minute.
- Do not claim that time elapsed unless the operator actually remained active and performed observations across that interval.
- Do not fabricate observations, screenshots, test results, command timings, or successful outcomes.
- If the execution environment cannot keep the operator active for the required observation window, stop and report that limitation rather than silently shortening the wait or claiming completion.
- Distinguish clearly between workflow start, command enqueue, command execution, post-action observation, and verified task completion.

## Safety and repository boundaries

- Work only on the explicitly authorized development/test branch for this project. Never modify the production/default branch as part of this workflow.
- Preserve the existing persistent A browser session; do not substitute a separate browser for B's commands.
- Keep credentials and device tokens in approved secret storage. Never print raw tokens in logs or user-facing reports.
- B may handle transport concerns only: authentication, request validation, queueing, delivery, polling, retries, leases, and returning result/artifact references. These mechanisms must not become task-level reasoning.
