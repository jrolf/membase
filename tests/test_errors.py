"""Tests for agent-friendly error classes."""

from membase.errors import (
    EditConflictError,
    FileNotFoundInWorkspaceError,
    MembaseError,
    WorkspaceNotFoundError,
    WorkspacePermissionError,
)


class TestFileNotFoundInWorkspaceError:
    """Tests for the enhanced FileNotFoundError."""

    def test_basic_message(self):
        err = FileNotFoundInWorkspaceError("config.yaml", "my-project")
        assert "config.yaml" in str(err)
        assert "my-project" in str(err)

    def test_includes_available_files(self):
        err = FileNotFoundInWorkspaceError(
            "config.yaml",
            "my-project",
            available=["README.md", "pyproject.toml", "src/"],
        )
        msg = str(err)
        assert "README.md" in msg
        assert "pyproject.toml" in msg
        assert "src/" in msg

    def test_truncates_long_listings(self):
        available = [f"file_{i}.py" for i in range(20)]
        err = FileNotFoundInWorkspaceError("x.py", "proj", available=available)
        msg = str(err)
        assert "20 total" in msg

    def test_is_filenotfounderror(self):
        """Ensure standard except FileNotFoundError catches it."""
        err = FileNotFoundInWorkspaceError("x.py", "proj")
        assert isinstance(err, FileNotFoundError)
        assert isinstance(err, MembaseError)


class TestEditConflictError:
    """Tests for the edit conflict error."""

    def test_basic_message(self):
        err = EditConflictError("main.py", "old_text")
        assert "main.py" in str(err)
        assert "old_text" in str(err)

    def test_long_old_string_truncated(self):
        long_text = "x" * 200
        err = EditConflictError("main.py", long_text)
        msg = str(err)
        assert "..." in msg


class TestWorkspaceNotFoundError:
    """Tests for workspace not found."""

    def test_basic(self):
        err = WorkspaceNotFoundError("my-project")
        assert "my-project" in str(err)

    def test_with_detail(self):
        err = WorkspaceNotFoundError("my-project", detail="HTTP 404")
        assert "HTTP 404" in str(err)


class TestWorkspacePermissionError:
    """Tests for permission errors."""

    def test_basic(self):
        err = WorkspacePermissionError("my-project")
        assert "my-project" in str(err)
        assert "HF_TOKEN" in str(err)

    def test_is_permissionerror(self):
        err = WorkspacePermissionError("proj")
        assert isinstance(err, PermissionError)
