"""Background-job guard regressions use command strings only."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


HOOK = Path(__file__).resolve().parents[1] / 'background_job_guard.py'
spec = importlib.util.spec_from_file_location('background_job_guard', HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def bash(command, background=False):
    return {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash',
            'tool_input': {'command': command, 'run_in_background': background}}


class BackgroundJobGuard(unittest.TestCase):
    def test_real_slip_is_denied(self):
        # The command that orphaned a review pass on 2026-11-22.
        slip = ('~/.cache/agent-scratch/project/bin/task-focused-review.sh feature '
                'share-copy 2 > /dev/null 2>&1 &\ndisown; sleep 1; cat /tmp/x.output | cut -c1-3000')
        self.assertTrue(guard.should_deny(bash(slip)))

    def test_detached_launches_are_denied(self):
        for command in [
            'codex exec review --uncommitted &',
            'nohup codex exec --model example',
            'gh pr checks 42 --watch &',
            'python3 ~/.claude/skills/review-fix-loop/scripts/run_review_pass.py --repo r &',
            'nohup python3 scripts/run_worker.py --brief b',
            'setsid -f ~/bin/ci-wait.sh 93 3600',
            'cd /x && heavy pnpm build & echo started',
            'python3 run_chrome.py --brief b & disown',
        ]:
            self.assertTrue(guard.should_deny(bash(command)), command)

    def test_tracked_and_unrelated_commands_pass(self):
        for command in [
            'python3 ~/.claude/skills/review-fix-loop/scripts/run_review_pass.py --repo r',
            '~/bin/ci-wait.sh 93 3600',
            'heavy pnpm build && echo done',
            'heavy pnpm build > out.log 2>&1',
            'heavy pnpm build &> out.log',
            'sleep 1 & wait',
            'git fetch && git status',
            'echo "use run_review_pass.py & friends"',
            "grep -n 'heavy &' notes.md",
            "cat > brief.md <<'EOF'\nrun ci-wait.sh 93 &\nEOF",
            'ls ~/.heavy-cache',
        ]:
            self.assertFalse(guard.should_deny(bash(command)), command)

    def test_review_round_1_findings(self):
        # S1: an unrelated background command doesn't make a foreground job detached.
        self.assertFalse(guard.should_deny(bash('sleep 1 & wait; heavy pnpm build')))
        # S2: a heredoc header's own `&` still detaches the job.
        self.assertTrue(guard.should_deny(bash('heavy python3 - <<EOF &\nprint(1)\nEOF')))
        # S3: `<<` needs the exact delimiter; indented lookalikes stay heredoc text.
        self.assertFalse(guard.should_deny(bash('cat <<EOF\nintro\n  EOF\nheavy pnpm build &\nEOF')))
        self.assertFalse(guard.should_deny(bash('cat <<-EOF\n\theavy pnpm build &\n\tEOF')))
        self.assertTrue(guard.should_deny(bash('(cd /x && heavy pnpm build) &')))
        self.assertTrue(guard.should_deny(bash('FOO=1 nohup ci-wait.sh 9 3600')))

    def test_review_round_2_findings(self):
        # S4: a trailing `&` backgrounds the whole pipeline / and-or list.
        self.assertTrue(guard.should_deny(bash('heavy pnpm build | tee build.log &')))
        self.assertTrue(guard.should_deny(bash('heavy pnpm build && echo done &')))
        self.assertFalse(guard.should_deny(bash('sleep 1 & heavy pnpm build | tee b.log')))
        # S5: here-strings and quoted `<<EOF` mentions don't start a heredoc.
        self.assertTrue(guard.should_deny(bash('cat <<< status\nheavy pnpm build &')))
        self.assertTrue(guard.should_deny(bash('echo "<<EOF"\nheavy pnpm build &')))
        # S6: detachers through wrappers or absolute paths.
        self.assertTrue(guard.should_deny(bash('env FOO=1 nohup python3 run_worker.py --brief b')))
        self.assertTrue(guard.should_deny(bash('/usr/bin/setsid ci-wait.sh 9 3600')))

    def test_review_round_3_findings(self):
        # S4: a newline after && || | continues the list.
        self.assertTrue(guard.should_deny(bash('heavy pnpm build &&\necho done &')))
        self.assertTrue(guard.should_deny(bash('heavy pnpm build |\n  tee b.log &')))
        # S7: detachers count only as the job's own wrapper.
        self.assertFalse(guard.should_deny(bash('command -v nohup && heavy pnpm build')))
        self.assertFalse(guard.should_deny(bash('heavy pytest tests/nohup/test_example.py')))
        self.assertTrue(guard.should_deny(bash('FOO=1 /usr/bin/nohup heavy pnpm build')))
        # S8: `&` inside a group backgrounds only the group's own list.
        self.assertFalse(guard.should_deny(bash('heavy pnpm build && (sleep 1 & wait)')))
        self.assertTrue(guard.should_deny(bash('(heavy pnpm build &)')))

    def test_inspection_exemptions_cannot_execute_jobs(self):
        for command in [
            r'find . -exec heavy pnpm build \; &',
            r'find . -execdir heavy pnpm build \; &',
            r'find . -ok heavy pnpm build \; &',
            "sed 'e heavy pnpm build' /dev/null &",
            "awk 'BEGIN {system(\"heavy pnpm build\")}' &",
            'echo $(heavy pnpm build) &',
            'echo "$(heavy pnpm build)" &',
            'echo `heavy pnpm build` &',
            'cat <(heavy pnpm build) &',
            'echo x >(heavy pnpm build) &',
            'echo x | xargs heavy pnpm build &',
            'echo "heavy pnpm build" | xargs &',
            'echo "heavy pnpm build" | sh &',
            'echo "heavy pnpm build" | cat | bash &',
            'echo heavy -exec build &',
        ]:
            with self.subTest(command=command):
                self.assertTrue(guard.should_deny(bash(command)))
        for command in [
            'echo "heavy pnpm build" | cat &',
            'rg heavy notes.md | head | wc &',
            'git show run_worker.py | tail &',
        ]:
            with self.subTest(command=command):
                self.assertFalse(guard.should_deny(bash(command)))

    def test_quoted_detachers_and_split_job_names(self):
        commands = [
            '"/usr/bin/nohup" heavy pnpm build',
            "'nohup' 'he'avy pnpm build",
            'nohu"p" he"avy" pnpm build',
            r'no\hup he\avy pnpm build',
            "'he'avy pnpm build &",
            'bash -c \'nohu"p" he"avy" pnpm build\'',
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(guard.should_deny(bash(command)))
                # The conservative fallback must recognize the same spellings.
                with patch.object(guard, 'parsed_should_deny', side_effect=ValueError('parse error')):
                    self.assertTrue(guard.should_deny(bash(command)))

    def test_fallback_strips_comments_before_normalizing_quotes(self):
        with patch.object(guard, 'parsed_should_deny', side_effect=ValueError('parse error')):
            self.assertFalse(guard.should_deny(bash('heavy pnpm build # "nohup" &')))
            self.assertFalse(guard.should_deny(bash('# "nohup" he"avy" pnpm build')))
            self.assertTrue(guard.should_deny(bash('"nohup" he"avy" "#build"')))

    def test_other_tools_pass(self):
        self.assertFalse(guard.should_deny({'tool_name': 'Read', 'tool_input': {'file_path': 'x &'}}))

    def test_background_groups_keep_earlier_lists(self):
        for command in [
            '(heavy pnpm build; echo done) &',
            '(heavy pnpm build\necho done) &',
            '((heavy pnpm build; echo inner); echo outer) &',
            '(heavy pnpm build; echo done) && echo finished &',
        ]:
            self.assertTrue(guard.should_deny(bash(command)), command)
        for command in [
            '(heavy pnpm build; echo done)',
            '(heavy pnpm build; sleep 1 & wait)',
            '(heavy pnpm build; echo done); sleep 1 &',
        ]:
            self.assertFalse(guard.should_deny(bash(command)), command)

    def test_quoted_executable_and_interpreter_script_paths(self):
        for command in [
            'python3 "$HOME/.claude/skills/review-fix-loop/scripts/run_review_pass.py" --repo /repo &',
            "python3 'scripts/run_worker.py' --brief b &",
            'nohup python3 "scripts/run_worker.py" --brief b',
            '"$HOME/bin/ci-wait.sh" 9 &',
            '"heavy" pnpm build &',
            'python3 -u "scripts/run_chrome.py" --brief b &',
            'command "scripts/run_worker.py" -v &',
        ]:
            self.assertTrue(guard.should_deny(bash(command)), command)

    def test_job_mentions_in_inspection_commands_are_allowed(self):
        for command in [
            'echo run_worker.py &',
            'echo "run_review_pass.py" &',
            'rg -n run_review_pass.py skills/ &',
            'echo heavy pnpm build &',
            'echo "codex exec" &',
            'FOO=1 echo run_worker.py &',
            '/usr/bin/printf "%s" run_worker.py &',
            'git grep run_worker.py &',
            'git log --grep run_worker.py &',
            'git show run_worker.py &',
        ]:
            self.assertFalse(guard.should_deny(bash(command)), command)
        for executable in guard.INSPECTION:
            command = executable + ' run_worker.py &'
            self.assertFalse(guard.should_deny(bash(command)), command)

    def test_job_tokens_through_arbitrary_wrappers_and_shell_syntax(self):
        for command in [
            'timeout 3600 heavy pnpm build &',
            'nice -n 10 heavy pnpm build &',
            'sudo -n heavy pnpm build &',
            '>build.log heavy pnpm build &',
            'if true; then heavy pnpm build & fi',
            'command heavy pnpm build -v &',
            'exec -a build heavy pnpm build &',
            'bash -o pipefail ci-wait.sh 93 &',
            'python3 unrelated.py run_worker.py &',
            'nohup echo run_worker.py',
            'python3 -c "print(\'run_worker.py\')" &',
            'echo done && heavy pnpm build &',
            'tool --script "run_worker.py" &',
            'tool > run_worker.py &',
            "cat <<EOF\n'\nEOF\nheavy pnpm build &",
            "printf $'can\\'t' && heavy pnpm build &",
            "heavy pnpm build $'can\\'t' &",
        ]:
            self.assertTrue(guard.should_deny(bash(command)), command)
        self.assertFalse(guard.should_deny(bash("printf $'can\\'t run_worker.py &'")))

    def test_heredoc_body_and_ansi_quoting_parse_without_fallback(self):
        for command in [
            "cat <<EOF\n'\nEOF\nheavy pnpm build &",
            "printf $'can\\'t' && heavy pnpm build &",
            "heavy pnpm build $'can\\'t' &",
        ]:
            self.assertTrue(guard.parsed_should_deny(command), command)

    def test_parse_failures_use_conservative_raw_text_fallback(self):
        for command in [
            "heavy pnpm build ' &",
            'nohup python3 "run_worker.py',
            'setsid "ci-wait.sh',
            'heavy pnpm build " ; disown',
            '"heavy" pnpm build & (',
        ]:
            self.assertTrue(guard.should_deny(bash(command)), command)
        self.assertFalse(guard.should_deny(bash("heavy pnpm build '")))
        self.assertFalse(guard.should_deny(bash("heavy pnpm build && '")))
        with patch.object(guard, 'shell_tokens', side_effect=ValueError('parse error')):
            self.assertTrue(guard.should_deny(bash('heavy pnpm build &')))
            self.assertTrue(guard.should_deny(bash('nohup heavy pnpm build')))
            self.assertFalse(guard.should_deny(bash('heavy pnpm build && echo done')))
        with patch.object(guard, 'parsed_should_deny', side_effect=RuntimeError('parser failed')):
            self.assertTrue(guard.should_deny(bash('ci-wait.sh 9 &')))

    def test_shell_comments_do_not_launch_jobs(self):
        for command in [
            'heavy pnpm build # example &',
            'heavy pnpm build; # nohup run_worker.py &',
            '# heavy pnpm build &',
            'echo done # <<EOF\nheavy pnpm build',
            "cat <<EOF\n'\nEOF\nheavy pnpm build # example &",
        ]:
            self.assertFalse(guard.should_deny(bash(command)), command)
        for command in [
            'heavy pnpm build # example &\nheavy pnpm test &',
            'echo done # <<EOF\nheavy pnpm build &',
            'heavy pnpm build#debug &',
            'heavy pnpm "build # debug" &',
            'heavy pnpm build \\# debug &',
            'heavy pnpm build # \\"\nheavy pnpm test &',
        ]:
            self.assertTrue(guard.should_deny(bash(command)), command)

    def test_hook_protocol(self):
        denied = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(bash('ci-wait.sh 9 &')),
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(denied.stdout)['hookSpecificOutput']['permissionDecision'], 'deny')
        allowed = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(bash('ci-wait.sh 9')),
                                 capture_output=True, text=True, check=True)
        self.assertEqual(allowed.stdout, '')
        broken = subprocess.run([sys.executable, str(HOOK)], input='not json',
                                capture_output=True, text=True, check=True)
        self.assertEqual(broken.stdout, '')

    def test_advisory_regressions_through_hook_protocol(self):
        for command, deny in [
            ('(heavy pnpm build; echo done) &', True),
            ('python3 "$HOME/.claude/skills/review-fix-loop/scripts/run_review_pass.py" --repo /repo &', True),
            ('echo run_worker.py &', False),
            ('rg -n run_review_pass.py skills/ &', False),
            ('heavy pnpm build # example &', False),
        ]:
            with self.subTest(command=command):
                result = subprocess.run([sys.executable, '-B', str(HOOK)],
                                        input=json.dumps(bash(command)), capture_output=True,
                                        text=True, check=True)
                self.assertEqual(result.stderr, '')
                if deny:
                    self.assertEqual(json.loads(result.stdout)['hookSpecificOutput'][
                        'permissionDecision'], 'deny')
                else:
                    self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
