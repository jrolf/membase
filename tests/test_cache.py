"""Tests for the LocalMirror caching layer.

sync_bucket is mocked — these tests exercise the mirror's state management
and local file operations without network calls.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from membase.cache import LocalMirror

# sync_bucket is lazily imported inside LocalMirror.sync(), so we
# patch it at the source (huggingface_hub) rather than membase.cache.
SYNC_BUCKET_PATH = "huggingface_hub.sync_bucket"


@pytest.fixture
def mirror():
    """A LocalMirror with no external dependencies."""
    return LocalMirror("user/test-project", "hf://buckets/user/test-project")


class TestMirrorInit:
    """Tests for initial mirror state."""

    def test_starts_not_synced(self, mirror):
        assert mirror.is_synced is False
        assert mirror.local_dir is None

    def test_stores_bucket_info(self, mirror):
        assert mirror.bucket_id == "user/test-project"
        assert mirror.bucket_uri == "hf://buckets/user/test-project"


class TestMirrorSync:
    """Tests for sync() behavior."""

    @patch(SYNC_BUCKET_PATH)
    def test_pull_creates_local_dir(self, mock_sync, mirror):
        result = mirror.sync(direction="pull")

        assert result is not None
        assert os.path.isdir(result)
        assert mirror.is_synced is True
        assert mirror.local_dir == result

        mock_sync.assert_called_once_with(
            "hf://buckets/user/test-project", result, delete=False
        )

        mirror.cleanup()

    @patch(SYNC_BUCKET_PATH)
    def test_push_direction(self, mock_sync, mirror):
        mirror.sync(direction="push")

        call_args = mock_sync.call_args
        assert call_args[0][0] == mirror.local_dir
        assert call_args[0][1] == "hf://buckets/user/test-project"

        # push-only does NOT set is_synced
        assert mirror.is_synced is False
        mirror.cleanup()

    @patch(SYNC_BUCKET_PATH)
    def test_both_direction(self, mock_sync, mirror):
        mirror.sync(direction="both")

        assert mock_sync.call_count == 2
        assert mirror.is_synced is True
        mirror.cleanup()

    def test_invalid_direction_raises(self, mirror):
        with pytest.raises(ValueError, match="direction"):
            mirror.sync(direction="sideways")

    @patch(SYNC_BUCKET_PATH)
    def test_reuses_existing_local_dir(self, mock_sync, mirror):
        mirror.sync(direction="pull")
        first_dir = mirror.local_dir

        mirror.sync(direction="pull")
        assert mirror.local_dir == first_dir

        mirror.cleanup()

    @patch(SYNC_BUCKET_PATH)
    def test_local_dir_has_membase_prefix(self, mock_sync, mirror):
        mirror.sync(direction="pull")
        dirname = os.path.basename(mirror.local_dir)
        assert dirname.startswith("membase_")
        mirror.cleanup()

    @patch(SYNC_BUCKET_PATH)
    def test_delete_flag_passed_through(self, mock_sync, mirror):
        mirror.sync(direction="pull", delete=True)

        mock_sync.assert_called_once_with(
            "hf://buckets/user/test-project", mirror.local_dir, delete=True
        )
        mirror.cleanup()


class TestMirrorInvalidate:
    """Tests for invalidate() behavior."""

    @patch(SYNC_BUCKET_PATH)
    def test_invalidate_marks_not_synced(self, mock_sync, mirror):
        mirror.sync(direction="pull")
        assert mirror.is_synced is True

        mirror.invalidate()
        assert mirror.is_synced is False
        # Directory is preserved for reuse
        assert mirror.local_dir is not None

        mirror.cleanup()

    def test_invalidate_on_fresh_mirror(self, mirror):
        """Should not raise even if never synced."""
        mirror.invalidate()
        assert mirror.is_synced is False


class TestMirrorEnsureSynced:
    """Tests for ensure_synced()."""

    @patch(SYNC_BUCKET_PATH)
    def test_syncs_if_not_synced(self, mock_sync, mirror):
        result = mirror.ensure_synced()
        assert result is not None
        assert mirror.is_synced is True
        mock_sync.assert_called_once()
        mirror.cleanup()

    @patch(SYNC_BUCKET_PATH)
    def test_skips_if_already_synced(self, mock_sync, mirror):
        mirror.sync(direction="pull")
        mock_sync.reset_mock()

        result = mirror.ensure_synced()
        assert result == mirror.local_dir
        mock_sync.assert_not_called()
        mirror.cleanup()


class TestMirrorListLocalFiles:
    """Tests for list_local_files()."""

    def test_empty_when_not_synced(self, mirror):
        assert mirror.list_local_files() == []

    def test_lists_files_in_temp_dir(self, mirror):
        mirror.local_dir = tempfile.mkdtemp(prefix="membase_test_")
        mirror.is_synced = True

        # Create some files
        os.makedirs(os.path.join(mirror.local_dir, "src"))
        with open(os.path.join(mirror.local_dir, "README.md"), "w") as f:
            f.write("hello")
        with open(os.path.join(mirror.local_dir, "src", "main.py"), "w") as f:
            f.write("print('hi')")

        files = mirror.list_local_files()
        assert "README.md" in files
        assert os.path.join("src", "main.py") in files

        mirror.cleanup()

    def test_suffix_filter(self, mirror):
        mirror.local_dir = tempfile.mkdtemp(prefix="membase_test_")
        mirror.is_synced = True

        with open(os.path.join(mirror.local_dir, "a.py"), "w") as f:
            f.write("x")
        with open(os.path.join(mirror.local_dir, "b.txt"), "w") as f:
            f.write("y")
        with open(os.path.join(mirror.local_dir, "c.py"), "w") as f:
            f.write("z")

        py_files = mirror.list_local_files(suffix=".py")
        assert len(py_files) == 2
        assert all(f.endswith(".py") for f in py_files)

        mirror.cleanup()

    def test_returns_sorted(self, mirror):
        mirror.local_dir = tempfile.mkdtemp(prefix="membase_test_")
        mirror.is_synced = True

        for name in ["c.txt", "a.txt", "b.txt"]:
            with open(os.path.join(mirror.local_dir, name), "w") as f:
                f.write(name)

        files = mirror.list_local_files()
        assert files == sorted(files)

        mirror.cleanup()


class TestMirrorCleanup:
    """Tests for cleanup()."""

    def test_removes_directory(self, mirror):
        tmpdir = tempfile.mkdtemp(prefix="membase_test_")
        mirror.local_dir = tmpdir
        with open(os.path.join(tmpdir, "f.txt"), "w") as f:
            f.write("data")

        assert os.path.exists(tmpdir)
        mirror.cleanup()
        assert not os.path.exists(tmpdir)
        assert mirror.local_dir is None
        assert mirror.is_synced is False

    def test_cleanup_when_no_dir(self, mirror):
        """Should not raise when cleanup is called with no local_dir."""
        mirror.cleanup()

    def test_cleanup_when_already_deleted(self, mirror):
        """Should not raise when directory was removed externally."""
        mirror.local_dir = "/tmp/membase_nonexistent_12345"
        mirror.cleanup()
        # os.path.exists returns False, so the rmtree branch is skipped
        # and local_dir is NOT reset — this is current behavior
        assert mirror.local_dir is not None
