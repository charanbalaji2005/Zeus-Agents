import assert from 'node:assert/strict'

import { test } from 'vitest'

import { hasWindowsPathPrefix, isExternalVenvHolder, isZeusOwnedVenvDaemon } from './venv-holder-select'

const SCRIPTS = 'C:\\Zeus\\venv\\Scripts'

test('matches the hindsight daemon shim (exe under venv Scripts + hindsight cmdline)', () => {
  assert.equal(
    isZeusOwnedVenvDaemon(
      'C:\\Zeus\\venv\\Scripts\\pythonw.exe',
      'C:\\Zeus\\venv\\Scripts\\pythonw.exe -m hindsight_api.main --daemon --idle-timeout 300 --port 9177',
      SCRIPTS
    ),
    true
  )
})

test('Windows path prefix match is ordinal case-insensitive', () => {
  assert.equal(
    isZeusOwnedVenvDaemon(
      'c:\\zeus\\venv\\scripts\\python.exe',
      'python.exe -m hindsight_api.main --daemon',
      'C:\\Zeus\\venv\\Scripts'
    ),
    true
  )
})

test('excludes external venv holders that are not the hindsight daemon', () => {
  // a user terminal running the zeus CLI from the venv — must NOT be killed
  assert.equal(isZeusOwnedVenvDaemon('C:\\Zeus\\venv\\Scripts\\zeus.exe', 'zeus chat -q "hi"', SCRIPTS), false)
  // an unrelated python script using the venv interpreter
  assert.equal(
    isZeusOwnedVenvDaemon('C:\\Zeus\\venv\\Scripts\\python.exe', 'python C:\\tools\\import.py', SCRIPTS),
    false
  )
})

test('excludes exes outside the venv even when the cmdline mentions hindsight', () => {
  assert.equal(
    isZeusOwnedVenvDaemon('C:\\Other\\pythonw.exe', 'pythonw -m hindsight_api.main --daemon', SCRIPTS),
    false
  )
})

test('prefix boundary: sibling dirs (ScriptsX) do not match', () => {
  assert.equal(hasWindowsPathPrefix('C:\\Zeus\\venv\\ScriptsX\\python.exe', SCRIPTS), false)
  assert.equal(hasWindowsPathPrefix('C:\\Zeus\\venv\\Scripts\\python.exe', SCRIPTS), true)
})

test('null/undefined fields never match', () => {
  assert.equal(isZeusOwnedVenvDaemon(null, 'x', SCRIPTS), false)
  assert.equal(isZeusOwnedVenvDaemon('C:\\Zeus\\venv\\Scripts\\pythonw.exe', null, SCRIPTS), false)
  assert.equal(isZeusOwnedVenvDaemon(undefined, undefined, SCRIPTS), false)
})

// --- isExternalVenvHolder (#62311) ------------------------------------------

test('matches the autostart gateway shim (zeus.exe under venv Scripts)', () => {
  assert.equal(
    isExternalVenvHolder(
      'C:\\Zeus\\venv\\Scripts\\zeus.exe',
      '"C:\\Zeus\\venv\\Scripts\\zeus.exe" gateway run --external-supervisor',
      SCRIPTS
    ),
    true
  )
})

test('matches the dashboard scheduled task (python -m zeus_cli / -m zeus)', () => {
  assert.equal(
    isExternalVenvHolder(
      'C:\\Zeus\\venv\\Scripts\\python.exe',
      '"C:\\Zeus\\venv\\Scripts\\python.exe" -m zeus_cli.main dashboard',
      SCRIPTS
    ),
    true
  )
  assert.equal(
    isExternalVenvHolder('C:\\Zeus\\venv\\Scripts\\pythonw.exe', 'pythonw.exe -m zeus serve', SCRIPTS),
    true
  )
})

test('never matches an unrelated process that merely borrows the venv interpreter', () => {
  // a user's own script running on the venv python — NOT Zeus, must NOT be killed
  assert.equal(
    isExternalVenvHolder('C:\\Zeus\\venv\\Scripts\\python.exe', 'python C:\\tools\\import.py', SCRIPTS),
    false
  )
  // hindsight daemon is selected by isZeusOwnedVenvDaemon, not here
  assert.equal(
    isExternalVenvHolder('C:\\Zeus\\venv\\Scripts\\pythonw.exe', 'pythonw -m hindsight_api.main --daemon', SCRIPTS),
    false
  )
})

test('never matches a process outside the venv, even with zeus in the cmdline', () => {
  // an editor / shell whose command line mentions the install root (#62445 regression guard)
  assert.equal(
    isExternalVenvHolder('C:\\Windows\\System32\\cmd.exe', 'cmd /c cd C:\\Zeus\\venv\\Scripts && dir', SCRIPTS),
    false
  )
  assert.equal(isExternalVenvHolder('C:\\Other\\zeus.exe', 'zeus gateway run', SCRIPTS), false)
})

test('sibling-dir and boundary safety for the external selector', () => {
  assert.equal(isExternalVenvHolder('C:\\Zeus\\venv\\ScriptsX\\zeus.exe', 'zeus gateway run', SCRIPTS), false)
  assert.equal(isExternalVenvHolder(null, 'zeus gateway run', SCRIPTS), false)
  assert.equal(isExternalVenvHolder('C:\\Zeus\\venv\\Scripts\\zeus.exe', null, SCRIPTS), false)
})
