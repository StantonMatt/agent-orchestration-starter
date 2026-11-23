#!/usr/bin/env python3
"""Claude Code PreToolUse guard: long agent jobs must use run_in_background.

Review passes, worker launches, CI waits and `heavy` jobs started with a shell
`&`, `nohup`, `setsid` or `disown` are invisible to the harness: nothing wakes
the session when they finish and they outlive the turn as orphans. Starting
them with the Bash tool's run_in_background keeps them tracked.

Inspects shell syntax only, without expanding or executing it. Job mentions in
inspection commands and heredoc bodies are ignored; parse failures use a
conservative raw-text check.
"""

import json
import re
import sys


JOB = re.compile(
    r'\bcodex\s+exec\b|\bgh\s+pr\s+checks\b[^;\n]*--watch\b|'
    r'run_review_pass\.py|focused-review\.sh|run_worker\.py|run_chrome\.py|'
    r'ci-wait\.sh|(?:^|[\s(/`])heavy\b'
)
ASSIGNMENT = re.compile(r'[A-Za-z_][A-Za-z_0-9]*=.*', re.S)
INSPECTION = {'echo', 'printf', 'rg', 'grep', 'cat', 'head', 'tail', 'less',
              'ls', 'wc'}
EXECUTION = re.compile(r'[$<>]\s*\(|`|(?:^|\s)-(?:execdir|exec|ok)(?=\s|$)')
DETACHER = re.compile(r'(?:^|[\s(])(?:\S*/)?(?:nohup|setsid)(?=\s)')
RAW_JOB = re.compile(JOB.pattern + r'|\bheavy\b')
RAW_BACKGROUND = re.compile(r'(?<![&<>])&(?![&>])|\b(?:nohup|setsid|disown)\b')
QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)(\w+)\2")
REASON = (
    'Blocked: this starts a review, worker, CI wait or heavy job detached from the '
    'harness (&, nohup, setsid or disown). Run it as its own Bash call with '
    'run_in_background: true so its completion wakes the session.'
)


def unquote_except_delimiters(line):
    """Blank quoted text, except a quoted heredoc delimiter such as <<'EOF'."""
    return QUOTED.sub(
        lambda m: m.group(0) if re.search(r'<<-?\s*$', line[:m.start()]) else ' ' * len(m.group(0)),
        line,
    )


def drop_heredoc_bodies(command):
    """Keep every heredoc header line (it is shell syntax); drop only the bodies."""
    lines, out, pending = command.split('\n'), [], []
    for line in lines:
        if pending:
            dash, word = pending[0]
            if (line.lstrip('\t') if dash else line) == word:
                pending.pop(0)
            continue
        out.append(line)
        header = unquote_except_delimiters(strip_comments(line))
        pending = [(m.group(1) == '-', m.group(3)) for m in HEREDOC.finditer(header)]
    return '\n'.join(out)


def shell_tokens(command):
    """Yield (value, is_operator) without expanding words or losing quoted paths.

    A # starts a comment only at the start of a word. Quoted/escaped operators
    stay words, including an empty quoted argument.
    """
    word, started, quote, ansi, i = [], False, None, False, 0
    while i < len(command):
        char = command[i]
        if char == '\\' and (quote != "'" or ansi) and i + 1 < len(command):
            following = command[i + 1]
            if following != '\n':
                if quote == '"' and following not in '$`"\\':
                    word.append('\\')
                word.append(following)
                started = True
            i += 2
            continue
        if quote:
            if char == quote:
                quote = None
                ansi = False
            else:
                word.append(char)
        elif command[i:i + 2] == "$'":
            quote, ansi, started = "'", True, True
            i += 1
        elif char in "'\"":
            quote, started = char, True
        elif char == '#' and not started:
            newline = command.find('\n', i)
            i = len(command) if newline < 0 else newline
            continue
        elif char.isspace() or char in '();&|<>':
            if started:
                yield ''.join(word), False
                word, started = [], False
            if char in '();&|<>\n':
                operator = command[i:i + 2]
                if operator in ('&&', '||', '&>', '>&', '<&', '>>', '<<'):
                    i += 1
                else:
                    operator = char
                yield operator, True
        else:
            word.append(char)
            started = True
        i += 1
    if quote:
        raise ValueError('unterminated shell quote')
    if started:
        yield ''.join(word), False


def strip_comments(command):
    """Strip comments before heredoc detection, keeping quotes and newlines."""
    quote, ansi, started, i, out = None, False, False, 0, []
    while i < len(command):
        char = command[i]
        if char == '\\' and (quote != "'" or ansi) and i + 1 < len(command):
            out.append(command[i:i + 2])
            if command[i + 1] != '\n':
                started = True
            i += 2
            continue
        if quote:
            if char == quote:
                quote = None
                ansi = False
        elif command[i:i + 2] == "$'":
            quote, ansi, started = "'", True, True
            out.append("$'")
            i += 2
            continue
        elif char in "'\"":
            quote, started = char, True
        elif char == '#' and not started:
            newline = command.find('\n', i)
            i = len(command) if newline < 0 else newline
            continue
        else:
            started = not (char.isspace() or char in '();&|<>')
        out.append(char)
        i += 1
    return ''.join(out)


def lists(tokens):
    """Yield lists with their background status, retaining complete group contents.

    Inner lists are checked on their own and retained until an enclosing group's
    background status is known. Only root list separators discard earlier lists.
    """
    stack = [([], [])]  # completed group contents, current list
    for token in tokens:
        value, operator = token
        completed, current = stack[-1]
        if operator and value == '(':
            stack.append(([], []))
        elif operator and value == ')' and len(stack) > 1:
            completed, current = stack.pop()
            stack[-1][1].extend([('(', True)] + completed + current + [token])
        elif operator and value in (';', '\n', '&'):
            if value == '\n' and current and current[-1] in (
                    ('&&', True), ('||', True), ('|', True)):
                continue
            yield current[:], value == '&'
            if len(stack) > 1:
                completed.extend(current + [token])
            current.clear()
        else:
            current.append(token)
    if len(stack) > 1:
        raise ValueError('unterminated shell group')
    yield stack[0][1], False


def simple_commands(tokens):
    """Keep each command's tokens together, including quoted and redirected text."""
    command = []
    for value, operator in tokens:
        if operator and value in ('&&', '||', '|', ';', '\n', '&', '(', ')'):
            if command:
                yield command
            command = []
        else:
            command.append((value, operator))
    if command:
        yield command


def command_words(tokens):
    """Find the leading command for inspection exemptions, skipping redirections."""
    words, redirect = [], False
    for value, operator in tokens:
        if operator and ('<' in value or '>' in value):
            if words and words[-1].isdigit():
                words.pop()  # optional redirection file descriptor
            redirect = True
        elif not operator:
            if not redirect:
                words.append(value)
            redirect = False
    return words


def normalize_scan(text):
    """Remove shell quoting and escapes for conservative name matching."""
    return re.sub(r'\\(.)|[\'\"]', lambda m: '' if m[1] == '\n' else (m[1] or ''),
                  text, flags=re.S)


def inspection_command(tokens):
    words = [normalize_scan(word) for word in command_words(tokens)]
    while words and ASSIGNMENT.fullmatch(words[0]):
        words.pop(0)
    if not words:
        return False
    executable = words[0].rsplit('/', 1)[-1]
    return executable in INSPECTION or (executable == 'git' and words[1:2] in (
        ['grep'], ['log'], ['show']))


def inspection_safe(tokens):
    """An inspection list must contain no execution syntax or unsafe pipe stage."""
    if EXECUTION.search(normalize_scan(' '.join(value for value, _ in tokens))):
        return False
    for index, token in enumerate(tokens):
        if token == ('|', True):
            stage = next(simple_commands(tokens[index + 1:]), [])
            if not inspection_command(stage):
                return False
    return True


def job_command(tokens, allow_inspection=True):
    """Recognize jobs through arbitrary wrappers, exempting safe inspection."""
    if allow_inspection and inspection_command(tokens):
        return False, False
    text = normalize_scan(' '.join(value for value, _ in tokens))
    job = JOB.search(text)
    return bool(job), bool(job and DETACHER.search(text[:job.start() + 1]))


def should_deny(event):
    if event.get('tool_name') != 'Bash':
        return False
    command = (event.get('tool_input') or {}).get('command')
    if not isinstance(command, str):
        return False
    try:
        return parsed_should_deny(command)
    except Exception:
        # Malformed or unsupported syntax must not hide a detached job.
        text = normalize_scan(strip_comments(command))
        return bool(RAW_JOB.search(text) and RAW_BACKGROUND.search(text))


def parsed_should_deny(command):
    parts = list(lists(shell_tokens(drop_heredoc_bodies(command))))
    for index, (tokens, backgrounded) in enumerate(parts):
        allow_inspection = inspection_safe(tokens)
        jobs = [job_command(words, allow_inspection) for words in simple_commands(tokens)]
        if not any(is_job for is_job, _ in jobs):
            continue
        if backgrounded or any(is_job and detached for is_job, detached in jobs):
            return True
        # `job ...; disown`: disown right after the job's list.
        following = parts[index + 1][0] if index + 1 < len(parts) else []
        first = command_words(next(simple_commands(following), []))
        if first[:1] == ['disown']:
            return True
    return False


def main():
    try:
        if should_deny(json.load(sys.stdin)):
            print(json.dumps({'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'deny',
                'permissionDecisionReason': REASON,
            }}))
    except Exception:
        # Malformed input or an internal failure must not break every tool call.
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
