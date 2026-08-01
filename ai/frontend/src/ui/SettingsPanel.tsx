import { useEffect, useRef, useState } from 'react'
import { theme } from '../core/theme'
import type { AppSettings } from '../core/store'
import { electronWindowBridge } from '../session/electron-window-bridge'
import { eventBus } from '../core/event-bus'
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

const CHARACTERS = [
  { id: 'monika', label: 'Monika' },
]

const LIVE2D_MODELS = [
  { id: 'Design_genius_White', label: 'Design Genius White' },
  { id: 'youxiaomiao', label: 'You Xiaomiao' },
  { id: 'ariu', label: 'Ariu' },
  { id: 'mao_zh-Hans', label: 'Mao (CN)' },
  { id: 'hiyori_zh-Hans', label: 'Hiyori (CN)' },
]

const LIVE2D_TOGGLES = [
  { key: 'live2dBlink' as const, label: '自动眨眼', desc: '根据模型能力自然控制双眼' },
  { key: 'live2dBreathe' as const, label: '呼吸微动', desc: '身体起伏与轻微摇摆' },
  { key: 'live2dLipSync' as const, label: '实时口型', desc: '按真实音频包络驱动开口' },
  { key: 'live2dHeadTracking' as const, label: '头部跟随', desc: '头部和视线跟随光标' },
  { key: 'live2dExpression' as const, label: '表情系统', desc: '使用模型原生表情并平滑混合' },
  { key: 'live2dIdle' as const, label: '待机动画', desc: '连续微动、呼吸与随机凝视' },
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

type TabId = 'general' | 'animation' | 'appearance' | 'about'

interface TabDef {
  id: TabId
  label: string
  icon: string
}

const TABS: TabDef[] = [
  { id: 'general', label: 'General', icon: '⚙' },
  { id: 'animation', label: 'Animation', icon: '✦' },
  { id: 'appearance', label: 'Appearance', icon: '◈' },
  { id: 'about', label: 'About', icon: 'ℹ' },
]

const TAB_ICONS: Record<TabId, string> = {
  general: '⚙',
  animation: '✦',
  appearance: '◈',
  about: 'ⓘ',
}

const TAB_LABELS: Record<TabId, string> = {
  general: '常规',
  animation: 'Live2D',
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
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                style={{
                  ...styles.tabBtn,
                  backgroundColor: activeTab === tab.id ? theme.colors.bg.surface : 'transparent',
                  borderLeft: activeTab === tab.id ? `2px solid ${theme.colors.accent}` : '2px solid transparent',
                }}
                onClick={() => setActiveTab(tab.id)}
              >
                <span style={styles.tabIcon}>{TAB_ICONS[tab.id]}</span>
                <span style={styles.tabLabel}>{TAB_LABELS[tab.id]}</span>
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div style={styles.content}>
            {activeTab === 'general' && (
              <GeneralTab settings={settings} onSettingChange={onSettingChange} />
            )}
            {activeTab === 'animation' && (
              <AnimationTab settings={settings} onSettingChange={onSettingChange} />
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

// ── Tab: General ──

function GeneralTab({ settings, onSettingChange }: {
  settings: AppSettings
  onSettingChange: (key: string, value: unknown) => void
}) {
  return (
    <div style={styles.tabContent}>
      <div style={styles.sectionLabel}>Character</div>

      <SettingRow label="Character">
        <select
          style={styles.select}
          value={settings.activeCharacterId}
          onChange={(e) => onSettingChange('activeCharacterId', e.target.value)}
        >
          {CHARACTERS.map((c) => (
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
          {LIVE2D_MODELS.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
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
            当前模型：{LIVE2D_MODELS.find(model => model.id === settings.live2dModel)?.label ?? settings.live2dModel}
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
    width: 84, flexShrink: 0, display: 'flex', flexDirection: 'column',
    padding: `${theme.spacing.sm}px 0`, gap: 2,
    borderRight: `1px solid ${theme.colors.border}`,
    backgroundColor: theme.colors.bg.surface,
  },
  tabBtn: {
    display: 'flex', alignItems: 'center', justifyContent: 'flex-start', gap: 4,
    padding: '8px 6px', border: 'none', cursor: 'pointer',
    color: theme.colors.text.secondary, fontSize: theme.fontSize.sm,
    textAlign: 'left' as const, transition: 'background-color 0.1s',
    width: '100%',
  },
  tabIcon: { fontSize: '0.95rem', flexShrink: 0, width: 20, textAlign: 'center' as const },
  tabLabel: { whiteSpace: 'nowrap' as const, fontSize: theme.fontSize.sm },

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
