import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createDiagnosticWavBytes,
  LipSyncDiagnosticProbe,
} from './diagnostic.ts'

test('diagnostic wave is a decodable mono PCM WAV with an audible signal', () => {
  const bytes = createDiagnosticWavBytes({ durationMs: 1200, sampleRate: 16_000 })
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const text = (offset: number, length: number) =>
    String.fromCharCode(...bytes.slice(offset, offset + length))

  assert.equal(text(0, 4), 'RIFF')
  assert.equal(text(8, 4), 'WAVE')
  assert.equal(view.getUint16(22, true), 1)
  assert.equal(view.getUint32(24, true), 16_000)
  assert.equal(view.getUint16(34, true), 16)
  assert.equal(view.getUint32(40, true), 19_200 * 2)

  let peak = 0
  for (let offset = 44; offset < bytes.byteLength; offset += 2) {
    peak = Math.max(peak, Math.abs(view.getInt16(offset, true)))
  }
  assert.ok(peak > 10_000)
})

test('diagnostic probe requires real volume, mouth response, and closed-mouth recovery', () => {
  const probe = new LipSyncDiagnosticProbe()
  probe.recordVolume(0.08)
  probe.recordMouth(0.42)
  probe.recordMouth(0.01)

  assert.deepEqual(probe.finish(), {
    passed: true,
    peakVolume: 0.08,
    peakMouth: 0.42,
    finalMouth: 0.01,
    volumeSamples: 1,
  })

  const silent = new LipSyncDiagnosticProbe()
  silent.recordMouth(0)
  assert.equal(silent.finish().passed, false)
})
