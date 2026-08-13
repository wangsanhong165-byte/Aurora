// Cubism Core initialization and model loading
// Wraps CubismWebFramework's CubismMoc + CubismModel for our controller API

import { CubismMoc } from './framework/model/cubismmoc'
import { CubismModel } from './framework/model/cubismmodel'
import { CubismFramework } from './framework/live2dcubismframework'
import { CubismPhysics } from './framework/physics/cubismphysics'

export interface ModelParameterMetadata {
  id: string
  displayName?: string
  groupName?: string
  minimum: number
  maximum: number
  defaultValue: number
  value: number
}

export interface ModelPartMetadata {
  id: string
  displayName?: string
  opacity: number
  parentIndex: number
}

export interface CubismModelHandle {
  model: Live2DCubismCore.Model
  moc: Live2DCubismCore.Moc
  frameworkModel: CubismModel
  frameworkMoc: CubismMoc
  canvasWidth: number
  canvasHeight: number
  /** Find parameter index by ID, returns -1 if not found */
  parameterIndex: (id: string) => number
  /** Set a parameter value by ID (absolute) */
  setParameter: (id: string, value: number) => void
  /** Add to a parameter value by ID (relative/additive) */
  addParameter: (id: string, value: number, weight?: number) => void
  /** Get a parameter value by ID */
  getParameter: (id: string) => number
  /** Read the model's complete parameter catalog or a selected subset. */
  getParameterMetadata: (ids?: Iterable<string>) => ModelParameterMetadata[]
  /** Enrich opaque moc IDs with names from the optional cdi3 display file. */
  setParameterDisplayInfo: (entries: Array<{ id: string; displayName?: string; groupName?: string }>) => void
  getPartMetadata: () => ModelPartMetadata[]
  setPartDisplayInfo: (entries: Array<{ id: string; displayName?: string }>) => void
  /** Set part opacity by ID */
  setPartOpacity: (id: string, opacity: number) => void
  /** Load the model's physics3.json rig, when one is provided. */
  setPhysics: (buffer: ArrayBuffer) => void
  /** Evaluate physics after controller inputs have been written. */
  updatePhysics: (deltaTimeSeconds: number) => void
  /** Release the optional physics rig. */
  releasePhysics: () => void
}

/** Initialize CubismFramework (call once at app startup) */
export function initCubismFramework(): void {
  if (!CubismFramework.isStarted()) {
    CubismFramework.startUp()
  }
  if (!CubismFramework.isInitialized()) {
    CubismFramework.initialize()
  }
}

/** Dispose CubismFramework (call once at app shutdown) */
export function disposeCubismFramework(): void {
  if (CubismFramework.isInitialized()) {
    CubismFramework.dispose()
  }
}

// Global mutex: prevents Cubism Core WASM conflicts from concurrent model loads.
let _modelLoadMutex = false

export function loadModelFromBuffer(buffer: ArrayBuffer): CubismModelHandle | null {
  if (_modelLoadMutex) {
    console.warn('[Cubism] loadModelFromBuffer: concurrent call prevented (mutex)')
    return null
  }
  _modelLoadMutex = true
  try {
    return _loadModelFromBufferUnsafe(buffer)
  } finally {
    _modelLoadMutex = false
  }
}

function _loadModelFromBufferUnsafe(buffer: ArrayBuffer): CubismModelHandle | null {
  // Validate Core API
  if (!Live2DCubismCore.Moc.fromArrayBuffer) {
    console.error('[Cubism] Core not initialized')
    return null
  }
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength === 0) {
    console.error('[Cubism] Refusing to load an empty or invalid MOC3 buffer')
    return null
  }

  try {
    // --- Direct Core Moc creation (bypass CubismMoc.create wrapper) ---
    console.log('[Cubism] Calling Live2DCubismCore.Moc.fromArrayBuffer...')
    console.log('[Cubism] buffer type:', typeof buffer, 'byteLength:', buffer?.byteLength)
    const coreMoc = Live2DCubismCore.Moc.fromArrayBuffer(buffer)
    if (!coreMoc) {
      console.error('[Cubism] Live2DCubismCore.Moc.fromArrayBuffer returned null')
      return null
    }
    console.log('[Cubism] Core Moc created OK:', typeof coreMoc, !!coreMoc)

    // Validate the exact buffer against the Core-created MOC before asking
    // Core to allocate a model. The official SDK performs this check as part
    // of its CubismMoc creation path; keeping it here preserves the direct
    // Core path while preventing malformed/stale assets from reaching the
    // Framework renderer.
    const consistencyCheck = (coreMoc as unknown as {
      hasMocConsistency?: (candidate: ArrayBuffer) => number
    }).hasMocConsistency
    if (typeof consistencyCheck === 'function' && consistencyCheck.call(coreMoc, buffer) !== 1) {
      console.error('[Cubism] MOC3 consistency check failed')
      coreMoc._release()
      return null
    }

    // Wrap in Framework's CubismMoc (private constructor 閳?cast bypass)
    const CubismMocCtor = CubismMoc as unknown as new (moc: Live2DCubismCore.Moc) => CubismMoc
    const frameworkMoc = new CubismMocCtor(coreMoc)
    console.log('[Cubism] CubismMoc wrapper created OK')

    // --- Direct Core Model creation (bypass frameworkMoc.createModel) ---
    console.log('[Cubism] Calling Core Model.fromMoc...')
    const coreModel = Live2DCubismCore.Model.fromMoc(coreMoc)
    console.log('[Cubism] Core Model:', typeof coreModel, !!coreModel)
    if (!coreModel) {
      console.error('[Cubism] Model.fromMoc returned null')
      CubismMoc.delete(frameworkMoc)
      return null
    }
    console.log('[Cubism] drawables:', typeof coreModel.drawables, coreModel.drawables ? 'count ' + coreModel.drawables.count : 'MISSING')
    console.log('[Cubism] parameters:', typeof coreModel.parameters, coreModel.parameters ? 'count ' + coreModel.parameters.count : 'MISSING')
    console.log('[Cubism] parts:', typeof coreModel.parts, coreModel.parts ? 'count ' + coreModel.parts.count : 'MISSING')

    // ── Core 5.0 → r.5 framework compatibility shim ──
    // The r.5 CubismWebFramework expects a Cubism Core 5.3 model interface
    // (offscreens, drawables.blendModes, getRenderOrders()). Our core is 5.0.
    // Provide the 5.3 accessors backed by 5.0 data; offscreen/blend features
    // are unused by our models, so the shim exposes empty values.
    const cm = coreModel as Live2DCubismCore.Model & {
      getRenderOrders: () => Int32Array
      offscreens: Record<string, unknown> & { count: number }
    }
    if (typeof cm.getRenderOrders !== 'function') {
      cm.getRenderOrders = () => cm.drawables.renderOrders
    }
    if (!cm.offscreens) {
      cm.offscreens = {
        count: 0,
        constantFlags: new Uint8Array(0),
        dynamicFlags: new Uint8Array(0),
        drawOrders: new Int32Array(0),
        renderOrders: new Int32Array(0),
        opacities: new Float32Array(0),
        multiplyColors: new Float32Array(0),
        screenColors: new Float32Array(0),
        maskCounts: new Int32Array(0),
        masks: [],
        blendModes: new Int32Array(0),
        ownerIndices: new Int32Array(0),
        vertexCounts: new Int32Array(0),
        vertexPositions: [],
        vertexUvs: [],
        indexCounts: new Int32Array(0),
        indices: [],
        parentPartIndices: new Int32Array(0),
      }
    }
    const drawables = coreModel.drawables as { blendModes?: Int32Array }
    if (!drawables.blendModes) {
      drawables.blendModes = new Int32Array(coreModel.drawables.count).fill(0)
    }

    // Wrap in Framework's CubismModel
    console.log('[Cubism] Creating CubismModel...')
    const CubismModelCtor = CubismModel as unknown as new (m: Live2DCubismCore.Model) => CubismModel
    const frameworkModel = new CubismModelCtor(coreModel)
    console.log('[Cubism] CubismModel constructed, calling initialize...')
    frameworkModel.initialize()
    ++frameworkMoc._modelCount
    console.log('[Cubism] CubismModel created OK')

    // Build parameter index map for O(1) lookups
    console.log('[Cubism] Building param map...')
    const paramCount = frameworkModel.getParameterCount()
    const paramIndexMap: Record<string, number> = {}
    const paramNames: string[] = []
    for (let i = 0; i < paramCount; i++) {
      const idObj = frameworkModel.getParameterId(i)
      // CubismId.getString() returns the raw parameter id string (r.5).
      const name = idObj.getString()
      paramIndexMap[name] = i
      paramNames.push(name)
    }
    const parameterMetadata: ModelParameterMetadata[] = paramNames.map((id, index) => ({
      id,
      minimum: coreModel.parameters.minimumValues[index],
      maximum: coreModel.parameters.maximumValues[index],
      defaultValue: coreModel.parameters.defaultValues[index],
      value: coreModel.parameters.values[index],
    }))

    // Build part index map
    const partCount = frameworkModel.getPartCount()
    const partIndexMap: Record<string, number> = {}
    const partMetadata: ModelPartMetadata[] = []
    for (let i = 0; i < partCount; i++) {
      const idObj = frameworkModel.getPartId(i)
      const name = idObj.getString()
      partIndexMap[name] = i
      partMetadata.push({
        id: name,
        opacity: coreModel.parts.opacities[i],
        parentIndex: coreModel.parts.parentIndices[i],
      })
    }
    console.log('[Cubism] Maps built OK, params:', paramCount, 'parts:', partCount)

    let physics: CubismPhysics | null = null

    // Diagnostic: check which PARAM_IDS exist in this model
    const ourIDs = ['ParamAngleX','ParamAngleY','ParamAngleZ','ParamEyeLOpen','ParamEyeROpen','ParamBodyAngleX','ParamBodyAngleY','ParamEyeBallX','ParamEyeBallY','ParamMouthOpenY','ParamBrowLY','ParamBrowRY']
    const missing = ourIDs.filter(id => paramIndexMap[id] === undefined)
    if (missing.length > 0) {
      console.warn('[Cubism] PARAM_IDS NOT FOUND in model:', missing)
    } else {
      console.log('[Cubism] All standard parameter IDs found')
    }
    // Dump first 30 param names to verify
    console.log('[Cubism] First 30 params:', paramNames.slice(0, 30).join(', '))

    const handle: CubismModelHandle = {
      model: coreModel,
      moc: (coreModel as any).moc,
      frameworkModel,
      frameworkMoc,
      canvasWidth: coreModel.canvasinfo.CanvasWidth,
      canvasHeight: coreModel.canvasinfo.CanvasHeight,

    parameterIndex(id: string): number {
      return paramIndexMap[id] ?? -1
    },

    setParameter(id: string, value: number): void {
      const idx = paramIndexMap[id]
      if (idx !== undefined) {
        frameworkModel.setParameterValueByIndex(idx, value)
      }
    },

    getParameter(id: string): number {
      const idx = paramIndexMap[id]
      return idx !== undefined ? frameworkModel.getParameterValueByIndex(idx) : 0
    },

    addParameter(id: string, value: number, weight = 1.0): void {
      const idx = paramIndexMap[id]
      if (idx !== undefined) {
        frameworkModel.addParameterValueByIndex(idx, value, weight)
      }
    },

    setPartOpacity(id: string, opacity: number): void {
      const idx = partIndexMap[id]
      if (idx !== undefined) {
        frameworkModel.setPartOpacityByIndex(idx, opacity)
      }
    },

    getParameterMetadata(ids?: Iterable<string>): ModelParameterMetadata[] {
      const selected = ids ? new Set(ids) : null
      return parameterMetadata
        .filter(parameter => !selected || selected.has(parameter.id))
        .map(parameter => ({
          ...parameter,
          value: coreModel.parameters.values[paramIndexMap[parameter.id]],
        }))
    },

    setParameterDisplayInfo(entries): void {
      const metadataById = new Map(parameterMetadata.map(parameter => [parameter.id, parameter]))
      for (const entry of entries) {
        const metadata = metadataById.get(entry.id)
        if (!metadata) continue
        metadata.displayName = entry.displayName
        metadata.groupName = entry.groupName
      }
    },

    getPartMetadata(): ModelPartMetadata[] {
      return partMetadata.map(part => ({
        ...part,
        opacity: coreModel.parts.opacities[partIndexMap[part.id]],
      }))
    },

    setPartDisplayInfo(entries): void {
      const metadataById = new Map(partMetadata.map(part => [part.id, part]))
      for (const entry of entries) {
        const metadata = metadataById.get(entry.id)
        if (metadata) metadata.displayName = entry.displayName
      }
    },

    setPhysics(buffer: ArrayBuffer): void {
      if (physics) CubismPhysics.delete(physics)
      physics = CubismPhysics.create(buffer, buffer.byteLength)
    },

    updatePhysics(deltaTimeSeconds: number): void {
      if (!physics) return
      physics.evaluate(frameworkModel, Math.max(0, Math.min(deltaTimeSeconds, 0.05)))
    },

    releasePhysics(): void {
      if (!physics) return
      CubismPhysics.delete(physics)
      physics = null
    },
  }

  return handle
  } catch (err) {
    console.error('[Cubism] loadModelFromBuffer error:', err)
    console.error('[Cubism] stack:', (err as any)?.stack)
    return null
  }
}

/** Release framework model and moc resources */
export function releaseModel(handle: CubismModelHandle): void {
  handle.releasePhysics()
  handle.frameworkModel.release()
  CubismMoc.delete(handle.frameworkMoc)
}

export { PARAM_IDS } from './parameters.ts'

export interface ModelConfig {
  /** URL/path to .model3.json */
  modelUrl: string
  /** Base URL for resolving relative paths */
  baseUrl: string
}
