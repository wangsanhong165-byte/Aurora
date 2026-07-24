import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'

const args = new Set(process.argv.slice(2))
const valueAfter = (flag, fallback) => {
  const index = process.argv.indexOf(flag)
  return index >= 0 ? process.argv[index + 1] : fallback
}
const cwd = process.cwd()
const modelsRoot = path.resolve(cwd, valueAfter('--models-root', '../models/live2d-models'))
const profilesRoot = path.resolve(cwd, valueAfter('--profiles-root', '../config/avatar_profiles'))

const readJson = async file => JSON.parse(await readFile(file, 'utf8'))
const files = await readdir(profilesRoot)
const reports = []

for (const file of files.filter(name => name.endsWith('.json'))) {
  const profile = await readJson(path.join(profilesRoot, file))
  const modelDir = path.join(modelsRoot, profile.model)
  const modelFile = path.join(modelDir, `${profile.model}.model3.json`)
  let model3
  try { model3 = await readJson(modelFile) } catch { continue }

  const refs = model3.FileReferences ?? {}
  const displayInfoFile = refs.DisplayInfo ? path.join(modelDir, refs.DisplayInfo) : null
  let knownParameters = new Set()
  if (displayInfoFile) {
    try {
      const display = await readJson(displayInfoFile)
      knownParameters = new Set((display.Parameters ?? []).map(parameter => parameter.Id))
    } catch { /* DisplayInfo is optional. */ }
  }

  const bindings = Object.entries(profile.bindings ?? {}).map(([logical, binding]) => ({
    logical,
    target: typeof binding === 'string' ? binding : binding.target,
  }))
  const missingBindings = knownParameters.size
    ? bindings.filter(binding => !knownParameters.has(binding.target))
    : []
  const validBindings = bindings.length - missingBindings.length
  const nativeExpressions = (refs.Expressions ?? []).map(item => item.Name)
  const nativeMotionCatalog = Object.entries(refs.Motions ?? {}).flatMap(([group, items]) =>
    items.map((item, index) => ({
      group,
      index,
      name: item.Name ?? `${group}:${index}`,
      file: item.File,
      basename: item.File ? path.basename(item.File).replace(/\.motion3\.json$/i, '') : undefined,
    })),
  )
  const nativeMotions = nativeMotionCatalog.map(item => item.name)
  const semanticGroups = { Talk: 'speak', Tap: 'react', Idle: 'idle' }
  const mappingSuggestions = Object.fromEntries(
    Object.entries(semanticGroups)
      .filter(([group]) => nativeMotionCatalog.some(item => item.group.toLowerCase() === group.toLowerCase()))
      .map(([group, semantic]) => [semantic, group]),
  )

  reports.push({
    model: profile.model,
    profile: file,
    coverage: bindings.length ? validBindings / bindings.length : 1,
    bindingCount: bindings.length,
    validBindings,
    missingBindings,
    nativeExpressions,
    nativeMotions,
    nativeMotionCatalog,
    mappingSuggestions,
    assets: {
      DisplayInfo: Boolean(refs.DisplayInfo),
      Expressions: nativeExpressions.length,
      Motions: nativeMotions.length,
      Physics: Boolean(refs.Physics),
      Pose: Boolean(refs.Pose),
    },
  })
}

if (args.has('--json')) {
  console.log(JSON.stringify(reports, null, 2))
} else {
  for (const report of reports) {
    console.log(`${report.model}: ${(report.coverage * 100).toFixed(1)}% bindings, ${report.nativeExpressions.length} expressions, ${report.nativeMotions.length} motions`)
    for (const missing of report.missingBindings) console.log(`  missing ${missing.logical} -> ${missing.target}`)
  }
}

if (args.has('--strict') && reports.some(report => report.missingBindings.length > 0)) {
  process.exitCode = 1
}
