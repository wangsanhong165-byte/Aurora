import { useEffect, useState } from 'react'
import type { RecorderState } from '../audio/recorder'
import type { AppSettings } from '../core/store'
import { CharacterView } from '../character/CharacterView'
import { ChatView } from '../conversation/ChatView'
import { HistoryPanel, type HistoryEntry } from '../conversation/HistoryPanel'
import { InputBar } from './InputBar'
import { SettingsPanel } from './SettingsPanel'
import { DrawerPanel } from './DrawerPanel'
import { Layout, type DrawerItem } from './Layout'
import { StageSubtitle } from './StageSubtitle'
import type { DrawerSection } from './workspace-state'
import {
  CapabilityPanel,
  CharacterSelfPanel,
  MemoryPanel,
  VoicePanel,
} from './UserViewPanels'
import { DeveloperWorkspace } from './DeveloperWorkspace'

const DRAWER_ITEMS: DrawerItem[] = [
  { id: 'chat', label: '对话', mark: '聊' },
  { id: 'character', label: '角色', mark: '角' },
  { id: 'memory', label: '记忆', mark: '忆' },
  { id: 'voice', label: '语音', mark: '声' },
  { id: 'capabilities', label: '能力', mark: '能' },
  { id: 'settings', label: '设置', mark: '设' },
  { id: 'developer', label: '开发者', mark: '研' },
]

export interface CompanionWorkspaceProps {
  settings: AppSettings
  requestCommand: (action: string, params?: Record<string, unknown>) => Promise<Record<string, unknown>>
  recorderState: RecorderState
  recordingSupported: boolean
  onToggleRecording: () => void | Promise<void>
  histories: HistoryEntry[]
  historyUid: string
  historyLoading: boolean
  historyRevision: number
  subtitleText: string
  accessoryParts: Record<string, string>
  accessoryState: Record<string, boolean>
  onSend: (text: string) => void
  onInterrupt: () => void
  onLoadHistory: (uid: string) => void
  onDeleteHistory: (uid: string) => void
  onCreateHistory: () => void
  onSettingChange: (key: string, value: unknown) => void
  onAccessoryToggle: (label: string) => void
}

export function CompanionWorkspace(props: CompanionWorkspaceProps) {
  const [chatMode, setChatMode] = useState<'conversation' | 'history'>('conversation')
  useEffect(() => {
    if (props.historyRevision > 0) setChatMode('conversation')
  }, [props.historyRevision])

  const renderDrawer = (section: DrawerSection) => {
    if (section === 'chat') {
      return (
        <DrawerPanel
          title={chatMode === 'conversation' ? '对话' : '历史对话'}
          action={
            <button
              type="button"
              className="drawer-text-action"
              onClick={() => setChatMode(mode => mode === 'conversation' ? 'history' : 'conversation')}
            >
              {chatMode === 'conversation' ? '历史' : '返回对话'}
            </button>
          }
        >
          {chatMode === 'conversation' ? (
            <div className="conversation-drawer">
              <ChatView />
              <InputBar
                onSend={props.onSend}
                onInterrupt={props.onInterrupt}
                recorderState={props.recorderState}
                recordingSupported={props.recordingSupported}
                onToggleRecording={props.onToggleRecording}
              />
            </div>
          ) : (
            <HistoryPanel
              histories={props.histories}
              activeUid={props.historyUid}
              loading={props.historyLoading}
              onLoad={props.onLoadHistory}
              onDelete={props.onDeleteHistory}
              onCreate={props.onCreateHistory}
            />
          )}
        </DrawerPanel>
      )
    }
    if (section === 'settings') {
      return (
        <SettingsPanel
          open
          embedded
          onClose={() => {}}
          settings={props.settings}
          onSettingChange={props.onSettingChange}
          accessoryParts={props.accessoryParts}
          accessoryState={props.accessoryState}
          onAccessoryToggle={props.onAccessoryToggle}
        />
      )
    }
    if (section === 'developer') {
      return <DeveloperWorkspace requestCommand={props.requestCommand} />
    }
    if (section === 'character') return <CharacterSelfPanel requestCommand={props.requestCommand} />
    if (section === 'memory') return <MemoryPanel requestCommand={props.requestCommand} />
    if (section === 'voice') return <VoicePanel requestCommand={props.requestCommand} />
    return <CapabilityPanel requestCommand={props.requestCommand} />
  }

  return (
    <Layout
      characterArea={<CharacterView />}
      subtitle={<StageSubtitle text={props.subtitleText} />}
      drawerItems={DRAWER_ITEMS}
      renderDrawer={renderDrawer}
      petMode={props.settings.windowMode === 'pet'}
      onExitPetMode={() => props.onSettingChange('windowMode', 'window')}
    />
  )
}
