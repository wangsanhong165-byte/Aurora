// WebGL renderer for Live2D Cubism models using CubismWebFramework
// Cached matrices, transparent background, one-pass projection setup.

import type { CubismModelHandle } from './core'
import { CubismRenderer_WebGL } from './framework/rendering/cubismrenderer_webgl'
import { CubismMatrix44 } from './framework/math/cubismmatrix44'
import { CubismModelMatrix } from './framework/math/cubismmodelmatrix'
import { CubismModel } from './framework/model/cubismmodel'

export interface FrameworkRendererState {
  gl: WebGLRenderingContext
  renderer: CubismRenderer_WebGL | null
  canvasWidth: number
  canvasHeight: number
}

let _rs: FrameworkRendererState | null = null

// ── Cached per-model projection resources ──
let _cachedModelW = -1
let _cachedModelH = -1
let _modelMatrix: CubismModelMatrix | null = null
let _baseProjection: CubismMatrix44 | null = null   // base projection WITHOUT viewport transform
let _projection: CubismMatrix44 | null = null       // final projection WITH viewport (rebuilt each frame)

// ── Viewport transform (drag + zoom) ──
let _viewOffsetX = 0
let _viewOffsetY = 0
let _viewScale = 1

// ── Public API ──

export function initRenderer(canvas: HTMLCanvasElement): boolean {
  const gl = canvas.getContext('webgl', {
    alpha: true,
    premultipliedAlpha: true,
    antialias: true,
  })
  if (!gl) {
    console.error('[Cubism] WebGL not supported')
    return false
  }

  _rs = {
    gl,
    renderer: null,
    canvasWidth: canvas.width,
    canvasHeight: canvas.height,
  }

  gl.viewport(0, 0, canvas.width, canvas.height)
  gl.enable(gl.BLEND)
  gl.blendFuncSeparate(gl.ONE, gl.ONE_MINUS_SRC_ALPHA, gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
  gl.clearColor(0, 0, 0, 0) // transparent

  return true
}

export function createFrameworkRenderer(model: CubismModel): CubismRenderer_WebGL | null {
  if (!_rs?.gl) return null

  const renderer = new CubismRenderer_WebGL()
  renderer.initialize(model)
  renderer.startUp(_rs.gl)
  renderer.setIsPremultipliedAlpha(true)

  _rs.renderer = renderer
  return renderer
}

export function resizeRenderer(width: number, height: number): void {
  if (!_rs) return
  _rs.canvasWidth = width
  _rs.canvasHeight = height
  _rs.gl.viewport(0, 0, width, height)
  // Invalidate cached matrices on resize
  _cachedModelW = -1
}

// ── Texture helpers ──

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

function premultiplyImage(image: HTMLImageElement): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = image.width
  canvas.height = image.height
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(image, 0, 0)
  // Premultiply RGB by A/255 — Cubism WebGL shader assumes premultiplied textures
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
  const data = imageData.data
  for (let i = 0; i < data.length; i += 4) {
    const a = data[i + 3] / 255
    data[i] *= a       // R
    data[i + 1] *= a   // G
    data[i + 2] *= a   // B
    // A stays unchanged
  }
  ctx.putImageData(imageData, 0, 0)
  return canvas
}

function createTexture(gl: WebGLRenderingContext, image: HTMLImageElement): WebGLTexture {
  const tex = gl.createTexture()!
  gl.bindTexture(gl.TEXTURE_2D, tex)
  const premul = premultiplyImage(image)
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, premul)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
  gl.bindTexture(gl.TEXTURE_2D, null)
  return tex
}

export async function loadTextures(
  renderer: CubismRenderer_WebGL,
  texturePaths: string[],
): Promise<void> {
  for (let i = 0; i < texturePaths.length; i++) {
    try {
      const img = await loadImage(texturePaths[i])
      const tex = createTexture(renderer['gl'] as WebGLRenderingContext, img)
      renderer.bindTexture(i, tex)
    } catch (e) {
      console.warn(`[Cubism] Failed to load texture: ${texturePaths[i]}`, e)
    }
  }
}

// ── Projection matrix (cached per model + canvas size) ──

function _buildBaseProjection(modelW: number, modelH: number): void {
  if (!_rs) return

  // Reuse cached base projection when model + canvas haven't changed
  if (modelW === _cachedModelW && modelH === _cachedModelH && _modelMatrix && _baseProjection) {
    return
  }

  _cachedModelW = modelW
  _cachedModelH = modelH

  const cw = _rs.canvasWidth
  const ch = _rs.canvasHeight

  _baseProjection = new CubismMatrix44() // identity
  _modelMatrix = new CubismModelMatrix(modelW, modelH)

  if (cw < ch) {
    // Portrait
    _modelMatrix.setWidth(2)
    _baseProjection.scale(1, cw / ch)
  } else {
    // Landscape / square
    _baseProjection.scale(ch / cw, 1)
  }

  _modelMatrix.centerX(0)
  _modelMatrix.centerY(0)
  _baseProjection.multiplyByMatrix(_modelMatrix)
}

/** Invalidate projection cache so next render picks up viewport changes */
function _invalidateProjection(): void {
  _cachedModelW = -1
}

// ── Main render ──

let _rendererMissingLogged = false

export function render(handle: CubismModelHandle): void {
  if (!_rs?.renderer) {
    if (!_rendererMissingLogged) {
      console.error('[Live2D] render() skipped: _rs.renderer is null')
      _rendererMissingLogged = true
    }
    return
  }
  _rendererMissingLogged = false

  const model = handle.frameworkModel

  // ── Reset GL state corrupted by Cubism mask pass ──
  // Cubism's mask rendering enables SCISSOR_TEST and writes to the stencil buffer.
  // If not reset, subsequent frames render with stale scissor clipping + stencil
  // mask, causing ghosting (drawables rendered in wrong positions, limbs duplicated).
  const gl = _rs.gl
  gl.disable(gl.SCISSOR_TEST)
  gl.disable(gl.STENCIL_TEST)
  gl.disable(gl.DEPTH_TEST)
  gl.disable(gl.CULL_FACE)

  // Set render target (null = default framebuffer = screen)
  _rs.renderer.setRenderState(
    null as unknown as WebGLFramebuffer,
    [0, 0, _rs.canvasWidth, _rs.canvasHeight],
  )

  // Clear ALL buffers — color AND stencil.
  // Cubism mask rendering writes to the stencil buffer for clipping but
  // never clears it between frames, causing stale mask regions to persist.
  // Reset clearColor BEFORE clearing — Cubism mask pass sets it to (1,1,1,1)
  // and never restores it, causing subsequent frames to clear to white.
  // Also reset clearStencil — Cubism mask writes arbitrary stencil values
  // that persist across frames if not explicitly cleared to 0.
  gl.clearColor(0, 0, 0, 0)
  gl.clearStencil(0)
  gl.clear(gl.COLOR_BUFFER_BIT | gl.STENCIL_BUFFER_BIT)

  // Build / reuse base projection (cached by model dimensions)
  _buildBaseProjection(model.getCanvasWidth(), model.getCanvasHeight())

  // ALWAYS build final projection from base + viewport (not cached — viewport changes per frame)
  _projection = new CubismMatrix44()
  if (_baseProjection) {
    // Copy base projection values
    const baseTr = _baseProjection.getArray()
    const finalTr = _projection.getArray()
    for (let i = 0; i < 16; i++) finalTr[i] = baseTr[i]
  }
  // Build viewport transform and multiply on the left of the base projection.
  // NOTE: scale() and translate() are ABSOLUTE setters (overwrite tr[0]/tr[5]/tr[12]/tr[13]),
  // so we build the viewport matrix on a FRESH identity, then multiply onto _projection.
  // This preserves the aspect ratio and model scale from the base projection.
  const _vp = new CubismMatrix44()
  _vp.scale(_viewScale, _viewScale)
  _vp.translate(_viewOffsetX, _viewOffsetY)
  // _projection = vp * _projection  (viewport * base)
  _projection.multiplyByMatrix(_vp)
  _rs.renderer.setMvpMatrix(_projection!)

  _rs.renderer.drawModel()
}

// ── Accessors ──

export function getGL(): WebGLRenderingContext | null {
  return _rs?.gl ?? null
}

export function getRenderer(): CubismRenderer_WebGL | null {
  return _rs?.renderer ?? null
}

/** Set viewport pan offset (normalized -1..1 coordinates) */
export function setViewOffset(x: number, y: number): void {
  _viewOffsetX = x
  _viewOffsetY = y
  _invalidateProjection()
}

/** Set viewport zoom scale (1 = default, >1 = zoom in, <1 = zoom out) */
export function setViewScale(scale: number): void {
  _viewScale = Math.max(0.1, Math.min(5, scale))
  _invalidateProjection()
}

/** Get current viewport transform */
export function getViewTransform(): { x: number; y: number; scale: number } {
  return { x: _viewOffsetX, y: _viewOffsetY, scale: _viewScale }
}

/** Reset viewport to default */
export function resetView(): void {
  _viewOffsetX = 0
  _viewOffsetY = 0
  _viewScale = 1
  _invalidateProjection()
}

export function destroyRenderer(): void {
  if (!_rs) return
  _rs.renderer?.release()
  _rs = null
  _modelMatrix = null
  _baseProjection = null
  _projection = null
  _cachedModelW = -1
}
