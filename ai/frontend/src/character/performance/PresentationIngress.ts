import type { CharacterIntent } from '../CharacterBehaviorResolver'

export type PresentationChannel = 'expression' | 'motion' | 'attention' | 'activity'
export type PresentationSource = 'idle' | 'llm' | 'interaction' | 'lifecycle' | 'explicit'

export interface PresentationRequest {
  source: PresentationSource
  owner: string
  intent: CharacterIntent
  channels?: PresentationChannel[]
  authority?: number
  leaseMs?: number
  turnId?: string
}

export interface AcceptedPresentation {
  intent: CharacterIntent
  channels: ReadonlySet<PresentationChannel>
}

type Lease = { owner: string; source: PresentationSource; authority: number; expiresAt: number; turnId: string }

const DEFAULT_AUTHORITY: Record<PresentationSource, number> = {
  idle: 10,
  llm: 50,
  interaction: 60,
  lifecycle: 80,
  explicit: 100,
}
const ALL_CHANNELS: PresentationChannel[] = ['expression', 'motion', 'attention', 'activity']

/** Arbitrates semantic ownership before any expression, attention, or motion controller. */
export class PresentationIngress {
  private readonly leases = new Map<PresentationChannel, Lease>()
  private readonly now: () => number

  constructor(now: () => number = () => performance.now()) {
    this.now = now
  }

  submit(request: PresentationRequest): AcceptedPresentation | null {
    const now = this.now()
    const authority = request.authority ?? DEFAULT_AUTHORITY[request.source]
    const turnId = request.turnId || request.intent.turnId || ''
    const accepted = new Set<PresentationChannel>()
    for (const channel of request.channels ?? ALL_CHANNELS) {
      const active = this.leases.get(channel)
      const activeValid = active && active.expiresAt > now
      const sameOwner = activeValid && active.owner === request.owner
      if (activeValid && !sameOwner && active.authority > authority) continue
      this.leases.set(channel, {
        owner: request.owner,
        source: request.source,
        authority,
        expiresAt: now + Math.max(0, request.leaseMs ?? 0),
        turnId,
      })
      accepted.add(channel)
    }
    return accepted.size ? { intent: { ...request.intent, turnId }, channels: accepted } : null
  }

  releaseOwner(owner: string): void {
    for (const [channel, lease] of this.leases) {
      if (lease.owner === owner) this.leases.delete(channel)
    }
  }

  releaseTurn(turnId: string): void {
    if (!turnId) return
    for (const [channel, lease] of this.leases) {
      if (lease.turnId === turnId) this.leases.delete(channel)
    }
  }

  reset(): void {
    this.leases.clear()
  }
}
