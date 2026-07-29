// Model Manager — handles Live2D model lifecycle (load, unload, swap)
// Supports dynamic model loading from model3.json URLs
// Uses CubismWebFramework for model loading and rendering

import { loadModelFromBuffer, releaseModel, type CubismModelHandle } from './core'
import { createFrameworkRenderer, loadTextures, getGL } from './renderer'
import { CubismRenderer_WebGL } from './framework/rendering/cubismrenderer_webgl'
import {
  registerModelPresets,
  resetPresets,
  type ExpressionPreset,
} from './expression'
import { PoseController } from './PoseController'
import { NativeMotionPlayer } from './NativeMotionPlayer'

export type ModelState = 'unloaded' | 'loading' | 'loaded' | 'error' | 'unavailable'

export interface ModelInfo {
  name: string
  url: string
  emotionMap?: Record<string, string>
  behaviors?: string[]
}

/**
 * Parse a Cubism expression .exp3.json file into an ExpressionPreset.
 * Handles both "Add" and "Multiply" blend modes.
 */
export function normalizeExpressionBlend(
  blend: unknown,
): 'add' | 'multiply' | 'overwrite' {
  const normalized = String(blend ?? 'Add').toLowerCase()
  if (normalized === 'multiply') return 'multiply'
  if (normalized === 'overwrite') return 'overwrite'
  return 'add'
}

function parseExp3Json(json: Record<string, unknown>): ExpressionPreset | null {
  try {
    const params = (json.Parameters as Array<Record<string, unknown>>) || []
    const preset: ExpressionPreset = { params: [] }
    for (const p of params) {
      preset.params.push({
        id: p.Id as string,
        value: p.Value as number,
        blend: normalizeExpressionBlend(p.Blend),
      })
    }
    return preset.params.length > 0 ? preset : null
  } catch {
    return null
  }
}

export class ModelManager {
  private model: CubismModelHandle | null = null
  private renderer: CubismRenderer_WebGL | null = null
  private _state: ModelState = 'unloaded'
  private _modelName: string = ''

  /** Expression presets loaded from model's .exp3.json files */
  private _expressionPresets: Record<string, ExpressionPreset> = {}
  /** Set of model-specific expression names (needed for resolveExpression) */
  private _expressionNames: string[] = []
  /** Pose controller for managing part opacity in pose groups */
  private _poseController: PoseController | null = null
  private _nativeMotionPlayer = new NativeMotionPlayer()

  /** Current model state */
  get state(): ModelState {
    return this._state
  }

  /** Current model name */
  get modelName(): string {
    return this._modelName
  }

  /** Get the loaded model handle (null if not loaded) */
  getModel(): CubismModelHandle | null {
    return this.model
  }

  /** Get the Framework renderer (null if not initialized) */
  getRenderer(): CubismRenderer_WebGL | null {
    return this.renderer
  }

  /** Get model-specific expression presets */
  getExpressionPresets(): Record<string, ExpressionPreset> {
    return this._expressionPresets
  }

  /** Get model-specific expression names */
  getExpressionNames(): string[] {
    return this._expressionNames
  }

  /** Pose constraints are owned by the model adapter during the frame loop. */
  getPoseController(): PoseController | null {
    return this._poseController
  }

  getNativeMotionPlayer(): NativeMotionPlayer {
    return this._nativeMotionPlayer
  }

  /** Load a model from a .model3.json URL */
  async load(modelUrl: string): Promise<boolean> {
    const gl = getGL()
    if (!gl) {
      this._state = 'error'
      return false
    }

    // Unload existing model first
    this.unload()

    this._state = 'loading'

    try {
      console.log('[ModelManager] Loading model from:', modelUrl)
      const res = await fetch(modelUrl)
      if (!res.ok) {
        console.error('[ModelManager] model3.json fetch failed:', res.status, modelUrl)
        this._state = 'unavailable'
        return false
      }

      const model3Json = await res.json()
      const baseUrl = modelUrl.substring(0, modelUrl.lastIndexOf('/'))
      console.log('[ModelManager] Base URL:', baseUrl)
      console.log('[ModelManager] Moc file:', model3Json.FileReferences?.Moc)

      // Extract model name from URL
      const urlParts = modelUrl.split('/')
      this._modelName = urlParts[urlParts.length - 2] || 'unknown'

      // Load moc3 file
      const mocFile = model3Json.FileReferences?.Moc
      if (!mocFile) {
        this._state = 'error'
        return false
      }

      const mocRes = await fetch(`${baseUrl}/${mocFile}`)
      console.log('[ModelManager] moc3 fetch status:', mocRes.status, `${baseUrl}/${mocFile}`)
      const mocBuffer = await mocRes.arrayBuffer()
      console.log('[ModelManager] moc3 buffer size:', mocBuffer.byteLength)

      // Create CubismModelHandle using Framework (CubismMoc + CubismModel)
      console.log('[ModelManager] Calling loadModelFromBuffer...')
      const handle = loadModelFromBuffer(mocBuffer)
      if (!handle) {
        console.error('[ModelManager] loadModelFromBuffer returned null')
        this._state = 'error'
        return false
      }
      console.log('[ModelManager] Model loaded, canvas size:', handle.canvasWidth, 'x', handle.canvasHeight)

      this.model = handle

      // Create Framework WebGL renderer for this model
      console.log('[ModelManager] Creating framework renderer...')
      const renderer = createFrameworkRenderer(handle.frameworkModel)
      if (!renderer) {
        console.error('[ModelManager] createFrameworkRenderer returned null')
        this._state = 'error'
        return false
      }
      this.renderer = renderer
      console.log('[ModelManager] Renderer created successfully')

      // Load and bind textures
      const texPaths: string[] = (model3Json.FileReferences?.Textures || []).map(
        (t: string) => `${baseUrl}/${t}`,
      )

      if (texPaths.length > 0) {
        await loadTextures(renderer, texPaths)
      }

      // ── Load model-specific .exp3.json expression files ──
      const expRefs: Array<{ Name: string; File: string }> =
        model3Json.FileReferences?.Expressions || []
      if (expRefs.length > 0) {
        console.log('[ModelManager] Loading %d expression files...', expRefs.length)
        const newPresets: Record<string, ExpressionPreset> = {}
        const newNames: string[] = []
        for (const expRef of expRefs) {
          try {
            const expRes = await fetch(`${baseUrl}/${expRef.File}`)
            if (!expRes.ok) {
              console.warn('[ModelManager] Failed to load expression:', expRef.File, expRes.status)
              continue
            }
            const expJson = await expRes.json()
            const preset = parseExp3Json(expJson)
            if (preset) {
              newPresets[expRef.Name] = preset
              newNames.push(expRef.Name)
              console.log('[ModelManager]   + expression:', expRef.Name, '(%d params)', preset.params.length)
            }
          } catch (e) {
            console.warn('[ModelManager] Error loading expression:', expRef.File, e)
          }
        }
        this._expressionPresets = newPresets
        this._expressionNames = newNames

        // Register model-specific presets for ExpressionController
        resetPresets()
        registerModelPresets(newPresets)
        console.log('[ModelManager] EXPRESSION PRESETS LOADED: %d expressions', newNames.length)
      } else {
        console.log('[ModelManager] No expression files in model3.json (using hardcoded presets)')
        this._expressionPresets = {}
        this._expressionNames = []
        resetPresets()
      }

      const motionGroups: Record<string, Array<{
        File: string
        Name?: string
        FadeInTime?: number
        FadeOutTime?: number
      }>> = model3Json.FileReferences?.Motions || {}
      this._nativeMotionPlayer = new NativeMotionPlayer()
      for (const [group, refs] of Object.entries(motionGroups)) {
        for (let index = 0; index < refs.length; index += 1) {
          const ref = refs[index]
          try {
            const motionRes = await fetch(`${baseUrl}/${ref.File}`)
            if (!motionRes.ok) continue
            const motionJson = await motionRes.json()
            if (ref.FadeInTime !== undefined) motionJson.FadeInTime = ref.FadeInTime
            if (ref.FadeOutTime !== undefined) motionJson.FadeOutTime = ref.FadeOutTime
            const basename = ref.File.split('/').pop()?.replace(/\.motion3\.json$/i, '') ?? ''
            this._nativeMotionPlayer.register(`${group}:${index}`, motionJson, [
              ref.Name ?? '', basename, group,
            ])
          } catch (error) {
            console.warn('[ModelManager] Error loading native motion:', ref.File, error)
          }
        }
      }

      // ── Load pose3.json for part opacity management ──
      const poseFile = model3Json.FileReferences?.Pose
      if (poseFile) {
        try {
          const poseRes = await fetch(`${baseUrl}/${poseFile}`)
          if (poseRes.ok) {
            const poseJson = await poseRes.json()
            this._poseController = new PoseController()
            this._poseController.load(poseJson)
            this._poseController.applyInitial(handle)
            console.log('[ModelManager] Pose loaded: %d groups', this._poseController.groupCount)
          } else {
            console.warn('[ModelManager] Failed to load pose:', poseFile, poseRes.status)
          }
        } catch (e) {
          console.warn('[ModelManager] Error loading pose:', poseFile, e)
        }
      } else {
        this._poseController = null
      }

      this._state = 'loaded'
      return true

    } catch (e) {
      console.error('[ModelManager] Error loading model:', e)
      this._state = 'error'
      return false
    }
  }

  /** Unload the current model and release resources */
  unload(): void {
    if (this.model) {
      // Release the CubismModel and CubismMoc properly, not just null the reference.
      // Without releaseModel(), the old model's GL textures and GPU buffers remain
      // allocated and can cause ghosting / memory leaks on model switch.
      releaseModel(this.model)
    }
    if (this.renderer) {
      this.renderer.release()
      this.renderer = null
    }
    this.model = null
    this._state = 'unloaded'
    this._modelName = ''
    this._expressionPresets = {}
    this._expressionNames = []
    this._poseController = null
    this._nativeMotionPlayer = new NativeMotionPlayer()
    resetPresets()
  }

  /** Reset state to allow retry after error */
  reset(): void {
    this.unload()
    this._state = 'unloaded'
  }
}
