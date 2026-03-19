"""Tests for the search module — GrepMatch class and local_grep."""

import os
import tempfile

from agentspace.search import GrepMatch, local_grep


class TestGrepMatch:
    """Tests for the GrepMatch data class."""

    def test_repr(self):
        m = GrepMatch("src/main.py", 42, "def main():")
        assert repr(m) == "src/main.py:42: def main():"

    def test_equality(self):
        a = GrepMatch("a.py", 1, "line")
        b = GrepMatch("a.py", 1, "line")
        assert a == b

    def test_inequality(self):
        a = GrepMatch("a.py", 1, "line")
        b = GrepMatch("a.py", 2, "line")
        assert a != b


class TestLocalGrep:
    """Tests for searching local files."""

    def test_finds_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.py")
            with open(path, "w") as f:
                f.write("import os\nimport sys\ndef main():\n    pass\n")

            results = local_grep(tmpdir, ["test.py"], r"import")
            assert len(results) == 2
            assert results[0].path == "test.py"
            assert results[0].line_number == 1
            assert results[0].line == "import os"

    def test_respects_max_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w") as f:
                for i in range(100):
                    f.write(f"match line {i}\n")

            results = local_grep(tmpdir, ["test.txt"], r"match", max_results=5)
            assert len(results) == 5

    def test_skips_binary_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "binary.bin")
            with open(path, "wb") as f:
                f.write(bytes(range(256)))

            results = local_grep(tmpdir, ["binary.bin"], r"something")
            assert len(results) == 0

    def test_skips_missing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = local_grep(tmpdir, ["nonexistent.py"], r"pattern")
            assert len(results) == 0
