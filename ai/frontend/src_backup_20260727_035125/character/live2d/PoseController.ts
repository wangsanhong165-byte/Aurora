// Enforces mutually-exclusive Cubism pose groups behind adapter ownership.

import type { CubismModelHandle } from './core'

interface PoseMember {
  id: string
  links: string[]
}

interface PoseGroup {
  members: PoseMember[]
  activeId: string
}

export class PoseController {
  private groups: PoseGroup[] = []
  private initialized = false

  load(poseJson: Record<string, unknown>): void {
    this.groups = []
    const rawGroups = poseJson.Groups as Array<Array<{ Id: string; Link?: string[] }>> | undefined
    if (!Array.isArray(rawGroups)) {
      console.warn('[Pose] No Groups in pose3.json')
      return
    }
    for (const raw of rawGroups) {
      if (!Array.isArray(raw) || raw.length < 2) continue
      const members = raw
        .filter(entry => Boolean(entry.Id))
        .map(entry => ({ id: entry.Id, links: entry.Link ?? [] }))
      if (members.length >= 2) {
        this.groups.push({ members, activeId: members[0].id })
      }
    }
    this.initialized = false
    console.log('[Pose] Loaded %d exclusive pose groups', this.groups.length)
  }

  applyInitial(handle: CubismModelHandle): void {
    if (this.initialized) return
    this.apply(handle)
    this.initialized = true
    console.log('[Pose] Applied initial state for %d groups', this.groups.length)
  }

  update(handle: CubismModelHandle): void {
    if (!this.initialized) {
      this.applyInitial(handle)
      return
    }
    this.apply(handle)
  }

  private apply(handle: CubismModelHandle): void {
    for (const group of this.groups) {
      for (const member of group.members) {
        const opacity = member.id === group.activeId ? 1 : 0
        handle.setPartOpacity(member.id, opacity)
        for (const link of member.links) handle.setPartOpacity(link, opacity)
      }
    }
  }

  select(partId: string): boolean {
    const group = this.groups.find(candidate =>
      candidate.members.some(member => member.id === partId),
    )
    if (!group) {
      console.warn('[Pose] Unknown pose part:', partId)
      return false
    }
    group.activeId = partId
    return true
  }

  getDebugState(): Array<{ activeId: string; members: string[] }> {
    return this.groups.map(group => ({
      activeId: group.activeId,
      members: group.members.map(member => member.id),
    }))
  }

  get groupCount(): number { return this.groups.length }
}
