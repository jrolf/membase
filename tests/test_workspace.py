"""Tests for the Workspace class, data classes, and list_workspaces().

All huggingface_hub calls are mocked — these tests exercise the logic in
workspace.py without any network calls.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from membase.errors import (
    EditConflictError,
    FileNotFoundInWorkspaceError,
    MembaseError,
    WorkspaceNotFoundError,
)
from membase.workspace import (
    FileStat,
    LSEntry,
    Workspace,
    WorkspaceInfo,
    WorkspaceSummary,
    list_workspaces,
)

# ── helpers ────────────────────────────────────────────────────────────


def _make_bucket_result(bucket_id="user/test-project"):
    """Fake return value for create_bucket()."""
    result = MagicMock()
    result.bucket_id = bucket_id
    return result


@pytest.fixture
def ws():
    """A Workspace with all external calls mocked.

    Returns a workspace bound to 'user/test-project'. The internal
    HfFileSystem (ws._fs) is a MagicMock that tests can configure
    freely.
    """
    result = _make_bucket_result()
    with patch("membase.workspace.create_bucket", return_value=result), \
         patch("membase.workspace.HfFileSystem"):
        workspace = Workspace("test-project", token="fake-token")

    workspace._fs = MagicMock()
    return workspace


@pytest.fixture
def ws_with_root():
    """A Workspace scoped to root='data/v1'."""
    result = _make_bucket_result()
    with patch("membase.workspace.create_bucket", return_value=result), \
         patch("membase.workspace.HfFileSystem"):
        workspace = Workspace("test-project", root="data/v1", token="fake-token")

    workspace._fs = MagicMock()
    return workspace


# ── data class tests ───────────────────────────────────────────────────


class TestWorkspaceSummary:
    """Tests for the WorkspaceSummary data class."""

    def test_repr_private(self):
        s = WorkspaceSummary("user/proj", "proj", "user", True, None)
        assert repr(s) == "WorkspaceSummary('user/proj', private)"

    def test_repr_public(self):
        s = WorkspaceSummary("user/proj", "proj", "user", False, None)
        assert repr(s) == "WorkspaceSummary('user/proj', public)"

    def test_attributes(self):
        s = WorkspaceSummary("org/bucket", "bucket", "org", True, "2026-01-01")
        assert s.bucket_id == "org/bucket"
        assert s.name == "bucket"
        assert s.namespace == "org"
        assert s.private is True
        assert s.created_at == "2026-01-01"

    def test_slots_prevent_extra_attributes(self):
        s = WorkspaceSummary("a/b", "b", "a", False, None)
        with pytest.raises(AttributeError):
            s.extra = "nope"


class TestWorkspaceInfo:
    """Tests for the WorkspaceInfo data class."""

    def test_repr_includes_file_count_and_size(self):
        info = WorkspaceInfo("proj", "user", "user/proj", True, 23, 47200, None)
        r = repr(info)
        assert "user/proj" in r
        assert "private" in r
        assert "23 files" in r
        assert "46.1 KB" in r

    def test_repr_public(self):
        info = WorkspaceInfo("proj", "user", "user/proj", False, 0, 0, None)
        assert "public" in repr(info)

    def test_all_attributes_accessible(self):
        info = WorkspaceInfo("proj", "ns", "ns/proj", True, 5, 1024, "ts")
        assert info.name == "proj"
        assert info.namespace == "ns"
        assert info.bucket_id == "ns/proj"
        assert info.file_count == 5
        assert info.total_size == 1024
        assert info.created_at == "ts"

    def test_slots_prevent_extra_attributes(self):
        info = WorkspaceInfo("p", "n", "n/p", True, 0, 0, None)
        with pytest.raises(AttributeError):
            info.extra = "nope"


class TestFileStat:
    """Tests for the FileStat data class."""

    def test_repr_file(self):
        s = FileStat("src/main.py", 1800, "file")
        assert repr(s) == "FileStat('src/main.py', 1.8 KB)"

    def test_repr_directory(self):
        s = FileStat("src", 0, "directory")
        assert repr(s) == "FileStat('src/', directory)"

    def test_repr_zero_size_file(self):
        s = FileStat("empty.txt", 0, "file")
        assert "0 B" in repr(s)

    def test_attributes(self):
        s = FileStat("a.txt", 100, "file")
        assert s.path == "a.txt"
        assert s.size == 100
        assert s.type == "file"


class TestLSEntry:
    """Tests for the LSEntry data class."""

    def test_repr_file(self):
        e = LSEntry("main.py", "src/main.py", "file", 1800)
        assert repr(e) == "main.py (1.8 KB)"

    def test_repr_directory(self):
        e = LSEntry("utils", "src/utils", "directory")
        assert repr(e) == "utils/"

    def test_default_size_is_zero(self):
        e = LSEntry("dir", "dir", "directory")
        assert e.size == 0

    def test_attributes(self):
        e = LSEntry("f.py", "src/f.py", "file", 500)
        assert e.name == "f.py"
        assert e.path == "src/f.py"
        assert e.type == "file"
        assert e.size == 500


# ── list_workspaces tests ─────────────────────────────────────────────


class TestListWorkspaces:
    """Tests for the module-level list_workspaces() function."""

    def test_returns_workspace_summaries(self):
        bucket_a = MagicMock()
        bucket_a.bucket_id = "user/project-a"
        bucket_a.private = True
        bucket_a.created_at = "2026-01-01"

        bucket_b = MagicMock()
        bucket_b.bucket_id = "user/project-b"
        bucket_b.private = False
        bucket_b.created_at = "2026-02-01"

        with patch("membase.workspace.list_buckets", return_value=[bucket_a, bucket_b]):
            results = list_workspaces(token="fake")

        assert len(results) == 2
        assert isinstance(results[0], WorkspaceSummary)
        assert results[0].name == "project-a"
        assert results[0].namespace == "user"
        assert results[0].private is True
        assert results[1].name == "project-b"
        assert results[1].private is False

    def test_passes_namespace_when_provided(self):
        with patch("membase.workspace.list_buckets", return_value=[]) as mock_lb:
            list_workspaces(namespace="my-org", token="tok")

        mock_lb.assert_called_once_with(namespace="my-org", token="tok")

    def test_omits_namespace_when_none(self):
        with patch("membase.workspace.list_buckets", return_value=[]) as mock_lb:
            list_workspaces(token="tok")

        mock_lb.assert_called_once_with(token="tok")

    def test_handles_bucket_id_without_slash(self):
        bucket = MagicMock()
        bucket.bucket_id = "standalone-bucket"
        bucket.private = False

        with patch("membase.workspace.list_buckets", return_value=[bucket]):
            results = list_workspaces()

        assert results[0].namespace == ""
        assert results[0].name == "standalone-bucket"

    def test_empty_result(self):
        with patch("membase.workspace.list_buckets", return_value=[]):
            results = list_workspaces()

        assert results == []


# ── Workspace construction and repr ───────────────────────────────────


class TestWorkspaceInit:
    """Tests for Workspace initialization and display."""

    def test_repr_basic(self, ws):
        assert repr(ws) == "Workspace('user/test-project')"

    def test_repr_with_root(self, ws_with_root):
        assert "root='data/v1'" in repr(ws_with_root)

    def test_repr_with_mirror(self):
        result = _make_bucket_result()
        with patch("membase.workspace.create_bucket", return_value=result), \
             patch("membase.workspace.HfFileSystem"):
            workspace = Workspace("test", mirror=True, token="fake")

        assert "mirror=True" in repr(workspace)

    def test_parses_namespace_from_bucket_id(self, ws):
        assert ws._namespace == "user"
        assert ws._name == "test-project"

    def test_bucket_id_without_namespace(self):
        result = _make_bucket_result("standalone")
        with patch("membase.workspace.create_bucket", return_value=result), \
             patch("membase.workspace.HfFileSystem"):
            workspace = Workspace("standalone", token="fake")

        assert workspace._namespace == ""
        assert workspace._name == "standalone"

    def test_root_strips_slashes(self, ws_with_root):
        assert ws_with_root._root == "data/v1"

    def test_context_manager_cleans_up_mirror(self):
        result = _make_bucket_result()
        with patch("membase.workspace.create_bucket", return_value=result), \
             patch("membase.workspace.HfFileSystem"):
            workspace = Workspace("test", mirror=True, token="fake")

        workspace._mirror = MagicMock()

        workspace.__exit__(None, None, None)
        workspace._mirror.cleanup.assert_called_once()

    def test_context_manager_no_mirror(self, ws):
        """__exit__ should not raise when there's no mirror."""
        result = ws.__exit__(None, None, None)
        assert result is False


# ── path helper tests ─────────────────────────────────────────────────


class TestPathHelpers:
    """Tests for _full_path, _rel_path, _remote_rel_path.

    These are the most important pure-logic functions in the library.
    Every other method depends on them being correct.
    """

    def test_full_path_simple(self, ws):
        assert ws._full_path("src/main.py") == "buckets/user/test-project/src/main.py"

    def test_full_path_empty(self, ws):
        assert ws._full_path("") == "buckets/user/test-project"

    def test_full_path_strips_leading_dot_slash(self, ws):
        assert ws._full_path("./src/main.py") == "buckets/user/test-project/src/main.py"

    def test_full_path_strips_leading_slash(self, ws):
        assert ws._full_path("/src/main.py") == "buckets/user/test-project/src/main.py"

    def test_full_path_with_root(self, ws_with_root):
        result = ws_with_root._full_path("train.csv")
        assert result == "buckets/user/test-project/data/v1/train.csv"

    def test_full_path_with_root_empty(self, ws_with_root):
        result = ws_with_root._full_path("")
        assert result == "buckets/user/test-project/data/v1"

    def test_rel_path_strips_prefix(self, ws):
        full = "buckets/user/test-project/src/main.py"
        assert ws._rel_path(full) == "src/main.py"

    def test_rel_path_no_match_returns_as_is(self, ws):
        assert ws._rel_path("some/other/path") == "some/other/path"

    def test_rel_path_with_root(self, ws_with_root):
        full = "buckets/user/test-project/data/v1/train.csv"
        assert ws_with_root._rel_path(full) == "train.csv"

    def test_remote_rel_path_simple(self, ws):
        assert ws._remote_rel_path("src/main.py") == "src/main.py"

    def test_remote_rel_path_strips_dot_slash(self, ws):
        assert ws._remote_rel_path("./src/main.py") == "src/main.py"

    def test_remote_rel_path_with_root(self, ws_with_root):
        assert ws_with_root._remote_rel_path("train.csv") == "data/v1/train.csv"

    def test_remote_rel_path_with_root_empty(self, ws_with_root):
        assert ws_with_root._remote_rel_path("") == "data/v1"


# ── read tests ────────────────────────────────────────────────────────


class TestRead:
    """Tests for Workspace.read() and its line-slicing modes."""

    def test_read_text(self, ws):
        ws._fs.read_text.return_value = "hello world"
        assert ws.read("test.txt") == "hello world"
        ws._fs.read_text.assert_called_once_with(
            "buckets/user/test-project/test.txt"
        )

    def test_read_binary(self, ws):
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"\x89PNG"
        ws._fs.open.return_value = mock_file

        result = ws.read("image.png", binary=True)
        assert result == b"\x89PNG"
        ws._fs.open.assert_called_once_with(
            "buckets/user/test-project/image.png", "rb"
        )

    def test_read_head(self, ws):
        ws._fs.read_text.return_value = "line1\nline2\nline3\nline4\nline5"
        result = ws.read("f.txt", head=3)
        assert result == "line1\nline2\nline3"

    def test_read_tail(self, ws):
        ws._fs.read_text.return_value = "line1\nline2\nline3\nline4\nline5"
        result = ws.read("f.txt", tail=2)
        assert result == "line4\nline5"

    def test_read_lines_range(self, ws):
        ws._fs.read_text.return_value = "a\nb\nc\nd\ne"
        result = ws.read("f.txt", lines=(2, 4))
        assert result == "b\nc\nd"

    def test_read_head_larger_than_file(self, ws):
        ws._fs.read_text.return_value = "only\ntwo"
        result = ws.read("f.txt", head=100)
        assert result == "only\ntwo"

    def test_read_file_not_found(self, ws):
        ws._fs.read_text.side_effect = FileNotFoundError()
        ws._fs.ls.return_value = []

        with pytest.raises(FileNotFoundInWorkspaceError) as exc_info:
            ws.read("missing.txt")

        assert "missing.txt" in str(exc_info.value)

    def test_read_with_root(self, ws_with_root):
        ws_with_root._fs.read_text.return_value = "data"
        ws_with_root.read("train.csv")
        ws_with_root._fs.read_text.assert_called_once_with(
            "buckets/user/test-project/data/v1/train.csv"
        )


# ── read_many tests ───────────────────────────────────────────────────


class TestReadMany:
    """Tests for Workspace.read_many() parallel read."""

    def test_empty_list_returns_empty_dict(self, ws):
        assert ws.read_many([]) == {}

    def test_returns_dict_of_contents(self, ws):
        # read_many creates fresh HfFileSystem instances per thread,
        # so we patch the class itself
        mock_fs_instance = MagicMock()
        mock_fs_instance.read_text.side_effect = lambda path: f"content of {path}"

        with patch("membase.workspace.HfFileSystem", return_value=mock_fs_instance):
            result = ws.read_many(["a.txt", "b.txt"])

        assert "a.txt" in result
        assert "b.txt" in result

    def test_skips_failed_reads(self, ws):
        call_count = 0

        def read_text_side_effect(path):
            nonlocal call_count
            call_count += 1
            if "bad" in path:
                raise Exception("read failed")
            return "ok"

        mock_fs_instance = MagicMock()
        mock_fs_instance.read_text.side_effect = read_text_side_effect

        with patch("membase.workspace.HfFileSystem", return_value=mock_fs_instance):
            result = ws.read_many(["good.txt", "bad.txt"])

        assert "good.txt" in result
        assert "bad.txt" not in result


# ── write tests ───────────────────────────────────────────────────────


class TestWrite:
    """Tests for Workspace.write() and write_many()."""

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_str_content(self, mock_fs_cls, mock_batch, ws):
        result = ws.write("hello.txt", "hello")
        assert result == "hello.txt"

        mock_batch.assert_called_once()
        call_args = mock_batch.call_args
        assert call_args[0][0] == "user/test-project"

        add_list = call_args[1]["add"]
        assert len(add_list) == 1
        content_bytes, path = add_list[0]
        assert content_bytes == b"hello"
        assert path == "hello.txt"

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_bytes_content(self, mock_fs_cls, mock_batch, ws):
        ws.write("data.bin", b"\x00\x01\x02")

        add_list = mock_batch.call_args[1]["add"]
        content_bytes, _ = add_list[0]
        assert content_bytes == b"\x00\x01\x02"

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_empty_string_gets_newline(self, mock_fs_cls, mock_batch, ws):
        """Empty content should be converted to b'\\n' to avoid the 0-byte bug."""
        ws.write("empty.txt", "")

        add_list = mock_batch.call_args[1]["add"]
        content_bytes, _ = add_list[0]
        assert content_bytes == b"\n"

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_with_root(self, mock_fs_cls, mock_batch, ws_with_root):
        ws_with_root.write("train.csv", "a,b,c")

        add_list = mock_batch.call_args[1]["add"]
        _, path = add_list[0]
        assert path == "data/v1/train.csv"

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_invalidates_mirror(self, mock_fs_cls, mock_batch, ws):
        ws._mirror = MagicMock()
        ws._mirror.is_synced = True

        ws.write("f.txt", "data")
        ws._mirror.invalidate.assert_called_once()

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_skips_invalidate_when_not_synced(self, mock_fs_cls, mock_batch, ws):
        ws._mirror = MagicMock()
        ws._mirror.is_synced = False

        ws.write("f.txt", "data")
        ws._mirror.invalidate.assert_not_called()

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_many_returns_paths(self, mock_fs_cls, mock_batch, ws):
        files = {"a.py": "print('a')", "b.py": "print('b')"}
        result = ws.write_many(files)
        assert result == ["a.py", "b.py"]

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_many_batches_all_files(self, mock_fs_cls, mock_batch, ws):
        files = {"a.py": "a", "b.py": "b", "c.py": "c"}
        ws.write_many(files)

        add_list = mock_batch.call_args[1]["add"]
        assert len(add_list) == 3

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_write_many_handles_bytes(self, mock_fs_cls, mock_batch, ws):
        files = {"img.png": b"\x89PNG"}
        ws.write_many(files)

        add_list = mock_batch.call_args[1]["add"]
        content_bytes, _ = add_list[0]
        assert content_bytes == b"\x89PNG"


# ── edit tests ────────────────────────────────────────────────────────


class TestEdit:
    """Tests for Workspace.edit() find-and-replace."""

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_edit_replaces_first_occurrence(self, mock_fs_cls, mock_batch, ws):
        ws._fs.read_text.return_value = "DEBUG = True\nDEBUG = True"

        result = ws.edit("config.py", old="DEBUG = True", new="DEBUG = False")
        assert result == "config.py"

        add_list = mock_batch.call_args[1]["add"]
        written_bytes, _ = add_list[0]
        written_str = written_bytes.decode("utf-8")

        # Only the first occurrence should be replaced
        assert written_str == "DEBUG = False\nDEBUG = True"

    def test_edit_raises_on_missing_old_string(self, ws):
        ws._fs.read_text.return_value = "existing content"

        with pytest.raises(EditConflictError) as exc_info:
            ws.edit("config.py", old="nonexistent", new="replacement")

        assert "config.py" in str(exc_info.value)

    def test_edit_raises_on_missing_file(self, ws):
        ws._fs.read_text.side_effect = FileNotFoundError()
        ws._fs.ls.return_value = []

        with pytest.raises(FileNotFoundInWorkspaceError):
            ws.edit("missing.py", old="x", new="y")


# ── append tests ──────────────────────────────────────────────────────


class TestAppend:
    """Tests for Workspace.append()."""

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_append_to_existing_file(self, mock_fs_cls, mock_batch, ws):
        ws._fs.read_text.return_value = "line1\n"
        result = ws.append("log.txt", "line2\n")
        assert result == "log.txt"

        add_list = mock_batch.call_args[1]["add"]
        written_bytes, _ = add_list[0]
        assert written_bytes == b"line1\nline2\n"

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_append_creates_new_file(self, mock_fs_cls, mock_batch, ws):
        ws._fs.read_text.side_effect = FileNotFoundError()
        ws._fs.ls.return_value = []

        ws.append("new.txt", "first line")

        add_list = mock_batch.call_args[1]["add"]
        written_bytes, _ = add_list[0]
        assert written_bytes == b"first line"


# ── rm tests ──────────────────────────────────────────────────────────


class TestRm:
    """Tests for Workspace.rm()."""

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_rm_single_file(self, mock_fs_cls, mock_batch, ws):
        ws._fs.exists.return_value = True
        ws._fs.isfile.return_value = True

        result = ws.rm("old.py")
        assert result == ["old.py"]

        mock_batch.assert_called_once()
        delete_list = mock_batch.call_args[1]["delete"]
        assert delete_list == ["old.py"]

    def test_rm_nonexistent_raises(self, ws):
        ws._fs.exists.return_value = False
        ws._fs.ls.return_value = []

        with pytest.raises(FileNotFoundInWorkspaceError):
            ws.rm("ghost.py")

    def test_rm_directory_without_recursive_raises(self, ws):
        ws._fs.exists.return_value = True
        ws._fs.isfile.return_value = False

        with pytest.raises(MembaseError, match="recursive"):
            ws.rm("mydir/")

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_rm_directory_recursive(self, mock_fs_cls, mock_batch, ws):
        ws._fs.exists.return_value = True
        ws._fs.isfile.return_value = False
        ws._fs.find.return_value = [
            "buckets/user/test-project/mydir/a.py",
            "buckets/user/test-project/mydir/b.py",
        ]

        result = ws.rm("mydir/", recursive=True)
        assert len(result) == 2
        assert "a.py" in result[0] or "mydir/a.py" in result[0]


# ── mv tests ─────────────────────────────────────────────────────────


class TestMv:
    """Tests for Workspace.mv()."""

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_mv_returns_destination(self, mock_fs_cls, mock_batch, ws):
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"content"
        ws._fs.open.return_value = mock_file

        result = ws.mv("old.py", "new.py")
        assert result == "new.py"

        call_args = mock_batch.call_args
        assert "add" in call_args[1]
        assert "delete" in call_args[1]
        assert call_args[1]["delete"] == ["old.py"]


# ── cp tests ─────────────────────────────────────────────────────────


class TestCp:
    """Tests for Workspace.cp()."""

    @patch("membase.workspace.batch_bucket_files")
    @patch("membase.workspace.HfFileSystem")
    def test_cp_returns_destination(self, mock_fs_cls, mock_batch, ws):
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"data"
        ws._fs.open.return_value = mock_file

        result = ws.cp("src.py", "dst.py")
        assert result == "dst.py"


# ── ls tests ──────────────────────────────────────────────────────────


class TestLs:
    """Tests for Workspace.ls()."""

    def test_ls_returns_entries(self, ws):
        ws._fs.ls.return_value = [
            {"name": "buckets/user/test-project/main.py", "type": "file", "size": 100},
            {"name": "buckets/user/test-project/src", "type": "directory", "size": 0},
        ]

        entries = ws.ls()
        assert len(entries) == 2
        assert isinstance(entries[0], LSEntry)

        names = [e.name for e in entries]
        assert "main.py" in names
        assert "src" in names

    def test_ls_not_found(self, ws):
        ws._fs.ls.side_effect = FileNotFoundError()
        ws._fs.ls.return_value = []

        # Need to handle the double call — the second ls is in _available_at_level
        side_effects = [FileNotFoundError(), []]
        ws._fs.ls.side_effect = side_effects

        with pytest.raises(FileNotFoundInWorkspaceError):
            ws.ls("nonexistent/")

    def test_ls_subdirectory(self, ws):
        ws._fs.ls.return_value = [
            {"name": "buckets/user/test-project/src/main.py", "type": "file", "size": 500},
        ]

        entries = ws.ls("src/")
        assert len(entries) == 1
        assert entries[0].name == "main.py"


# ── walk tests ────────────────────────────────────────────────────────


class TestWalk:
    """Tests for Workspace.walk()."""

    def test_walk_yields_tuples(self, ws):
        ws._fs.walk.return_value = [
            ("buckets/user/test-project", ["src"], ["README.md"]),
            ("buckets/user/test-project/src", [], ["main.py"]),
        ]

        results = list(ws.walk())
        assert len(results) == 2

        dirpath, dirs, files = results[0]
        assert dirpath == ""
        assert dirs == ["src"]
        assert files == ["README.md"]

        dirpath, dirs, files = results[1]
        assert dirpath == "src"
        assert files == ["main.py"]

    def test_walk_with_root(self, ws_with_root):
        ws_with_root._fs.walk.return_value = [
            ("buckets/user/test-project/data/v1", ["train"], ["readme.txt"]),
            ("buckets/user/test-project/data/v1/train", [], ["data.csv"]),
        ]

        results = list(ws_with_root.walk())
        assert results[0][0] == ""
        assert results[1][0] == "train"


# ── exists / is_file / is_dir tests ──────────────────────────────────


class TestExistsAndTypeChecks:
    """Tests for exists(), is_file(), is_dir()."""

    def test_exists_true(self, ws):
        ws._fs.exists.return_value = True
        assert ws.exists("file.txt") is True

    def test_exists_false(self, ws):
        ws._fs.exists.return_value = False
        assert ws.exists("nope.txt") is False

    def test_exists_delegates_correct_path(self, ws):
        ws._fs.exists.return_value = True
        ws.exists("src/main.py")
        ws._fs.exists.assert_called_with("buckets/user/test-project/src/main.py")

    def test_is_file_true(self, ws):
        ws._fs.isfile.return_value = True
        assert ws.is_file("main.py") is True

    def test_is_file_false_for_dir(self, ws):
        ws._fs.isfile.return_value = False
        assert ws.is_file("src/") is False

    def test_is_dir_true(self, ws):
        ws._fs.isdir.return_value = True
        assert ws.is_dir("src/") is True

    def test_is_dir_false_for_file(self, ws):
        ws._fs.isdir.return_value = False
        assert ws.is_dir("main.py") is False

    def test_is_file_delegates_correct_path(self, ws_with_root):
        ws_with_root._fs.isfile.return_value = True
        ws_with_root.is_file("train.csv")
        ws_with_root._fs.isfile.assert_called_with(
            "buckets/user/test-project/data/v1/train.csv"
        )


# ── stat tests ────────────────────────────────────────────────────────


class TestStat:
    """Tests for Workspace.stat()."""

    def test_stat_returns_filestat(self, ws):
        ws._fs.info.return_value = {"size": 2048, "type": "file"}

        result = ws.stat("data.csv")
        assert isinstance(result, FileStat)
        assert result.path == "data.csv"
        assert result.size == 2048
        assert result.type == "file"

    def test_stat_not_found(self, ws):
        ws._fs.info.side_effect = FileNotFoundError()
        ws._fs.ls.return_value = []

        with pytest.raises(FileNotFoundInWorkspaceError):
            ws.stat("nope.txt")


# ── du tests ──────────────────────────────────────────────────────────


class TestDu:
    """Tests for Workspace.du()."""

    def test_du_workspace_root(self, ws):
        ws._fs.du.return_value = 12345
        assert ws.du() == 12345
        ws._fs.du.assert_called_with("buckets/user/test-project")

    def test_du_subdirectory(self, ws):
        ws._fs.du.return_value = 5000
        assert ws.du("src/") == 5000
        ws._fs.du.assert_called_with("buckets/user/test-project/src/")


# ── download tests ────────────────────────────────────────────────────


class TestDownload:
    """Tests for Workspace.download()."""

    def test_download_writes_local_file(self, ws):
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"csv,data\n1,2\n"
        ws._fs.open.return_value = mock_file

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, "result.csv")
            result = ws.download("data.csv", local_path)

            assert result == local_path
            with open(local_path, "rb") as f:
                assert f.read() == b"csv,data\n1,2\n"

    def test_download_creates_parent_directories(self, ws):
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = b"data"
        ws._fs.open.return_value = mock_file

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, "deep", "nested", "file.txt")
            ws.download("remote.txt", local_path)
            assert os.path.exists(local_path)


# ── url tests ─────────────────────────────────────────────────────────


class TestUrl:
    """Tests for Workspace.url()."""

    def test_url_root(self, ws):
        assert ws.url() == "hf://buckets/user/test-project"

    def test_url_with_path(self, ws):
        expected = "hf://buckets/user/test-project/data/train.csv"
        assert ws.url("data/train.csv") == expected

    def test_url_with_root(self, ws_with_root):
        expected = "hf://buckets/user/test-project/data/v1/train.csv"
        assert ws_with_root.url("train.csv") == expected

    def test_url_empty_string(self, ws):
        assert ws.url("") == "hf://buckets/user/test-project"


# ── fs property test ──────────────────────────────────────────────────


class TestFsProperty:
    """Tests for Workspace.fs escape hatch."""

    def test_fs_returns_the_filesystem(self, ws):
        assert ws.fs is ws._fs


# ── info tests ────────────────────────────────────────────────────────


class TestInfo:
    """Tests for Workspace.info()."""

    @patch("membase.workspace.list_bucket_tree")
    @patch("membase.workspace.bucket_info")
    def test_info_returns_workspace_info(self, mock_bi, mock_tree, ws):
        mock_bi.return_value = MagicMock(private=True)

        file_item = MagicMock()
        file_item.type = "file"
        file_item.size = 1024

        dir_item = MagicMock()
        dir_item.type = "directory"
        dir_item.size = 0

        mock_tree.return_value = [file_item, file_item, dir_item]

        result = ws.info()
        assert isinstance(result, WorkspaceInfo)
        assert result.file_count == 2
        assert result.total_size == 2048
        assert result.private is True
        assert result.name == "test-project"


# ── sync / invalidate tests ──────────────────────────────────────────


class TestSyncAndInvalidate:
    """Tests for Workspace.sync() and invalidate()."""

    def test_sync_creates_mirror_if_none(self, ws):
        assert ws._mirror is None

        with patch("huggingface_hub.sync_bucket"):
            ws.sync()

        assert ws._mirror is not None
        assert ws._mirror_enabled is True

    def test_sync_passes_delete_flag(self, ws):
        ws._mirror = MagicMock()
        ws.sync(direction="pull", delete=True)
        ws._mirror.sync.assert_called_once_with(direction="pull", delete=True)

    @patch("membase.workspace.HfFileSystem")
    def test_invalidate_refreshes_fs(self, mock_fs_cls, ws):
        old_fs = ws._fs
        ws.invalidate()
        assert ws._fs is not old_fs or mock_fs_cls.called

    @patch("membase.workspace.HfFileSystem")
    def test_invalidate_with_mirror(self, mock_fs_cls, ws):
        ws._mirror = MagicMock()
        ws.invalidate()
        ws._mirror.invalidate.assert_called_once()

    @patch("membase.workspace.HfFileSystem")
    def test_invalidate_without_mirror(self, mock_fs_cls, ws):
        """invalidate() should not raise when there's no mirror."""
        ws._mirror = None
        ws.invalidate()


# ── delete class method tests ─────────────────────────────────────────


class TestWorkspaceDelete:
    """Tests for Workspace.delete() classmethod."""

    @patch("membase.workspace.delete_bucket")
    def test_delete_calls_sdk(self, mock_delete):
        Workspace.delete("old-project", token="tok")
        mock_delete.assert_called_once_with("old-project", missing_ok=False, token="tok")

    @patch("membase.workspace.delete_bucket")
    def test_delete_missing_ok(self, mock_delete):
        Workspace.delete("old-project", missing_ok=True, token="tok")
        mock_delete.assert_called_once_with("old-project", missing_ok=True, token="tok")

    @patch("membase.workspace.delete_bucket")
    def test_delete_wraps_404_with_missing_ok(self, mock_delete):
        mock_delete.side_effect = Exception("HTTP 404 not found")
        Workspace.delete("gone", missing_ok=True, token="tok")

    @patch("membase.workspace.delete_bucket")
    def test_delete_raises_workspace_not_found(self, mock_delete):
        mock_delete.side_effect = Exception("HTTP 500 server error")

        with pytest.raises(WorkspaceNotFoundError):
            Workspace.delete("broken", token="tok")


# ── grep filtering tests ─────────────────────────────────────────────


class TestGrepFiltering:
    """Tests for the include/exclude filtering in _grep_remote."""

    @patch("membase.workspace.parallel_grep", return_value=[])
    def test_grep_include_filters_files(self, mock_pg, ws):
        ws._fs.find.return_value = [
            "buckets/user/test-project/main.py",
            "buckets/user/test-project/data.csv",
            "buckets/user/test-project/test.py",
        ]

        ws.grep("pattern", include="*.py")

        filtered_files = mock_pg.call_args[0][2]
        paths = [f.split("/")[-1] for f in filtered_files]
        assert "main.py" in paths
        assert "test.py" in paths
        assert "data.csv" not in paths

    @patch("membase.workspace.parallel_grep", return_value=[])
    def test_grep_exclude_filters_files(self, mock_pg, ws):
        ws._fs.find.return_value = [
            "buckets/user/test-project/main.py",
            "buckets/user/test-project/test_main.py",
        ]

        ws.grep("pattern", exclude="test_*")

        filtered_files = mock_pg.call_args[0][2]
        paths = [f.split("/")[-1] for f in filtered_files]
        assert "main.py" in paths
        assert "test_main.py" not in paths

    def test_grep_empty_workspace(self, ws):
        ws._fs.find.return_value = []
        results = ws.grep("pattern")
        assert results == []

    def test_grep_uses_local_when_mirror_synced(self, ws):
        ws._mirror = MagicMock()
        ws._mirror.is_synced = True
        ws._mirror.list_local_files.return_value = []

        with patch("membase.workspace.local_grep", return_value=[]) as mock_lg:
            ws.grep("pattern")

        mock_lg.assert_called_once()


# ── _available_at_level tests ─────────────────────────────────────────


class TestAvailableAtLevel:
    """Tests for the error hint helper."""

    def test_returns_relative_paths(self, ws):
        ws._fs.ls.return_value = [
            "buckets/user/test-project/README.md",
            "buckets/user/test-project/src",
        ]

        available = ws._available_at_level("missing.py")
        assert "README.md" in available
        assert "src" in available

    def test_returns_empty_on_ls_failure(self, ws):
        ws._fs.ls.side_effect = Exception("network error")
        assert ws._available_at_level("missing.py") == []

    def test_nested_path_lists_parent(self, ws):
        ws._fs.ls.return_value = [
            "buckets/user/test-project/src/main.py",
            "buckets/user/test-project/src/utils.py",
        ]

        available = ws._available_at_level("src/missing.py")
        assert "src/main.py" in available
