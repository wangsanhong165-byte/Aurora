// Live2DModelAdapter — the ONLY class that may call Cubism SDK methods.
//
// All parameter writes, part opacity changes, and model updates must go
// through this adapter. Business controllers may NOT hold CubismModelHandle.
//
// The adapter is pure pass-through — it contains NO priority logic,
// NO state machine, NO AI decision-making. It only translates calls
// to the underlying Cubism SDK.
//
// The renderer (infrastructure, not a business controller) may access
// the handle via getHandleForRenderer().

import type { CubismModelHandle, ModelParameterMetadata, ModelPartMetadata } from './live2d/core'
import { PoseController } from './live2d/PoseController'

interface BaselineAwareMixer {
  setBaselineProvider(provider: ((parameterId: string) => number) | null): void
}

export class Live2DModelAdapter {
  private _handle: CubismModelHandle | null = null
  private _poseController: PoseController | null = null

  /** Attach a Cubism model handle (called when model loads). */
  attach(handle: CubismModelHandle): void {
    this._handle = handle
  }

  /** Detach the model handle (called when model unloads). */
  detach(): void {
    this._handle = null
    this._poseController = null
  }

  /** Get the underlying handle — ONLY for renderer/model lifecycle use. */
  getHandleForRenderer(): CubismModelHandle | null {
    return this._handle
  }

  // ── Parameter control ──────────────────────────────────────

  /** Set a parameter value by ID (absolute write). */
  setParameter(id: string, value: number): void {
    this._handle?.setParameter(id, value)
  }

  /** Get a parameter value by ID. */
  getParameter(id: string): number {
    return this._handle?.getParameter(id) ?? 0
  }

  configureMixerBaseline(mixer: BaselineAwareMixer): void {
    mixer.setBaselineProvider(parameterId => this.getParameter(parameterId))
  }

  /** Read-only capability query used by diagnostics and profile calibration. */
  hasParameter(id: string): boolean {
    return (this._handle?.parameterIndex(id) ?? -1) >= 0
  }

  getParameterMetadata(ids?: Iterable<string>): ModelParameterMetadata[] {
    return this._handle?.getParameterMetadata(ids) ?? []
  }

  getPartMetadata(): ModelPartMetadata[] { return this._handle?.getPartMetadata() ?? [] }

  /** Set part opacity by ID. */
  setPartOpacity(id: string, opacity: number): void {
    this._handle?.setPartOpacity(id, opacity)
  }

  // ── Model lifecycle ─────────────────────────────────────────

  /** Apply parameter changes to vertex data. Calls framework model.update(). */
  updateModel(deltaTimeSeconds = 0): void {
    this._handle?.updatePhysics(deltaTimeSeconds)
    this._handle?.frameworkModel.update()
  }

  // ── Pose control ────────────────────────────────────────────

  /** Set the pose controller (registered by ModelManager after loading pose3.json). */
  setPoseController(pc: PoseController | null): void {
    this._poseController = pc
  }

  /** Return pose baselines for the frame mixer; never writes the model directly. */
  getPoseContributions(): Array<{ partId: string; opacity: number }> {
    return this._poseController?.getContributions() ?? []
  }

  getPoseDebug(): Array<{ activeId: string; members: string[] }> {
    return this._poseController?.getDebugState() ?? []
  }

  // ── Accessors for renderer ──────────────────────────────────

  get canvasWidth(): number { return this._handle?.canvasWidth ?? 0 }
  get canvasHeight(): number { return this._handle?.canvasHeight ?? 0 }

  /** True when a model handle is attached. */
  get isAttached(): boolean { return this._handle !== null }
}
