export type RandomSource = () => number

/** Mulberry32: a small reproducible PRNG for animation scheduling and tests. */
export function createSeededRandom(seed: number): RandomSource {
  let state = normalizeSeed(seed)
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let value = state
    value = Math.imul(value ^ (value >>> 15), value | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 0x100000000
  }
}

export function normalizeSeed(seed: number): number {
  if (!Number.isFinite(seed)) return 1
  return (Math.abs(Math.floor(seed)) >>> 0) || 1
}
