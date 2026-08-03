'use strict'

const http = require('node:http')
const https = require('node:https')

function probeUrl (url, timeoutMs = 1500) {
  const target = new URL(url)
  const transport = target.protocol === 'https:' ? https : http

  return new Promise(resolve => {
    let settled = false
    const finish = value => {
      if (settled) return
      settled = true
      resolve(value)
    }

    const request = transport.get(target, { timeout: timeoutMs }, response => {
      response.resume()
      finish(response.statusCode >= 200 && response.statusCode < 400)
    })
    request.on('timeout', () => {
      request.destroy()
      finish(false)
    })
    request.on('error', () => finish(false))
  })
}

async function waitForUrl (
  url,
  { intervalMs = 250, timeoutMs = 60_000, probe = probeUrl, shouldStop = () => false } = {},
) {
  const deadline = Date.now() + timeoutMs

  while (true) {
    if (shouldStop()) return null
    try {
      if (await probe(url)) return true
    } catch (_) {
      // A malformed or temporarily unavailable endpoint belongs to the same
      // bounded degraded-start path as a refused connection.
    }

    const remaining = deadline - Date.now()
    if (remaining <= 0) return false
    await new Promise(resolve => setTimeout(resolve, Math.min(intervalMs, remaining)))
  }
}

module.exports = { probeUrl, waitForUrl }
