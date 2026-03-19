"""Agent-friendly error classes for membase.

These exceptions are designed to give AI agents enough context to self-correct.
Each error message includes not just what went wrong, but what the agent can
do next — listing nearby files, suggesting alternative paths, etc.
"""


class MembaseError(Exception):
    """Base exception for all membase errors."""
    pass


class WorkspaceNotFoundError(MembaseError):
    """Raised when a workspace (bucket) does not exist and cannot be created.

    Attributes:
        workspace_name: The name that was requested.
        message: Human-readable (and agent-readable) error description.
    """

    def __init__(self, workspace_name, detail=None):
        self.workspace_name = workspace_name
        msg = f"Workspace '{workspace_name}' not found."
        if detail:
            msg += f" {detail}"
        super().__init__(msg)


class FileNotFoundInWorkspaceError(MembaseError, FileNotFoundError):
    """Raised when a file does not exist in the workspace.

    Inherits from both MembaseError and FileNotFoundError so that
    standard ``except FileNotFoundError`` blocks catch it naturally.

    The error message includes a listing of nearby files so the agent
    can self-correct (e.g. fix a typo in the path).

    Attributes:
        path: The relative path that was requested.
        workspace_name: The workspace the lookup was attempted in.
        available: List of files/dirs at the same level, if known.
    """

    def __init__(self, path, workspace_name, available=None):
        self.path = path
        self.workspace_name = workspace_name
        self.available = available or []

        msg = f"'{path}' does not exist in workspace '{workspace_name}'."
        if self.available:
            listing = ", ".join(self.available[:15])
            if len(self.available) > 15:
                listing += f", ... ({len(self.available)} total)"
            msg += f" Available: {listing}"
        super().__init__(msg)


class EditConflictError(MembaseError):
    """Raised when an edit() call cannot find the old string in the file.

    This tells the agent that the file content doesn't match what it
    expected, which usually means the file was modified between the time
    the agent read it and the time it attempted the edit.

    Attributes:
        path: The file path.
        old_string: The string the agent tried to find.
    """

    def __init__(self, path, old_string):
        self.path = path
        self.old_string = old_string
        preview = old_string[:80]
        if len(old_string) > 80:
            preview += "..."
        super().__init__(
            f"Cannot edit '{path}': the text to replace was not found. "
            f"Searched for: {preview!r}"
        )


class WorkspacePermissionError(MembaseError, PermissionError):
    """Raised when the agent lacks permission to access a workspace.

    Attributes:
        workspace_name: The workspace that was denied.
    """

    def __init__(self, workspace_name, detail=None):
        self.workspace_name = workspace_name
        msg = f"Permission denied for workspace '{workspace_name}'."
        if detail:
            msg += f" {detail}"
        msg += " Check that your HF_TOKEN has write access."
        super().__init__(msg)
