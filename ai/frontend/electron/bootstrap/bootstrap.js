const summary = document.querySelector('#summary')
const progressBar = document.querySelector('#progress-bar')
const errorHost = document.querySelector('#error')
const actions = document.querySelector('#actions')
const detail = document.querySelector('#detail')
const detailBody = document.querySelector('#detail-body')

const svcLabel = { ready: '就绪', warming: '启动中', failed: '失败', blocked: '等待', unavailable: '不可用' }
const svcClass = s => `s-${s}`
const serviceStatus = svc => svc.status || svc.state || 'unavailable'

function renderServiceRows(services) {
  detailBody.replaceChildren(...(services || []).map(svc => {
    const row = document.createElement('div')
    const currentStatus = serviceStatus(svc)
    row.className = 'svc-row ' + svcClass(currentStatus)
    const name = document.createElement('span')
    name.className = 'n'
    name.textContent = svc.display_name || svc.id || svc.name
    const state = document.createElement('span')
    state.className = 's'
    state.textContent = svcLabel[currentStatus] || currentStatus
    row.append(name, state)
    return row
  }))
}

function render(snapshot) {
  const level = snapshot.availability || 'BLOCKED'
  const caps = snapshot.capabilities || []

  // Remove loading animation once we have data
  summary.classList.remove('loading')

  if (level === 'BLOCKED') {
    summary.textContent = '正在启动服务…'
  } else if (level === 'TEXT_READY') {
    summary.textContent = '文字模式已就绪，语音加载中…'
  } else if (level === 'FULL_READY') {
    summary.textContent = '正在进入…'
  } else {
    summary.textContent = level
  }

  // Progress bar
  const ready = caps.filter(c => c.state === 'ready').length
  const total = caps.length
  const pct = total > 0 ? (ready / total) * 100 : 8
  progressBar.style.width = Math.max(8, Math.min(100, pct)) + '%'

  // Error display
  const hasErr = caps.some(c => c.state === 'failed')
  const detailSvc = snapshot.services || []
  const hasSvcErr = detailSvc.some(s => serviceStatus(s) === 'failed')

  if (hasErr || hasSvcErr) {
    errorHost.style.display = 'block'
    errorHost.textContent = '部分服务启动失败'
    actions.style.display = 'flex'
  } else if (level === 'FULL_READY') {
    errorHost.style.display = 'none'
    actions.style.display = 'none'
  } else {
    errorHost.style.display = 'none'
    actions.style.display = 'none'
  }

  // Detail panel
  if (detailSvc.length > 0) {
    renderServiceRows(detailSvc)
  }
}

// Wire up events
window.electronAPI.onLifecycleSnapshot(render)
window.electronAPI.onLifecycleError(msg => {
  summary.classList.remove('loading')
  summary.textContent = '启动失败'
  errorHost.style.display = 'block'
  errorHost.textContent = msg
  actions.style.display = 'flex'
})
document.querySelector('#retry').addEventListener('click', () => window.electronAPI.lifecycleCommand('restart'))
document.querySelector('#logs').addEventListener('click', () => window.electronAPI.openLogs())

// Initial load
window.electronAPI.getLifecycleSnapshot().then(snapshot => {
  if (snapshot) render(snapshot)
})
