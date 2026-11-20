"""Exercise the command-line contract without modifying an existing repository."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tree_fingerprint.py"


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "--quiet")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test-user")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "core.filemode", "true")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def run_tool(self, *args, check=True):
        return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), *args],
                              check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def capture(self):
        result = self.run_tool("capture").stdout.decode().strip()
        self.assertRegex(result, r"^[0-9a-f]{64}$")
        return result

    def write(self, name, data):
        (self.repo / name).write_text(data)

    def commit_file(self):
        self.write("tracked.txt", "old\nsecond\n")
        self.git("add", "tracked.txt")
        self.git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")

    def test_no_commit_repo(self):
        first = self.capture()
        self.assertEqual(first, self.capture())
        self.assertFalse((self.repo / ".git" / "index").exists())
        self.write("new.txt", "one\ntwo\n")
        report = json.loads(self.run_tool("estimate").stdout)
        self.assertEqual((report["changed_files"], report["added_lines"], report["removed_lines"]), (1, 2, 0))
        self.git("add", "new.txt")
        self.assertEqual(json.loads(self.run_tool("estimate").stdout)["added_lines"], 2)

    def test_untracked_add_edit_and_remove(self):
        first = self.capture()
        self.write("new.txt", "one")
        second = self.capture()
        self.assertNotEqual(first, second)
        self.write("new.txt", "two")
        self.assertNotEqual(second, self.capture())
        (self.repo / "new.txt").unlink()
        self.assertEqual(first, self.capture())

    def test_tracked_edit_and_delete(self):
        self.commit_file()
        first = self.capture()
        self.write("tracked.txt", "new\nsecond\n")
        second = self.capture()
        self.assertNotEqual(first, second)
        (self.repo / "tracked.txt").unlink()
        self.assertNotEqual(second, self.capture())

    def test_staged_only_change(self):
        self.commit_file()
        first = self.capture()
        self.write("tracked.txt", "new\nsecond\n")
        self.git("add", "tracked.txt")
        self.write("tracked.txt", "old\nsecond\n")
        self.assertEqual(self.git("diff", "HEAD", "--", "tracked.txt"), b"")
        self.assertNotEqual(first, self.capture())
        report = json.loads(self.run_tool("estimate").stdout)
        self.assertEqual((report["changed_files"], report["added_lines"], report["removed_lines"]), (1, 2, 2))

    def test_ignored_file_is_excluded(self):
        self.write(".gitignore", "ignored.txt\n")
        first = self.capture()
        self.write("ignored.txt", "private\n")
        self.assertEqual(first, self.capture())
        self.assertEqual(json.loads(self.run_tool("estimate").stdout)["paths"], [".gitignore"])

    def test_spaces_newlines_and_tabs_in_paths(self):
        for name in ("two words.txt", "line\nbreak.txt", "tab\tname.txt"):
            self.write(name, "one\n")
        report = json.loads(self.run_tool("estimate").stdout)
        self.assertEqual(report["added_lines"], 3)
        first = self.capture()
        self.git("add", ".")
        self.assertNotEqual(first, self.capture())
        self.write("line\nbreak.txt", "two\nthree\n")
        report = json.loads(self.run_tool("estimate").stdout)
        self.assertEqual((report["changed_files"], report["added_lines"], report["removed_lines"]), (3, 5, 1))

    def test_verify_exit_codes(self):
        first = self.capture()
        self.assertEqual(self.run_tool("verify", first, check=False).returncode, 0)
        self.write("new.txt", "new\n")
        mismatch = self.run_tool("verify", first, check=False)
        self.assertEqual(mismatch.returncode, 1)
        self.assertIn(b"changed", mismatch.stderr)

    def test_user_index_unchanged(self):
        self.commit_file()
        self.write("tracked.txt", "new\n")
        index = self.repo / ".git" / "index"
        before = index.read_bytes()
        before_stat = index.stat()
        self.capture()
        self.run_tool("estimate")
        self.assertEqual(before, index.read_bytes())
        self.assertEqual(before_stat.st_mtime_ns, index.stat().st_mtime_ns)
        self.assertFalse((self.repo / ".git" / "index.lock").exists())

    def test_estimate_counts(self):
        self.commit_file()
        self.write("tracked.txt", "new\nsecond\nthird\n")
        self.write("extra.txt", "extra\nlast")
        report = json.loads(self.run_tool("estimate").stdout)
        self.assertEqual((report["changed_files"], report["added_lines"], report["removed_lines"]), (2, 4, 1))
        self.assertEqual(report["binary_files"], 0)

    def test_binary_file_and_modes(self):
        (self.repo / "data.bin").write_bytes(b"a\0b")
        first = self.capture()
        os.chmod(self.repo / "data.bin", 0o755)
        self.assertNotEqual(first, self.capture())
        report = json.loads(self.run_tool("estimate").stdout)
        self.assertEqual((report["binary_files"], report["added_lines"]), (1, 0))

    def test_symlink_target_is_captured_without_following(self):
        (self.repo / "link").symlink_to("first")
        first = self.capture()
        (self.repo / "link").unlink()
        (self.repo / "link").symlink_to("second")
        self.assertNotEqual(first, self.capture())

    def test_subdirectory_and_repo_argument_after_command(self):
        self.commit_file()
        (self.repo / "subdir").mkdir()
        result = subprocess.run([sys.executable, str(SCRIPT), "capture", "--repo", str(self.repo / "subdir")],
                                check=True, stdout=subprocess.PIPE)
        self.assertEqual(result.stdout.decode().strip(), self.capture())

    def test_split_index_is_read_without_changes(self):
        self.commit_file()
        self.git("update-index", "--split-index")
        index = self.repo / ".git" / "index"
        shared = Path(os.fsdecode(self.git("rev-parse", "--shared-index-path").strip()))
        if not shared.is_absolute():
            shared = self.repo / shared
        original = (index.read_bytes(), shared.read_bytes())
        first = self.capture()
        self.write("tracked.txt", "changed\n")
        self.assertNotEqual(first, self.capture())
        self.assertEqual(original, (index.read_bytes(), shared.read_bytes()))

    def test_nested_repository_fails_closed(self):
        nested = self.repo / "nested"
        nested.mkdir()
        self.git("-C", str(nested), "init", "--quiet")
        (nested / "file.txt").write_text("nested data\n")
        result = self.run_tool("capture", check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"directory or special file", result.stderr)


if __name__ == "__main__":
    unittest.main()
