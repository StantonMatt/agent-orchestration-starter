#!/usr/bin/env python3
"""Merge starter hooks without replacing unrelated client configuration."""

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import sys
import tempfile
import os


def read_config(path, home):
    parent = path.parent
    while True:
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(f'Unsafe configuration parent: {parent}')
        if parent == home or parent == parent.parent:
            break
        parent = parent.parent
    if path.is_symlink():
        raise ValueError(f'Refusing configuration symlink; merge manually: {path}')
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
        raise ValueError(f'Expected configuration object with hooks object: {path}')
    for event, entries in data.get('hooks', {}).items():
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise ValueError(f'Expected hook entries for {event}: {path}')
    return data


def command(home, name):
    return 'python3 ' + shlex.quote(str(home / '.claude/hooks' / name))


def merge(data, additions):
    result = copy.deepcopy(data)
    hooks = result.setdefault('hooks', {})
    for event, entries in additions.items():
        current = hooks.setdefault(event, [])
        for entry in entries:
            if entry not in current:
                current.append(entry)
    return result


def planned_configs(home, repo, codex=False, t3=False):
    def entry(name, matcher=None):
        result = {'hooks': [{'type': 'command', 'command': command(home, name), 'timeout': 5}]}
        if matcher is not None:
            result['matcher'] = matcher
        return result

    # The template is also useful for manual installation. Resolve its home
    # shorthand here so hook commands work when HOME contains spaces.
    template = json.loads((repo / 'hooks/codex-hooks.json').read_text())
    codex_hooks = copy.deepcopy(template['hooks'])
    for entries in codex_hooks.values():
        for item in entries:
            for hook in item['hooks']:
                name = hook['command'].rsplit('/', 1)[-1]
                hook['command'] = command(home, name)
    configs = [(home / '.claude/settings.json', {
        'SessionStart': [entry('orchestration_mode.py')],
        'PreToolUse': [entry('background_job_guard.py', 'Bash')],
        'Stop': [entry('signin_handoff_check.py')],
    })]
    if codex:
        configs.append((home / '.codex/hooks.json', codex_hooks))
    if t3:
        configs.append((home / '.t3/codex-home/hooks.json', codex_hooks))
    return [(path, original, merge(original, additions))
            for path, additions in configs
            for original in [read_config(path, home)]]


def write_config(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve a byte-for-byte backup only when a configuration will change.
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        backup = Path(str(path) + '.bak-' + stamp)
        counter = 0
        while backup.exists() or backup.is_symlink():
            counter += 1
            backup = Path(str(path) + f'.bak-{stamp}-{counter}')
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(path.read_bytes())
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + '.write-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', required=True, type=Path)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--codex', action='store_true')
    parser.add_argument('--t3', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--validate', action='store_true')
    args = parser.parse_args()
    try:
        plans = planned_configs(args.home, args.repo, args.codex, args.t3)
        for path, original, updated in plans:
            if args.validate:
                continue
            if original == updated:
                print(f'ok {path}')
            elif args.dry_run:
                print(f'would merge hooks into {path}')
            else:
                write_config(path, updated)
                print(f'merged hooks into {path}')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Hook configuration error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
