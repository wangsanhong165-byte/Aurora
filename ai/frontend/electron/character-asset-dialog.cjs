const fs = require('node:fs')
const path = require('node:path')

const definitions = {
  live2d_directory: {
    title: '选择完整 Live2D 模型目录',
    properties: ['openDirectory'],
  },
  reference_audio: {
    title: '选择声线参考音频',
    properties: ['openFile'],
    filters: [{ name: 'Audio', extensions: ['wav', 'flac', 'mp3', 'ogg', 'm4a'] }],
  },
  t2s_model: {
    title: '选择 GPT 文本语义模型',
    properties: ['openFile'],
    filters: [{ name: 'GPT weights', extensions: ['ckpt'] }],
  },
  vits_model: {
    title: '选择 SoVITS 声学模型',
    properties: ['openFile'],
    filters: [{ name: 'SoVITS weights', extensions: ['pth'] }],
  },
}

// Conventional in-repo locations for each asset type, relative to the project
// root. Opens the native picker where these resources actually live instead of
// the last-used/global folder.
const DEFAULT_DIRS = {
  live2d_directory: 'models/live2d-models',
  reference_audio: 'config/characters/monika/model',
  t2s_model: 'config/characters/monika/model',
  vits_model: 'config/characters/monika/model',
}

function dialogOptionsFor(kind, rootDir) {
  const definition = definitions[kind]
  if (!definition) throw new Error(`unsupported character asset kind: ${kind}`)
  const options = { ...definition }
  const defaultSub = DEFAULT_DIRS[kind]
  if (defaultSub && rootDir) {
    const candidate = path.join(rootDir, defaultSub)
    try {
      if (fs.statSync(candidate).isDirectory()) options.defaultPath = candidate
    } catch {
      // Directory absent — fall back to the OS default.
    }
  }
  return options
}

module.exports = { dialogOptionsFor }
