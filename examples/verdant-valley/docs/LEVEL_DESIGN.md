# Level design: The Lantern Path

## Player objectives
1. Learn movement and jumping on wide, safe ground.
2. Follow gold fragments and elevated stone platforms to read the route.
3. Cross thorn beds and patrol spaces using timed jumps.
4. Reach the midpoint flag and establish a recovery anchor.
5. Find the pale crystal switch and activate it nearby with E/F.
6. Pass the opened arch and reach the luminous portal.

## Beat structure
| Beat | Space | Purpose | Pressure |
|---|---|---|---|
| Welcome | Wide starting shelf | Teach movement and first pickup | Low |
| First rise | Staggered ledges | Teach vertical route reading | Low–medium |
| Thorn rhythm | Gaps and visible thorn beds | Ask for jump timing | Medium |
| Rest point | Broad shelf and flag | Lower tension and checkpoint | Low |
| Patrol garden | Amber creatures and optional ledges | Read movement and choose a route | Medium |
| Crystal seal | Switch and visible gate | Foreshadow the goal and interaction | Low |
| Final approach | Last platforms and portal | Payoff and clear landmark | Medium |

## Movement and collision feel
The player capsule ends at the same baseline as the character sprite boots. Terrain art is tiled at native 64 px scale and cropped at partial edges, so its visible footprint follows the collision rectangle instead of being stretched. The controller uses separate ground/air acceleration, stronger ground braking, a 0.13 s coyote window, a 0.15 s jump buffer, variable jump height and a capped fall speed. Damage applies directional knockback and brief invulnerability.

## Items and event chain
Eleven animated gold fragments are optional route rewards. A single restorative crystal beside the midpoint checkpoint restores up to two hearts and disappears after use. The checkpoint records the recovery point. The player must activate the pale crystal switch to open the ancient gate; the exit portal rejects contact while the seal is still closed. The portal pulses after the final approach to make the payoff readable.

## Readability
Gold fragments create a breadcrumb trail; pale mint crystals consistently indicate interaction; the golden flag is the checkpoint silhouette; the portal is the final landmark. Red thorn shapes communicate danger, while moss-green platforms are safe.

## Difficulty and recovery
Five hearts; hazards remove one, apply a small directional knockback and grant brief invulnerability. The restorative crystal can recover up to two hearts. Falling below the play space returns the player to the current checkpoint and costs one heart. Zero health restores the player at the checkpoint with full health.

## References and principles applied
- Gillian Smith, Mee Cha and Jim Whitehead, *A Framework for Analysis of 2D Platformer Levels* (2008): platforms, obstacles, movement aids, collectibles and challenge areas should be analyzed as connected components.
- *Level Design Patterns in 2D Games*: Guidance, Foreshadowing, Safe Zone, Layering, Branching and Pace Breaking. This level uses breadcrumb pickups, a visible switch/gate relationship, a checkpoint rest beat and optional elevated rewards.
- Platformer flow guidance: introduce mechanics safely, increase pressure in measured steps, and provide a breather before the final objective.

These references inform design principles; no existing level layout or artwork is copied.
