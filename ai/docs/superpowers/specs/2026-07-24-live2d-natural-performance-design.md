# Live2D Natural Performance Design

## Goal

Make the existing Live2D runtime feel continuous and intentional across idle,
listening, thinking, speaking, interaction, and recovery. Preserve the current
single control chain:

CharacterIntent -> BehaviorResolver -> PerformancePolicy -> MotionArbiter /
ParameterResolver -> ParameterMixer -> Live2DAdapter -> Cubism.

No second controller stack, direct Cubism writes, or model-specific parameters
may enter LLM output, policies, or logical motion presets.

## Current Root Causes

1. MotionArbiter selects the latest keyframe as a step value. It does not
   interpolate between keyframes, so motion starts, reversals, and recovery
   visibly snap.
2. Runtime activity changes and audio playback have separate clocks. Speaking
   contributions can appear or disappear on a single frame, causing a pause at
   the boundary.
3. Expressions have no complete lifecycle. A special expression can remain
   active after speaking because recovery is timer-dependent and is skipped
   when another motion is active.
4. Cubism expression Blend metadata is discarded. Add and Multiply parameters
   are treated as the same absolute value, which distorts eye-open values and
   can leave eye effects visually stacked.
5. Idle is a random list of complete semantic intents every 9-18 seconds.
   Between those events it only has blink/breath/gaze, so it lacks continuous
   weight shift and attention behavior; random emotion changes also compete
   with AI presentation.
6. PoseController forces the first part of each pose group every frame instead
   of preserving an explicit selected member. This can fight component or
   motion state.
7. Motion sequences are mostly empty or shallow. `greet` schedules `wave`, but
   ordinary speaking, thinking exit, reaction, and return-to-idle composition
   are not defined.

## Runtime Layers

Each frame resolves these layers through ParameterMixer:

| Layer | Responsibility | Typical priority |
|---|---|---:|
| Pose safety | Mutually exclusive part visibility | 100 |
| Expression | Face and temporary visual effects | 75 |
| Lip sync | Audio-driven mouth opening | 60 |
| Motion | Intentional gesture keyframes | 50 |
| Speech rhythm | Continuous head/body movement while speaking | 45 |
| Blink | Eye closure only | 40 |
| Attention | Gaze and head focus | 30 |
| Breath | Breathing and small body movement | 20 |
| Idle drift | Slow posture and weight shift | 10 |

Higher layers do not disable lower layers globally. Arbitration occurs per
resolved parameter, so lip sync does not freeze the body and a body motion does
not disable blinking.

## State Timeline

### Idle

- Continuous low-amplitude breath and body weight shift.
- Slow gaze target changes with bounded dwell time.
- Small posture variations every 8-18 seconds.
- Rare neutral micro-gesture every 20-45 seconds.
- No happy/surprised/special-effect expression is introduced by idle.

### Listening

- Ease gaze toward the user over 250ms.
- Reduce body drift rather than stopping it.
- Close the current AI gesture naturally; do not hard-stop its parameters.

### Thinking

- Ease gaze away and apply a mild head tilt over 350ms.
- Keep blink and breath active at reduced energy.
- Never reuse a special eye-effect expression as the thinking baseline.

### Speaking

- Crossfade into speech rhythm over 220ms.
- Apply the semantic response expression and hold it for the utterance.
- Run lip sync independently from head/body rhythm.
- Optional semantic gesture plays through MotionArbiter without stopping
  speech rhythm on unrelated parameters.

### Recovery

- Audio playback completion starts a 350-600ms recovery.
- Mouth closes with release smoothing.
- Temporary expression parameters, including eye effects, return to neutral.
- Motion parameters ease to their baseline rather than disappearing.
- Idle resumes only after recovery has begun, preventing a one-frame pause.

## Expression Semantics

ExpressionPreset parameters preserve Cubism blend metadata:

- `Add`: contribution is `value * intensity` relative to the neutral base.
- `Multiply`: contribution is interpolated from 1 to `value` by intensity.
- `Overwrite`: contribution is interpolated from the current/base value.

The active expression remains a per-frame Mixer contribution. Temporary visual
effect parameters are explicitly reset when the expression exits. Recovery is
state-driven and retryable, not a one-shot timer guarded by motion state.

Blink may override eye-open values only while an actual blink is closing the
eyes. It must not blend continuously with expression eye-open values.

## Motion Interpolation

Motion presets remain logical-parameter JSON. For each logical parameter,
MotionArbiter finds the surrounding keyframes and interpolates with a smoothstep
curve. Before the first keyframe, it holds the first value; after the final
keyframe, it eases toward zero during the preset recovery window.

Preset additions:

- `speak`: subtle nod/body emphasis with a neutral recovery.
- `greet`: focus user -> happy expression -> wave -> settle.
- `think`: gaze away -> head tilt -> hold -> partial recovery.
- `agree`: short nod -> settle.
- `disagree`: small lateral tilt -> settle.
- `react`: short surprised recoil -> settle.
- `return_idle`: explicit neutral posture recovery.

Sequences reuse MotionArbiter steps and PerformancePolicy. They do not create a
new playback engine.

## Idle Policy

IdleBehaviorController becomes a scheduler for low-frequency semantic events
and continuous procedural targets. It emits no special expression by default.
It tracks dwell time, next gaze target, posture phase, and micro-gesture
cooldown. Idle is allowed only when activity is idle and no interaction or AI
motion owns the affected channel.

Randomness is bounded and seeded only at event boundaries; frame-level output
is deterministic interpolation. This avoids jitter.

## Pose Exclusivity

PoseController stores the active part ID for every pose group. Its per-frame
update enforces exactly one visible member and its linked parts. Model initial
pose chooses the first member, but component or approved motion state can select
another member without being overwritten on the next frame.

Pose writes remain adapter-owned. Pose state never controls facial parameters.

## Diagnostics

Character Performance diagnostics expose:

- activity and transition progress;
- active expression and effect parameters;
- active motion, elapsed time, and interpolation progress;
- speech rhythm and lip-sync values;
- idle phase and current gaze target;
- active pose member per group;
- resolved Mixer owner for contested parameters.

Warnings are emitted when a logical binding, motion preset, expression preset,
or pose part is missing.

## Verification

Automated tests cover:

1. motion midpoint interpolation and end recovery;
2. expression Add/Multiply intensity semantics;
3. special eye effects reset after speaking;
4. speaking keeps body motion and blink active alongside lip sync;
5. idle never emits special expressions or overrides speaking;
6. state transitions do not hard-stop active parameter values;
7. pose groups expose exactly one member after selection;
8. every sequence references existing logical presets and supported semantic
   expressions;
9. all logical motion values pass through AvatarParameterResolver;
10. typecheck, production build, and focused runtime protocol tests.

Manual verification uses desktop Electron with the active Mao profile. Capture
short idle, listening, thinking, speaking, and recovery samples and confirm no
one-frame freeze, eye-effect residue, duplicated pose parts, or abrupt return to
neutral.

## Scope Boundaries

- Do not integrate native `.motion3.json` playback in this pass.
- Do not change ParameterMixer's public architecture or adapter ownership.
- Do not make LLM output animation files, parameters, or keyframes.
- Do not duplicate per-model logical motion libraries.
- Do not redesign the React frontend.
