// Frontend logger — thin wrapper over console with timestamp + level prefix.
// Avoids pulling in a heavy logging library while still giving structured output.

type LogLevel = 'debug' | 'info' | 'warn' | 'error'

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
}

const CURRENT_LEVEL: LogLevel = (() => {
  try {
    const stored = localStorage.getItem('logLevel')
    if (stored && stored in LOG_LEVELS) return stored as LogLevel
  } catch { /* localStorage unavailable (SSR) */ }
  return import.meta.env.DEV ? 'debug' : 'warn'
})()

function formatTime(): string {
  const now = new Date()
  return now.toISOString().split('T')[1].replace('Z', '')
}

export interface Logger {
  debug: (msg: string, extra?: Record<string, unknown>) => void
  info: (msg: string, extra?: Record<string, unknown>) => void
  warn: (msg: string, extra?: Record<string, unknown>) => void
  error: (msg: string, extra?: Record<string, unknown>) => void
}

export function createLogger(name: string): Logger {
  function log(level: LogLevel, msg: string, extra?: Record<string, unknown>) {
    if (LOG_LEVELS[level] < LOG_LEVELS[CURRENT_LEVEL]) return
    const ts = formatTime()
    const prefix = `[${ts}] [${name}] ${level.toUpperCase()}`
    const payload = extra ? `${msg} ${JSON.stringify(extra)}` : msg
    switch (level) {
      case 'debug': console.debug(prefix, payload); break
      case 'info':  console.info(prefix, payload); break
      case 'warn':  console.warn(prefix, payload); break
      case 'error': console.error(prefix, payload); break
    }
  }

  return {
    debug: (m, e) => log('debug', m, e),
    info:  (m, e) => log('info', m, e),
    warn:  (m, e) => log('warn', m, e),
    error: (m, e) => log('error', m, e),
  }
}

// Global level control (exposed for DebugPanel)
export function setLogLevel(level: LogLevel) {
  try { localStorage.setItem('logLevel', level) } catch { /* noop */ }
  // Reload needed to take effect (avoids making the module mutable)
}
