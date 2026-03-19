"""Tests for the compatibility / workaround layer.

Covers ensure_nonempty_bytes (0-byte bug workaround) and find_files_by_pattern
(hffs.glob fallback).
"""

from unittest.mock import MagicMock

from membase._compat import _manual_glob, ensure_nonempty_bytes, find_files_by_pattern

# ── ensure_nonempty_bytes tests ────────────────────────────────────────


class TestEnsureNonemptyBytes:
    """Tests for the 0-byte file workaround."""

    def test_empty_bytes_get_newline(self):
        assert ensure_nonempty_bytes(b"") == b"\n"

    def test_nonempty_bytes_pass_through(self):
        assert ensure_nonempty_bytes(b"hello") == b"hello"

    def test_single_byte_passes(self):
        assert ensure_nonempty_bytes(b"\n") == b"\n"

    def test_none_treated_as_empty(self):
        """None is falsy, so it should get the newline treatment."""
        assert ensure_nonempty_bytes(None) == b"\n"

    def test_large_content_passes_through(self):
        big = b"x" * 10_000
        assert ensure_nonempty_bytes(big) is big

    def test_single_null_byte_passes(self):
        assert ensure_nonempty_bytes(b"\x00") == b"\x00"


# ── find_files_by_pattern tests ────────────────────────────────────────


class TestFindFilesByPattern:
    """Tests for the glob fallback that works around hffs.glob bugs."""

    def _make_hffs(self, glob_result=None, glob_error=None, files=None):
        """Build a mock HfFileSystem with configurable glob/find behavior."""
        hffs = MagicMock()

        if glob_error:
            hffs.glob.side_effect = glob_error
        else:
            hffs.glob.return_value = glob_result or []

        hffs.find.return_value = files or []
        hffs.isfile.return_value = True

        return hffs

    def test_uses_glob_when_it_works(self):
        hffs = self._make_hffs(
            glob_result=["buckets/u/b/src/main.py", "buckets/u/b/src/utils.py"]
        )

        result = find_files_by_pattern(hffs, "buckets/u/b", "**/*.py")
        assert result == ["buckets/u/b/src/main.py", "buckets/u/b/src/utils.py"]
        hffs.glob.assert_called_once_with("buckets/u/b/**/*.py")

    def test_filters_out_directories_from_glob(self):
        """glob() may return directories — only files should be kept."""
        hffs = self._make_hffs(
            glob_result=["buckets/u/b/src/main.py", "buckets/u/b/src"]
        )
        hffs.isfile.side_effect = lambda p: p.endswith(".py")

        result = find_files_by_pattern(hffs, "buckets/u/b", "**/*.py")
        assert result == ["buckets/u/b/src/main.py"]

    def test_falls_back_to_manual_on_typeerror(self):
        """When hffs.glob raises TypeError (SDK bug), use find+fnmatch."""
        hffs = self._make_hffs(
            glob_error=TypeError("maxdepth not supported"),
            files=[
                "buckets/u/b/main.py",
                "buckets/u/b/data.csv",
                "buckets/u/b/src/utils.py",
            ],
        )

        result = find_files_by_pattern(hffs, "buckets/u/b", "**/*.py")
        assert "buckets/u/b/main.py" in result
        assert "buckets/u/b/src/utils.py" in result
        assert "buckets/u/b/data.csv" not in result

    def test_glob_returns_empty(self):
        hffs = self._make_hffs(glob_result=[])
        result = find_files_by_pattern(hffs, "buckets/u/b", "*.txt")
        assert result == []


# ── _manual_glob tests ─────────────────────────────────────────────────


class TestManualGlob:
    """Tests for the find+fnmatch fallback used when hffs.glob is broken."""

    def _make_hffs(self, files):
        hffs = MagicMock()
        hffs.find.return_value = files
        return hffs

    def test_double_star_matches_nested(self):
        files = [
            "buckets/u/b/main.py",
            "buckets/u/b/src/utils.py",
            "buckets/u/b/src/deep/helper.py",
            "buckets/u/b/data.csv",
        ]
        hffs = self._make_hffs(files)

        result = _manual_glob(hffs, "buckets/u/b", "**/*.py")
        assert "buckets/u/b/main.py" in result
        assert "buckets/u/b/src/utils.py" in result
        assert "buckets/u/b/src/deep/helper.py" in result
        assert "buckets/u/b/data.csv" not in result

    def test_double_star_specific_prefix(self):
        files = [
            "buckets/u/b/test_main.py",
            "buckets/u/b/tests/test_utils.py",
            "buckets/u/b/src/main.py",
        ]
        hffs = self._make_hffs(files)

        result = _manual_glob(hffs, "buckets/u/b", "**/test_*.py")
        assert "buckets/u/b/test_main.py" in result
        assert "buckets/u/b/tests/test_utils.py" in result
        assert "buckets/u/b/src/main.py" not in result

    def test_single_directory_pattern(self):
        """Pattern like 'src/*.py' should match only files in src/."""
        files = [
            "buckets/u/b/src/main.py",
            "buckets/u/b/src/utils.py",
            "buckets/u/b/src/deep/helper.py",
            "buckets/u/b/main.py",
        ]
        hffs = self._make_hffs(files)

        result = _manual_glob(hffs, "buckets/u/b", "src/*.py")
        assert "buckets/u/b/src/main.py" in result
        assert "buckets/u/b/src/utils.py" in result
        assert "buckets/u/b/src/deep/helper.py" not in result
        assert "buckets/u/b/main.py" not in result

    def test_root_level_pattern(self):
        """Pattern like '*.py' should match only root-level files."""
        files = [
            "buckets/u/b/main.py",
            "buckets/u/b/data.csv",
            "buckets/u/b/src/utils.py",
        ]
        hffs = self._make_hffs(files)

        result = _manual_glob(hffs, "buckets/u/b", "*.py")
        assert "buckets/u/b/main.py" in result
        assert "buckets/u/b/src/utils.py" not in result

    def test_no_matches_returns_empty(self):
        files = ["buckets/u/b/data.csv"]
        hffs = self._make_hffs(files)

        result = _manual_glob(hffs, "buckets/u/b", "**/*.py")
        assert result == []

    def test_empty_workspace(self):
        hffs = self._make_hffs([])
        result = _manual_glob(hffs, "buckets/u/b", "**/*")
        assert result == []

    def test_files_not_under_prefix_are_ignored(self):
        """Files that don't start with bucket_path/ should be skipped."""
        files = [
            "buckets/u/b/main.py",
            "some/other/path/file.py",
        ]
        hffs = self._make_hffs(files)

        result = _manual_glob(hffs, "buckets/u/b", "**/*.py")
        assert "buckets/u/b/main.py" in result
        assert len(result) == 1
