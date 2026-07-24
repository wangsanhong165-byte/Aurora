// Character selection panel — shows available characters and allows switching

import { theme } from '../core/theme'

export interface CharacterInfo {
  id: string
  name: string
  description: string
}

export interface CharacterSelectProps {
  activeCharacterId: string
  onSwitchCharacter: (characterId: string) => void
  disabled?: boolean
}

/** Default characters matching the Live2D config and config/characters/index.yaml layout */
export const DEFAULT_CHARACTERS: CharacterInfo[] = [
  {
    id: 'monika',
    name: 'Monika',
    description: 'The cheerful Literature Club president',
  },
  {
    id: 'youxiaomiao',
    name: 'You Xiaomiao',
    description: 'A lively and playful companion',
  },
  {
    id: 'ariu',
    name: 'Ariu',
    description: 'A gentle and caring presence',
  },
]

function AvatarPlaceholder({ name, size }: { name: string; size: number }) {
  const initial = name.charAt(0).toUpperCase()
  const hue = name.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0) % 360

  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        backgroundColor: `hsl(${hue}, 40%, 35%)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#f0f0f0',
        fontSize: size * 0.42,
        fontWeight: theme.fontWeight.semibold,
        flexShrink: 0,
        userSelect: 'none',
      }}
    >
      {initial}
    </div>
  )
}

export function CharacterSelect({
  activeCharacterId,
  onSwitchCharacter,
  disabled = false,
}: CharacterSelectProps) {
  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.headerTitle}>Characters</span>
      </div>
      <div style={styles.list}>
        {DEFAULT_CHARACTERS.map((char) => {
          const isActive = char.id === activeCharacterId
          return (
            <button
              key={char.id}
              type="button"
              disabled={disabled || isActive}
              onClick={() => onSwitchCharacter(char.id)}
              style={{
                ...styles.card,
                borderColor: isActive ? theme.colors.accent : 'transparent',
                backgroundColor: isActive
                  ? theme.colors.bg.surface
                  : 'transparent',
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: isActive ? 1 : 0.75,
              }}
              onMouseEnter={(e) => {
                if (!isActive && !disabled) {
                  e.currentTarget.style.backgroundColor = theme.colors.bg.hover
                  e.currentTarget.style.opacity = '1'
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  e.currentTarget.style.backgroundColor = 'transparent'
                  e.currentTarget.style.opacity = '0.75'
                }
              }}
            >
              <AvatarPlaceholder name={char.name} size={36} />
              <div style={styles.cardInfo}>
                <div style={styles.cardName}>{char.name}</div>
                <div style={styles.cardDesc}>{char.description}</div>
              </div>
              {isActive && <div style={styles.activeDot} />}
            </button>
          )
        })}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    padding: `${theme.spacing.md}px ${theme.spacing.lg}px`,
    borderBottom: `1px solid ${theme.colors.border}`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexShrink: 0,
  },
  headerTitle: {
    fontSize: theme.fontSize.sm,
    fontWeight: theme.fontWeight.semibold,
    color: theme.colors.text.secondary,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    padding: `${theme.spacing.xs}px`,
    overflowY: 'auto',
  },
  card: {
    display: 'flex',
    alignItems: 'center',
    gap: theme.spacing.md,
    padding: `${theme.spacing.sm}px ${theme.spacing.md}px`,
    borderRadius: theme.radius.md,
    border: `2px solid transparent`,
    backgroundColor: 'transparent',
    transition: `background-color ${theme.animation.fast}, border-color ${theme.animation.fast}, opacity ${theme.animation.fast}`,
    textAlign: 'left' as const,
    width: '100%',
    boxSizing: 'border-box' as const,
  },
  cardInfo: {
    flex: 1,
    minWidth: 0,
  },
  cardName: {
    fontSize: theme.fontSize.md,
    fontWeight: theme.fontWeight.medium,
    color: theme.colors.text.primary,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  cardDesc: {
    fontSize: theme.fontSize.xs,
    color: theme.colors.text.muted,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginTop: 2,
  },
  activeDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: theme.colors.accent,
    flexShrink: 0,
  },
}
