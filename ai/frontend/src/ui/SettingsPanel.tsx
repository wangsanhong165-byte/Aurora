import { useEffect, useRef, useState } from 'react'
import { Info, Palette, Settings2, type LucideIcon } from 'lucide-react'
import { theme } from '../core/theme'
import type { AppSettings } from '../core/store'
import { electronWindowBridge } from '../session/electron-window-bridge'
import { eventBus, type EventMap } from '../core/event-bus'
import {
  normalizeLive2DPerformanceSettings,
  readModelPerformanceDefaults,
  type Live2DPerformanceSettings,
} from '../character/Live2DPerformanceSettings'
import { Live2DActionStudio } from './Live2DActionStudio'

export interface SettingsPanelProps {
  open: boolean
  onClose: () => void
  embedded?: boolean
  settings: AppSettings
  onSettingChange: (key: string, value: unknown) => void
  /** Accessory parts: label -> partId */
  accessoryParts?: Record<string, string>
  /** Current accessory state: label -> enabled */
  accessoryState?: Record<string, boolean>
  /** Called when user toggles an accessory */
  onAccessoryToggle?: (label: string) => void
}

const LIVE2D_TOGGLES = [
  { key: 'live2dBlink' as const, label: '自动眨眼', desc: '根据模型能力自然控制双眼' },
  { key: 'live2dBreathe' as const, label: '呼吸微动', desc: '身体起伏与轻微摇摆' },
  { key: 'live2dLipSync' as const, label: '实时口型', desc: '按真实音频包络驱动开口' },
  { key: 'live2dHeadTracking' as const, label: '头部跟随', desc: '头部和视线跟随光标' },
  { key: 'live2dExpression' as const, label: '表情系统', desc: '使用模型原生表情并平滑混合' },
  { key: 'live2dIdle' as const, label: '待机动画', desc: '连续微动、呼吸与随机凝视' },
  { key: 'live2dClickFeedback' as const, label: '点击反馈', desc: '点击或拖动模型时触发互动回应' },
]

const CALIBRATION_CONTROLS = [
  { logical: 'head.x', label: '头部左右', min: -20, max: 20, step: .5 },
  { logical: 'head.y', label: '头部俯仰', min: -16, max: 16, step: .5 },
  { logical: 'head.z', label: '头部倾斜', min: -14, max: 14, step: .5 },
  { logical: 'body.x', label: '身体左右', min: -9, max: 9, step: .25 },
  { logical: 'body.y', label: '身体俯仰', min: -7, max: 7, step: .25 },
  { logical: 'eye.x', label: '视线左右', min: -1, max: 1, step: .05 },
  { logical: 'eye.y', label: '视线上下', min: -1, max: 1, step: .05 },
  { logical: 'mouth.open', label: '嘴巴张合', min: 0, max: 1, step: .05 },
  { logical: 'mouth.form', label: '嘴型变化', min: -1, max: 1, step: .05 },
] as const

type TabId = 'general' | 'appearance' | 'about'

interface TabDef {
  id: TabId
  label: string
  icon: LucideIcon
}

const TABS: TabDef[] = [
  { id: 'general', label: 'General', icon: Settings2 },
  { id: 'appearance', label: 'Appearance', icon: Palette },
  { id: 'about', label: 'About', icon: Info },
]

const TAB_LABELS: Record<TabId, string> = {
  general: '常规',
  appearance: '装扮',
  about: '关于',
}

const isElectron = electronWindowBridge.available

export function SettingsPanel({
  open,
  onClose,
  embedded = false,
  settings,
  onSettingChange,
  accessoryParts,
  accessoryState,
  onAccessoryToggle,
}: SettingsPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('general')

  if (!open) return null

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose()
    }
  }

  const panel = (
      <div style={embedded ? styles.embedded : styles.modal}>
        <div style={styles.header}>
          <span style={styles.title}>设置</span>
          {!embedded && <button type="button" style={styles.closeBtn} onClick={onClose}>&times;</button>}
        </div>

        <div style={styles.body}>
          {/* Tab sidebar */}
          <div style={styles.tabBar}>
            {TABS.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.id}
                  type="button"
                  aria-label={TAB_LABELS[tab.id]}
                  title={TAB_LABELS[tab.id]}
                  style={{
                    ...styles.tabBtn,
                    backgroundColor: activeTab === tab.id ? theme.colors.bg.surface : 'transparent',
                    borderLeft: activeTab === tab.id ? `2px solid ${theme.colors.accent}` : '2px solid transparent',
                  }}
                  onClick={() => setActiveTab(tab.id)}
                >
                  <Icon style={styles.tabIcon} aria-hidden="true" />
                </button>
              )
            })}
          </div>

          {/* Tab content */}
          <div style={styles.content}>
            {activeTab === 'general' && (
              <GeneralTab settings={settings} onSettingChange={onSettingChange} />
            )}
            {activeTab === 'appearance' && (
              <AppearanceTab
                accessoryParts={accessoryParts}
                accessoryState={accessoryState}
                onAccessoryToggle={onAccessoryToggle}
              />
            )}
            {activeTab === 'about' && <AboutTab />}
          </div>
        </div>
      </div>
  )

  if (embedded) return panel

  return (
    <div style={styles.overlay} onClick={handleOverlayClick}>
      {panel}
    </div>
  )
}

export function Live2DWorkbench({
  settings,
  onSettingChange,
}: Pick<SettingsPanelProps, 'settings' | 'onSettingChange'>) {
  return (
    <div style={{ ...styles.content, height: '100%', boxSizing: 'border-box' }}>
      <AnimationTab settings={settings} onSettingChange={onSettingChange} />
    </div>
  )
}

// ── Tab: General ──

function GeneralTab({ settings, onSettingChange }: {
  settings: AppSettings
  onSettingChange: (key: string, value: unknown) => void
}) {
  const characters = [{ id: settings.activeCharacterId, label: settings.activeCharacterId }]
  const [models, setModels] = useState<string[]>([settings.live2dModel])
  useEffect(() => {
    void fetch('/api/models')
      .then(response => response.ok ? response.json() : Promise.reject(new Error('models unavailable')))
      .then((body: { models?: Array<{ name?: string }> }) => {
        const names = (body.models ?? []).map(model => String(model.name || '')).filter(Boolean)
        setModels(Array.from(new Set([settings.live2dModel, ...names])))
      })
      .catch(() => {})
  }, [settings.live2dModel])

  return (
    <div style={styles.tabContent}>
      <div style={styles.sectionLabel}>Character</div>

      <SettingRow label="Character">
        <select
          style={styles.select}
          value={settings.activeCharacterId}
          onChange={(e) => onSettingChange('activeCharacterId', e.target.value)}
        >
          {characters.map((c) => (
            <option key={c.id} value={c.id}>{c.label}</option>
          ))}
        </select>
      </SettingRow>

      <SettingRow label="Live2D Model">
        <select
          style={styles.select}
          value={settings.live2dModel}
          onChange={(e) => onSettingChange('live2dModel', e.target.value)}
        >
          {models.map((model) => (
            <option key={model} value={model}>{model}</option>
          ))}
        </select>
      </SettingRow>

      <div style={styles.divider} />
      <div style={styles.sectionLabel}>Window</div>

      <SettingRow label="Window Mode" desc="Pet mode removes window frame">
        <select
          style={styles.select}
          value={settings.windowMode}
          onChange={(e) => onSettingChange('windowMode', e.target.value as 'window' | 'pet')}
        >
          <option value="window">Window</option>
          <option value="pet">Pet</option>
        </select>
      </SettingRow>

      <SettingRow label="Always on Top" desc={isElectron ? '' : 'Desktop app only'}>
        <Toggle
          checked={settings.alwaysOnTop}
          disabled={!isElectron}
          onChange={(v) => onSettingChange('alwaysOnTop', v)}
        />
      </SettingRow>

      <div style={styles.divider} />
      <div style={styles.sectionLabel}>Interaction</div>

      <SettingRow label="Proactive Mode" desc="AI initiates conversation">
        <Toggle
          checked={settings.proactive}
          onChange={(v) => onSettingChange('proactive', v)}
        />
      </SettingRow>
      {settings.proactive && (
        <div style={styles.proactiveIdleRow}>
          <span style={styles.proactiveIdleLabel}>Idle time:</span>
          <input
            type="number"
            min="10"
            max="3600"
            step="10"
            value={settings.proactiveIdleTime}
            onChange={(e) => {
              const v = parseInt(e.target.value, 10)
              if (!isNaN(v) && v >= 10) onSettingChange('proactiveIdleTime', v)
            }}
            style={{
              width: 72,
              padding: '3px 8px',
              borderRadius: 4,
              border: `1px solid ${theme.colors.border}`,
              backgroundColor: theme.colors.bg.surface,
              color: theme.colors.text.primary,
              fontSize: '0.75rem',
              outline: 'none',
            }}
          />
        </div>
      )}

      <SettingRow label="Voice Input" desc="Enable microphone for voice chat">
        <Toggle
          checked={settings.voiceInputEnabled}
          onChange={(v) => onSettingChange('voiceInputEnabled', v)}
        />
      </SettingRow>
    </div>
  )
}

// ── Tab: Animation ──

function AnimationTab({ settings, onSettingChange }: {
  settings: AppSettings
  onSettingChange: (key: string, value: unknown) => void
}) {
  const [calibrating, setCalibrating] = useState(false)
  const [calibrationValues, setCalibrationValues] = useState<Record<string, number>>({})
  const [audioDiagnostic, setAudioDiagnostic] = useState<{
    requestId: string
    phase: 'idle' | 'running' | 'passed' | 'failed'
    message: string
    peakVolume?: number
    peakMouth?: number
    finalMouth?: number
  }>({ requestId: '', phase: 'idle', message: '使用真实 AudioContext 验证播放、口型与中断闭嘴。' })
  const fallback = readModelPerformanceDefaults(settings.live2dModel)
  const tuning = normalizeLive2DPerformanceSettings(
    settings.live2dPerformanceProfiles?.[settings.live2dModel],
    fallback,
  )
  const tuningRef = useRef(tuning)
  tuningRef.current = tuning

  useEffect(() => {
    setCalibrating(false)
    setCalibrationValues({})
    eventBus.emit('character:calibration_override', { clear: true })
  }, [settings.live2dModel])

  useEffect(() => () => {
    eventBus.emit('character:calibration_override', { clear: true })
    eventBus.emit('character:performance_tuning', tuningRef.current)
  }, [])

  useEffect(() => eventBus.on('audio:diagnostic.result', result => {
    setAudioDiagnostic(current => (
      !current.requestId || current.requestId === result.requestId
        ? { ...result }
        : current
    ))
  }), [])

  const updateTuning = (patch: Partial<Live2DPerformanceSettings>) => {
    const currentProfiles = settings.live2dPerformanceProfiles ?? {}
    onSettingChange('live2dPerformanceProfiles', {
      ...currentProfiles,
      [settings.live2dModel]: { ...tuning, ...patch },
    })
  }

  const toggleCalibration = () => {
    const next = !calibrating
    setCalibrating(next)
    setCalibrationValues({})
    eventBus.emit('character:calibration_override', { clear: true })
    eventBus.emit('character:performance_tuning', next ? { mode: 'calibration' } : tuning)
  }

  return (
    <div style={styles.tabContent}>
      <div style={styles.heroCard}>
        <div>
          <div style={styles.heroTitle}>Live2D 表现工作台</div>
          <div style={styles.heroDesc}>
            当前模型：{settings.live2dModel}
          </div>
        </div>
        <span style={styles.profileBadge}>模型独立配置</span>
      </div>

      <div style={styles.sectionLabel}>基础组件</div>
      <div style={styles.sectionDesc}>模型不支持的参数会由能力配置自动过滤。</div>

      <div style={styles.toggleCards}>
        {LIVE2D_TOGGLES.map(({ key, label, desc }) => (
          <div key={key} style={styles.toggleCard}>
            <div style={styles.toggleCardInfo}>
              <span style={styles.toggleCardLabel}>{label}</span>
              <span style={styles.toggleCardDesc}>{desc}</span>
            </div>
            <Toggle
              checked={settings[key]}
              onChange={(v) => onSettingChange(key, v)}
            />
          </div>
        ))}
      </div>

      <div style={styles.sectionDivider} />
      <div style={styles.sectionLabel}>表现强度</div>
      <div style={styles.sectionDesc}>按模型保存；增强模式启用连续微动和语义动作。</div>

      <div style={styles.controlCard}>
        <SettingRow label="表现模式" desc="兼容模式只保留旧控制链">
          <select
            style={styles.select}
            value={tuning.mode === 'legacy' ? 'legacy' : 'enhanced'}
            onChange={(event) => updateTuning({
              mode: event.target.value === 'legacy' ? 'legacy' : 'enhanced',
            })}
          >
            <option value="enhanced">自然增强</option>
            <option value="legacy">兼容模式</option>
          </select>
        </SettingRow>
        <RangeSetting
          label="整体动作"
          value={tuning.parameterGain}
          min={0.8}
          max={2.2}
          step={0.05}
          onChange={(parameterGain) => updateTuning({ parameterGain })}
        />
        <RangeSetting
          label="身体动作"
          value={tuning.bodyMotionGain}
          min={0.6}
          max={2}
          step={0.05}
          onChange={(bodyMotionGain) => updateTuning({ bodyMotionGain })}
        />
        <button
          type="button"
          style={styles.textButton}
          onClick={() => {
            const profiles = { ...(settings.live2dPerformanceProfiles ?? {}) }
            delete profiles[settings.live2dModel]
            onSettingChange('live2dPerformanceProfiles', profiles)
          }}
        >
          恢复该模型默认值
        </button>
        <button
          type="button"
          style={styles.textButton}
          onClick={() => eventBus.emit('character:viewport_reset', undefined)}
        >
          恢复模型默认构图
        </button>
      </div>

      <div style={styles.sectionDivider} />
      <div style={styles.sectionLabel}>快速试演</div>
      <div style={styles.buttonGrid}>
        {(['happy', 'sad', 'angry', 'surprised', 'shy', 'neutral'] as const).map(emotion => (
          <button
            type="button"
            key={emotion}
            style={styles.previewButton}
            onClick={() => eventBus.emit('character:intent', {
              emotion,
              behavior: 'react',
              intensity: 0.85,
            })}
          >
            {emotion}
          </button>
        ))}
        <button
          type="button"
          style={styles.previewButton}
          onClick={() => eventBus.emit('character:interaction', {
            type: 'touch',
            region: 'head',
            intensity: 0.8,
          })}
        >
          触摸反应
        </button>
      </div>

      <Live2DActionStudio
        model={settings.live2dModel}
        actionsByModel={settings.live2dActions ?? {}}
        onChange={actions => onSettingChange('live2dActions', actions)}
      />

      <Live2DRuntimeMonitor model={settings.live2dModel} />

      <div style={styles.controlCard}>
        <div style={styles.calibrationHeader}>
          <div>
            <div style={styles.cardTitle}>真实口型诊断</div>
            <div style={styles.cardDesc}>{audioDiagnostic.message}</div>
          </div>
          <button
            type="button"
            disabled={audioDiagnostic.phase === 'running'}
            style={{
              ...styles.calibrationButton,
              opacity: audioDiagnostic.phase === 'running' ? 0.6 : 1,
              backgroundColor: audioDiagnostic.phase === 'passed'
                ? '#246b4a'
                : audioDiagnostic.phase === 'failed'
                  ? '#7a3542'
                  : theme.colors.bg.surface,
            }}
            onClick={() => {
              const requestId = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
              setAudioDiagnostic({
                requestId,
                phase: 'running',
                message: '正在启动浏览器音频……',
              })
              eventBus.emit('audio:diagnostic.request', { requestId })
            }}
          >
            {audioDiagnostic.phase === 'running' ? '诊断中…' : '开始诊断'}
          </button>
        </div>
        {(audioDiagnostic.phase === 'passed' || audioDiagnostic.phase === 'failed') && (
          <div style={styles.sectionDesc}>
            音量峰值 {audioDiagnostic.peakVolume?.toFixed(3) ?? '—'} ·
            开口峰值 {audioDiagnostic.peakMouth?.toFixed(3) ?? '—'} ·
            结束嘴型 {audioDiagnostic.finalMouth?.toFixed(3) ?? '—'}
          </div>
        )}
      </div>

      <div style={styles.sectionDivider} />
      <div style={styles.calibrationCard}>
        <div style={styles.calibrationHeader}>
          <div>
            <div style={styles.cardTitle}>参数校准实验室</div>
            <div style={styles.cardDesc}>即时检查映射；离开页面后自动恢复，不写入模型文件。</div>
          </div>
          <button
            type="button"
            style={{
              ...styles.calibrationButton,
              backgroundColor: calibrating ? theme.colors.accent : theme.colors.bg.surface,
            }}
            onClick={toggleCalibration}
          >
            {calibrating ? '结束校准' : '开始校准'}
          </button>
        </div>
        {calibrating && (
          <div style={styles.calibrationGrid}>
            {CALIBRATION_CONTROLS.map(control => {
              const value = calibrationValues[control.logical] ?? 0
              return (
                <RangeSetting
                  key={control.logical}
                  label={control.label}
                  value={value}
                  min={control.min}
                  max={control.max}
                  step={control.step}
                  onChange={(next) => {
                    setCalibrationValues(current => ({ ...current, [control.logical]: next }))
                    eventBus.emit('character:calibration_override', {
                      logicalParameter: control.logical,
                      value: next,
                    })
                  }}
                />
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function Live2DRuntimeMonitor({ model }: { model: string }) {
  const [snapshot, setSnapshot] = useState<EventMap['character:performance_debug'] | null>(null)
  const [capability, setCapability] = useState<EventMap['character:model_capability'] | null>(null)
  const [probeId, setProbeId] = useState('')
  const [probeValue, setProbeValue] = useState(0)
  const [partProbeId, setPartProbeId] = useState('')
  const [partProbeOpacity, setPartProbeOpacity] = useState(1)

  useEffect(() => eventBus.on('character:performance_debug', setSnapshot), [])
  useEffect(() => {
    const dispose = eventBus.on('character:model_capability', next => {
      if (next.model === model) setCapability(next)
    })
    eventBus.emit('character:model_capability_request', undefined)
    return dispose
  }, [model])
  useEffect(() => () => {
    eventBus.emit('character:parameter_probe', { clear: true })
    eventBus.emit('character:part_probe', { clear: true })
  }, [])

  const frame = snapshot?.frame
  const fps = frame?.averageIntervalMs ? 1000 / frame.averageIntervalMs : 0
  const contested = snapshot ? Object.keys(snapshot.contestedParameters).length : 0
  const motion = String(snapshot?.motion.motion ?? 'idle')
  const coverage = (snapshot?.profileCoverage.coverage ?? 0) * 100
  const probe = capability?.parameters.find(parameter => parameter.id === probeId)
  const partProbe = capability?.parts.find(part => part.id === partProbeId)
  const resolved = snapshot?.resolvedParameters ?? {}
  const formatControl = (x: number | undefined, y: number | undefined) => (
    x === undefined && y === undefined ? '—' : `${(x ?? 0).toFixed(2)} / ${(y ?? 0).toFixed(2)}`
  )

  return (
    <div style={styles.runtimeMonitor}>
      <div style={styles.calibrationHeader}>
        <div>
          <div style={styles.cardTitle}>实时表现监控</div>
          <div style={styles.cardDesc}>逐帧采样控制、物理与渲染；界面以 4 Hz 汇总，不干扰动画循环。</div>
        </div>
        <span style={{ ...styles.profileBadge, color: frame && frame.longFrameCount === 0 ? '#77d6a0' : theme.colors.accent }}>
          {frame ? `${fps.toFixed(0)} FPS` : '等待模型'}
        </span>
      </div>
      <div style={styles.metricGrid}>
        <RuntimeMetric label="帧间隔 P95" value={frame ? `${frame.p95IntervalMs.toFixed(1)} ms` : '—'} />
        <RuntimeMetric label="单帧工作" value={frame ? `${frame.workMs.toFixed(1)} ms` : '—'} />
        <RuntimeMetric label="控制 / 物理" value={frame ? `${frame.controllerMs.toFixed(1)} / ${frame.modelMs.toFixed(1)} ms` : '—'} />
        <RuntimeMetric label="渲染" value={frame ? `${frame.renderMs.toFixed(1)} ms` : '—'} />
        <RuntimeMetric label="长帧 (>33ms)" value={frame ? String(frame.longFrameCount) : '—'} />
        <RuntimeMetric label="参数覆盖" value={snapshot ? `${coverage.toFixed(0)}%` : '—'} />
        <RuntimeMetric label="参数冲突" value={snapshot ? String(contested) : '—'} />
        <RuntimeMetric label="模型参数" value={capability ? String(capability.parameters.length) : '—'} />
        <RuntimeMetric label="模型部件" value={capability ? String(capability.parts.length) : '—'} />
      </div>
      <div style={styles.runtimeLine}>
        <span>动作：{motion}</span>
        <span>占用通道：{snapshot?.activeChannels.join(', ') || '无'}</span>
        <span>表情：{snapshot?.expression.name || 'neutral'}</span>
        <span>眼球 X/Y：{formatControl(resolved.ParamEyeBallX, resolved.ParamEyeBallY)}</span>
        <span>头部 X/Y：{formatControl(resolved.ParamAngleX, resolved.ParamAngleY)}</span>
      </div>
      {snapshot && contested > 0 && (
        <details style={styles.parameterCatalog}>
          <summary style={styles.parameterSummary}>查看参数所有权冲突（{contested}）</summary>
          <div style={styles.conflictList}>
            {Object.entries(snapshot.contestedParameters).slice(0, 12).map(([parameterId, owners]) => (
              <div key={parameterId}>
                <strong>{parameterId}</strong>：{owners
                  .map(owner => `${owner.source}@${owner.priority}=${owner.value.toFixed(2)}`)
                  .join('；')}
              </div>
            ))}
          </div>
        </details>
      )}
      {capability && (
        <details style={styles.parameterCatalog}>
          <summary style={styles.parameterSummary}>模型参数目录（{capability.parameters.length}）</summary>
          <div style={styles.parameterList}>
            {capability.parameters.map(parameter => (
              <button
                type="button"
                key={parameter.id}
                title={`${parameter.minimum} … ${parameter.maximum}; default ${parameter.defaultValue}`}
                style={{ ...styles.parameterChip, borderColor: probeId === parameter.id ? theme.colors.accent : theme.colors.border }}
                onClick={() => {
                  setProbeId(parameter.id)
                  setProbeValue(parameter.value)
                }}
              >
                {parameter.displayName ? `${parameter.displayName} · ` : ''}{parameter.id}
              </button>
            ))}
          </div>
          <div style={styles.runtimeLine}>
            {capability.parts
              .filter(part => /尾|tail|尻|しっぽ/i.test(`${part.displayName ?? ''} ${part.id}`))
              .map(part => (
                <span key={part.id}>{part.displayName || part.id}：opacity {part.opacity.toFixed(2)}</span>
              ))}
          </div>
          {probe && (
            <div style={styles.probeControl}>
              <div style={styles.cardDesc}>探针仍通过统一混合器写入；物理输出参数可能在同一帧被模型物理层接管。</div>
              <RangeSetting
                label={probe.displayName || probe.id}
                value={probeValue}
                min={probe.minimum}
                max={probe.maximum}
                step={Math.max(0.001, (probe.maximum - probe.minimum) / 100)}
                onChange={value => {
                  setProbeValue(value)
                  eventBus.emit('character:parameter_probe', { parameterId: probe.id, value })
                }}
              />
              <input
                aria-label="参数探针精确值"
                type="number"
                min={probe.minimum}
                max={probe.maximum}
                step={Math.max(0.001, (probe.maximum - probe.minimum) / 100)}
                value={probeValue}
                style={styles.probeNumber}
                onChange={event => {
                  const value = Number(event.target.value)
                  if (!Number.isFinite(value)) return
                  setProbeValue(value)
                  eventBus.emit('character:parameter_probe', { parameterId: probe.id, value })
                }}
              />
              <button
                type="button"
                style={styles.textButton}
                onClick={() => {
                  eventBus.emit('character:parameter_probe', { clear: true })
                  setProbeId('')
                }}
              >
                清除参数探针
              </button>
            </div>
          )}
        </details>
      )}
      {capability && (
        <details style={styles.parameterCatalog}>
          <summary style={styles.parameterSummary}>模型部件目录（{capability.parts.length}）</summary>
          <div style={styles.parameterList}>
            {capability.parts.map(part => (
              <button
                type="button"
                key={part.id}
                title={`baseline opacity ${part.opacity}; parent ${part.parentIndex}`}
                style={{ ...styles.parameterChip, borderColor: partProbeId === part.id ? theme.colors.accent : theme.colors.border }}
                onClick={() => {
                  setPartProbeId(part.id)
                  setPartProbeOpacity(part.opacity)
                }}
              >
                {part.displayName ? `${part.displayName} · ` : ''}{part.id}
              </button>
            ))}
          </div>
          {partProbe && (
            <div style={styles.probeControl}>
              <RangeSetting
                label={partProbe.displayName || partProbe.id}
                value={partProbeOpacity}
                min={0}
                max={1}
                step={0.01}
                onChange={opacity => {
                  setPartProbeOpacity(opacity)
                  eventBus.emit('character:part_probe', { partId: partProbe.id, opacity })
                }}
              />
              <button
                type="button"
                style={styles.textButton}
                onClick={() => {
                  eventBus.emit('character:part_probe', { clear: true })
                  setPartProbeId('')
                }}
              >
                清除全部部件探针
              </button>
            </div>
          )}
        </details>
      )}
    </div>
  )
}

function RuntimeMetric({ label, value }: { label: string; value: string }) {
  return (
    <div style={styles.metricItem}>
      <span style={styles.metricLabel}>{label}</span>
      <span style={styles.metricValue}>{value}</span>
    </div>
  )
}

// ── Tab: Appearance (Accessories) ──

function AppearanceTab({
  accessoryParts,
  accessoryState,
  onAccessoryToggle,
}: {
  accessoryParts?: Record<string, string>
  accessoryState?: Record<string, boolean>
  onAccessoryToggle?: (label: string) => void
}) {
  const parts = accessoryParts ? Object.keys(accessoryParts) : []

  if (parts.length === 0) {
    return (
      <div style={styles.tabContent}>
        <div style={styles.sectionLabel}>Accessories</div>
        <div style={styles.emptyState}>No accessories available for this model</div>
      </div>
    )
  }

  return (
    <div style={styles.tabContent}>
      <div style={styles.sectionLabel}>Accessories</div>
      <div style={styles.sectionDesc}>Toggle model accessories on/off</div>

      <div style={styles.toggleCards}>
        {parts.map((label) => (
          <div key={label} style={styles.toggleCard}>
            <div style={styles.toggleCardInfo}>
              <span style={styles.toggleCardLabel}>{label}</span>
            </div>
            <Toggle
              checked={accessoryState?.[label] ?? true}
              onChange={() => onAccessoryToggle?.(label)}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Tab: About ──

function AboutTab() {
  return (
    <div style={styles.tabContent}>
      <div style={styles.sectionLabel}>Monika Companion</div>
      <div style={styles.aboutDesc}>
        A virtual companion powered by AI with Live2D character rendering.
      </div>
      <div style={styles.divider} />
      <div style={styles.aboutRow}>
        <span style={styles.aboutKey}>Version</span>
        <span style={styles.aboutValue}>0.1.0</span>
      </div>
      <div style={styles.aboutRow}>
        <span style={styles.aboutKey}>Renderer</span>
        <span style={styles.aboutValue}>Live2D Cubism 4</span>
      </div>
      <div style={styles.aboutRow}>
        <span style={styles.aboutKey}>Engine</span>
        <span style={styles.aboutValue}>WebGL</span>
      </div>
    </div>
  )
}

// ── Shared components ──

function SettingRow({ label, desc, children }: {
  label: string
  desc?: string
  children: React.ReactNode
}) {
  return (
    <div style={styles.settingRow}>
      <div style={styles.settingInfo}>
        <span style={styles.settingLabel}>{label}</span>
        {desc && <span style={styles.settingDesc}>{desc}</span>}
      </div>
      {children}
    </div>
  )
}

function RangeSetting({ label, value, min, max, step, onChange }: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <label style={styles.rangeRow}>
      <span style={styles.rangeLabel}>{label}</span>
      <input
        aria-label={label}
        style={styles.rangeInput}
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <span style={styles.rangeValue}>{value.toFixed(2)}</span>
    </label>
  )
}

function Toggle({ checked, disabled, onChange }: {
  checked: boolean
  disabled?: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label style={{ ...styles.toggleWrap, opacity: disabled ? 0.4 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }}>
      <input
        type="checkbox"
        style={styles.toggleInput}
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span style={{
        ...styles.toggleTrack,
        backgroundColor: checked ? theme.colors.accent : theme.colors.border,
      }}>
        <span style={{
          ...styles.toggleThumb,
          transform: checked ? 'translateX(18px)' : 'translateX(2px)',
        }} />
      </span>
    </label>
  )
}

// ── Styles ──

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', inset: 0, backgroundColor: 'rgba(0, 0, 0, 0.6)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: theme.zIndex.modal,
  },
  modal: {
    width: 560, maxWidth: '95vw', maxHeight: '85vh',
    backgroundColor: theme.colors.bg.root, border: `1px solid ${theme.colors.border}`,
    borderRadius: theme.radius.lg, display: 'flex', flexDirection: 'column', overflow: 'hidden',
    boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5)',
  },
  embedded: {
    width: '100%',
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    backgroundColor: theme.colors.bg.root,
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: `${theme.spacing.lg}px ${theme.spacing.xl}px`,
    borderBottom: `1px solid ${theme.colors.border}`, flexShrink: 0,
  },
  title: { fontSize: theme.fontSize.lg, fontWeight: theme.fontWeight.semibold, color: theme.colors.text.primary },
  closeBtn: {
    width: 30, height: 30, borderRadius: theme.radius.sm, border: 'none',
    backgroundColor: 'transparent', color: theme.colors.text.secondary,
    fontSize: '1.3rem', cursor: 'pointer', display: 'flex', alignItems: 'center',
    justifyContent: 'center', lineHeight: 1, padding: 0,
  },
  body: {
    display: 'flex', flex: 1, overflow: 'hidden',
  },

  // ── Tab bar (left sidebar) ──
  tabBar: {
    width: 52, flexShrink: 0, display: 'flex', flexDirection: 'column',
    padding: `${theme.spacing.sm}px 0`, gap: 2,
    borderRight: `1px solid ${theme.colors.border}`,
    backgroundColor: theme.colors.bg.surface,
  },
  tabBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    width: '100%', minHeight: 40, padding: '8px 0', border: 'none', cursor: 'pointer',
    color: theme.colors.text.secondary, transition: 'background-color 0.1s',
  },
  tabIcon: { width: 17, height: 17, flexShrink: 0 },

  // ── Content area ──
  content: {
    flex: 1, overflowY: 'auto', padding: `${theme.spacing.lg}px ${theme.spacing.lg}px`,
  },
  tabContent: {
    display: 'flex', flexDirection: 'column', gap: theme.spacing.md,
  },

  // ── Section labels ──
  sectionLabel: {
    fontSize: theme.fontSize.xs, fontWeight: theme.fontWeight.semibold,
    color: theme.colors.text.muted, textTransform: 'uppercase' as const,
    letterSpacing: '0.08em', marginTop: theme.spacing.xs,
  },
  sectionDesc: {
    fontSize: theme.fontSize.xs, color: theme.colors.text.muted,
    marginTop: -theme.spacing.sm,
  },
  divider: {
    height: 1, backgroundColor: theme.colors.border,
    margin: `${theme.spacing.xs}px 0`,
  },
  emptyState: {
    fontSize: theme.fontSize.sm, color: theme.colors.text.muted,
    padding: `${theme.spacing.xl}px 0`, textAlign: 'center' as const,
  },

  // ── Setting row ──
  settingRow: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: theme.spacing.lg, minHeight: 36,
  },
  settingInfo: { display: 'flex', flexDirection: 'column', gap: 1 },
  settingLabel: { fontSize: theme.fontSize.md, fontWeight: theme.fontWeight.medium, color: theme.colors.text.primary },
  settingDesc: { fontSize: theme.fontSize.xs, color: theme.colors.text.muted, marginTop: 1 },
  select: {
    padding: `${theme.spacing.xs}px ${theme.spacing.md}px`, borderRadius: theme.radius.md,
    border: `1px solid ${theme.colors.border}`, backgroundColor: theme.colors.bg.surface,
    color: theme.colors.text.primary, fontSize: theme.fontSize.sm, outline: 'none',
    cursor: 'pointer', minWidth: 96, flexShrink: 0,
  },

  // ── Toggle cards ──
  toggleCards: {
    display: 'flex', flexDirection: 'column', gap: theme.spacing.xs,
  },
  toggleCard: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: `${theme.spacing.sm}px ${theme.spacing.md}px`,
    backgroundColor: theme.colors.bg.surface,
    borderRadius: theme.radius.md,
    border: `1px solid ${theme.colors.border}`,
    gap: theme.spacing.md,
  },
  toggleCardInfo: {
    display: 'flex', flexDirection: 'column', gap: 1, flex: 1,
  },
  toggleCardLabel: {
    fontSize: theme.fontSize.sm, fontWeight: theme.fontWeight.medium,
    color: theme.colors.text.primary,
  },
  toggleCardDesc: {
    fontSize: theme.fontSize.xs, color: theme.colors.text.muted,
  },
  heroCard: {
    display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: theme.spacing.sm,
    padding: theme.spacing.md, borderRadius: theme.radius.md,
    background: `linear-gradient(135deg, ${theme.colors.bg.surface}, rgba(127, 99, 255, 0.12))`,
    border: `1px solid ${theme.colors.border}`,
  },
  heroTitle: {
    color: theme.colors.text.primary, fontSize: theme.fontSize.md,
    fontWeight: theme.fontWeight.semibold,
  },
  heroDesc: { color: theme.colors.text.muted, fontSize: theme.fontSize.xs, marginTop: 3 },
  profileBadge: {
    padding: '3px 7px', borderRadius: 999, whiteSpace: 'nowrap',
    color: theme.colors.accent, border: `1px solid ${theme.colors.accent}`,
    fontSize: theme.fontSize.xs,
  },
  sectionDivider: {
    height: 1, backgroundColor: theme.colors.border,
    margin: `${theme.spacing.sm}px 0 ${theme.spacing.xs}px`,
  },
  controlCard: {
    display: 'flex', flexDirection: 'column', gap: theme.spacing.sm,
    padding: theme.spacing.md, borderRadius: theme.radius.md,
    backgroundColor: theme.colors.bg.surface, border: `1px solid ${theme.colors.border}`,
  },
  rangeRow: {
    display: 'grid', gridTemplateColumns: '72px minmax(90px, 1fr) 42px',
    alignItems: 'center', gap: theme.spacing.sm, minHeight: 28,
  },
  rangeLabel: { color: theme.colors.text.secondary, fontSize: theme.fontSize.sm },
  rangeInput: { width: '100%', minWidth: 0, accentColor: theme.colors.accent },
  rangeValue: {
    color: theme.colors.text.primary, fontSize: theme.fontSize.xs,
    fontVariantNumeric: 'tabular-nums', textAlign: 'right',
  },
  textButton: {
    alignSelf: 'flex-start', border: 'none', padding: 0, background: 'transparent',
    color: theme.colors.accent, cursor: 'pointer', fontSize: theme.fontSize.xs,
  },
  buttonGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(78px, 1fr))',
    gap: theme.spacing.xs,
  },
  previewButton: {
    padding: '6px 8px', borderRadius: theme.radius.sm,
    border: `1px solid ${theme.colors.border}`, backgroundColor: theme.colors.bg.surface,
    color: theme.colors.text.secondary, cursor: 'pointer', fontSize: theme.fontSize.xs,
  },
  calibrationCard: {
    padding: theme.spacing.md, borderRadius: theme.radius.md,
    backgroundColor: theme.colors.bg.surface, border: `1px solid ${theme.colors.border}`,
  },
  calibrationHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    gap: theme.spacing.md,
  },
  cardTitle: {
    color: theme.colors.text.primary, fontWeight: theme.fontWeight.medium,
    fontSize: theme.fontSize.sm,
  },
  cardDesc: {
    color: theme.colors.text.muted, fontSize: theme.fontSize.xs,
    marginTop: 2, lineHeight: 1.45,
  },
  calibrationButton: {
    flexShrink: 0, padding: '5px 8px', borderRadius: theme.radius.sm,
    border: `1px solid ${theme.colors.border}`, color: theme.colors.text.primary,
    cursor: 'pointer', fontSize: theme.fontSize.xs,
  },
  calibrationGrid: {
    display: 'flex', flexDirection: 'column', gap: 5,
    marginTop: theme.spacing.md, paddingTop: theme.spacing.md,
    borderTop: `1px solid ${theme.colors.border}`,
  },
  runtimeMonitor: {
    display: 'flex', flexDirection: 'column', gap: theme.spacing.md,
    padding: theme.spacing.md, borderRadius: theme.radius.md,
    backgroundColor: theme.colors.bg.surface, border: `1px solid ${theme.colors.border}`,
  },
  metricGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 6,
  },
  metricItem: {
    display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0,
    padding: '7px 8px', borderRadius: theme.radius.sm,
    backgroundColor: theme.colors.bg.elevated,
  },
  metricLabel: { color: theme.colors.text.muted, fontSize: theme.fontSize.xs },
  metricValue: {
    color: theme.colors.text.primary, fontSize: theme.fontSize.sm,
    fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap',
  },
  runtimeLine: {
    display: 'flex', flexWrap: 'wrap', gap: '5px 12px',
    color: theme.colors.text.secondary, fontSize: theme.fontSize.xs,
  },
  parameterCatalog: {
    borderTop: `1px solid ${theme.colors.border}`, paddingTop: theme.spacing.sm,
  },
  parameterSummary: {
    cursor: 'pointer', color: theme.colors.text.secondary, fontSize: theme.fontSize.xs,
  },
  parameterList: {
    display: 'flex', flexWrap: 'wrap', gap: 4, maxHeight: 180, overflow: 'auto',
    marginTop: theme.spacing.sm, color: theme.colors.text.muted, fontSize: 10,
  },
  conflictList: {
    display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 150, overflow: 'auto',
    marginTop: theme.spacing.sm, color: theme.colors.text.muted, fontSize: 10,
    fontVariantNumeric: 'tabular-nums', lineHeight: 1.45,
  },
  parameterChip: {
    padding: '2px 4px', borderRadius: 4, border: `1px solid ${theme.colors.border}`,
    background: 'transparent', color: theme.colors.text.muted, fontSize: 10, cursor: 'pointer',
  },
  probeControl: {
    display: 'flex', flexDirection: 'column', gap: theme.spacing.sm,
    marginTop: theme.spacing.sm, paddingTop: theme.spacing.sm,
    borderTop: `1px solid ${theme.colors.border}`,
  },
  probeNumber: {
    width: 96, padding: '4px 6px', borderRadius: theme.radius.sm,
    border: `1px solid ${theme.colors.border}`, background: theme.colors.bg.panel,
    color: theme.colors.text.primary, fontSize: theme.fontSize.xs,
  },

  // ── About tab ──
  aboutDesc: {
    fontSize: theme.fontSize.sm, color: theme.colors.text.secondary,
    lineHeight: 1.5,
  },
  aboutRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '6px 0',
  },
  aboutKey: { fontSize: theme.fontSize.sm, color: theme.colors.text.secondary },
  aboutValue: { fontSize: theme.fontSize.sm, color: theme.colors.text.primary, fontWeight: theme.fontWeight.medium },

  // ── Proactive idle time ──
  proactiveIdleRow: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: theme.spacing.md, paddingLeft: theme.spacing.lg,
  },
  proactiveIdleLabel: {
    fontSize: theme.fontSize.xs, color: theme.colors.text.muted, whiteSpace: 'nowrap',
  },
  proactiveIdleButtons: {
    display: 'flex', gap: 4,
  },
  proactiveIdleBtn: {
    padding: '3px 8px', borderRadius: theme.radius.sm,
    border: `1px solid ${theme.colors.border}`,
    fontSize: theme.fontSize.xs, cursor: 'pointer',
    transition: 'all 0.12s',
  },

  // ── Toggle switch ──
  toggleWrap: { position: 'relative' as const, display: 'inline-block', flexShrink: 0 },
  toggleInput: { position: 'absolute' as const, opacity: 0, width: 0, height: 0, margin: 0 },
  toggleTrack: {
    display: 'inline-block', width: 40, height: 22, borderRadius: 11,
    transition: 'background-color 0.15s', position: 'relative' as const,
  },
  toggleThumb: {
    display: 'inline-block', width: 18, height: 18, borderRadius: '50%',
    backgroundColor: theme.colors.text.primary, position: 'absolute' as const, top: 2, left: 0,
    transition: 'transform 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
  },
}
