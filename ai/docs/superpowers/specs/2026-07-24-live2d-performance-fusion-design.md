# Live2D Performance Fusion Design

## Goal

Turn the existing Live2D runtime into a character-performance platform by
adopting the strongest reusable ideas from Soullink Emotion SDK, the official
Cubism samples, Open-LLM-VTuber, and AITuberKit without introducing a second
controller stack.

The invariant control chain remains:

CharacterIntent -> emotional state -> CharacterBehaviorResolver ->
CharacterPerformancePolicy -> MotionArbiter / procedural performance ->
ParameterMixer -> AvatarParameterResolver -> Live2DModelAdapter -> Cubism.

## Architecture Constitution

1. The LLM emits semantic emotion, behavior, attention, and energy only.
2. ParameterMixer is the only real-time parameter arbitration point.
3. Live2DModelAdapter is the only Cubism write owner.
4. Model-specific IDs and ranges exist only in avatar profiles and adapters.
5. Every expression and motion has enter, hold, interrupt, release, and recovery
   semantics.
6. Imported projects contribute algorithms, data, and calibration practices;
   they do not retain runtime ownership.

## Fusion Sources

### Soullink Emotion SDK

Adopt:

- continuous VAD emotion state and emotion inertia;
- model-independent FACS-like performance channels;
- deterministic seeded motion variation;
- motion styles (`natural`, `lively`, `calm`, `shy`);
- layered blink, gaze, breath, micro-motion, body sway, and idle bias;
- capability-aware spontaneous idle actions;
- personality- and VAD-weighted action selection;
- recent-action and direction repetition avoidance;
- profile generation and calibration concepts;
- native expression/motion suppression rules;
- graceful degradation when a channel is unsupported.

Do not adopt its runtime, mixer, PIXI renderer, session, TTS, or direct Cubism
parameter output.

### Official Cubism Samples

Adopt native `.motion3.json` and `.exp3.json` lifecycle semantics, fade timing,
priority, completion, physics ordering, and model-owned animation assets.

### Open-LLM-VTuber

Adopt interaction triggers: speech interruption, touch/drag reaction, proactive
speech, desktop-pet events, and separation of internal thought from visible
performance.

### AITuberKit

Adopt event policy concepts: time-aware greetings, presence detection,
inactivity behavior, scene modes, and external event reactions. All events
enter through CharacterIntent.

## Performance Layers

| Layer | Responsibility | Priority |
| --- | --- | ---: |
| Pose safety | Exclusive parts and safe model state | 100 |
| Expression | FACS-like face and temporary effects | 75 |
| Lip sync | Audio-driven mouth opening | 60 |
| Semantic motion | Intentional gestures and native motions | 50 |
| Speech accents | Onset, emphasis, cadence, sentence release | 45 |
| Blink | Eye closure only | 40 |
| Attention | Gaze and head focus | 30 |
| Breath | Non-periodic breathing | 20 |
| Idle drift | Micro-motion and weight shift | 10 |

Arbitration is per resolved parameter. A semantic body motion does not suppress
blink, lip sync, or unrelated expression channels.

## Motion Style

Every character has a resolved performance style with:

- spontaneity;
- gesture frequency;
- gaze stability;
- blink rate;
- breath rate and variance;
- micro-motion gain;
- idle-action gain;
- body-motion gain;
- speech-accent gain;
- recent-action avoidance window;
- optional deterministic seed for tests and recordings.

Profiles may inherit a named preset and override individual values.

## Procedural Idle

Idle consists of concurrent continuous layers:

- breathing with slow amplitude and tempo variation;
- target-based head and face micro-motion;
- correlated head/body weight shifts;
- dwell-based gaze targets;
- natural blinking;
- temporary bias from emotional state.

Low-frequency actions are scheduled separately:

- small nod;
- head tilt;
- side look;
- weight shift;
- gentle lean;
- sigh sink;
- slow blink.

Each action uses normalized logical keyframes, capability gates, an entry and
release curve, personality/VAD weights, random amplitude within safe bounds,
and recent-history suppression. No idle action introduces a special expression.

## Emotional State

Discrete emotion remains the external vocabulary. Internally it resolves to a
continuous VAD target:

- valence: unpleasant to pleasant;
- arousal: calm to activated;
- dominance: withdrawn to assertive.

The state approaches targets, retains short-lived stimulus effects, and decays
toward the character baseline. VAD modifies action probability, direction,
amplitude, gaze, posture, and recovery without writing model parameters.

## Native Animation

Profiles catalog native expressions and motions. PerformancePolicy may request
a semantic animation. MotionArbiter chooses:

1. an explicitly mapped native motion when present;
2. a logical keyframe preset as fallback.

Native expressions temporarily suppress only the FACS-like channels they own.
Native playback never bypasses arbitration, and logical blink/lip-sync layers
remain active when they do not conflict.

## Profile And Calibration

Avatar profiles grow to describe:

- motion style and personality;
- logical binding ranges, neutral values, and smoothing;
- detected capabilities;
- native expression and motion catalogs;
- semantic animation mappings;
- private effect mappings;
- safe idle ranges.

A later profile tool scans model3, cdi3, exp3, motion3, pose3, and physics3
metadata. Automatic guesses must validate against actual model IDs. Calibration
supports parameter sweep, direction/range confirmation, coverage reporting,
live preview, and profile export.

## Diagnostics

The existing Character Performance diagnostics gain:

- resolved motion style and seed;
- current VAD and target;
- continuous idle layer values;
- active spontaneous action, direction, progress, next action, and recent
  history;
- native animation selection and fallback reason;
- unsupported capability degradation;
- final owner for contested parameters.

## Delivery Phases

1. Motion-style schema and deterministic procedural idle.
2. Capability-aware spontaneous idle action scheduler.
3. Speech accents, cadence, and recovery.
4. Continuous VAD state and personality-weighted performance.
5. FACS-like logical channels and profile range semantics.
6. Native motion/expression catalog and arbitration.
7. Profile generation and calibration workflow.
8. Touch, proactive, time, presence, and scene event policies.

Each phase must leave the application runnable and retain the architecture
constitution.

## Licensing

Substantial code adapted from MIT-licensed projects must retain the applicable
copyright and license notice. Live2D model assets, Cubism Core, and sample data
remain outside the application-code license and require separate review.
