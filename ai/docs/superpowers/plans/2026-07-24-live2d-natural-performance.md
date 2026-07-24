# Live2D Natural Performance Implementation Plan

> **For AI workers:** Required sub-skill: use executing-plans to implement this plan task by task. Track every task with checkboxes.

**Goal:** Make idle, listening, thinking, speaking, gesture, expression, pose, and recovery transitions continuous and model-safe through the existing Live2D control chain.

**Architecture:** Preserve CharacterIntent -> BehaviorResolver -> PerformancePolicy -> MotionArbiter / AvatarParameterResolver -> ParameterMixer -> Live2DAdapter. Improve semantics and lifecycle inside existing owners; add no second control path or SDK writer.

**Tech stack:** TypeScript, React, Cubism Web Framework, Vite, Python pytest boundary tests.

---

## Files

- Modify `frontend/src/character/live2d/expression.ts`: preserve Cubism expression blend metadata.
- Modify `frontend/src/character/live2d/ModelManager.ts`: parse Add, Multiply, and Overwrite modes.
- Modify `frontend/src/character/controllers.ts`: persistent expression lifecycle, state recovery, speech/idle layer composition, diagnostics.
- Modify `frontend/src/character/ExpressionController.ts`: expression effect lifecycle and neutral recovery.
- Modify `frontend/src/character/MotionArbiter.ts`: keyframe interpolation and recovery.
- Modify `frontend/src/character/IdleBehaviorController.ts`: continuous bounded idle targets and low-frequency micro-events.
- Modify `frontend/src/character/live2d/PoseController.ts`: explicit exclusive pose member state.
- Modify `frontend/src/character/Live2DModelAdapter.ts`: keep pose writes behind adapter ownership.
- Modify `frontend/src/character/AvatarCapabilityProfile.ts`: optional timing and idle tuning schema.
- Modify `config/avatar_profiles/*.json`: model-safe tuning and missing logical bindings.
- Modify/create `config/motions/*.json`: complete logical motion and sequence presets.
- Modify `frontend/src/ui/DebugPanel.tsx`: expose transition, expression effect, motion, idle, pose, and contested parameter state.
- Modify `tests/test_live2d_control_boundaries.py`: architecture, preset, sequence, and lifecycle regression guards.
- Create `frontend/src/character/__tests__/performance-runtime.test.ts` only if the existing frontend test runner is configured; otherwise use deterministic exported helpers plus Python source/config boundary tests.

### Task 1: Expression Blend And Effect Lifecycle

- [ ] Add failing tests that require model expression presets to retain `Add`, `Multiply`, and `Overwrite` modes and require special effect parameters to return to neutral.
- [ ] Run focused tests and confirm failure.
- [ ] Extend `ExpressionPreset.params` with `blend?: 'add' | 'multiply' | 'overwrite'`.
- [ ] Parse `Blend` in `ModelManager.parseExp3Json`.
- [ ] Make ParameterController calculate intensity by blend type: Add from 0, Multiply from 1, Overwrite from current value.
- [ ] Replace one-shot neutral timer with a retryable recovery state triggered by audio end/activity exit.
- [ ] Run focused tests and typecheck.

### Task 2: Motion Interpolation And Recovery

- [ ] Add failing tests for midpoint interpolation, smoothstep easing, final recovery, and no Cubism IDs in presets.
- [ ] Run focused tests and confirm failure.
- [ ] Add pure keyframe sampling helpers to MotionArbiter.
- [ ] Interpolate between surrounding frames instead of selecting the latest frame.
- [ ] Add a bounded recovery interval that eases the final value to zero before the motion becomes idle.
- [ ] Ensure sequence steps execute once and queued motions begin without a blank frame.
- [ ] Run focused tests and typecheck.

### Task 3: Continuous Idle And State Transitions

- [ ] Add failing guards that idle never emits happy/surprised/special expressions and speaking never disables blink/body rhythm.
- [ ] Run focused tests and confirm failure.
- [ ] Replace idle's random complete intents with continuous posture/gaze targets plus rare neutral micro-gestures.
- [ ] Add transition progress and activity-enter timestamps to CharacterController.
- [ ] Crossfade speech rhythm, breath, gaze, and idle energy instead of toggling them per frame.
- [ ] Ensure listening and thinking do not hard-stop active parameter values.
- [ ] Ensure audio end initiates recovery before full idle energy resumes.
- [ ] Run focused tests and typecheck.

### Task 4: Pose Exclusivity And Duplicate Prevention

- [ ] Add failing guards for exactly one active member per pose group and explicit member selection.
- [ ] Run focused tests and confirm failure.
- [ ] Store active part ID per PoseController group.
- [ ] Enforce selected member opacity and linked parts each frame.
- [ ] Keep initial selection deterministic and ignore unknown part selections with diagnostics.
- [ ] Confirm CharacterView owns exactly one animation loop across model switches.
- [ ] Run focused tests and typecheck.

### Task 5: Fill Motion And Sequence Library

- [ ] Add failing config validation for required presets: `speak`, `greet`, `wave`, `nod`, `tilt`, `thinking`, `react`, `return_idle`.
- [ ] Run focused tests and confirm failure.
- [ ] Add logical keyframes with explicit zero recovery frames to every primitive preset.
- [ ] Fill sequence steps for greet, think, react, and speaking emphasis without creating a new player.
- [ ] Add missing body/arm bindings only where the model profile declares a real parameter; preserve head/body fallback for profiles without arm capability.
- [ ] Validate every step reference and logical binding.
- [ ] Run focused tests and typecheck.

### Task 6: Diagnostics

- [ ] Add failing source guards for transition progress, expression effects, motion progress, idle target, pose selection, and Mixer contention diagnostics.
- [ ] Expose structured debug snapshots from CharacterController, MotionArbiter, IdleBehaviorController, PoseController, and ParameterMixer.
- [ ] Render the snapshots in the existing DebugPanel Character Performance area.
- [ ] Keep diagnostics read-only and out of the control path.
- [ ] Run typecheck and production build.

### Task 7: End-To-End Verification

- [ ] Run `python -m pytest -q tests/test_live2d_control_boundaries.py tests/test_live2d_v2_protocol.py tests/test_avatar_controller.py tests/test_character_intent.py` with project root on `PYTHONPATH`.
- [ ] Run `npm.cmd run typecheck` in `frontend`.
- [ ] Run `npm.cmd run build` in `frontend`.
- [ ] Launch through `start_electron.bat` or the equivalent production bridge/electron path.
- [ ] Inspect logs for one animation loop, resolved expressions, interpolated motions, lip-sync volume, recovery completion, and pose selection.
- [ ] Manually exercise idle -> listening -> thinking -> speaking -> recovery and rapid repeated model interactions.
- [ ] Record remaining model-art limitations separately from runtime defects.
