"""agentspace — A fast, ergonomic workspace in the cloud for AI agents.

Gives AI agents a filesystem interface backed by Hugging Face Storage
Buckets. Designed for tool-calling agents that need to read, write,
search, and organize files in persistent cloud storage.

Quick start::

    from agentspace import Workspace

    ws = Workspace("my-project")
    ws.write("hello.txt", "Hello from Agent Space.")
    print(ws.read("hello.txt"))

The five essential operations — ``read``, ``write``, ``ls``, ``glob``,
``grep`` — cover the vast majority of agent filesystem needs.
"""

__version__ = "0.0.1"

from .errors import (
    AgentSpaceError,
    EditConflictError,
    FileNotFoundInWorkspaceError,
    WorkspaceNotFoundError,
    WorkspacePermissionError,
)
from .search import GrepMatch
from .workspace import FileStat, LSEntry, Workspace, WorkspaceInfo

__all__ = [
    "Workspace",
    "WorkspaceInfo",
    "FileStat",
    "LSEntry",
    "GrepMatch",
    "AgentSpaceError",
    "EditConflictError",
    "FileNotFoundInWorkspaceError",
    "WorkspaceNotFoundError",
    "WorkspacePermissionError",
]
