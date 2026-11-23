"""Configured mode selection never needs a service or credentials."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[1] / 'orchestration_mode.py'
spec = importlib.util.spec_from_file_location('orchestration_mode', HOOK)
mode = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mode)


class ModeTest(unittest.TestCase):
    def test_all_setups_and_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'instructions.md'
            self.assertIn('could not be determined', mode.configured_mode(path))
            for setup in mode.SETUPS:
                path.write_text('## Setups\n\nActive setup: ' + setup + '\n')
                self.assertEqual(mode.configured_mode(path), 'Orchestration mode: ' + setup)
            for content in ('Active setup: anything\n', 'no setup\n'):
                path.write_text(content)
                self.assertIn('could not be determined', mode.configured_mode(path))

    def test_session_protocol(self):
        result = subprocess.run([sys.executable, str(HOOK)], input='{}',
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['hookEventName'], 'SessionStart')


if __name__ == '__main__':
    unittest.main()
