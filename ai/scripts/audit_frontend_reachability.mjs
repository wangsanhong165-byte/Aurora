import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'

const frontendRoot = path.resolve(process.cwd(), 'frontend')
const sourceRoot = path.join(frontendRoot, 'src')
const productionEntry = path.join(sourceRoot, 'main.tsx')

const walk = async directory => {
  const entries = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(entries.map(entry => {
    const absolute = path.join(directory, entry.name)
    return entry.isDirectory() ? walk(absolute) : [absolute]
  }))
  return nested.flat()
}

const allSourceFiles = (await walk(sourceRoot))
  .filter(file => /\.(?:ts|tsx)$/.test(file) && !file.endsWith('.d.ts'))
const sourceSet = new Set(allSourceFiles.map(file => path.normalize(file)))

const resolveLocal = (fromFile, specifier) => {
  if (!specifier.startsWith('.')) return null
  const unresolved = path.resolve(path.dirname(fromFile), specifier)
  const candidates = [
    unresolved,
    `${unresolved}.ts`,
    `${unresolved}.tsx`,
    path.join(unresolved, 'index.ts'),
    path.join(unresolved, 'index.tsx'),
  ]
  return candidates.map(candidate => path.normalize(candidate)).find(candidate => sourceSet.has(candidate)) ?? null
}

const importPattern = /(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?['"]([^'"]+)['"]|import\(\s*['"]([^'"]+)['"]\s*\)/g
const graph = new Map()
for (const file of allSourceFiles) {
  const source = await readFile(file, 'utf8')
  const dependencies = new Set()
  for (const match of source.matchAll(importPattern)) {
    const resolved = resolveLocal(file, match[1] ?? match[2])
    if (resolved) dependencies.add(resolved)
  }
  graph.set(path.normalize(file), dependencies)
}

const reachableFrom = entries => {
  const reachable = new Set()
  const pending = entries.map(entry => path.normalize(entry))
  while (pending.length) {
    const current = pending.pop()
    if (!current || reachable.has(current)) continue
    reachable.add(current)
    for (const dependency of graph.get(current) ?? []) pending.push(dependency)
  }
  return reachable
}

const productionReachable = reachableFrom([productionEntry])
const testEntries = allSourceFiles.filter(file => /\.test\.(?:ts|tsx)$/.test(file))
const testReachable = reachableFrom(testEntries)
const relative = file => path.relative(frontendRoot, file).replaceAll('\\', '/')
const unreachable = allSourceFiles
  .filter(file => !/\.test\.(?:ts|tsx)$/.test(file))
  .filter(file => !productionReachable.has(path.normalize(file)))
  .map(file => ({
    file: relative(file),
    testOnly: testReachable.has(path.normalize(file)),
    vendor: relative(file).startsWith('src/character/live2d/framework/'),
  }))
  .sort((left, right) => left.file.localeCompare(right.file))
const unreachableBusiness = unreachable.filter(item => !item.vendor && !item.testOnly)

console.log(JSON.stringify({
  productionEntry: relative(productionEntry),
  sourceFiles: allSourceFiles.length,
  productionReachable: productionReachable.size,
  unreachableBusiness,
  unreachable,
}, null, 2))

if (process.argv.includes('--strict') && unreachableBusiness.length) process.exitCode = 1
