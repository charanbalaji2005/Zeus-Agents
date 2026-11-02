import { describe, expect, it } from 'vitest'

import {
  normalizeZeusOpenString,
  pathFromZeusDeepLink,
  pathFromOpenDeepLink,
  resolveZeusOpenPath
} from './zeus-open-target'

describe('normalizeZeusOpenString', () => {
  it('accepts hash-router paths and strips a leading hash', () => {
    expect(normalizeZeusOpenString('/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeZeusOpenString('#/index-network/intent/1')).toBe('/index-network/intent/1')
  })

  it('maps plugin-scoped zeus:// deep links to the same path', () => {
    expect(normalizeZeusOpenString('zeus://index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeZeusOpenString('zeus://index-network/intent/1?focus=true')).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('maps zeus://open/… deep links by stripping the open host', () => {
    expect(normalizeZeusOpenString('zeus://open/index-network/intent/1')).toBe('/index-network/intent/1')
    expect(normalizeZeusOpenString('zeus://open/settings/plugins')).toBe('/settings/plugins')
  })

  it('rejects reserved zeus kinds and unsafe paths', () => {
    expect(normalizeZeusOpenString('zeus://blueprint/morning-brief')).toBeNull()
    expect(normalizeZeusOpenString('zeus://plugin/install')).toBeNull()
    expect(normalizeZeusOpenString('https://example.com/x')).toBeNull()
    expect(normalizeZeusOpenString('/../etc/passwd')).toBeNull()
    expect(normalizeZeusOpenString('index-network')).toBeNull()
  })
})

describe('resolveZeusOpenPath', () => {
  it('merges structured path + params', () => {
    expect(resolveZeusOpenPath({ path: '/index-network/intent/1', params: { focus: 'true' } })).toBe(
      '/index-network/intent/1?focus=true'
    )
  })

  it('resolves href the same as a bare string', () => {
    expect(resolveZeusOpenPath({ href: 'zeus://index-network/intent/1' })).toBe('/index-network/intent/1')
  })
})

describe('pathFromZeusDeepLink', () => {
  it('builds the navigate path from a plugin-scoped deep-link payload', () => {
    expect(pathFromZeusDeepLink('index-network', 'intent/1')).toBe('/index-network/intent/1')
  })

  it('builds the navigate path from zeus://open/… payloads', () => {
    expect(pathFromOpenDeepLink('index-network/intent/1')).toBe('/index-network/intent/1')
    expect(pathFromZeusDeepLink('open', 'agent/42')).toBe('/agent/42')
  })

  it('ignores reserved kinds', () => {
    expect(pathFromZeusDeepLink('blueprint', 'morning-brief')).toBeNull()
    expect(pathFromZeusDeepLink('plugin', 'install')).toBeNull()
  })
})
