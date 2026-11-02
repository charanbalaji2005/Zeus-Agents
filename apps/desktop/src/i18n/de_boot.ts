import type { TranslationOverrides } from './define-locale'

// The boot screen's copy (including the update-hold screen), composed by de.ts.
export const deBoot = {
  boot: {
    ready: 'Zeus Desktop ist bereit',
    desktopBootFailedWithMessage: message => `Desktop-Start fehlgeschlagen: ${message}`,
    steps: {
      connectingGateway: 'Live-Desktop-Gateway wird verbunden',
      loadingSettings: 'Zeus-Einstellungen werden geladen',
      loadingSessions: 'Letzte Sessions werden geladen',
      retryingRemoteBackend: 'Wird mit dem Remote-Zeus-Backend neu verbunden…',
      startingDesktopConnection: 'Desktop-Verbindung wird gestartet',
      startingZeusDesktop: 'Zeus Desktop wird gestartet…'
    },
    errors: {
      backgroundExited: 'Der Zeus-Hintergrundprozess wurde beendet.',
      backgroundExitedDuringStartup: 'Der Zeus-Hintergrundprozess wurde während des Starts beendet.',
      backendStopped: 'Backend gestoppt',
      restartZeus: 'Zeus neu starten',
      openLogs: 'Logs öffnen',
      desktopBootFailed: 'Desktop-Start fehlgeschlagen',
      gatewayConnectionLost: 'Verbindung zum Gateway verloren',
      gatewayConnectionLostDetail:
        'Im Hintergrund wird weiterhin versucht, die Verbindung herzustellen. Sie können weiterlesen und weiterschreiben – öffnen Sie die Gateway-Einstellungen, falls das anhält.',
      reconnectNow: 'Jetzt neu verbinden',
      connectionSettings: 'Verbindungseinstellungen',
      gatewaySignInRequired: 'Gateway-Sign-in erforderlich',
      gatewaySignInRequiredDetail:
        'Melden Sie sich erneut an, um die Verbindung wiederherzustellen. Ihre Chats und Einstellungen sind sicher.',
      signInAgain: 'Erneut anmelden',
      ipcBridgeUnavailable: 'Der Desktop-IPC-Bridge ist nicht verfügbar.'
    },
    causes: {
      exitedEarly: 'Der Hintergrunddienst von Zeus hat direkt nach dem Start aufgehört.',
      timedOut: 'Der Hintergrunddienst von Zeus hat nicht rechtzeitig geantwortet.',
      permission: 'Zeus konnte nicht in seinen Datenordner schreiben (Berechtigungsproblem).',
      diskFull: 'Die Festplatte ist voll, deshalb konnte Zeus nicht starten.',
      portInUse: 'Ein anderes Programm verwendet den Netzwerkport, den Zeus braucht.',
      installMissing:
        'Ein Teil der Zeus-Installation fehlt. Wählen Sie „Installation reparieren“, um sie wiederherzustellen.'
    },
    failure: {
      title: 'Zeus konnte nicht gestartet werden',
      description:
        'Das Hintergrund-Gateway ist nicht gestartet. Probieren Sie einen der Wiederherstellungsschritte unten. Keiner davon löscht Ihre Chats oder Einstellungen.',
      details: 'Details',
      remoteTitle: 'Remote-Gateway-Sign-in erforderlich',
      remoteDescription:
        'Ihre Remote-Gateway-Session ist abgelaufen. Melden Sie sich erneut an, um die Verbindung wiederherzustellen. Keiner dieser Schritte löscht Ihre Chats oder Einstellungen.',
      retry: 'Erneut versuchen',
      repairInstall: 'Installation reparieren',
      useLocalGateway: 'Lokales Gateway verwenden',
      gatewaySettings: 'Gateway-Einstellungen',
      back: 'Zurück',
      openLogs: 'Logs öffnen',
      repairHint:
        'Die Reparatur führt den Installer erneut aus und kann auf einem frischen Computer ein paar Minuten dauern.',
      remoteSignInHint: signInLabel =>
        `Meldet Sie von der gespeicherten Remote-Browser-Session ab und öffnet dann ${signInLabel}. Verwenden Sie das lokale Gateway, um stattdessen zum integrierten Backend zu wechseln.`,
      signOutAndSignIn: 'Abmelden & anmelden',
      remoteFailureHint:
        'Überprüfen Sie die Gateway-URL und die Anmeldung in den Gateway-Einstellungen, oder wechseln Sie zum lokalen Gateway.',
      cloudDownTitle: 'Nous Cloud Agent ist down',
      cloudDownDescription:
        'Der von Nous verwaltete Cloud-Agent, mit dem sich dieses Gateway verbindet, meldet einen Serverfehler. Er kann von hier aus nicht neu gestartet werden – prüfen Sie seinen Status, wechseln Sie zum lokalen Gateway oder wenden Sie sich an den Support.',
      cloudDownHint:
        'Die Schaltflächen unten öffnen das Nous Portal (Instanzstatus und Steuerung) und unseren Discord für Support.',
      cloudDownCheckPortal: 'Portal-Status prüfen',
      cloudDownDiscord: 'Hilfe auf Discord holen',
      hideRecentLogs: 'Neueste Logs ausblenden',
      showRecentLogs: 'Neueste Logs anzeigen',
      signedInTitle: 'Angemeldet',
      signedInMessage: 'Wird mit dem Remote-Gateway neu verbunden…',
      signInIncompleteTitle: 'Sign-in unvollständig',
      signInIncompleteMessage: 'Das Anmeldefenster wurde geschlossen, bevor die Authentifizierung abgeschlossen war.',
      signInFailed: 'Sign-in fehlgeschlagen',
      signInToRemoteGateway: 'Beim Remote-Gateway anmelden',
      signInWithProvider: provider => `Mit ${provider} anmelden`,
      identityProvider: 'Ihr Identity-Provider'
    },
    updateHold: {
      title: 'Ein früheres Update hält Zeus noch fest',
      titleUnverified: 'Zeus kann nicht bestätigen, dass das letzte Update fertig ist',
      description:
        'Zeus startet noch nicht, damit es keine Dateien lädt, die ein Update womöglich noch ändert. Sobald die Sperre endet, startet Zeus von selbst.',
      heldByProcess: pid =>
        `Das Update (Prozess ${pid}) wurde beendet, aber ein von ihm gestarteter Prozess hält die Zeus-Installation noch fest.`,
      heldUnknown:
        'Ein Update wurde beendet, aber ein von ihm gestarteter Prozess hält die Zeus-Installation noch fest.',
      unverified:
        'Der Update-Helfer konnte gerade nicht prüfen, wem die Zeus-Installation gehört. Zeus prüft weiter.',
      since: time => `Wartet seit ${time}`,
      lastChecked: time => `Zuletzt geprüft ${time}`,
      recoveryHint:
        'Das löst sich meist in wenigen Minuten. Falls nicht: Zeus beenden, übrig gebliebene git- oder zeus-Prozesse beenden (oder den Computer neu starten) und Zeus erneut öffnen.',
      checkAgain: 'Erneut prüfen',
      quit: 'Zeus beenden',
      openLogs: 'Logs öffnen',
      startAnyway: 'Trotzdem starten…',
      confirmTitle: 'Zeus starten, obwohl das Update es noch festhält?',
      confirmBody:
        'Der übrig gebliebene Update-Prozess ändert womöglich noch Dateien von Zeus. Ein Start jetzt kann eine halb aktualisierte Installation laden, die erst nach einem erneuten Update wieder funktioniert. Zeus protokolliert diese Entscheidung und lässt die Update-Markierung bestehen.',
      confirmKeepWaiting: 'Weiter warten',
      confirmStart: 'Trotzdem starten',
      startAnywayRefused:
        'Was die Installation festhält, hat sich geändert, bevor Zeus starten konnte. Bitte erneut prüfen.'
    }
  }
} satisfies Pick<TranslationOverrides, 'boot'>
