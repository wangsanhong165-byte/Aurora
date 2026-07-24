# Live2D Performance Fusion Implementation Plan

> **For AI workers:** Required sub-skill: use executing-plans to implement this
> plan task by task. Track every task with checkboxes.

**Goal:** Add emotion-aware, capability-safe character performance to the
existing single-writer Live2D runtime without importing a second controller
stack.

**Architecture:** Keep CharacterIntent, CharacterBehaviorResolver,
CharacterPerformancePolicy, MotionArbiter, ParameterMixer,
AvatarParameterResolver, and Live2DModelAdapter as the only production control
chain. Add focused, model-independent performance units that emit normalized
logical contributions into the existing chain.

**Tech stack:** TypeScript 5.5, React 18, Cubism Web Framework, JSON avatar
profiles and motion presets, Python pytest architecture/config guards.

---

## File Responsibilities

- Create `frontend/src/character/performance/MotionStyle.ts`: style schema,
  presets, clamping, and deterministic seed derivation.
- Create `frontend/src/character/performance/SeededRandom.ts`: reproducible
  random source for motion scheduling only.
- Create `frontend/src/character/performance/BodySwayController.ts`: correlated
  target-based head/body drift.
- Create `frontend/src/character/performance/IdleActionScheduler.ts`:
  capability-aware spontaneous action selection and normalized keyframes.
- Modify `frontend/src/character/IdleBehaviorController.ts`: compose continuous
  performance layers and scheduled actions.
- Modify `frontend/src/character/AvatarCapabilityProfile.ts`: optional motion
  style, personality, capability, range, and native animation declarations.
- Modify `frontend/src/character/controllers.ts`: configure the performance
  subsystem and submit its outputs through the existing resolver and mixer.
- Modify `config/avatar_profiles/*.json`: character-specific style and safe
  capability declarations.
- Modify `tests/test_live2d_control_boundaries.py`: architecture, schema,
  deterministic-motion, and config regression guards.
- Later modify `frontend/src/character/MotionArbiter.ts` and
  `frontend/src/character/live2d/ModelManager.ts`: native animation arbitration.
- Later create `frontend/src/character/performance/VADState.ts`: continuous
  emotional state.
- Later create `frontend/src/character/performance/FACSState.ts`: normalized
  face and posture vocabulary.

### Task 1: Motion Style And Deterministic Randomness

- [x] Add failing regression guards for named styles, safe ranges, seeded
  variation, profile overrides, and the absence of Cubism IDs.
- [x] Run the focused guards and confirm failure because the performance style
  module does not exist.
- [x] Implement `SeededRandom.ts` and `MotionStyle.ts` with `natural`, `lively`,
  `calm`, and `shy` presets.
- [x] Extend `AvatarCapabilityProfile` with optional `motionStyle`,
  `personality`, and `capabilities`.
- [x] Add a conservative style to every current avatar profile.
- [x] Run focused pytest guards and frontend typecheck.

### Task 2: Target-Based Body Sway

- [x] Add failing guards requiring target/hold timing, quintic easing,
  correlated head/body compensation, focus recentering, and profile-safe
  logical ranges.
- [x] Run the focused guards and confirm failure.
- [x] Implement `BodySwayController` with normalized logical outputs only.
- [x] Replace fixed sine-only head sway in `IdleBehaviorController` with the
  target-based controller while preserving transition energy.
- [x] Submit head and body outputs through `AvatarParameterResolver`.
- [x] Run focused pytest guards and frontend typecheck.

### Task 3: Capability-Aware Idle Actions

- [x] Add failing guards for seven required idle actions, recent-history
  avoidance, direction alternation, capability gates, and neutral recovery.
- [x] Run the focused guards and confirm failure.
- [x] Implement `IdleActionScheduler` with weighted selection based on
  personality, focus, and a neutral VAD input.
- [x] Convert scheduled action samples into logical contributions rather than
  synthetic `CharacterIntent` events.
- [x] Expose scheduler diagnostics through `IdleBehaviorSnapshot`.
- [x] Run focused pytest guards and frontend typecheck.

### Task 4: Speech Accents And Recovery

- [x] Add failing guards for speech onset, bounded peak accents, sentence
  release, and coexistence with lip sync and blink.
- [x] Implement a focused `SpeechPerformanceController`.
- [x] Replace fixed speech sine motion with style-controlled cadence and accent
  envelopes.
- [x] Start recovery from browser audio completion and preserve unrelated
  layers.
- [x] Run focused guards, typecheck, and production build.

### Task 5: Continuous VAD And Emotion Inertia

- [x] Add failing tests for preset resolution, bounded target approach,
  stimulus deltas, decay to personality baseline, and deterministic updates.
- [x] Implement `VADState.ts` without model or renderer dependencies.
- [x] Map existing semantic emotions to VAD targets in
  `CharacterBehaviorResolver`.
- [x] Feed VAD into idle-action weights, gaze tendency, posture, and amplitude.
- [x] Expose current and target VAD diagnostics.
- [x] Run focused guards, typecheck, and production build.

### Task 6: FACS-Like Performance Vocabulary

- [x] Add failing guards for model-independent brow, eye, gaze, mouth, head, and
  body channels.
- [x] Implement `FACSState.ts` and composition helpers.
- [x] Extend profile bindings with neutral values, normalized ranges, modes,
  and smoothing without breaking current string bindings.
- [x] Route expressions, idle, and VAD posture through the shared vocabulary.
- [x] Run focused guards, typecheck, and production build.

### Task 7: Native Motion And Expression Arbitration

- [x] Add failing guards for native catalogs, semantic mappings, fallback,
  fade/completion lifecycle, and parameter-level suppression.
- [x] Parse native motion/expression metadata without changing renderer
  ownership.
- [x] Add native requests to MotionArbiter and retain logical preset fallback.
- [x] Suppress only conflicting procedural channels while native animation is
  active.
- [x] Run focused guards, typecheck, build, and model catalog validation.

### Task 8: Profile Generation And Calibration

- [x] Add failing tests for deterministic model3/cdi3/exp3/motion3 metadata
  scanning and actual-ID validation.
- [x] Implement a Node-side profile inspection command.
- [x] Add coverage, direction, neutral, and safe-range diagnostics.
- [x] Add read-only preview diagnostics to the existing DebugPanel before allowing
  profile export.
- [x] Run fixture tests, typecheck, and build.

### Task 9: Interaction And Proactive Event Policies

- [x] Add failing tests that touch, drag, inactivity, time, presence, and scene
  events become CharacterIntent rather than direct Live2D writes.
- [x] Add event-policy adapters inspired by Open-LLM-VTuber and AITuberKit.
- [x] Add cooldown, interruption, and priority rules.
- [x] Verify desktop-pet and conversation flows use the same performance chain.
- [x] Run focused tests, full pytest, typecheck, and build.

### Task 10: End-To-End Quality Gate

- [ ] Verify architecture guards and all runtime protocol tests.
- [ ] Run frontend typecheck and production build.
- [ ] Record idle, listening, thinking, speaking, reacting, interruption, and
  recovery with the Mao profile.
- [ ] Compare against a fixed baseline for freezes, repetition, residue,
  parameter contention, and unsupported-channel degradation.
- [ ] Record model-art limitations separately from runtime defects.
