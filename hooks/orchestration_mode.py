#!/usr/bin/env python3
"""Report the configured setup; no account probing or automatic quota guesses."""

import json
from pathlib import Path
import re
import sys

SETUPS = ('Codex + Claude', 'Claude only', 'Codex only')


def configured_mode(path=None):
    path = Path(path) if path is not None else Path.home() / '.claude/CLAUDE.md'
    try:
        match = re.search(r'^Active setup: (.+)$', path.read_text(), re.M)
        if match and match.group(1).strip() in SETUPS:
            return 'Orchestration mode: ' + match.group(1).strip()
    except (OSError, UnicodeError):
        pass
    return 'Orchestration mode could not be determined; read the global instructions.'


def main():
    line = configured_mode()
    if sys.argv[1:] == ['--status']:
        print(line)
    elif not sys.argv[1:]:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'SessionStart', 'additionalContext': line,
        }}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
