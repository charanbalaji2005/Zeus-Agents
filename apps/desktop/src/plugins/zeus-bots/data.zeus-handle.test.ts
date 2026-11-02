/**
 * @zeus belongs to the default bot only while its source has no real
 * (pre-reservation) `zeus` profile. With one, the roster shows exactly one
 * @zeus — the real profile — and the default answers to @default, so a
 * typed @zeus reaches the same profile the backend's message_agent does.
 */

import { describe, expect, it, vi } from 'vitest'

import { botHandle, botMentionTag, claimDefaultHandles, mergeMultiSourceRoster, resolveRosterMentions } from './data'
import { previewKind } from './row-helpers'
import type { RosterRow } from './types'

vi.mock('@zeus/plugin-sdk', async () => {
  const { atom } = await import('nanostores')

  return { atom, host: {}, queryClient: undefined, useQuery: vi.fn(), useValue: vi.fn() }
})

vi.mock('./shared', () => ({ getPluginCtx: () => null, ID: 'zeus-bots' }))

function roster(names: string[]): RosterRow[] {
  const local = { profiles: names.map(name => ({ name })) }

  // What Electron's buildAgentRoster reports for a single local source: bare-name handles.
  const union = {
    agents: names.map(profile => ({
      connectionId: 'local',
      connectionKind: 'local' as const,
      connectionLabel: 'This device',
      handle: profile,
      profile,
      targetProfile: profile
    })),
    primaryConnectionId: 'local'
  }

  return mergeMultiSourceRoster(local, union, 'local').profiles as RosterRow[]
}

describe('the @zeus handle', () => {
  it.each([
    [['default', 'researcher'], 'default'],
    [['default', 'zeus', 'researcher'], 'zeus']
  ])('roster %j shows one @zeus and a typed @zeus reaches %s', (names, owner) => {
    const rows = roster(names)
    const handles = rows.map(row => botHandle(row.name, row))

    expect(handles.filter(handle => handle === 'zeus')).toHaveLength(1)
    expect(rows.map(row => botMentionTag(row)).filter(tag => tag === 'zeus')).toHaveLength(1)
    expect(resolveRosterMentions('@zeus ping', rows, { name: 'researcher' }).map(row => row.name)).toEqual([owner])
  })

  it('names the default @default once a real zeus profile holds the handle', () => {
    const rows = roster(['default', 'zeus', 'researcher'])
    const byName = Object.fromEntries(rows.map(row => [row.name, botHandle(row.name, row)]))

    expect(byName).toEqual({ default: 'default', zeus: 'zeus', researcher: 'researcher' })
    expect(resolveRosterMentions('@default ping', rows, { name: 'researcher' }).map(row => row.name)).toEqual(['default'])
  })

  it('keeps each source separate: a remote zeus profile does not rename the local default', () => {
    const rows = claimDefaultHandles<Partial<RosterRow>>([
      { connectionId: 'local', name: 'default' },
      { connectionId: 'mini', name: 'default' },
      { connectionId: 'mini', name: 'zeus' }
    ])

    expect(rows.map(row => botHandle(String(row.name), row))).toEqual(['zeus', 'default', 'zeus'])
  })

  it("never lets a source's stale 'zeus' handle on its default answer @zeus", () => {
    // An older backend labels its default @zeus even beside a real zeus profile.
    const rows = claimDefaultHandles<RosterRow>([
      { connectionId: 'mini', handle: 'zeus', name: 'default', remoteSource: true },
      { connectionId: 'mini', handle: 'zeus', name: 'zeus', remoteSource: true },
      { connectionId: 'local', name: 'researcher' }
    ])

    expect(resolveRosterMentions('@zeus ping', rows, { name: 'researcher' }).map(row => row.name)).toEqual(['zeus'])
  })

  it('names a DM sender in a row preview by its roster handle', () => {
    const rows = claimDefaultHandles<RosterRow>(
      ['default', 'zeus', 'researcher'].map(name => ({ connectionId: 'local', name }))
    )

    const sender = (name: string, list: RosterRow[]) =>
      previewKind(`Message from 🤖 ${name} (@x): hi`, list, 'local').fromBot

    expect([sender('default', rows), sender('zeus', rows)]).toEqual(['default', 'zeus'])
    // No real zeus profile: the default is still @zeus (#89484).
    expect(sender('default', claimDefaultHandles<RosterRow>([{ connectionId: 'local', name: 'default' }]))).toBe(
      'zeus'
    )
  })
})
