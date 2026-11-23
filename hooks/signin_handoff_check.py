#!/usr/bin/env python3
"""Nudge Claude Code and Codex away from handing the user website steps.

This is a deliberately narrow text heuristic, not an authorization check.
Stop's continuation flag limits it to one nudge; malformed input fails open.
"""

import json
import os
import re
import sys


REASON = (
    'Your reply may hand the user an authorized website step. Follow the global '
    'Website sign-ins rules: use the Chrome worker and explicitly connected '
    'credential tools only within the user-approved scope. Never expose secrets. '
    'If tools are unavailable, an account is ambiguous, consent is needed, or '
    'a human-only challenge remains, end the turn without repeating your reply.'
)

ACTION = (
    r'(?:open|visit|click|follow|go to|head to|sign in|log in|'
    r'approve|authori[sz]e|turn off|turn on|disable|enable|'
    # Challenge steps only, so ordinary "check that..." advice doesn't match.
    r'verify (?:your|the) email|(?:complete|solve|tick|check) (?:the )?(?:\w+ )?(?:captcha|checkbox|human check)|tick the box|'
    r'confirm (?:it[’\x27]?s|it is) you|verify (?:that )?(?:you[’\x27]re|you are) (?:a )?human|'
    r'check the box(?=\s*(?:$|[.,;:!]|to\b|on\b|that\b|labell?ed\b|and\b))|'
    r'enter (?:the )?(?:emailed |email )?(?:verification )?code(?: from (?:the|your) email)?|press and hold|'
    r'change (?=the\b|your\b)|download)\b'
)
HANDOFF = re.compile(
    r'(?:^(?:please\s+)?' + ACTION + r'|'
    r'\byou(?:[’\x27]ll| will)?\s+(?:(?:still|just|also)\s+)?'
    r'(?:(?:need|have) to|must|can|should)\s+' + ACTION + r'|'
    r'\b(?:needs?|wants?) you to\s+' + ACTION + r'|'
    r'^on your (?:mac|computer|desktop|browser)[,:]?\s+' + ACTION + r'|'
    r'^(?:in|on) (?:the |your )?(?:admin console|dashboard)[,:]?\s+' + ACTION + r')', re.I)
# Account evidence only: a bare link, browser or dashboard is usually a preview
# or report the user is meant to open (local previews or a usage report).
WEBSITE = re.compile(
    r'\b(?:admin(?:istration)? (?:console|portal)|'
    r'sign[ -]?in|signed[ -]?in|log[ -]?in|login|'
    r'key expir(?:y|ation)|your account|captcha|turnstile|cloudflare|'
    r'email verification|(?:email|e-mail) (?:code|link)|verify (?:your|the) email|'
    r'verify you are human|not a robot)\b', re.I)
LINK_APPROVAL = re.compile(
    r'(?:\b(?:link|url)\b|https?://).{0,220}\b(?:approv\w*|authori[sz]\w*|sign[ -]?in|login)\b', re.I)
EXCEPTION = re.compile(
    r'\b(?:passkey|(?:image(?:[ -]selection)?|audio|puzzle) captcha|'
    r'captcha\b[^.!?\n]{0,50}\b(?:images?|audio|puzzle)|'
    r'(?:sms|push|text(?: message)?) (?:verification |confirmation |one.time )?code|'
    r'push approval|'
    r'no (?:single |matching |saved )*(?:login|credential)|'
    r'(?:tools?|browser|helper) (?:refused|failed|requires approval)|'
    r'(?:phone|mobile) app|someone else[’\x27]s (?:device|account)|'
    r'(?:command.line|cli|terminal) (?:login|sign.in)|'
    r'(?:sign in|log in) (?:to|with) (?:the )?(?:cli|terminal)|'
    r'phone\b[^.\n]{0,220}\b(?:in their apps|on your phone)|'
    r'private test copy|demo (?:account|site)|'
    # The user's own local, demo or preview apps are for them to try.
    r'localhost|127\.0\.0\.1|\bdemo\b|\bpreview\b|:\d{4,5}\b|'
    r'(?:extra|additional|unapproved) (?:account )?change)\b', re.I)
MISSING_LOGIN = re.compile(
    r'\b(?:no (?:single |matching |saved )*login|'
    r'(?:multiple|two|several) (?:saved )?logins (?:match|matched)|'
    r'(?:vault|helper|tools?)\b[^.!?\n]{0,100}\b(?:no login|no matching login|refused|failed|requires approval))', re.I)
CONSOLE_HEADING = re.compile(
    r'(?:\b(?:in|on|from) (?:the |your )?[^\n.!?]{0,50})?'
    r'\b(?:admin console|dashboard)\s*:\s*$', re.I)
WORKER_SUBJECT = r'(?:it|the (?:agent|worker)|the chrome worker)'
WORKER_PLAN = re.compile(r'\b' + WORKER_SUBJECT + r'\s+(?:should|will)\s*:\s*$', re.I)
WORKER_SENTENCE = re.compile(r'^' + WORKER_SUBJECT + r'\b', re.I)
USER_DIRECTED = re.compile(
    r'\byou(?:[’\x27]ll| will)?\s+(?:(?:still|just|also)\s+)?'
    r'(?:(?:need|have) to|must|can|should)\s+' + ACTION + r'|'
    r'\b(?:needs?|wants?) you to\s+' + ACTION, re.I)


def is_handoff(message):
    """Require a user-directed action and nearby account/browser evidence."""
    if not isinstance(message, str):
        return False
    # Ignore code and Markdown quotations, which commonly quote the rule or a
    # regression fixture. Inline code stays: it can name a real console button.
    message = re.sub(r'(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1[^\n]*', '', message)
    message = re.sub(r'"[^"\n]*"|“[^”\n]*”', '', message)
    # A vault mismatch can be explained several paragraphs before the ask.
    if MISSING_LOGIN.search(message):
        return False
    previous = ''
    worker_list = False
    item_indent = None
    for paragraph in re.split(r'\n\s*\n', message):
        paragraph = '\n'.join(line for line in paragraph.splitlines()
                              if not line.lstrip().startswith('>'))
        context = re.sub(r'[*_`]', '', previous[-300:] + '\n' + paragraph)
        heading = previous if len(previous) < 250 else ''
        for line in paragraph.splitlines():
            # Parse list structure before removing emphasis, including '*' bullets.
            line = line.expandtabs(4)
            marker = re.match(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)', line)
            listed = marker is not None
            continuation = item_indent is not None and len(line) - len(line.lstrip()) >= item_indent
            if listed:
                item_indent = marker.end()
            elif not continuation:
                item_indent = None
            line = line[marker.end():] if listed else re.sub(r'^\s*#{1,6}\s*', '', line)
            line = re.sub(r'[*_`]', '', line).strip()
            if not line:
                continue
            described_list_step = worker_list and (listed or continuation)
            if not listed and not continuation:
                worker_list = False
            for sentence in re.split(r'(?<=[.!?])\s+', line):
                if WORKER_PLAN.search(sentence):
                    worker_list = True
                    heading = sentence
                    continue
                described_step = described_list_step or WORKER_SENTENCE.match(sentence)
                # Worker plans do not exempt explicit instructions to the user.
                if described_step and not USER_DIRECTED.search(sentence):
                    heading = sentence
                    continue
                if re.match(r'open (?:an?|the|your) account\b|download site:', sentence, re.I):
                    continue
                if (HANDOFF.search(sentence) and not EXCEPTION.search(context)
                        and (WEBSITE.search(sentence) or LINK_APPROVAL.search(context)
                             or CONSOLE_HEADING.search(heading))):
                    return True
                heading = sentence
        previous = re.sub(r'[*_`]', '', paragraph)
    return False


def last_assistant_text(payload):
    if 'last_assistant_message' in payload:
        return payload['last_assistant_message']
    path = payload.get('transcript_path')
    if not isinstance(path, str) or not path:
        return ''
    last = ''
    with open(path, encoding='utf-8') as transcript:
        for line in transcript:
            row = json.loads(line)
            if row.get('type') != 'assistant':
                continue
            content = row.get('message', {}).get('content', [])
            text = '\n'.join(block['text'] for block in content
                             if block.get('type') == 'text')
            if text:
                last = text
    return last


def main():
    try:
        if os.environ.get("STARTER_SIGNIN_TOOLS") != "1":
            return
        payload = json.load(sys.stdin)
        if payload.get('stop_hook_active'):
            return
        if is_handoff(last_assistant_text(payload)):
            print(json.dumps({'decision': 'block', 'reason': REASON}))
    except Exception:
        # A Stop hook must never prevent a reply because of a parsing/IO error.
        pass


if __name__ == '__main__':
    main()
