"""Tests for the search module — GrepMatch class, local_grep, and parallel_grep."""

import os
import tempfile
from unittest.mock import MagicMock, patch

from membase.search import GrepMatch, local_grep, parallel_grep

# ── GrepMatch tests ───────────────────────────────────────────────────


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

    def test_inequality_different_path(self):
        a = GrepMatch("a.py", 1, "line")
        b = GrepMatch("b.py", 1, "line")
        assert a != b

    def test_inequality_different_line_content(self):
        a = GrepMatch("a.py", 1, "foo")
        b = GrepMatch("a.py", 1, "bar")
        assert a != b

    def test_equality_with_non_grepmatch_returns_notimplemented(self):
        m = GrepMatch("a.py", 1, "line")
        assert m.__eq__("not a match") is NotImplemented

    def test_slots_prevent_extra_attributes(self):
        m = GrepMatch("a.py", 1, "line")
        try:
            m.extra = "nope"
            assert False, "Should have raised AttributeError"
        except AttributeError:
            pass

    def test_repr_with_empty_line(self):
        m = GrepMatch("f.py", 10, "")
        assert repr(m) == "f.py:10: "

    def test_repr_with_special_characters(self):
        m = GrepMatch("f.py", 1, 'print("hello\\n")')
        assert "f.py:1:" in repr(m)


# ── local_grep tests ──────────────────────────────────────────────────


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

    def test_regex_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "code.py")
            with open(path, "w") as f:
                f.write("def foo():\ndef bar_baz():\nclass MyClass:\n")

            results = local_grep(tmpdir, ["code.py"], r"def \w+\(\)")
            assert len(results) == 2

    def test_multiple_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for name, content in [("a.py", "import os\n"), ("b.py", "import sys\n")]:
                with open(os.path.join(tmpdir, name), "w") as f:
                    f.write(content)

            results = local_grep(tmpdir, ["a.py", "b.py"], r"import")
            assert len(results) == 2
            paths = {r.path for r in results}
            assert "a.py" in paths
            assert "b.py" in paths

    def test_strips_trailing_whitespace_from_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "f.txt")
            with open(path, "w") as f:
                f.write("hello   \nworld\n")

            results = local_grep(tmpdir, ["f.txt"], r"hello")
            assert results[0].line == "hello"

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.txt")
            with open(path, "w") as f:
                f.write("")

            results = local_grep(tmpdir, ["empty.txt"], r"anything")
            assert results == []

    def test_max_results_across_files(self):
        """max_results should apply globally, not per-file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ["a.txt", "b.txt", "c.txt"]:
                with open(os.path.join(tmpdir, name), "w") as f:
                    for i in range(10):
                        f.write(f"match {i}\n")

            results = local_grep(tmpdir, ["a.txt", "b.txt", "c.txt"], r"match", max_results=5)
            assert len(results) == 5


# ── parallel_grep tests ──────────────────────────────────────────────


class TestParallelGrep:
    """Tests for parallel_grep with mocked HfFileSystem.

    HfFileSystem is imported lazily inside the per-thread worker, so we
    patch it at the source package (huggingface_hub).
    """

    HF_FS_PATH = "huggingface_hub.HfFileSystem"

    def test_finds_matches_across_files(self):
        mock_fs = MagicMock()
        mock_fs.read_text.side_effect = lambda path: {
            "buckets/u/b/a.py": "def hello():\n    pass\n",
            "buckets/u/b/b.py": "import os\ndef world():\n",
        }.get(path, "")

        with patch(self.HF_FS_PATH, return_value=mock_fs):
            results = parallel_grep(
                mock_fs,
                "buckets/u/b",
                ["buckets/u/b/a.py", "buckets/u/b/b.py"],
                r"def \w+",
            )

        assert len(results) == 2
        lines = [r.line for r in results]
        assert any("hello" in text for text in lines)
        assert any("world" in text for text in lines)

    def test_respects_max_results(self):
        big_content = "\n".join(f"match line {i}" for i in range(50))
        mock_fs = MagicMock()
        mock_fs.read_text.return_value = big_content

        with patch(self.HF_FS_PATH, return_value=mock_fs):
            results = parallel_grep(
                mock_fs,
                "buckets/u/b",
                ["buckets/u/b/big.txt"],
                r"match",
                max_results=10,
            )

        assert len(results) == 10

    def test_strips_bucket_prefix_from_path(self):
        mock_fs = MagicMock()
        mock_fs.read_text.return_value = "found it\n"

        with patch(self.HF_FS_PATH, return_value=mock_fs):
            results = parallel_grep(
                mock_fs,
                "buckets/u/b",
                ["buckets/u/b/src/main.py"],
                r"found",
            )

        assert results[0].path == "src/main.py"

    def test_skips_files_with_read_errors(self):
        mock_fs = MagicMock()
        mock_fs.read_text.side_effect = Exception("read error")

        with patch(self.HF_FS_PATH, return_value=mock_fs):
            results = parallel_grep(
                mock_fs,
                "buckets/u/b",
                ["buckets/u/b/broken.py"],
                r"pattern",
            )

        assert results == []

    def test_no_matches_returns_empty(self):
        mock_fs = MagicMock()
        mock_fs.read_text.return_value = "no match here\n"

        with patch(self.HF_FS_PATH, return_value=mock_fs):
            results = parallel_grep(
                mock_fs,
                "buckets/u/b",
                ["buckets/u/b/f.txt"],
                r"zzz_not_found",
            )

        assert results == []
