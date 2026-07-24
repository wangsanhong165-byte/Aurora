declare global {
  interface Window {
    electronAPI?: {
      platform: string
      minimize: () => void
      close: () => void
      setAlwaysOnTop: (value: boolean) => void
      setPetMode: (enabled: boolean) => void
      getSettings: () => Record<string, unknown>
    }
  }
}

export interface TitleBarProps {
  onSettingsClick?: () => void
  onHistoryClick?: () => void
}

export function TitleBar({ onSettingsClick, onHistoryClick }: TitleBarProps) {
  const api = window.electronAPI

  return (
    <div style={styles.bar}>
      <div style={styles.left}>
        <button type="button" style={styles.settingsBtn} onClick={onHistoryClick} title="History">
          &#9776;
        </button>
        <button type="button" style={styles.settingsBtn} onClick={onSettingsClick} title="Settings">
          &#9881;
        </button>
      </div>
      <span style={styles.title}>Monika Companion</span>
      {api ? (
        <div style={styles.controls}>
          <button type="button" style={styles.btn} onClick={() => api.minimize()} title="Minimize">
            &#x2014;
          </button>
          <button type="button" style={{ ...styles.btn, ...styles.closeBtn }} onClick={() => api.close()} title="Close">
            &#x2715;
          </button>
        </div>
      ) : (
        <div style={styles.controls}>
          <button type="button" style={styles.btn} onClick={onSettingsClick} title="Settings">
            &#9881;
          </button>
        </div>
      )}
    </div>
  )
}

type StyleObj = Record<string, string | number | undefined>

const styles: Record<string, StyleObj> = {
  bar: {
    height: 32, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 8px', backgroundColor: '#121216', userSelect: 'none', flexShrink: 0,
    WebkitAppRegion: 'drag' as string,
  },
  left: { WebkitAppRegion: 'no-drag' as string },
  title: { fontSize: '0.8rem', color: '#888', marginLeft: 8 },
  controls: { display: 'flex', gap: 4, WebkitAppRegion: 'no-drag' as string },
  btn: {
    width: 36, height: 24, border: 'none', background: 'transparent', color: '#aaa',
    fontSize: '0.8rem', cursor: 'pointer', borderRadius: 4, display: 'flex',
    alignItems: 'center', justifyContent: 'center',
  },
  closeBtn: { fontSize: '0.7rem' },
  settingsBtn: {
    width: 28, height: 24, border: 'none', background: 'transparent', color: '#666',
    fontSize: '0.9rem', cursor: 'pointer', borderRadius: 4, display: 'flex',
    alignItems: 'center', justifyContent: 'center',
  },
}
