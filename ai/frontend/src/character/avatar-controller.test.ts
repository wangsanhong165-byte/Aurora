import assert from 'node:assert/strict'
import test from 'node:test'

import { eventBus } from '../core/event-bus.ts'
import { AvatarController } from './AvatarController.ts'
import type { CharacterController } from './controllers.ts'
import type { ComponentManager } from './ComponentManager.ts'

test('avatar protocol expression and motion use the character presentation boundary', () => {
  const calls: Array<{ kind: string; args: unknown[] }> = []
  const characterController = {
    applyAvatarExpression: (...args: unknown[]) => {
      calls.push({ kind: 'expression', args })
      return true
    },
    applyAvatarMotion: (...args: unknown[]) => {
      calls.push({ kind: 'motion', args })
      return true
    },
  } as unknown as CharacterController
  const avatar = new AvatarController()
  avatar.wire(characterController, {} as ComponentManager)
  avatar.attach()

  try {
    eventBus.emit('avatar:expression_update', {
      name: 'shy', intensity: 0.7, controller: 'user', priority: 100,
    })
    eventBus.emit('avatar:motion_update', {
      name: 'nod', controller: 'user', priority: 100, loop: false,
    })
  } finally {
    avatar.detach()
  }

  assert.deepEqual(calls, [
    { kind: 'expression', args: ['shy', 0.7, 'user', 100, 500] },
    { kind: 'motion', args: ['nod', 'user', 100] },
  ])
})
