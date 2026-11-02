import { contextBridge, ipcRenderer, webFrame, webUtils } from 'electron'

import type { DesktopProfileRoute } from './desktop-profile'
import type { HudModifierApi, HudModifierStatus } from './hud-modifier-types'
import { customWindowControlsEnabled } from './window-controls'

// Which translucency the OS can back. Asked synchronously because the renderer
// needs it before its first paint, and answered by main because deciding it
// needs `os.release()` — a sandboxed preload may only require electron, events,
// timers and url, so importing node:os here throws before contextBridge runs
// and takes the ENTIRE bridge down with it (window.zeusDesktop undefined =>
// "Desktop IPC bridge is unavailable"). No reply means no glass, which degrades
// to an ordinary opaque window rather than a page thinned over nothing.
const translucencySupport = ipcRenderer.sendSync('zeus:translucency:support')
const hudWindowing = ipcRenderer.sendSync('zeus:hud:windowing')
const hudNativeDrag = hudWindowing?.nativeDrag === true

const launchFlags: { localModels?: boolean; assumeFreshInstall?: boolean } | undefined =
  ipcRenderer.sendSync('zeus:feature-flags')

// Local, sanitized skin payload for the first renderer theme paint. This does
// not wait on `gateway.ready`, so an unreachable remote primary cannot force
// the built-in palette over the skin configured on this machine.
const localSkin = ipcRenderer.sendSync('zeus:skin:local')

// This machine's UI preferences store (#145213), read before the first paint so
// a preference set in another window or in this machine's Webapp paints at once.
const uiPreferencesSnapshot = ipcRenderer.sendSync('zeus:ui-preferences:snapshot')

import { unwrapExpectedNotFound } from './api-expected-404'

contextBridge.exposeInMainWorld('zeusDesktop', {
  glassSupported: translucencySupport?.glass === true,
  translucencySupported: translucencySupport?.translucency === true,
  // Launch-flag fact: the app was started with --local, so the renderer may
  // show the local-models surfaces. Static for the window's lifetime.
  localModelsEnabled: launchFlags?.localModels === true,
  // Dev-only launch fact: an unpackaged app started with --fresh-install, so
  // onboarding treats this launch as a fresh install. Always false when packaged.
  assumeFreshInstall: launchFlags?.assumeFreshInstall === true,
  localSkin: localSkin && typeof localSkin === 'object' ? localSkin : null,
  uiPreferences: {
    snapshot: uiPreferencesSnapshot && typeof uiPreferencesSnapshot === 'object' ? uiPreferencesSnapshot : null,
    read: () => ipcRenderer.invoke('zeus:ui-preferences:read'),
    write: payload => ipcRenderer.invoke('zeus:ui-preferences:write', payload),
    onChanged: callback => {
      const listener = (_event, snapshot) => callback(snapshot)
      ipcRenderer.on('zeus:ui-preferences:changed', listener)

      return () => ipcRenderer.removeListener('zeus:ui-preferences:changed', listener)
    }
  },
  getConnection: (profile, opts) => ipcRenderer.invoke('zeus:connection', profile, opts),
  // Loopback origin that hosts YouTube's player for the file:// renderer.
  getEmbedHostOrigin: () => ipcRenderer.invoke('zeus:embed-host:origin'),
  // Registry-scoped backend resolution: { connectionId, profile } → descriptor.
  getConnectionFor: payload => ipcRenderer.invoke('zeus:connection:for', payload),
  getProfileRoutes: profiles => ipcRenderer.invoke('zeus:plugin-profile-routes', profiles),
  revalidateConnection: () => ipcRenderer.invoke('zeus:connection:revalidate'),
  getGatewayWsUrl: profile => ipcRenderer.invoke('zeus:gateway:ws-url', profile),
  // Registry-scoped fresh WS URL: { connectionId, profile } → result shape of
  // getGatewayWsUrl, minted against that connection's backend.
  getGatewayWsUrlFor: payload => ipcRenderer.invoke('zeus:gateway:ws-url-for', payload),
  // { connectionId, profile, pluginId, path } → one-use local plugin socket URL, null, or { refused: 'permission' }.
  getPluginWsUrl: payload => ipcRenderer.invoke('zeus:plugin:ws-url', payload),
  // Union agent roster across every registered connection.
  getAgentRoster: () => ipcRenderer.invoke('zeus:agents:roster'),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('zeus:window:openSession', sessionId, opts),
  openSessionInTerminal: (sessionId, opts) => ipcRenderer.invoke('zeus:window:openInTerminal', sessionId, opts),
  openWindow: (options?: DesktopProfileRoute) => ipcRenderer.invoke('zeus:window:openInstance', options),
  openBrowserWindow: tabId => ipcRenderer.invoke('zeus:window:openBrowser', tabId),
  windowRelay: {
    send: payload => ipcRenderer.send('zeus:window:relay', payload),
    onMessage: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:window:relay', listener)

      return () => ipcRenderer.removeListener('zeus:window:relay', listener)
    }
  },
  onBrowserPopoutClosed: callback => {
    const listener = (_event, tabId) => callback(tabId)
    ipcRenderer.on('zeus:browser-popout:closed', listener)

    return () => ipcRenderer.removeListener('zeus:browser-popout:closed', listener)
  },
  claimAmbientCue: key => ipcRenderer.invoke('zeus:ambient:claim', key),
  windowControls: {
    custom: customWindowControlsEnabled(),
    minimize: () => ipcRenderer.send('zeus:window-control', 'minimize'),
    toggleMaximize: () => ipcRenderer.send('zeus:window-control', 'toggle-maximize'),
    close: () => ipcRenderer.send('zeus:window-control', 'close')
  },
  wakeIndicator: {
    getState: () => ipcRenderer.invoke('zeus:wake-indicator:get'),
    setState: state => ipcRenderer.send('zeus:wake-indicator:set', state),
    onState: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('zeus:wake-indicator:state', listener)

      return () => ipcRenderer.removeListener('zeus:wake-indicator:state', listener)
    }
  },
  chatOnboarding: {
    size: mode => ipcRenderer.send('zeus:window:size', mode)
  },
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('zeus:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('zeus:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('zeus:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('zeus:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('zeus:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('zeus:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('zeus:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('zeus:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('zeus:pet-overlay:control', listener)
    }
  },
  // HUD mode: the chrome-free floating chat. A full app renderer (own gateway)
  // sized as a floating bar, so it mounts the real composer. Main owns the
  // window; `onChanged` keeps every window's toggle truthful.
  hud: {
    nativeDrag: hudNativeDrag,
    windowing: {
      clientPlacement: hudWindowing?.clientPlacement !== false,
      controlDrag: hudWindowing?.controlDrag === true,
      nativeDrag: hudNativeDrag,
      solid: hudWindowing?.solid === true,
      workspaceTransfer: hudWindowing?.workspaceTransfer === true
    },
    open: request => ipcRenderer.invoke('zeus:hud:open', request),
    close: () => ipcRenderer.invoke('zeus:hud:close'),
    setIgnoreMouse: ignore => ipcRenderer.send('zeus:hud:ignore-mouse', ignore),
    beginMove: () => ipcRenderer.send('zeus:hud:begin-move'),
    endMove: () => ipcRenderer.send('zeus:hud:end-move'),
    moveBy: delta => ipcRenderer.send('zeus:hud:move-by', delta),
    setWorkspaceTransfer: transferring => ipcRenderer.send('zeus:hud:workspace-transfer', transferring),
    setBounds: bounds => ipcRenderer.send('zeus:hud:set-bounds', bounds),
    resetLayout: () => ipcRenderer.invoke('zeus:hud:reset-layout'),
    // Whether the band covers the window below the bar. Main pairs it with the
    // user's translucency setting to decide the native frost (macOS vibrancy /
    // Windows 11 DWM backdrop) — see hudFrostFor.
    setFrost: showing => ipcRenderer.invoke('zeus:hud:frost', showing),
    // The HUD tells main which session it is on; main hands that back to the
    // app window when the HUD closes, so the app can re-home onto it.
    setSession: sessionId => ipcRenderer.send('zeus:hud:session', sessionId),
    onGoto: callback => {
      const listener = (_event, sessionId) => callback(sessionId)
      ipcRenderer.on('zeus:hud:goto', listener)

      return () => ipcRenderer.removeListener('zeus:hud:goto', listener)
    },
    onChanged: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('zeus:hud:changed', listener)

      return () => ipcRenderer.removeListener('zeus:hud:changed', listener)
    },
    // Linux only, and silent elsewhere: where the cursor is, in page
    // coordinates, or null when it has left the window. Stands in for the
    // mousemove that `setIgnoreMouseEvents(true, { forward: true })` delivers on
    // macOS and Windows but not here.
    onCursor: callback => {
      const listener = (_event, point) => callback(point)
      ipcRenderer.on('zeus:hud:cursor', listener)

      return () => ipcRenderer.removeListener('zeus:hud:cursor', listener)
    },
    // Main's game-overlay watch: whether a fullscreen app (a game) is under
    // the HUD, so the renderer can step back to the low-opacity overlay
    // treatment while one owns the screen.
    onGameOverlay: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('zeus:hud:game-overlay', listener)

      return () => ipcRenderer.removeListener('zeus:hud:game-overlay', listener)
    }
  },
  hudModifier: {
    getSettings: () => ipcRenderer.invoke('zeus:hud-modifier:settings:get'),
    setEnabled: enabled => ipcRenderer.invoke('zeus:hud-modifier:settings:set', enabled),
    openPermissionSettings: () => ipcRenderer.invoke('zeus:hud-modifier:permission'),
    onStatus: callback => {
      const listener = (_event: Electron.IpcRendererEvent, status: HudModifierStatus) => callback(status)
      ipcRenderer.on('zeus:hud-modifier:status', listener)

      return () => ipcRenderer.removeListener('zeus:hud-modifier:status', listener)
    }
  } satisfies HudModifierApi,
  // macOS native screenshot gesture; captures require a main-issued request.
  screenshot:
    process.platform === 'darwin'
      ? {
          getSettings: () => ipcRenderer.invoke('zeus:screenshot:settings:get'),
          setEnabled: enabled => ipcRenderer.invoke('zeus:screenshot:settings:set', enabled),
          openPermissionSettings: kind => ipcRenderer.invoke('zeus:screenshot:permission', kind),
          capture: requestId => ipcRenderer.invoke('zeus:screenshot:capture', requestId),
          onStatus: callback => {
            const listener = (_event, status) => callback(status)
            ipcRenderer.on('zeus:screenshot:status', listener)

            return () => ipcRenderer.removeListener('zeus:screenshot:status', listener)
          },
          onRequest: callback => {
            const channel = 'zeus:screenshot:request'
            const listener = (_event, requestId) => callback(requestId)

            if (ipcRenderer.listenerCount(channel) === 0) {
              ipcRenderer.send('zeus:screenshot:subscribe', true)
            }

            ipcRenderer.on(channel, listener)

            return () => {
              ipcRenderer.removeListener(channel, listener)

              if (ipcRenderer.listenerCount(channel) === 0) {
                ipcRenderer.send('zeus:screenshot:subscribe', false)
              }
            }
          }
        }
      : undefined,
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('zeus:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('zeus:quick-entry:settings:set', patch),
    // Invoke returns the delivery result so the draft is not lost (#85590).
    submit: payload => ipcRenderer.invoke('zeus:quick-entry:submit', payload),
    // Main cannot invoke the primary renderer, so it receives this ack (#85590).
    ackSubmit: (correlationId, result) => ipcRenderer.send('zeus:quick-entry:ack', { correlationId, result }),
    dismiss: () => ipcRenderer.send('zeus:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('zeus:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('zeus:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('zeus:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('zeus:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('zeus:quick-entry:shown', listener)
    },
    // Main → quick window: the outcome of a submit whose relay already timed
    // out. Delivery is now KNOWN — reconcile the unknown state instead of
    // leaving the user to resend a prompt that may already be delivered.
    onLateResult: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:quick-entry:late-result', listener)

      return () => ipcRenderer.removeListener('zeus:quick-entry:late-result', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('zeus:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('zeus:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('zeus:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('zeus:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('zeus:connection-config:test', payload),
  // Opt-in OS-keychain encryption for stored gateway secrets (default off —
  // see secret-storage-policy.ts). get never touches the OS keychain.
  getSecretStorageEncryption: () => ipcRenderer.invoke('zeus:secret-storage:get'),
  setSecretStorageEncryption: (on: boolean) => ipcRenderer.invoke('zeus:secret-storage:set', on),
  // v2 multi-connection registry: named agent sources (local / remote / cloud / ssh).
  connections: {
    list: () => ipcRenderer.invoke('zeus:connections:list'),
    save: payload => ipcRenderer.invoke('zeus:connections:save', payload),
    remove: id => ipcRenderer.invoke('zeus:connections:remove', id),
    setPrimary: id => ipcRenderer.invoke('zeus:connections:set-primary', id),
    setLaunchMode: mode => ipcRenderer.invoke('zeus:connections:set-launch-mode', mode),
    setLastUsed: id => ipcRenderer.invoke('zeus:connections:set-last-used', id),
    test: id => ipcRenderer.invoke('zeus:connections:test', id),
    updateManaged: id => ipcRenderer.invoke('zeus:connections:update-managed', id),
    // Fan out `zeus update` to every eligible registered connection.
    // Optional excludeIds skips rows the caller updates through another path.
    updateAll: options => ipcRenderer.invoke('zeus:connections:update-all', options),
    // Registry lifecycle push (main → renderer): a connection was removed or
    // materially edited, so secondaries scoped to it must be disposed (and,
    // for edits, re-dialed at the new target).
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:connections:changed', listener)

      return () => ipcRenderer.removeListener('zeus:connections:changed', listener)
    }
  },
  sshConfigHosts: () => ipcRenderer.invoke('zeus:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('zeus:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('zeus:connection-config:probe', remoteUrl),
  // `options` lets a registry-editor draft sign in BEFORE it is saved: the
  // main process settles the draft's connection id up front so the login
  // window writes into the per-connection cookie jar the saved entry will
  // read (not the legacy shared jar an unsaved URL would fall back to).
  oauthLoginConnectionConfig: (remoteUrl, options) =>
    ipcRenderer.invoke('zeus:connection-config:oauth-login', remoteUrl, options),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('zeus:connection-config:oauth-logout', remoteUrl),
  // Zeus Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('zeus:cloud:status'),
    login: () => ipcRenderer.invoke('zeus:cloud:login'),
    logout: () => ipcRenderer.invoke('zeus:cloud:logout'),
    discover: org => ipcRenderer.invoke('zeus:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('zeus:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    getDefault: () => ipcRenderer.invoke('zeus:profile:default:get'),
    setDefault: (route: DesktopProfileRoute) => ipcRenderer.invoke('zeus:profile:default:set', route),
    onDefaultChanged: (callback: (route: DesktopProfileRoute | null) => void) => {
      const listener = (_event: Electron.IpcRendererEvent, route: DesktopProfileRoute | null) => callback(route)
      ipcRenderer.on('zeus:profile:default:changed', listener)

      return () => ipcRenderer.removeListener('zeus:profile:default:changed', listener)
    },
    get: () => ipcRenderer.invoke('zeus:profile:get'),
    remember: name => ipcRenderer.invoke('zeus:profile:remember', name),
    set: name => ipcRenderer.invoke('zeus:profile:set', name)
  },
  // The handler resolves an expected 404 with a sentinel instead of rejecting
  // (Electron logs a stack for every rejected invoke). Turn it back into the
  // rejection the renderer expects — see electron/api-expected-404.ts.
  api: request => ipcRenderer.invoke('zeus:api', request).then(unwrapExpectedNotFound),
  notify: payload => ipcRenderer.invoke('zeus:notify', payload),
  claimStartupLatency: () => ipcRenderer.invoke('zeus:startup-latency:claim'),
  requestMicrophoneAccess: () => ipcRenderer.invoke('zeus:requestMicrophoneAccess'),
  readWindowBelow: () => ipcRenderer.invoke('zeus:window:readBelow'),
  readFileDataUrl: filePath => ipcRenderer.invoke('zeus:readFileDataUrl', filePath),
  readFileDataUrlForAttach: filePath => ipcRenderer.invoke('zeus:readFileDataUrlForAttach', filePath),
  dataUrlReadMax: {
    get: () => ipcRenderer.invoke('zeus:data-url-read-max:get'),
    set: maxMb => ipcRenderer.invoke('zeus:data-url-read-max:set', maxMb)
  },
  readFileText: filePath => ipcRenderer.invoke('zeus:readFileText', filePath),
  readPluginSource: (filePath: string) => ipcRenderer.invoke('zeus:readPluginSource', filePath),
  selectPaths: options => ipcRenderer.invoke('zeus:selectPaths', options),
  selectSavePath: options => ipcRenderer.invoke('zeus:selectSavePath', options),
  saveTextFileAs: request => ipcRenderer.invoke('zeus:saveTextFileAs', request),
  writeClipboard: text => ipcRenderer.invoke('zeus:writeClipboard', text),
  readClipboard: () => ipcRenderer.invoke('zeus:readClipboard'),
  saveGatewayFile: payload => ipcRenderer.invoke('zeus:saveGatewayFile', payload),
  saveImageFromUrl: url => ipcRenderer.invoke('zeus:saveImageFromUrl', url),
  contextMenuEdit: command => ipcRenderer.invoke('zeus:context-menu:edit', command),
  contextMenuCopyImage: () => ipcRenderer.invoke('zeus:context-menu:copy-image'),
  contextMenuSpellcheck: action => ipcRenderer.invoke('zeus:context-menu:spellcheck', action),
  contextMenuGuestAddWord: payload => ipcRenderer.invoke('zeus:context-menu:guest-add-word', payload),
  spellcheckDictionary: (op, word) => ipcRenderer.invoke('zeus:spellcheck:dictionary', { op, word }),
  onContextMenuSpellcheck: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:context-menu-spellcheck', listener)

    return () => ipcRenderer.removeListener('zeus:context-menu-spellcheck', listener)
  },
  saveImageBuffer: (data, ext, name) => ipcRenderer.invoke('zeus:saveImageBuffer', { data, ext, name }),
  capturePreview: payload => ipcRenderer.invoke('zeus:capturePreview', payload),
  savePastedText: text => ipcRenderer.invoke('zeus:savePastedText', { text }),
  saveClipboardImage: () => ipcRenderer.invoke('zeus:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('zeus:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('zeus:watchPreviewFile', url),
  watchDirectory: dir => ipcRenderer.invoke('zeus:watchDirectory', dir),
  stopPreviewFileWatch: id => ipcRenderer.invoke('zeus:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('zeus:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('zeus:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('zeus:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('zeus:translucency', payload),
  setKeepAwake: mode => ipcRenderer.send('zeus:keep-awake', mode),
  // Once per computer, after a timed sleep interrupted a turn with keep-awake off.
  onKeepAwakeOffer: callback => {
    const listener = () => callback()
    ipcRenderer.on('zeus:keep-awake-offer', listener)

    return () => ipcRenderer.removeListener('zeus:keep-awake-offer', listener)
  },
  minimizeToTray: {
    get: () => ipcRenderer.invoke('zeus:minimize-to-tray:get'),
    set: on => ipcRenderer.invoke('zeus:minimize-to-tray:set', on),
    onChanged: callback => {
      const listener = (_event, status) => callback(status)
      ipcRenderer.on('zeus:minimize-to-tray:changed', listener)

      return () => ipcRenderer.removeListener('zeus:minimize-to-tray:changed', listener)
    }
  },
  setDisableF12: blocked => ipcRenderer.send('zeus:devtools:disable-f12', blocked),
  setF12ShortcutActive: active => ipcRenderer.send('zeus:f12ShortcutActive', Boolean(active)),
  onF12Shortcut: callback => {
    const listener = (_event, input) => callback(input)
    ipcRenderer.on('zeus:f12-shortcut', listener)

    return () => ipcRenderer.removeListener('zeus:f12-shortcut', listener)
  },
  setPreviewShortcutActive: active => ipcRenderer.send('zeus:previewShortcutActive', Boolean(active)),
  setPreviewGuestHidden: (webContentsId, hidden) =>
    ipcRenderer.send('zeus:preview-guest-hidden', { webContentsId, hidden: Boolean(hidden) }),
  openExternal: url => ipcRenderer.invoke('zeus:openExternal', url),
  freeTierChallenge: {
    // Load the account service's challenge page in a hidden window (revealed
    // only if the page asks for the human). Resolves with how it ended.
    run: request => ipcRenderer.invoke('zeus:freeTierChallenge:run', request)
  },
  mcpOauth: {
    // One-shot loopback listener for MCP OAuth against remote backends: bind
    // on this machine, hand redirectUri to mcp.servers.oauth.start, then wait
    // for the provider redirect and relay code/state via oauth.callback.
    listen: () => ipcRenderer.invoke('zeus:mcp-oauth:listen'),
    wait: (id, timeoutMs) => ipcRenderer.invoke('zeus:mcp-oauth:wait', id, timeoutMs),
    cancel: id => ipcRenderer.invoke('zeus:mcp-oauth:cancel', id)
  },
  openPreviewInBrowser: url => ipcRenderer.invoke('zeus:openPreviewInBrowser', url),
  reachPreviewUrl: url => ipcRenderer.invoke('zeus:preview:reach', url),
  setActiveConnectionRoute: route => ipcRenderer.send('zeus:connection:active-route', route),
  fetchLinkTitle: url => ipcRenderer.invoke('zeus:fetchLinkTitle', url),
  resolveFavicon: url => ipcRenderer.invoke('zeus:resolveFavicon', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('zeus:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('zeus:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('zeus:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('zeus:setting:defaultProjectDir:pick')
  },
  preparedSubmissions: {
    read: () => ipcRenderer.invoke('zeus:prepared-submissions:read'),
    update: (key, entry) => ipcRenderer.invoke('zeus:prepared-submissions:update', key, entry),
    compareAndSet: (key, expected, entry) =>
      ipcRenderer.invoke('zeus:prepared-submissions:compare-and-set', key, expected, entry)
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('zeus:zoom:get'),
    // Synchronous zoom factor (1 = 100%). Coordinate math needs it in the
    // same tick as the event it converts, so no IPC round-trip here.
    factor: () => webFrame.getZoomFactor(),
    setPercent: percent => ipcRenderer.send('zeus:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:zoom:changed', listener)

      return () => ipcRenderer.removeListener('zeus:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('zeus:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('zeus:logs:recent'),
  // Fire-and-forget: persists a renderer error-boundary catch (with component
  // stack) to desktop.log so crashes survive the window (#79428).
  reportRendererError: report => ipcRenderer.send('zeus:logs:renderer-error', report),
  logLine: (line: string): void => ipcRenderer.send('zeus:logs:renderer-line', line),
  readDir: dirPath => ipcRenderer.invoke('zeus:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('zeus:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('zeus:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('zeus:fs:openDir', dirPath),
  desktopPluginsRoot: () => ipcRenderer.invoke('zeus:fs:desktopPluginsRoot'),
  reconcileDesktopPlugins: async () => (await ipcRenderer.invoke('zeus:fs:reconcileDesktopPlugins')).published,
  reconcileDesktopPluginsReport: () => ipcRenderer.invoke('zeus:fs:reconcileDesktopPlugins'),
  logsRoot: (profile?: string) => ipcRenderer.invoke('zeus:fs:logsRoot', profile),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('zeus:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('zeus:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('zeus:fs:trash', targetPath),
  pluginFiles: {
    request: (pluginId, labels) => ipcRenderer.invoke('zeus:pluginFiles:request', pluginId, labels),
    grants: pluginId => ipcRenderer.invoke('zeus:pluginFiles:grants', pluginId),
    revoke: (pluginId, folderId) => ipcRenderer.invoke('zeus:pluginFiles:revoke', pluginId, folderId),
    op: (pluginId, request) => ipcRenderer.invoke('zeus:pluginFiles:op', pluginId, request),
    onChanged: callback => {
      const listener = (_event, change) => callback(change)
      ipcRenderer.on('zeus:pluginFiles:changed', listener)

      return () => ipcRenderer.removeListener('zeus:pluginFiles:changed', listener)
    }
  },
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('zeus:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('zeus:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('zeus:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('zeus:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('zeus:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('zeus:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('zeus:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('zeus:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('zeus:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('zeus:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('zeus:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('zeus:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('zeus:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('zeus:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('zeus:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('zeus:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('zeus:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('zeus:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('zeus:git:review:shipInfo', repoPath),
      prList: (repoPath, branches, numbers) =>
        ipcRenderer.invoke('zeus:git:review:prList', repoPath, branches, numbers),
      createPr: repoPath => ipcRenderer.invoke('zeus:git:review:createPr', repoPath)
    }
  },
  terminal: {
    attach: id => ipcRenderer.invoke('zeus:terminal:attach', id),
    cwd: id => ipcRenderer.invoke('zeus:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('zeus:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('zeus:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('zeus:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('zeus:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `zeus:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `zeus:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('zeus:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('zeus:close-preview-requested', listener)
  },
  onPreviewNav: callback => {
    const listener = (_event, command) => callback(command)
    ipcRenderer.on('zeus:preview-nav', listener)

    return () => ipcRenderer.removeListener('zeus:preview-nav', listener)
  },
  onOpenFolderRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('zeus:open-folder-requested', listener)

    return () => ipcRenderer.removeListener('zeus:open-folder-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('zeus:open-updates', listener)

    return () => ipcRenderer.removeListener('zeus:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:deep-link', listener)

    return () => ipcRenderer.removeListener('zeus:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('zeus:deep-link-ready'),
  probePluginRepo: payload => ipcRenderer.invoke('zeus:plugin:probe', payload),
  installDesktopPlugin: payload => ipcRenderer.invoke('zeus:plugin:installDesktop', payload),
  removeDesktopPlugin: payload => ipcRenderer.invoke('zeus:plugin:removeDesktop', payload),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:window-state-changed', listener)

    return () => ipcRenderer.removeListener('zeus:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('zeus:focus-session', listener)

    return () => ipcRenderer.removeListener('zeus:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:notification-action', listener)

    return () => ipcRenderer.removeListener('zeus:notification-action', listener)
  },
  onNotificationActivate: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:notification-activate', listener)

    return () => ipcRenderer.removeListener('zeus:notification-activate', listener)
  },
  onExternalOpenFailed: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:external-open-failed', listener)

    return () => ipcRenderer.removeListener('zeus:external-open-failed', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('zeus:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:backend-exit', listener)

    return () => ipcRenderer.removeListener('zeus:backend-exit', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('zeus:connection:applied', listener)

    return () => ipcRenderer.removeListener('zeus:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('zeus:power-resume', listener)

    return () => ipcRenderer.removeListener('zeus:power-resume', listener)
  },
  // AC ↔ battery transitions; renderers slow their backstop polls on battery.
  getOnBattery: () => ipcRenderer.invoke('zeus:power-battery:get'),
  onBatteryChanged: callback => {
    const listener = (_event, onBattery) => callback(Boolean(onBattery))
    ipcRenderer.on('zeus:power-battery', listener)

    return () => ipcRenderer.removeListener('zeus:power-battery', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:boot-progress', listener)

    return () => ipcRenderer.removeListener('zeus:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('zeus:bootstrap:get'),
  probeLocalBackend: () => ipcRenderer.invoke('zeus:local-backend:probe'),
  continueBootstrapLocal: () => ipcRenderer.invoke('zeus:bootstrap:continue-local'),
  recycleBackend: profile => ipcRenderer.invoke('zeus:backend:recycle', profile),
  resetBootstrap: () => ipcRenderer.invoke('zeus:bootstrap:reset'),
  updateHold: {
    recheck: () => ipcRenderer.invoke('zeus:update-hold:recheck'),
    quit: () => ipcRenderer.invoke('zeus:update-hold:quit'),
    startAnyway: (request: { holdId: string; confirmed: true }) =>
      ipcRenderer.invoke('zeus:update-hold:start-anyway', request)
  },
  repairBootstrap: () => ipcRenderer.invoke('zeus:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('zeus:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('zeus:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('zeus:bootstrap:event', listener)
  },
  getVersion: (scope?: { connectionId?: string; profile?: string }) => ipcRenderer.invoke('zeus:version', scope),
  relaunchApp: () => ipcRenderer.invoke('zeus:app:relaunch'),
  getMachineProfile: () => ipcRenderer.invoke('zeus:machine:profile'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('zeus:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('zeus:uninstall:summary'),
    run: mode => ipcRenderer.invoke('zeus:uninstall:run', { mode }),
    openAppsSettings: () => ipcRenderer.invoke('zeus:uninstall:openAppsSettings')
  },
  updates: {
    check: opts => ipcRenderer.invoke('zeus:updates:check', opts),
    apply: opts => ipcRenderer.invoke('zeus:updates:apply', opts),
    setChannel: name => ipcRenderer.invoke('zeus:updates:channel:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('zeus:updates:progress', listener)

      return () => ipcRenderer.removeListener('zeus:updates:progress', listener)
    },
    takePendingRun: () => ipcRenderer.invoke('zeus:updates:metric:take'),
    ackPendingRun: sent => ipcRenderer.invoke('zeus:updates:metric:ack', sent),
    onPendingRun: callback => {
      const listener = () => callback()
      ipcRenderer.on('zeus:updates:metric:pending', listener)

      return () => ipcRenderer.removeListener('zeus:updates:metric:pending', listener)
    }
  },
  desktopMetrics: {
    setEnabled: (on, profile) => ipcRenderer.invoke('zeus:desktop-metrics:set-enabled', on, profile),
    takeRendererCrashes: () => ipcRenderer.invoke('zeus:desktop-metrics:crash:take'),
    ackRendererCrashes: sent => ipcRenderer.invoke('zeus:desktop-metrics:crash:ack', sent)
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('zeus:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('zeus:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('zeus:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('zeus:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('zeus:found-in-page', listener)

    return () => ipcRenderer.removeListener('zeus:found-in-page', listener)
  },
  // Main-process `before-input-event` forwards Ctrl/Cmd+F here so renderer
  // can open the FindBar even when the GTK compositor has already grabbed
  // the chord at the windowing layer (#81727).
  onOpenFindBarRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('zeus:open-find-bar', listener)

    return () => ipcRenderer.removeListener('zeus:open-find-bar', listener)
  }
})
