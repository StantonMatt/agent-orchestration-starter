# Agent orchestration starter

A starter trimmed from a real working setup for Claude Code with a Claude
subscription. The main session plans and delegates; role-specific subagents do
scoped work, and a fresh reviewer checks each review round before commits.
Read it and adapt it rather than installing it blind.

## Roles

| Role | Agent | Default model / effort | What it does |
| --- | --- | --- | --- |
| Orchestrator | Main session | Your choice | Plans, briefs, verifies, integrates and owns review |
| Research | `scout` | `claude-haiku-5-5` / xhigh | Read-only prep, lookups and mechanical checks |
| Implementation | `worker` | `claude-opus-5-5` / high | Code, tests, docs, browser and 3D work |
| Design | `designer` | `claude-opus-5-5` / xhigh | Screens, flows, visual work and product checks |
| Advice | `advisor` | `claude-fable-5-2` / xhigh | Independent read-only advice; a second instance uses `model: opus` |
| Review | `reviewer` | `claude-opus-5-5` / xhigh | Fresh read-only review each round |

## How a task flows

1. The orchestrator scopes the task and sends scouts for prep.
2. Workers build independent parts in parallel. UI features start with a designer.
3. The orchestrator verifies and integrates the results, including real UI flows.
4. `review-fix-loop` uses a fresh reviewer each round. Fixes get affected checks
   and another round until approved within the budget.
5. Commit only approved changes. Push when authorized and ready; let CI run its
   full suites, then merge only when checks are green.

Subagents use Claude Code's Agent tool and do not start more subagents. Workers
run in the background by default. The main session supervises and owns the result.

## Files

- [instructions/CLAUDE.md](instructions/CLAUDE.md): global orchestration and working rules.
- [agents/](agents/): the five role definitions and their model defaults.
- [skills/delegate-work/](skills/delegate-work/SKILL.md): briefs, parallel work, verification and optional CLI workers.
- [skills/review-fix-loop/](skills/review-fix-loop/SKILL.md): bounded review loop, native reviewer instructions and tree fingerprints.
- [skills/full-send/](skills/full-send/SKILL.md): carry authorized work through publication and checks.
- [skills/full-stop/](skills/full-stop/SKILL.md): prepare and verify a pull request, then leave it open and unmerged.
- [skills/babysit-pr/](skills/babysit-pr/SKILL.md): watch a pull request and handle actionable failures.
- [bin/heavy](bin/heavy): optional gate for finite resource-intensive commands.
- [install.sh](install.sh): symlink installer; [tests/](tests/test_install.py): isolated installer checks.
- [LICENSE](LICENSE): MIT license for this repo.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): attribution and upstream license text.
- [.gitignore](.gitignore): local generated files.

## Install

Requires Claude Code, Bash and Python 3. Linux and macOS are supported; the
installer uses Bash 3.2-compatible syntax. Choose models available on your plan
before use. Keep this checkout in place: installed files link back to it.

```sh
./install.sh --dry-run
./install.sh
```

This links skills into `~/.claude/skills/`, agent definitions into
`~/.claude/agents/`, and instructions into `~/.claude/CLAUDE.md`. Existing regular
files or directories are renamed to `<path>.bak-<UTC stamp>` (with a counter on
collision). Existing destination symlinks are replaced; their targets are untouched.
Symlinked parent directories are refused. Correct links print `ok` on rerun.
It checks all selected sources before writing and does not edit `settings.json`.
Read any existing global instructions and merge rules you need before replacing them.

Flags may be combined:

- `--dry-run`: show planned changes without writing anything.
- `--codex`: also link skills into `~/.agents/skills/` and instructions into
  `~/.codex/AGENTS.md`. This does not install Claude's named agents into Codex.
- `--with-heavy`: also link `bin/heavy` into `~/.local/bin/heavy`.

Run installer checks with:

```sh
python3 -m unittest discover -s tests
```

Tests use a fixture repo and a throwaway home directory, not your configuration.

## Adapt it

Give your agent this prompt:

> Read this repo, ask me which tools, models and subscriptions I have, then write
> a minimal version for me, starting with the role split and the review loop.

Start small: one worker, a read-only scout, and a fresh reviewer before commits.
Add rules when real problems show up. Keep project-specific requirements in each
project, and remove integrations you do not use.

Change `model` and `effort` in [agents/](agents/) to fit your plan and the model IDs
your Claude Code version supports. Update the role table and instruction defaults
to match. The Opus second advisor uses the Agent tool's `model: opus` override.
Model availability and supported effort settings can change; confirm them locally.
Use narrow briefs and small research inputs to keep subscription usage predictable.

Codex CLI is optional. See [Codex workers](skills/delegate-work/references/codex-workers.md)
for the separate worker route. Installing `--codex` makes skills discoverable;
it does not give Codex Claude Code's Agent or SendMessage tools. The default
orchestrator and authoritative reviewer remain in Claude Code.

If installed, use `~/.local/bin/heavy <command> ...` for full suites, builds and
whole-project type checks. Focused tests and development servers run directly.
It is a command gate, not a sandbox; see [bin/heavy](bin/heavy) for its limits.

## Credits

`full-send`, `full-stop` and `babysit-pr` are adapted from
[t3dotgg/tstack](https://github.com/t3dotgg/tstack), MIT.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

MIT. See [LICENSE](LICENSE).
