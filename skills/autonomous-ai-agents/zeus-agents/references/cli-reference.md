# Zeus CLI Reference

Live sources when anything looks stale: `zeus --help`, `zeus <command> --help`,
https://charanbalaji2005.github.io/Zeus-Agents/docs/reference/cli-commands

### Global Flags

```
zeus [flags] [command]        (no subcommand = interactive chat)

  --version, -V             Show version
  -z, --oneshot PROMPT      One-shot: print ONLY the final response (for scripts/pipes)
  -m MODEL  --provider P    Model/provider override for this invocation
  -t, --toolsets LIST       Comma-separated toolsets for this invocation
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --tui / --cli             Force the Ink TUI / classic REPL
  --ignore-rules            Skip AGENTS.md/SOUL.md/memory/skill injection
  --safe-mode               Disable ALL customizations (troubleshooting)
  --pass-session-id         Include session ID in system prompt
```

### Chat

```
zeus chat [flags]
  -q, --query TEXT          Single query, non-interactive
  --image PATH              Attach a local image to a single query
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --max-turns N             Cap tool-calling iterations
  --source TAG              Session source tag (default: cli)
```
(plus the global flags above)

### Configuration

```
zeus setup [section]      Wizard (model|tts|terminal|gateway|tools|agent)
zeus model                Interactive model/provider picker
zeus fallback [add|remove|list]  Fallback provider chain
zeus config [show|edit|get|set|unset|path|env-path|check|migrate]
zeus login / logout       OAuth sign-in / clear stored auth
zeus doctor [--fix]       Check dependencies and config
zeus status [--full]      Component summary (--full: every section)
```

### Tools & Skills

```
zeus tools [list|enable NAME|disable NAME]   Per-platform toolsets (curses UI with no args)

zeus skills list|browse|search QUERY|inspect ID
zeus skills install ID    Hub identifier OR a direct https://…/SKILL.md URL
zeus skills config        Enable/disable skills per platform
zeus skills check|update|uninstall|publish PATH
zeus skills tap add REPO  Add a GitHub repo as a skill source
zeus bundles              Skill bundles (one /<name> alias loads several skills)
```

### MCP Servers

```
zeus mcp add NAME (--url or --command) | remove | list | test NAME
zeus mcp catalog | install NAME     Curated catalog install
zeus mcp configure NAME             Toggle tool selection
zeus mcp-serve                      Run Zeus as an MCP server (mcp-serve plugin)
```
Details (transport, tool discovery, catalog): `references/native-mcp.md`.

### Gateway (Messaging Platforms)

```
zeus gateway run|install|start|stop|restart|status|setup
```

20+ platforms: Telegram, Discord, Slack, WhatsApp (Baileys + Business Cloud API), iMessage (Photon — `zeus photon setup`), Signal, Email, SMS, Matrix, Mattermost, Teams, LINE, SimpleX, ntfy, Google Chat, Home Assistant, DingTalk, Feishu, WeCom, Weixin, API Server, Webhooks. Open WebUI connects via the API Server adapter. Most adapters ship under `plugins/platforms/`.
Docs: https://charanbalaji2005.github.io/Zeus-Agents/docs/user-guide/messaging/

### Sessions

```
zeus sessions list|browse|rename ID TITLE|delete ID|export OUT|prune|stats
```

### Cron / Webhooks

```
zeus cron list|create SCHED|edit ID|pause|resume|run ID|remove|status
    Schedules: '30m', 'every 2h', '0 9 * * *', ISO timestamp
zeus webhook subscribe NAME|list|remove NAME|test NAME
```
Webhook payloads/routes: `references/webhooks.md`.

### Profiles

```
zeus profile list|create NAME (--clone|--clone-all|--clone-from)|use|show|delete
zeus profile rename A B | alias NAME | export NAME | import FILE
zeus profile migrate-identity A B   Retry a completed rename's session/routing identity migration
```

### Credentials & Pools

```
zeus auth                 Interactive credential manager
zeus auth add [PROVIDER]  Add OAuth or API-key credential (nous, openai-codex, qwen-oauth, …)
zeus auth list|remove P IDX|reset PROVIDER|status
```
Multiple credentials per provider form a pool that rotates automatically and skips exhausted keys.

### Other

```
zeus desktop / gui        Native desktop app
zeus dashboard            Web admin panel + embedded chat (--stop / --status)
zeus proxy                OpenAI-compatible local proxy backed by an OAuth provider
zeus portal               Quick setup / sign in via Nous Portal
zeus kanban <verb>        Multi-agent work-queue board
zeus project              Named multi-folder workspaces
zeus skin list|use|set    Switch/tweak skins (see references/themes.md)
zeus pets <verb>          Pet mascots (see references/petdex.md)
zeus memory setup|status|off|reset   Memory provider
zeus secrets bitwarden|onepassword   External secret stores
zeus moa                  Mixture-of-Agents slots
zeus hooks / security / backup / import / checkpoints / console
zeus logs [-f] [errors]   View agent/error logs
zeus send                 One-off message through a gateway platform
zeus pairing / plugins / insights / journey / computer-use
zeus acp                  ACP server (IDE integration)
zeus completion bash|zsh|fish
zeus update / uninstall
```

Plugin- and provider-supplied subcommands (e.g. `zeus photon setup`) only appear once their plugin is installed/active. Importing from OpenClaw, Claude Code, Codex CLI or Cursor (`zeus import-agent <agent>`, plus the older `zeus claw migrate|cleanup`) comes from the `agent-importers` plugin; a fresh `zeus setup` that finds one of those agents offers to install it.

### Where to Find Things

| Looking for... | Location |
|---|---|
| Config options | `zeus config edit` · [Configuration docs](https://charanbalaji2005.github.io/Zeus-Agents/docs/user-guide/configuration) |
| Tools / toolsets | `zeus tools list` · [Tools reference](https://charanbalaji2005.github.io/Zeus-Agents/docs/reference/tools-reference) |
| Skills catalog | `zeus skills browse` · [Skills catalog](https://charanbalaji2005.github.io/Zeus-Agents/docs/reference/skills-catalog) |
| Provider setup | `zeus model` · [Providers guide](https://charanbalaji2005.github.io/Zeus-Agents/docs/integrations/providers) |
| Env variables | `zeus config env-path` · [Env vars reference](https://charanbalaji2005.github.io/Zeus-Agents/docs/reference/environment-variables) |
| Gateway logs | `~/.zeus/logs/gateway.log` (or `zeus logs`) |
| Sessions | `zeus sessions browse` (reads state.db) |
