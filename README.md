# Agent orchestration starter

A starter trimmed from a real working setup for Claude Code and Codex CLI.
The main session plans and delegates; role-specific children do
scoped work, and a fresh reviewer checks each review round before commits.
Read it and adapt it rather than installing it blind.

## Roles

| Role | Codex + Claude (default) | Claude only | Codex only |
|---|---|---|---|
| Orchestrator (main session) | Claude Code (any model) | Claude Code | Codex CLI |
| Workers (implementation, refactors, tests, debugging, scripts, docs, browser, 3D) | `gpt-6.1-sol` at high, run as `codex exec` | `worker` agent, `claude-opus-5-5` at high | `gpt-6.1-sol` at high, `codex exec` |
| Browser work in the user's real Chrome | `gpt-6.1-terra` at medium with Codex's Chrome plugin | `worker` agent with Claude in Chrome | `gpt-6.1-terra` at medium with Codex's Chrome plugin |
| Scouts (read-only research) | `scout` agent, `claude-haiku-5-5` at xhigh | same | `gpt-6.1-terra` at high, read-only `codex exec`, with the `scout` role text |
| Designer | `designer` agent, `claude-opus-5-5` at xhigh | same | `gpt-6.2-astra` at xhigh, `codex exec`, with the `designer` role text |
| Advisors (4 / 2 / 3, all xhigh, all started at once) | `advisor` (`claude-fable-5-2`), `advisor` with `model: opus`, `gpt-6-astra`, `gpt-6.2-astra` | Fable and Opus `advisor` agents | `gpt-6-astra`, `gpt-6.2-astra`, `gpt-6.2-sol` |
| Authoritative reviewer (fresh each round) | Codex `gpt-6.1-sol` at high, `codex exec review`, read-only | `reviewer` agent, `claude-opus-5-5` at xhigh | Codex `gpt-6.1-sol` at high, `codex exec review` |
| Review tiebreak | `gpt-6-astra` at xhigh, read-only | Fable and Opus `advisor` agents | `gpt-6-astra` at xhigh, read-only |

Set `Active setup: Codex + Claude` near the top of [instructions/CLAUDE.md](instructions/CLAUDE.md),
or choose `Claude only` or `Codex only`. Codex only needs a Codex CLI main session.
Codex + Claude needs both a Claude subscription and authenticated Codex CLI with
access to the listed models. Model names and availability change; use models your plans offer.

## How a task flows

1. The orchestrator scopes the task and sends scouts for prep.
2. Workers build independent parts in parallel. UI features start with a designer.
3. The orchestrator verifies and integrates the results, including real UI flows.
4. `review-fix-loop` uses a fresh reviewer each round. Fixes get affected checks
   and another round until approved within the budget.
5. Commit only approved changes. Push when authorized and ready; let CI run its
   full suites, then merge only when checks are green.

Claude children use Claude Code's Agent tool; Codex children use `codex exec`.
Children do not start more children. Workers run in parallel when independent.
The main session supervises and owns the result.

## Files

- [instructions/CLAUDE.md](instructions/CLAUDE.md): global orchestration and working rules.
- [agents/](agents/): the five role definitions and their model defaults.
- [skills/delegate-work/](skills/delegate-work/SKILL.md): briefs, parallel work, verification and Codex children.
- [skills/review-fix-loop/](skills/review-fix-loop/SKILL.md): bounded review loop, reviewer routes and tree fingerprints.
- [skills/full-send/](skills/full-send/SKILL.md): carry authorized work through publication and checks.
- [skills/full-stop/](skills/full-stop/SKILL.md): prepare and verify a pull request, then leave it open and unmerged.
- [skills/babysit-pr/](skills/babysit-pr/SKILL.md): watch a pull request and handle actionable failures.
- [bin/heavy](bin/heavy): optional gate for finite resource-intensive commands.
- [install.sh](install.sh): symlink installer; [tests/](tests/test_install.py): isolated installer checks.
- [LICENSE](LICENSE): MIT license for this repo.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): attribution and upstream license text.
- [.gitignore](.gitignore): local generated files.

## Install

Requires Bash and Python 3, plus Claude Code for Claude only, Codex CLI for
Codex only, or both for Codex + Claude. Linux and macOS are supported; the
installer uses Bash 3.2-compatible syntax. Choose models available on your plan
before use. Keep this checkout in place: installed files link back to it.

```sh
./install.sh --dry-run
./install.sh --codex
```

Codex + Claude and Codex only use `./install.sh --codex`; Claude only can use
`./install.sh`. The installer always links skills into `~/.claude/skills/`, agent definitions into
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

> Read this repo, ask me which tools, models and subscriptions I have, choose
> Codex + Claude, Claude only or Codex only, then adapt the role split and review loop.

Start small: one worker, a read-only scout, and a fresh reviewer before commits.
Add rules when real problems show up. Keep project-specific requirements in each
project, and remove integrations you do not use.

Change `model` and `effort` in [agents/](agents/) for Claude children and the
[Codex role defaults](skills/delegate-work/references/codex-workers.md) for Codex children
to fit your plans. Update the role table and instruction defaults to match.
The Opus second advisor uses the Agent tool's `model: opus` override.
Model availability and supported effort settings can change; confirm them locally.
Use narrow briefs and small research inputs to keep subscription usage predictable.

See [Codex children](skills/delegate-work/references/codex-workers.md) for workers,
scouts, designers and advisors, and [Codex review](skills/review-fix-loop/references/codex-reviewer.md)
for authoritative reviews. Installing `--codex` makes skills discoverable;
it does not give Codex Claude Code's Agent or SendMessage tools. In Codex only,
every role is a `codex exec` child; no Claude children run.

If installed, use `~/.local/bin/heavy <command> ...` for full suites, builds and
whole-project type checks. Focused tests and development servers run directly.
It is a command gate, not a sandbox; see [bin/heavy](bin/heavy) for its limits.

## Credits

`full-send`, `full-stop` and `babysit-pr` are adapted from
[t3dotgg/tstack](https://github.com/t3dotgg/tstack), MIT.
See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## License

MIT. See [LICENSE](LICENSE).
