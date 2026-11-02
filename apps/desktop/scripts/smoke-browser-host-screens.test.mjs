import { describe, expect, it } from 'vitest'

import { shownStartupTitlesExpression, startupScreenFailures, STARTUP_FAILURE_TITLES } from './smoke-browser-host-screens.mjs'

/** Runs the page-side expression against a page whose visible text is `innerText`. */
function shownTitles(innerText) {
  return new Function('document', `return ${shownStartupTitlesExpression}`)({ body: { innerText } })
}

describe('browser smoke startup screens', () => {
  it("knows the boot-failure and sign-in titles the renderer shows", () => {
    expect(STARTUP_FAILURE_TITLES).toContain("Zeus couldn't start")
    expect(STARTUP_FAILURE_TITLES).toContain('Sign in to Zeus')
  })

  it('finds the boot-failure screen on the page', () => {
    const titles = shownTitles("Zeus couldn't start\nZeus' background service didn't come up.\nRetry")

    expect(titles).toEqual(["Zeus couldn't start"])
    expect(startupScreenFailures(titles, { allowGatewayFailure: false })).toEqual([
      'Webapp shows the boot-failure screen ("Zeus couldn\'t start")'
    ])
  })

  it('finds the Webapp sign-in screen on the page', () => {
    const titles = shownTitles('Sign in to Zeus\nRun zeus webapp on this computer to sign this browser in.')

    expect(startupScreenFailures(titles, { allowGatewayFailure: false })).toEqual([
      'Webapp shows the sign-in screen ("Sign in to Zeus")'
    ])
  })

  it('tolerates the boot-failure screen only when a gateway failure is allowed', () => {
    const titles = shownTitles("Zeus couldn't start")

    expect(startupScreenFailures(titles, { allowGatewayFailure: true })).toEqual([])
  })

  it('fails on the sign-in screen even when a gateway failure is allowed', () => {
    const titles = shownTitles('Sign in to Zeus')

    expect(startupScreenFailures(titles, { allowGatewayFailure: true })).toHaveLength(1)
  })

  it('passes a ready Webapp', () => {
    const titles = shownTitles('New session\nAsk Zeus anything')

    expect(titles).toEqual([])
    expect(startupScreenFailures(titles, { allowGatewayFailure: false })).toEqual([])
  })
})
