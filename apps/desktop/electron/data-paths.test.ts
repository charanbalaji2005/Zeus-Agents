import assert from 'node:assert/strict'
import os from 'node:os'
import path from 'node:path'

import { afterEach, test, vi } from 'vitest'

import { platformDefaultZeusHome, resolveDesktopZeusHome, resolveDesktopUserData } from './data-paths'
import { controlSocketPath } from './ssh-connection'

afterEach((): void => {
  vi.unstubAllEnvs()
})

test.skipIf(process.platform === 'win32')('local SSH sockets use the suffixed default root', (): void => {
  vi.stubEnv('ZEUS_DATA_DIR_SUFFIX', 'magic-test')
  const socket: string = controlSocketPath('user', 'host', 22)

  assert.equal(path.dirname(socket), path.join(platformDefaultZeusHome(os.homedir()), 'desktop-ssh'))
})

test('default data roots append the suffix literally on each platform', (): void => {
  for (const platform of ['linux', 'darwin', 'win32'] as const) {
    const paths: typeof path = platform === 'win32' ? path.win32 : path.posix
    const home: string = platform === 'win32' ? 'C:\\Users\\test' : '/home/test'
    const local: string = paths.join(home, 'AppData', 'Local')
    const userData: string = paths.join(home, 'app-data', 'Zeus')
    const base: string = platform === 'win32' ? paths.join(local, 'zeus') : paths.join(home, '.zeus')

    for (const suffix of ['', '-asdfasdf', 'magic-test', ' spaced ']) {
      const env: NodeJS.ProcessEnv = { LOCALAPPDATA: local, ZEUS_DATA_DIR_SUFFIX: suffix }

      assert.equal(platformDefaultZeusHome(home, env, platform), base + suffix)
      assert.equal(resolveDesktopUserData(userData, env), userData + suffix)
      assert.equal(
        resolveDesktopZeusHome({ home, env, platform, directoryExists: (): boolean => false }),
        base + suffix
      )
    }
  }
})

test('explicit homes and userData retain precedence, and suffixed Windows homes never use legacy state', (): void => {
  const home: string = '/home/test'

  const env: NodeJS.ProcessEnv = {
    ZEUS_DATA_DIR_SUFFIX: 'magic-test',
    ZEUS_HOME: '/explicit/home',
    ZEUS_DESKTOP_USER_DATA_DIR: '/explicit/electron'
  }

  assert.equal(resolveDesktopUserData('/default/electron', env), path.resolve(env.ZEUS_DESKTOP_USER_DATA_DIR!))
  assert.equal(resolveDesktopZeusHome({ home, env, platform: 'linux' }), env.ZEUS_HOME)
  delete env.ZEUS_HOME
  assert.equal(resolveDesktopZeusHome({ home, env, platform: 'linux' }), '/explicit/electron/zeus-home')

  const windowsHome: string = 'C:\\Users\\test'
  const windowsEnv: NodeJS.ProcessEnv = { ZEUS_DATA_DIR_SUFFIX: 'magic-test' }
  const expected: string = path.win32.join(windowsHome, 'AppData', 'Local', 'zeusmagic-test')

  assert.equal(
    resolveDesktopZeusHome({
      home: windowsHome,
      env: windowsEnv,
      platform: 'win32',
      directoryExists: (): boolean => true
    }),
    expected
  )
  assert.equal(
    resolveDesktopZeusHome({
      home: windowsHome,
      env: windowsEnv,
      platform: 'win32',
      readWindowsHome: (): string => 'C:\\custom'
    }),
    'C:\\custom'
  )
})
