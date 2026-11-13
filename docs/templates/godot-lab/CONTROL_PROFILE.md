# Control Profile

Record only controls observed in this exact project. Do not copy mappings from another game.

| Action | UI/key mapping | Behavior (tap/hold/drag) | State | Evidence | Last verified commit |
|---|---|---|---|---|---|
| Example action | Pending observation | Pending observation | Pending | — | — |

Allowed states: **Verified**, **Pending**, **Obsolete**. Mark a control Verified only after repeating the interaction and observing the same result.

The machine-readable `control-profile.json` must remain `pending` until the mapping has been checked. When verified, its `verification.commit_sha` must be the full SHA of the exact project revision tested. A different project revision makes the previous verification obsolete.
