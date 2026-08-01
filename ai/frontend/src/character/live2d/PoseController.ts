// Enforces mutually-exclusive Cubism pose groups as mixer contributions.

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
    console.log('[Pose] Loaded %d exclusive pose groups', this.groups.length)
  }

  getContributions(): Array<{ partId: string; opacity: number }> {
    const contributions: Array<{ partId: string; opacity: number }> = []
    for (const group of this.groups) {
      for (const member of group.members) {
        const opacity = member.id === group.activeId ? 1 : 0
        contributions.push({ partId: member.id, opacity })
        for (const link of member.links) contributions.push({ partId: link, opacity })
      }
    }
    return contributions
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
