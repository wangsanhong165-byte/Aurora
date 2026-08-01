import { loadModelFromBuffer, releaseModel, type CubismModelHandle } from './core'
import { createFrameworkRenderer, loadTextures, getGL } from './renderer'
import { CubismRenderer_WebGL } from './framework/rendering/cubismrenderer_webgl'
import { registerModelPresets, resetPresets, type ExpressionPreset } from './expression'
import { PoseController } from './PoseController'
import { NativeMotionPlayer } from './NativeMotionPlayer'
import {
  LatestModelLoadCoordinator,
  type ModelLoadResult,
  type ModelLoadToken,
} from './ModelLoadCoordinator'

export type ModelState = 'unloaded' | 'loading' | 'loaded' | 'error' | 'unavailable'
export type ModelLoadOutcome = ModelLoadResult<void>

export interface ModelInfo {
  name: string
  url: string
  emotionMap?: Record<string, string>
  behaviors?: string[]
}

interface CandidateSession {
  name: string
  generation: number
  handle: CubismModelHandle
  renderer: CubismRenderer_WebGL
  expressionPresets: Record<string, ExpressionPreset>
  expressionNames: string[]
  poseController: PoseController | null
  nativeMotionPlayer: NativeMotionPlayer
}

export function normalizeExpressionBlend(blend: unknown): 'add' | 'multiply' | 'overwrite' {
  const normalized = String(blend ?? 'Add').toLowerCase()
  if (normalized === 'multiply') return 'multiply'
  if (normalized === 'overwrite') return 'overwrite'
  return 'add'
}

function parseExp3Json(json: Record<string, unknown>): ExpressionPreset | null {
  try {
    const params = (json.Parameters as Array<Record<string, unknown>>) || []
    const preset: ExpressionPreset = { params: [] }
    for (const parameter of params) {
      preset.params.push({
        id: parameter.Id as string,
        value: parameter.Value as number,
        blend: normalizeExpressionBlend(parameter.Blend),
      })
    }
    return preset.params.length > 0 ? preset : null
  } catch {
    return null
  }
}

function modelNameFromUrl(modelUrl: string): string {
  return modelUrl.split('/').filter(Boolean).reverse()[1] || 'unknown'
}

function releaseSession(session: Pick<CandidateSession, 'handle' | 'renderer'> | null): void {
  if (!session) return
  const gl = getGL()
  const textures = session.renderer.getBindedTextures()
  if (gl && textures) {
    for (let index = 0; index < textures.getSize(); index += 1) {
      const texture = textures.getValue(index)
      if (texture) gl.deleteTexture(texture)
    }
  }
  session.renderer.release()
  releaseModel(session.handle)
}

export class ModelManager {
  private session: CandidateSession | null = null
  private coordinator = new LatestModelLoadCoordinator<CandidateSession>()
  private inFlight: { name: string; promise: Promise<ModelLoadOutcome> } | null = null
  private _state: ModelState = 'unloaded'
  private _requestedModel = ''

  get state(): ModelState { return this._state }
  get modelName(): string { return this.session?.name ?? '' }
  get generation(): number { return this.session?.generation ?? 0 }
  get requestedModel(): string { return this._requestedModel }
  getModel(): CubismModelHandle | null { return this.session?.handle ?? null }
  getRenderer(): CubismRenderer_WebGL | null { return this.session?.renderer ?? null }
  getExpressionPresets(): Record<string, ExpressionPreset> { return this.session?.expressionPresets ?? {} }
  getExpressionNames(): string[] { return this.session?.expressionNames ?? [] }
  getPoseController(): PoseController | null { return this.session?.poseController ?? null }
  getNativeMotionPlayer(): NativeMotionPlayer { return this.session?.nativeMotionPlayer ?? new NativeMotionPlayer() }

  getDiagnostics(): {
    requestedModel: string
    loadedModel: string
    generation: number
    rendererGeneration: number
  } {
    return {
      requestedModel: this._requestedModel,
      loadedModel: this.session?.name ?? '',
      generation: this.session?.generation ?? 0,
      rendererGeneration: this.session?.generation ?? 0,
    }
  }

  load(modelUrl: string): Promise<ModelLoadOutcome> {
    const name = modelNameFromUrl(modelUrl)
    this._requestedModel = name
    if (this.inFlight?.name === name) return this.inFlight.promise
    if (this.session?.name === name && this._state === 'loaded') {
      return Promise.resolve({
        status: 'loaded', modelName: name, generation: this.session.generation, value: undefined,
      })
    }
    if (!getGL()) {
      this._state = 'error'
      return Promise.resolve({
        status: 'failed', modelName: name, generation: this.coordinator.currentGeneration, error: new Error('WebGL unavailable'),
      })
    }

    this._state = 'loading'
    let promise!: Promise<ModelLoadOutcome>
    promise = this.coordinator.run(name, token => this.buildCandidate(modelUrl, name, token))
      .then(result => {
        if (result.status === 'loaded') {
          const candidate = result.value
          if (!candidate || candidate.generation !== result.generation) {
            if (candidate) releaseSession(candidate)
            this._state = 'error'
            return { status: 'failed', modelName: name, generation: result.generation, error: new Error('generation mismatch') } as ModelLoadOutcome
          }
          const previous = this.session
          this.session = candidate
          resetPresets()
          registerModelPresets(candidate.expressionPresets)
          releaseSession(previous)
          this._state = 'loaded'
          console.log('[ModelManager] load commit', this.getDiagnostics())
          return { status: 'loaded', modelName: name, generation: result.generation, value: undefined } as ModelLoadOutcome
        }
        if (result.status === 'failed') {
          this._state = this.session ? 'loaded' : 'error'
          console.error('[ModelManager] load failed:', name, result.error)
        }
        return result
      })
      .finally(() => {
        if (this.inFlight?.promise === promise) this.inFlight = null
      })
    this.inFlight = { name, promise }
    return promise
  }

  private async buildCandidate(modelUrl: string, name: string, token: ModelLoadToken): Promise<CandidateSession> {
    let handle: CubismModelHandle | null = null
    let renderer: CubismRenderer_WebGL | null = null
    let committed = false
    try {
      const modelResponse = await fetch(modelUrl, { signal: token.signal })
      if (!modelResponse.ok) throw new Error(`model3.json fetch failed: ${modelResponse.status}`)
      const model3Json = await modelResponse.json()
      const references = model3Json.FileReferences ?? {}
      const baseUrl = modelUrl.substring(0, modelUrl.lastIndexOf('/'))
      if (!references.Moc) throw new Error('model3.json has no Moc reference')

      const mocResponse = await fetch(`${baseUrl}/${references.Moc}`, { signal: token.signal })
      if (!mocResponse.ok) throw new Error(`moc3 fetch failed: ${mocResponse.status}`)
      handle = loadModelFromBuffer(await mocResponse.arrayBuffer())
      if (!handle) throw new Error('loadModelFromBuffer returned null')
      renderer = createFrameworkRenderer(handle.frameworkModel)
      if (!renderer) throw new Error('createFrameworkRenderer returned null')

      const textures: string[] = (references.Textures ?? []).map((file: string) => `${baseUrl}/${file}`)
      await loadTextures(renderer, textures)
      if (!token.isCurrent()) throw new DOMException('Superseded', 'AbortError')

      const expressionPresets: Record<string, ExpressionPreset> = {}
      const expressionNames: string[] = []
      for (const expression of references.Expressions ?? []) {
        const response = await fetch(`${baseUrl}/${expression.File}`, { signal: token.signal })
        if (!response.ok) continue
        const preset = parseExp3Json(await response.json())
        if (!preset) continue
        expressionPresets[expression.Name] = preset
        expressionNames.push(expression.Name)
      }

      const nativeMotionPlayer = new NativeMotionPlayer()
      const motionGroups: Record<string, Array<{
        File: string; Name?: string; FadeInTime?: number; FadeOutTime?: number
      }>> = model3Json.FileReferences?.Motions ?? {}
      for (const [group, motionReferences] of Object.entries(motionGroups)) {
        for (let index = 0; index < motionReferences.length; index += 1) {
          const reference = motionReferences[index]
          const response = await fetch(`${baseUrl}/${reference.File}`, { signal: token.signal })
          if (!response.ok) continue
          const motionJson = await response.json()
          if (reference.FadeInTime !== undefined) motionJson.FadeInTime = reference.FadeInTime
          if (reference.FadeOutTime !== undefined) motionJson.FadeOutTime = reference.FadeOutTime
          const basename = reference.File.split('/').pop()?.replace(/\.motion3\.json$/i, '') ?? ''
          nativeMotionPlayer.register(`${group}:${index}`, motionJson, [
            reference.Name ?? '', basename, group,
          ])
        }
      }

      let poseController: PoseController | null = null
      if (references.Pose) {
        const response = await fetch(`${baseUrl}/${references.Pose}`, { signal: token.signal })
        if (response.ok) {
          poseController = new PoseController()
          poseController.load(await response.json())
        }
      }
      if (!token.isCurrent()) throw new DOMException('Superseded', 'AbortError')
      committed = true
      return {
        name,
        generation: token.generation,
        handle,
        renderer,
        expressionPresets,
        expressionNames,
        poseController,
        nativeMotionPlayer,
      }
    } finally {
      if (!committed && handle && renderer) releaseSession({ handle, renderer })
      else if (!committed && handle) releaseModel(handle)
      else if (!committed && renderer) renderer.release()
    }
  }

  unload(): void {
    this.coordinator.cancel()
    this.inFlight = null
    releaseSession(this.session)
    this.session = null
    this._state = 'unloaded'
    this._requestedModel = ''
    resetPresets()
  }

  reset(): void { this.unload() }
}
