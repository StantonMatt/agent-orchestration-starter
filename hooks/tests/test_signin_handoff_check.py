"""Stop regressions use trimmed, anonymised real messages and synthetic input."""

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


HOOK = Path(__file__).resolve().parents[1] / 'signin_handoff_check.py'
spec = importlib.util.spec_from_file_location('signin_handoff_check', HOOK)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

# Real Claude turn endings; names, hosts, accounts and page titles removed.
REAL_HANDOFFS = (
    "Open it on your Mac, signed in to your account, and approve the laptop.\n\n"
    "After approving, in the admin console:\n"
    "1. **Turn off key expiry for the laptop.** Otherwise it signs itself out.",
    "Installed but not yet signed in. You'll need to approve its login.",
    '**Open the admin page once, signed in.** Check that the list looks right.',
)


class SigninHandoffCheckTest(unittest.TestCase):
    def setUp(self):
        enabled = patch.dict(os.environ, STARTER_SIGNIN_TOOLS='1')
        enabled.start()
        self.addCleanup(enabled.stop)

    def test_disabled_without_explicit_tools(self):
        with patch.dict(os.environ, STARTER_SIGNIN_TOOLS='0'):
            self.assertIsNone(self.run_hook({'last_assistant_message': REAL_HANDOFFS[0]}))

    def run_hook(self, payload):
        result = subprocess.run([sys.executable, '-B', str(HOOK)],
                                input=json.dumps(payload), text=True,
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout) if result.stdout else None

    def test_real_handoffs_block(self):
        for message in REAL_HANDOFFS:
            with self.subTest(message=message):
                self.assertTrue(check.is_handoff(message))
                self.assertEqual(self.run_hook({'last_assistant_message':message})['decision'], 'block')

    def test_admin_console_step_alone_blocks(self):
        for message in (
                'After approving, in the admin console:\n1. Turn off key expiry for the laptop.',
                'In your dashboard:\n\nDisable device expiry for the laptop.',
                'Please change the setting in your admin console.',
                'In the admin console, turn off key expiry for the laptop.',
                'You need to click Approve in your account.',
                'I need you to sign in to the website.',
                'On your Mac, open the browser and approve its login.',
                'Open this link to approve the laptop: https://example.ts.net/approve',
                'Visit https://example.ts.net and approve the laptop.'):
            with self.subTest(message=message):
                self.assertTrue(check.is_handoff(message))

    def test_preview_and_report_links_pass(self):
        for message in (
                'You can open it at https://example.org/preview on your Mac or phone.',
                'Open https://example.org/preview to try it.',
                'You can download the PDF here: https://example.org/report.pdf',
                'Open the dashboard Overview at https://example.org/usage to check quota.',
                'Open it in your browser to see the new layout.',
                'Sign in at http://localhost:5297 with any of the test accounts below.',
                'The demo is running. You can sign in as the receptionist and try it.',
                'Open the preview and log in with your account to check the new screen.'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_success_reports_pass(self):
        for message in (
                'I signed in myself and approved the laptop in your admin console.',
                'The Chrome worker signed in and disabled expiry in the dashboard.',
                'Sign-in worked, but the operation has not finished.',
                'Change merged: the release is on https://example.ts.net.',
                'Download site: https://example.ts.net serves the current release.'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_real_delegated_worker_plan_passes(self):
        message = '''Both service.example and GitHub are signed out in the Agent Use profile, so this time it has to go all the way. It should:
1. Learn from the vault helper that service.example uses GitHub, then click "Continue with GitHub".
2. Sign in on GitHub with your GitHub vault login.
3. Handle GitHub's second step. An authenticator code comes from the vault; an emailed device code comes through the email helper.
4. Land on the service.example dashboard.

It stops if GitHub asks for a passkey, a GitHub Mobile approval or a text code. It also stops on an "Authorize app" screen.'''
        self.assertFalse(check.is_handoff(message))
        self.assertIsNone(self.run_hook({'last_assistant_message': message}))

    def test_worker_lists_and_sentences_pass_but_user_directions_still_block(self):
        for intro in ('It should:', 'The agent will:', 'It will:', 'The worker will:'):
            with self.subTest(intro=intro):
                self.assertFalse(check.is_handoff(intro + '\n1. Sign in with your vault login.\n2. Verify your email.'))
                self.assertFalse(check.is_handoff(intro + '\n\n- Sign in with your vault login.'))
                self.assertTrue(check.is_handoff(intro + '\n1. You need to sign in to your account.'))
                self.assertTrue(check.is_handoff(intro + '\n1. Sign in with the vault.\n\nSign in to your account.'))
        for subject in ('It', 'The agent', 'The worker'):
            self.assertFalse(check.is_handoff(subject + ' will sign in using your account.'))
            self.assertTrue(check.is_handoff(subject + ' needs you to sign in to your account.'))

    def test_worker_markdown_lists_and_wrapped_items_pass(self):
        for marker in ('-', '*', '+', '1.'):
            with self.subTest(marker=marker):
                self.assertFalse(check.is_handoff(
                    'The agent will:\n' + marker + ' Sign in to your account.'))
                self.assertTrue(check.is_handoff(
                    'To finish:\n' + marker + ' Sign in to your account at example.com.'))
        self.assertFalse(check.is_handoff(
            'It should:\n- Open the login page, then\n  Sign in to your account.\n'
            '- Continue with the task.'))
        self.assertTrue(check.is_handoff(
            'It should:\n- Open the login page, then\n  You need to sign in to your account.'))
        self.assertTrue(check.is_handoff(
            'It should:\n- Open the login page.\nSign in to your account.'))

    def test_human_only_auth_steps_pass(self):
        for message in (
                'Sign in with your passkey in the browser, then tell me.',
                'Open the website and complete the image-selection CAPTCHA.',
                'Sign in using the SMS code the website sent you.',
                'You need to approve the push approval in your bank app for your account.',
                'Sign in using the audio CAPTCHA.',
                'Sign in and solve the CAPTCHA puzzle.',
                'Sign in using the push code.',
                'The tools refused. Sign in yourself in Chrome.',
                'The helper failed. Sign in yourself in Chrome.',
                'The password manager has no matching login.\n\nSign in yourself in Chrome.',
                'The vault has no login matching the sign-in page.\n\nSign in yourself.',
                'Two saved logins match.\n\nSign in yourself in Chrome.',
                'This is an extra change. You can disable expiry in your dashboard.'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_email_and_simple_check_handoffs_block(self):
        for message in (
                'Sign in using the email verification code.',
                'Open the email verification link to sign in.',
                'You need to verify your email for your account.',
                'The broker asked to verify your email. Sign in yourself in Chrome.',
                'You need to approve the new-device confirmation for your account.',
                'Open the website and complete the CAPTCHA.',
                'Complete the checkbox CAPTCHA to sign in.',
                'Click Verify you are human in Cloudflare.',
                'Check the Turnstile checkbox to sign in.',
                'Press and hold the button to sign in.',
                'Confirm it is you to sign in.'):
            with self.subTest(message=message):
                self.assertTrue(check.is_handoff(message))

    def test_failed_email_helper_handoffs_pass(self):
        for message in (
                'The email helper failed. Sign in using the email verification code.',
                'The email helper refused. Open the email verification link to sign in.',
                'The browser refused the checkbox. Complete the CAPTCHA to sign in.',
                'The tools failed. Click Verify you are human in Cloudflare.',
                'The email helper requires approval. Sign in yourself in Chrome.'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_phone_and_physical_steps_pass(self):
        for message in (
                'Open the phone app and approve the login.',
                'Keep your phone nearby: you may need to approve the link in their apps. '
                'Approve only the requested transfer.',
                'Open the browser on someone else\'s device and sign in to their account.',
                'You need to open the laptop lid and press its power button.',
                'Open the mobile app and sign in.'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_command_line_auth_is_not_a_website_handoff(self):
        for message in ('Sign in to the CLI before retrying.',
                        'Sign in using the command-line login.'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_rule_quotes_and_code_pass(self):
        for message in (
                'The rule says "Open it on your Mac, signed in to your account, '
                'and approve the laptop." This is the hand-off to prevent.',
                '> Sign in yourself in Chrome.\n\nThat was the original mistake.',
                'Regression fixture:\n```text\nSign in yourself in Chrome.\n```',
                'Regression fixture:\n~~~text\nOpen your dashboard and disable expiry.\n~~~',
                'The instruction says agents do website steps themselves, including '
                'opening a link to approve a device and changing an admin-console setting.',
                'The upstream error says "Credits depleted. Please go to '
                'https://example.ts.net to manage billing."'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_demo_invitation_and_account_creation_pass(self):
        for message in (
                'Sign in and try it. This is a private test copy. I already walked the flow.',
                'Open the account on its website with your ID and proof of address.',
                'Open the account. This is an online form asking for ID.',
                'Would you like me to disable expiry in the admin console?',
                'Please approve my proposed extra change to the dashboard.'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_unrelated_code_review_does_not_inherit_dashboard_context(self):
        self.assertFalse(check.is_handoff(
            'The dashboard server needs a fix in its account handler.\n\n'
            'Change the status popover detail to Ready.'))

    def test_named_human_checks_still_block(self):
        for message in ('Verify you are human to sign in.', 'Check the box on the login page to continue.'):
            with self.subTest(message=message):
                self.assertTrue(check.is_handoff(message))

    def test_engineering_advice_about_logins_passes(self):
        for message in ('Check that the login handler rejects stale tokens.',
                        'Confirm the login flow works after deploy.',
                        'Check the box size in the login form CSS.'):
            with self.subTest(message=message):
                self.assertFalse(check.is_handoff(message))

    def test_stop_hook_active_is_silent_and_does_not_read_transcript(self):
        with patch.object(check, 'last_assistant_text', side_effect=AssertionError('read')):
            with patch('sys.stdin', io.StringIO(json.dumps({'stop_hook_active':True}))):
                with patch('sys.stdout', new_callable=io.StringIO) as out:
                    check.main()
        self.assertEqual(out.getvalue(), '')
        self.assertIsNone(self.run_hook(dict(stop_hook_active=True,
                                            last_assistant_message=REAL_HANDOFFS[0])))

    def test_captured_runtime_payload_shapes(self):
        # Claude Code 2.1.329 and Codex 0.171.0, non-content fields anonymised.
        for extra in (
                dict(prompt_id='test-prompt', background_tasks=[], session_crons=[],
                     transcript_path='/nonexistent/transcript.jsonl'),
                dict(turn_id='test-turn', model='test-model', transcript_path=None)):
            payload = dict(session_id='test-session', cwd='/tmp/hook-test',
                           hook_event_name='Stop', stop_hook_active=False,
                           permission_mode='default', last_assistant_message=REAL_HANDOFFS[0])
            payload.update(extra)
            self.assertEqual(self.run_hook(payload)['decision'], 'block')

    def test_transcript_fallback_last_assistant_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'transcript.jsonl'
            rows = [
                dict(type='assistant', message=dict(content=[dict(type='text', text='Done.')])),
                dict(type='user', message=dict(content='User message.')),
                dict(type='assistant', message=dict(content=[
                    dict(type='thinking', thinking='private reasoning'),
                    dict(type='text', text=REAL_HANDOFFS[1])])),
                dict(type='assistant', message=dict(content=[dict(type='tool_use', name='Read')])),
                dict(type='system', message='trailing hook record'),
            ]
            path.write_text('\n'.join(json.dumps(row) for row in rows))
            self.assertEqual(self.run_hook({'transcript_path':str(path)})['decision'], 'block')
            self.assertIsNone(self.run_hook({'transcript_path':str(path),
                                            'last_assistant_message':'Done.'}))
            self.assertIsNone(self.run_hook({'transcript_path':str(path),
                                            'last_assistant_message':''}))

    def test_bad_input_fails_open(self):
        for raw in ('{', 'null', '[]', '1', '"text"',
                    '{"last_assistant_message":{}}', '{"transcript_path":[]}',
                    '{"transcript_path":"/nonexistent/transcript.jsonl"}'):
            with self.subTest(raw=raw):
                result = subprocess.run([sys.executable, '-B', str(HOOK)], input=raw,
                                        text=True, capture_output=True, timeout=5)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, '', ''))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.jsonl'
            path.write_text('{broken')
            self.assertIsNone(self.run_hook({'transcript_path':str(path)}))

    def test_codex_registration(self):
        config = json.loads((HOOK.parent / 'codex-hooks.json').read_text())
        self.assertEqual(config['hooks']['Stop'], [{'hooks':[{
            'type':'command', 'command':'python3 ~/.claude/hooks/signin_handoff_check.py',
            'timeout':5}]}])


if __name__ == '__main__':
    unittest.main()
