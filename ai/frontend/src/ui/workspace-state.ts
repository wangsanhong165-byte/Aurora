export type DrawerSection =
  | 'history'
  | 'prompt'
  | 'character'
  | 'characters'
  | 'memory'
  | 'capabilities'
  | 'live2d'
  | 'settings'
  | 'developer'

export interface DrawerState {
  section: DrawerSection
  expanded: boolean
  width: number
}

export type DrawerAction =
  | { type: 'select'; section: DrawerSection }
  | { type: 'toggle' }
  | { type: 'resize'; width: number }

// Settings needs enough room for labels and controls to breathe.
export const MIN_DRAWER_WIDTH = 400
export const MAX_DRAWER_WIDTH = 560
export const DEFAULT_DRAWER_WIDTH = 420

const DRAWER_SECTIONS: DrawerSection[] = [
  'history',
  'prompt',
  'character',
  'characters',
  'memory',
  'capabilities',
  'live2d',
  'settings',
  'developer',
]

export function clampDrawerWidth(width: number): number {
  return Math.min(MAX_DRAWER_WIDTH, Math.max(MIN_DRAWER_WIDTH, Math.round(width)))
}

export function createInitialDrawerState(
  storedActive: string | null,
  storedWidth: number,
): DrawerState {
  const migratedSection = storedActive === 'chat' ? 'history' : storedActive
  const section = DRAWER_SECTIONS.includes(migratedSection as DrawerSection)
    ? migratedSection as DrawerSection
    : 'history'
  return {
    section,
    expanded: storedActive !== 'closed',
    width: Number.isFinite(storedWidth) && storedWidth > 0
      ? clampDrawerWidth(storedWidth)
      : DEFAULT_DRAWER_WIDTH,
  }
}

export function reduceDrawerState(state: DrawerState, action: DrawerAction): DrawerState {
  if (action.type === 'resize') {
    return { ...state, width: clampDrawerWidth(action.width) }
  }
  if (action.type === 'toggle') {
    return { ...state, expanded: !state.expanded }
  }
  return {
    ...state,
    section: action.section,
    expanded: true,
  }
}
