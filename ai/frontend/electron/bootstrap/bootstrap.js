const capabilityHost = document.querySelector('#capabilities')
const serviceHost = document.querySelector('#services')
const summary = document.querySelector('#summary')
const availability = document.querySelector('#availability')
const errorHost = document.querySelector('#error')

function renderCards (host, items, detail = false) {
  host.replaceChildren(...items.map(item => {
    const card = document.createElement('div')
    card.className = 'card'
    const label = document.createElement('span')
    label.textContent = item.display_name || item.id || item.name
    const state = document.createElement('span')
    state.className = `state-${item.state || item.status}`
    state.textContent = item.state || item.status
    if (detail && item.provider) label.title = `Provider: ${item.provider}`
    card.append(label, state)
    return card
  }))
}

function render (snapshot) {
  const level = snapshot.availability || 'BLOCKED'
  availability.textContent = level
  summary.textContent = level === 'BLOCKED'
    ? '核心能力仍在启动；你可以查看下面的实时进度。'
    : level === 'TEXT_READY'
      ? '文字交流已可用，语音能力仍在加载。'
      : '角色能力已经就绪，正在进入舞台。'
  renderCards(capabilityHost, snapshot.capabilities || [])
  renderCards(serviceHost, snapshot.services || [], true)
}

window.electronAPI.onLifecycleSnapshot(render)
window.electronAPI.onLifecycleError(message => { errorHost.textContent = message })
document.querySelector('#retry').addEventListener('click', () => window.electronAPI.lifecycleCommand('restart'))
document.querySelector('#logs').addEventListener('click', () => window.electronAPI.openLogs())
window.electronAPI.getLifecycleSnapshot().then(render)
