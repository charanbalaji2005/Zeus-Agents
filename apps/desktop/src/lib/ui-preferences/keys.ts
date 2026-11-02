/**
 * Which persisted keys are machine-level UI preferences (#145213).
 *
 * Only these leave localStorage for the machine's shared store, so native
 * Desktop and every browser that opens this machine's Webapp show the same
 * choices. Scoped families keep their scope inside the key name (a
 * `….profile.<name>` or per-connection suffix): only the location changes.
 *
 * Deliberately NOT here (they stay in this browser/window):
 * - credentials, grants and connection config: gateway registry, custom model
 *   endpoints, plugin decisions and preview-script grants, embed permissions;
 * - per-window or per-device runtime state: layout tree, open tiles and tabs,
 *   last route/session, scroll, zoom, pet and popout geometry, keep-awake;
 * - drafts, queues, journals and caches: composer queue, in-flight turns,
 *   pending/prepared submissions, previews, pricing, backend skin cache, the
 *   "provider configured" onboarding cache (each backend answers that itself);
 * - one-off notices: butterbar, update and real-profile prompts.
 */

const SHARED_KEYS: ReadonlySet<string> = new Set([
  // Appearance.
  'zeus-desktop-theme-v2',
  'zeus-desktop-mode-v1',
  'zeus-desktop-profile-themes-v1',
  'zeus-desktop-profile-modes-v1',
  'zeus-desktop-user-themes-v1',
  'zeus.desktop.backdrop.v1',
  'zeus.desktop.chat-text-scale.v1',
  'zeus.desktop.interfaceMode.v1',
  'zeus.desktop.textDirection',
  'zeus.desktop.translucency.v2',
  'zeus.desktop.user-bubble-transparency.v1',
  // Sessions sidebar and profile rail.
  'zeus.desktop.agentsGroupedByWorkspace',
  'zeus.desktop.profileColors',
  'zeus.desktop.profileOrder',
  'zeus.desktop.profileRailVisible',
  'zeus.desktop.sessionListDensity',
  'zeus.desktop.sessionOrder',
  'zeus.desktop.sessionOrder.manual',
  'zeus.desktop.showAllProfiles',
  'zeus.desktop.sidebarAgentsGrouped.allProfiles',
  'zeus.desktop.sidebarCardRows',
  'zeus.desktop.sidebarGrouping',
  'zeus.desktop.sidebarGrouping.allProfiles',
  'zeus.desktop.sidebarRowMeta',
  'zeus.desktop.sidebarShowAllSessions',
  'zeus.desktop.sidebarShowArchived',
  'zeus.desktop.sidebarSortKey',
  // Status bar.
  'zeus.desktop.statusbarHidden.v2',
  'zeus.desktop.statusbarVisible.v2',
  // Transcript and tools.
  'zeus.desktop.hideThreadTimeline',
  'zeus.desktop.reasoning.collapsedByDefault',
  'zeus.desktop.toolView.hideCodeDiffs',
  'zeus.desktop.toolView.technical',
  // Shell, panes and behaviour.
  'zeus.desktop.alwaysExternalLinks.v1',
  'zeus.desktop.capabilities.catalogCardView',
  'zeus.desktop.composerPopout.enabled',
  'zeus.desktop.composerPopout.gesturesEnabled',
  'zeus.desktop.files.showIgnored',
  'zeus.desktop.keybinds',
  'zeus.desktop.layoutPresets.v2',
  'zeus.desktop.panesFlipped',
  'zeus.desktop.tabStripDefault',
  'zeus.desktop.titlebarAppActions',
  // Guidance: what the user already skipped, saw or dismissed does not come
  // back in every new browser or origin (#145600).
  'zeus-onboarding-skipped-v1',
  'zeus.desktop.tips.last.v1',
  'zeus.desktop.tips.next.v1',
  'zeus.desktop.tips.retired.v1',
  'zeus.desktop.tips.rotation.v1',
  'zeus.desktop.tips.shownAt.v1',
  'zeus.desktop.tours.v1',
  // Sound and media.
  'zeus.desktop.autoSpeakReplies',
  'zeus.desktop.completionSoundVariantId',
  'zeus.desktop.hapticsMuted',
  'zeus.desktop.videoPlaybackSpeed',
  // Model picker.
  'zeus.desktop.collapsed-providers',
  'zeus.desktop.favorite-models',
  // visible-models is a diff against known-models: they only make sense together.
  'zeus.desktop.known-models',
  'zeus.desktop.model-presets',
  'zeus.desktop.visible-models'
])

/** Families whose scope rides in the key suffix (gateway aliases/order/collapsed). */
const SHARED_PREFIXES: readonly string[] = ['zeus.desktop.sidebar.gatewayGroups.v1.']

export function isSharedPreferenceKey(key: string): boolean {
  return SHARED_KEYS.has(key) || SHARED_PREFIXES.some(prefix => key.startsWith(prefix))
}
