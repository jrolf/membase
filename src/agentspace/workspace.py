"""The Workspace class — the entire public API of agentspace.

A Workspace is a Python object bound to a single Hugging Face Storage Bucket.
Every filesystem operation goes through this class. Paths are always relative
to the workspace root.
"""

import fnmatch

from huggingface_hub import (
    HfFileSystem,
    batch_bucket_files,
    bucket_info,
    create_bucket,
    delete_bucket,
    list_bucket_tree,
)

from ._compat import ensure_nonempty_bytes, find_files_by_pattern
from .cache import LocalMirror
from .errors import (
    AgentSpaceError,
    EditConflictError,
    FileNotFoundInWorkspaceError,
    WorkspaceNotFoundError,
)
from .formatting import format_size, format_tree
from .search import local_grep, parallel_grep


class WorkspaceInfo:
    """Metadata about a workspace.

    Returned by ``Workspace.info()``. Has a compact ``__repr__`` for
    agent consumption.

    Attributes:
        name: The bucket name (without namespace).
        namespace: The owner namespace (user or org).
        bucket_id: Full bucket identifier ("namespace/name").
        private: Whether the workspace is private.
        file_count: Number of files in the workspace.
        total_size: Total size in bytes.
        created_at: Creation timestamp (datetime or None).
    """

    __slots__ = ("name", "namespace", "bucket_id", "private",
                 "file_count", "total_size", "created_at")

    def __init__(self, name, namespace, bucket_id, private,
                 file_count, total_size, created_at):
        self.name = name
        self.namespace = namespace
        self.bucket_id = bucket_id
        self.private = private
        self.file_count = file_count
        self.total_size = total_size
        self.created_at = created_at

    def __repr__(self):
        vis = "private" if self.private else "public"
        return (
            f"WorkspaceInfo('{self.bucket_id}', {vis}, "
            f"{self.file_count} files, {format_size(self.total_size)})"
        )


class FileStat:
    """Metadata about a single file.

    Returned by ``Workspace.stat()``.

    Attributes:
        path: Relative path within the workspace.
        size: File size in bytes.
        type: "file" or "directory".
    """

    __slots__ = ("path", "size", "type")

    def __init__(self, path, size, file_type):
        self.path = path
        self.size = size
        self.type = file_type

    def __repr__(self):
        if self.type == "directory":
            return f"FileStat('{self.path}/', directory)"
        return f"FileStat('{self.path}', {format_size(self.size)})"


class LSEntry:
    """A single entry from a directory listing.

    Attributes:
        name: File or directory name (basename only).
        path: Relative path from workspace root.
        type: "file" or "directory".
        size: Size in bytes (0 for directories).
    """

    __slots__ = ("name", "path", "type", "size")

    def __init__(self, name, path, entry_type, size=0):
        self.name = name
        self.path = path
        self.type = entry_type
        self.size = size

    def __repr__(self):
        if self.type == "directory":
            return f"{self.name}/"
        return f"{self.name} ({format_size(self.size)})"


class Workspace:
    """An agent workspace backed by a Hugging Face Storage Bucket.

    The primary interface for all agentspace operations. Each Workspace
    is bound to a single bucket. All paths are relative to the workspace
    root — no URIs, no namespace prefixes.

    Args:
        name: Bucket name. Can include a namespace ("org/name") or just
            the name (uses the authenticated user's namespace).
        private: Whether to create the bucket as private. Only matters
            when the bucket doesn't already exist. Defaults to True.
        root: Optional subdirectory to scope all operations to. When set,
            every path is relative to this root within the bucket.
        mirror: If True, enables local mirroring for faster repeated
            reads and searches. The first operation syncs the bucket to
            a temporary local directory.
        token: HF API token. If None, auto-discovers from environment
            (``HF_TOKEN``, ``hf auth login`` stored token).

    Example:
        >>> from agentspace import Workspace
        >>> ws = Workspace("my-project")
        >>> ws.write("hello.txt", "Hello from Agent Space.")
        'hello.txt'
        >>> ws.read("hello.txt")
        'Hello from Agent Space.'
    """

    def __init__(self, name, private=True, root=None, mirror=False, token=None):
        self._token = token
        self._mirror_enabled = mirror
        self._mirror = None
        self._root = root.strip("/") if root else None

        result = create_bucket(name, private=private, exist_ok=True, token=token)
        self._bucket_id = result.bucket_id
        self._bucket_uri = f"hf://buckets/{self._bucket_id}"
        self._bucket_path = f"buckets/{self._bucket_id}"

        if "/" in self._bucket_id:
            self._namespace, self._name = self._bucket_id.split("/", 1)
        else:
            self._namespace = ""
            self._name = self._bucket_id

        self._fs = HfFileSystem(token=token)

        if mirror:
            self._mirror = LocalMirror(self._bucket_id, self._bucket_uri)

    def __repr__(self):
        root_suffix = f", root='{self._root}'" if self._root else ""
        mirror_suffix = ", mirror=True" if self._mirror_enabled else ""
        return f"Workspace('{self._bucket_id}'{root_suffix}{mirror_suffix})"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._mirror:
            self._mirror.cleanup()
        return False

    # ── internal helpers ──────────────────────────────────────────────

    def _full_path(self, relative_path):
        """Convert a relative path to a full bucket path for HfFileSystem.

        Handles leading slashes, dot-slash prefixes, and the workspace
        root scoping.
        """
        path = relative_path.lstrip("./")
        if self._root:
            path = f"{self._root}/{path}" if path else self._root
        return f"{self._bucket_path}/{path}" if path else self._bucket_path

    def _rel_path(self, full_path):
        """Convert a full bucket path back to a workspace-relative path."""
        prefix = f"{self._bucket_path}/"
        if self._root:
            prefix = f"{self._bucket_path}/{self._root}/"
        if full_path.startswith(prefix):
            return full_path[len(prefix):]
        return full_path

    def _remote_rel_path(self, relative_path):
        """Convert a workspace-relative path to a bucket-relative path.

        Used for SDK calls that take bucket-relative paths (not fsspec paths).
        """
        path = relative_path.lstrip("./")
        if self._root:
            return f"{self._root}/{path}" if path else self._root
        return path

    def _refresh_fs(self):
        """Create a fresh HfFileSystem to avoid stale cache after writes."""
        self._fs = HfFileSystem(token=self._token, skip_instance_cache=True)

    def _available_at_level(self, path):
        """List available files/dirs at the same directory level as path.

        Used for error messages that help agents self-correct.
        """
        parts = path.strip("/").split("/")
        if len(parts) <= 1:
            parent = self._full_path("")
        else:
            parent = self._full_path("/".join(parts[:-1]))

        try:
            items = self._fs.ls(parent, detail=False)
            prefix = f"{self._bucket_path}/"
            if self._root:
                prefix = f"{self._bucket_path}/{self._root}/"
            return [item[len(prefix):] for item in items if item.startswith(prefix)]
        except Exception:
            return []

    # ── reading ───────────────────────────────────────────────────────

    def read(self, path, binary=False, head=None, tail=None, lines=None):
        """Read a file from the workspace.

        Args:
            path: Relative path to the file.
            binary: If True, return bytes instead of str.
            head: If set, return only the first N lines.
            tail: If set, return only the last N lines.
            lines: If set, a (start, end) tuple for a specific line range
                (1-indexed, inclusive).

        Returns:
            File content as str (default) or bytes (if binary=True).
            When head/tail/lines is used, returns only the requested lines
            as a single string.

        Raises:
            FileNotFoundInWorkspaceError: If the file does not exist.

        Example:
            >>> ws.read("src/main.py")
            'def main():\\n    ...'
            >>> ws.read("src/main.py", head=5)
            '(first 5 lines)'
        """
        full = self._full_path(path)

        try:
            if binary:
                with self._fs.open(full, "rb") as f:
                    return f.read()

            content = self._fs.read_text(full)
        except FileNotFoundError:
            available = self._available_at_level(path)
            raise FileNotFoundInWorkspaceError(path, self._name, available)

        if head is not None:
            all_lines = content.split("\n")
            return "\n".join(all_lines[:head])

        if tail is not None:
            all_lines = content.split("\n")
            return "\n".join(all_lines[-tail:])

        if lines is not None:
            start, end = lines
            all_lines = content.split("\n")
            return "\n".join(all_lines[start - 1:end])

        return content

    def read_many(self, paths, max_workers=16):
        """Read multiple files in parallel.

        Uses ThreadPoolExecutor for concurrent reads. Reading 10 files
        takes ~150ms instead of ~900ms sequential.

        Args:
            paths: List of relative file paths.
            max_workers: Number of parallel reader threads. Defaults to 16.

        Returns:
            Dict mapping each path to its content (str). Files that fail
            to read are silently omitted.

        Example:
            >>> contents = ws.read_many(["a.py", "b.py", "c.py"])
            >>> contents["a.py"]
            '...'
        """
        from concurrent.futures import ThreadPoolExecutor

        def read_one(rel_path):
            full = self._full_path(rel_path)
            try:
                fs = HfFileSystem(token=self._token)
                content = fs.read_text(full)
                return rel_path, content
            except Exception:
                return rel_path, None

        results = {}
        worker_count = min(max_workers, len(paths))
        if worker_count == 0:
            return results

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            for rel_path, content in pool.map(read_one, paths):
                if content is not None:
                    results[rel_path] = content

        return results

    # ── writing ───────────────────────────────────────────────────────

    def write(self, path, content):
        """Write a file to the workspace.

        Creates parent directories automatically. Overwrites existing files.

        Args:
            path: Relative path for the file.
            content: File content as str or bytes.

        Returns:
            The path that was written (same as the input path).

        Example:
            >>> ws.write("src/main.py", "def main(): pass")
            'src/main.py'
        """
        bucket_rel = self._remote_rel_path(path)

        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
        else:
            content_bytes = content

        content_bytes = ensure_nonempty_bytes(content_bytes)
        batch_bucket_files(
            self._bucket_id,
            add=[(content_bytes, bucket_rel)],
            token=self._token,
        )
        self._refresh_fs()

        if self._mirror and self._mirror.is_synced:
            self._mirror.invalidate()

        return path

    def write_many(self, files):
        """Write multiple files in a single network call.

        Batch upload takes ~700ms whether it's 1 file or 200.

        Args:
            files: Dict mapping relative paths to content (str or bytes).

        Returns:
            List of paths that were written.

        Example:
            >>> ws.write_many({
            ...     "src/__init__.py": "",
            ...     "src/core.py": "def run(): pass",
            ... })
            ['src/__init__.py', 'src/core.py']
        """
        add_list = []
        for rel_path, content in files.items():
            bucket_rel = self._remote_rel_path(rel_path)
            if isinstance(content, str):
                content_bytes = content.encode("utf-8")
            else:
                content_bytes = content
            content_bytes = ensure_nonempty_bytes(content_bytes)
            add_list.append((content_bytes, bucket_rel))

        batch_bucket_files(self._bucket_id, add=add_list, token=self._token)
        self._refresh_fs()

        if self._mirror and self._mirror.is_synced:
            self._mirror.invalidate()

        return list(files.keys())

    def edit(self, path, old, new):
        """Find-and-replace within a file.

        Implements the StrReplace pattern used by coding agents. Reads the
        file, performs the replacement, and writes it back — all without
        the agent needing to hold the full file in its context window.

        Only the **first** occurrence of ``old`` is replaced. If the old
        string is not found, raises EditConflictError.

        Args:
            path: Relative path to the file.
            old: The exact string to find.
            new: The replacement string.

        Returns:
            The path that was edited.

        Raises:
            FileNotFoundInWorkspaceError: If the file does not exist.
            EditConflictError: If the old string is not found in the file.

        Example:
            >>> ws.edit("config.py", old="DEBUG = True", new="DEBUG = False")
            'config.py'
        """
        content = self.read(path)

        if old not in content:
            raise EditConflictError(path, old)

        updated = content.replace(old, new, 1)
        self.write(path, updated)
        return path

    def append(self, path, content):
        """Append content to an existing file (or create it).

        Handles the read-modify-write cycle internally. There is no native
        append mode on HF Buckets — this method encapsulates the workaround.

        Args:
            path: Relative path to the file.
            content: Content to append (str).

        Returns:
            The path that was appended to.

        Example:
            >>> ws.append("log.txt", "[10:00:01] Step complete\\n")
            'log.txt'
        """
        try:
            existing = self.read(path)
        except FileNotFoundInWorkspaceError:
            existing = ""

        self.write(path, existing + content)
        return path

    # ── deleting and moving ───────────────────────────────────────────

    def rm(self, path, recursive=False):
        """Delete a file or directory from the workspace.

        Args:
            path: Relative path to delete.
            recursive: If True and path is a directory, delete all contents.
                Required for non-empty directories.

        Returns:
            List of paths that were deleted.

        Raises:
            FileNotFoundInWorkspaceError: If the path does not exist.

        Example:
            >>> ws.rm("old_file.py")
            ['old_file.py']
            >>> ws.rm("old_dir/", recursive=True)
            ['old_dir/a.py', 'old_dir/b.py']
        """
        full = self._full_path(path)

        if not self._fs.exists(full):
            available = self._available_at_level(path)
            raise FileNotFoundInWorkspaceError(path, self._name, available)

        if self._fs.isfile(full):
            bucket_rel = self._remote_rel_path(path)
            batch_bucket_files(self._bucket_id, delete=[bucket_rel], token=self._token)
            self._refresh_fs()
            return [path]

        if not recursive:
            raise AgentSpaceError(
                f"'{path}' is a directory. Use rm(path, recursive=True) to delete it."
            )

        all_files = self._fs.find(full)
        prefix = f"{self._bucket_path}/"
        bucket_rels = [f[len(prefix):] for f in all_files if f.startswith(prefix)]

        if bucket_rels:
            batch_bucket_files(self._bucket_id, delete=bucket_rels, token=self._token)
            self._refresh_fs()

        return [self._rel_path(f) for f in all_files]

    def mv(self, src, dst):
        """Move or rename a file within the workspace.

        Implemented as read + batch(add, delete) since HF Buckets do not
        support native move operations.

        Args:
            src: Source relative path.
            dst: Destination relative path.

        Returns:
            The destination path.

        Raises:
            FileNotFoundInWorkspaceError: If the source does not exist.

        Example:
            >>> ws.mv("old_name.py", "new_name.py")
            'new_name.py'
        """
        content = self.read(src, binary=True)
        src_bucket_rel = self._remote_rel_path(src)
        dst_bucket_rel = self._remote_rel_path(dst)

        batch_bucket_files(
            self._bucket_id,
            add=[(content, dst_bucket_rel)],
            delete=[src_bucket_rel],
            token=self._token,
        )
        self._refresh_fs()
        return dst

    def cp(self, src, dst):
        """Copy a file within the workspace.

        Implemented as read + write since HF Buckets do not support native
        copy operations.

        Args:
            src: Source relative path.
            dst: Destination relative path.

        Returns:
            The destination path.

        Raises:
            FileNotFoundInWorkspaceError: If the source does not exist.

        Example:
            >>> ws.cp("template.py", "new_module.py")
            'new_module.py'
        """
        content = self.read(src, binary=True)
        self.write(dst, content)
        return dst

    # ── exploration ───────────────────────────────────────────────────

    def ls(self, path=""):
        """List the contents of a directory.

        Args:
            path: Relative directory path. Defaults to workspace root.

        Returns:
            List of LSEntry objects, each with name, path, type, and size.

        Example:
            >>> for entry in ws.ls("src/"):
            ...     print(entry)
            __init__.py (45 B)
            main.py (1.8 KB)
            utils/
        """
        full = self._full_path(path)

        try:
            items = self._fs.ls(full, detail=True)
        except FileNotFoundError:
            available = self._available_at_level(path)
            raise FileNotFoundInWorkspaceError(path, self._name, available)

        root_prefix = f"{self._bucket_path}/"
        if self._root:
            root_prefix = f"{self._bucket_path}/{self._root}/"

        entries = []
        for item in items:
            item_name = item["name"]

            if item_name.startswith(root_prefix):
                rel = item_name[len(root_prefix):]
            else:
                rel = item_name.rsplit("/", 1)[-1]

            basename = rel.rsplit("/", 1)[-1] if "/" in rel else rel
            entry_type = item.get("type", "file")
            size = item.get("size", 0) if entry_type == "file" else 0
            entries.append(LSEntry(basename, rel, entry_type, size))

        return entries

    def tree(self, path="", depth=None):
        """Generate an ASCII tree representation of the workspace.

        Designed to give an agent a full structural overview in minimal
        tokens — including file sizes so the agent can estimate context
        cost before reading.

        Args:
            path: Subtree root. Defaults to entire workspace.
            depth: Maximum depth to display. None for unlimited.

        Returns:
            Multi-line string with the ASCII tree.

        Example:
            >>> print(ws.tree())
            my-project/
            ├── README.md (200 B)
            └── src/
                └── main.py (1.8 KB)
            <BLANKLINE>
            2 files, 2.0 KB total
        """
        full = self._full_path(path)

        try:
            all_files = self._fs.find(full, detail=True)
        except FileNotFoundError:
            return f"{self._name}/\n(empty workspace)"

        root_prefix = f"{self._bucket_path}/"
        if self._root:
            root_prefix = f"{self._bucket_path}/{self._root}/"

        entries = []
        total_size = 0
        for file_path, info in all_files.items():
            if not file_path.startswith(root_prefix):
                continue
            rel = file_path[len(root_prefix):]
            if not rel:
                continue

            if depth is not None:
                if rel.count("/") >= depth:
                    continue

            size = info.get("size", 0)
            total_size += size
            entries.append({
                "path": rel,
                "type": "file",
                "size": size,
                "name": rel.rsplit("/", 1)[-1],
            })

        display_name = self._name
        if path:
            display_name = path.strip("/")

        return format_tree(entries, display_name, total_size)

    def glob(self, pattern):
        """Find files matching a glob pattern.

        Works around the hffs.glob() maxdepth bug by falling back to
        find() + fnmatch when needed.

        Args:
            pattern: Glob pattern relative to workspace root. Supports
                ``**/*.py``, ``src/*.py``, ``**/test_*.py``, etc.

        Returns:
            List of relative file paths matching the pattern.

        Example:
            >>> ws.glob("**/*.py")
            ['src/__init__.py', 'src/main.py', 'tests/test_main.py']
        """
        search_root = self._full_path("")
        full_matches = find_files_by_pattern(self._fs, search_root, pattern)
        return sorted(self._rel_path(m) for m in full_matches)

    def grep(self, pattern, include=None, exclude=None, max_results=200,
             context=0, max_workers=16):
        """Search for a regex pattern inside file contents.

        Uses parallel reads by default (16 workers, ~16x speedup over
        sequential). When a local mirror is active, searches locally
        instead (completes in <1ms for typical workspaces).

        Args:
            pattern: Regex pattern to search for.
            include: Optional glob pattern to filter which files to search
                (e.g. "*.py"). Only files matching this pattern are searched.
            exclude: Optional glob pattern to exclude files from search.
            max_results: Maximum matches to return. Prevents flooding the
                agent's context. Defaults to 200.
            context: Number of context lines before/after each match.
                Defaults to 0.
            max_workers: Number of parallel reader threads. Defaults to 16.

        Returns:
            List of GrepMatch objects with .path, .line_number, .line.

        Example:
            >>> results = ws.grep("def train", include="*.py")
            >>> for m in results:
            ...     print(f"{m.path}:{m.line_number}: {m.line}")
        """
        if self._mirror and self._mirror.is_synced:
            return self._grep_local(pattern, include, exclude, max_results)

        return self._grep_remote(pattern, include, exclude, max_results,
                                 context, max_workers)

    def _grep_remote(self, pattern, include, exclude, max_results,
                     context, max_workers):
        """Grep using parallel remote reads."""
        search_root = self._full_path("")
        all_files = self._fs.find(search_root)

        prefix = search_root + "/"
        filtered = []
        for f in all_files:
            if not f.startswith(prefix):
                continue
            rel = f[len(prefix):]
            if include and not fnmatch.fnmatch(rel, include):
                continue
            if exclude and fnmatch.fnmatch(rel, exclude):
                continue
            filtered.append(f)

        if not filtered:
            return []

        return parallel_grep(
            self._fs, search_root, filtered, pattern,
            max_results=max_results, context=context, max_workers=max_workers,
        )

    def _grep_local(self, pattern, include, exclude, max_results):
        """Grep using the local mirror (fast path)."""
        local_files = self._mirror.list_local_files()

        filtered = []
        for rel in local_files:
            if include and not fnmatch.fnmatch(rel, include):
                continue
            if exclude and fnmatch.fnmatch(rel, exclude):
                continue
            filtered.append(rel)

        return local_grep(self._mirror.local_dir, filtered, pattern, max_results)

    def exists(self, path):
        """Check whether a path exists in the workspace.

        Args:
            path: Relative path to check.

        Returns:
            True if the path exists (file or directory), False otherwise.

        Example:
            >>> ws.exists("src/main.py")
            True
            >>> ws.exists("nonexistent.py")
            False
        """
        full = self._full_path(path)
        return self._fs.exists(full)

    def stat(self, path):
        """Get metadata for a file or directory.

        Args:
            path: Relative path.

        Returns:
            A FileStat object with path, size, and type attributes.

        Raises:
            FileNotFoundInWorkspaceError: If the path does not exist.

        Example:
            >>> ws.stat("src/main.py")
            FileStat('src/main.py', 1.8 KB)
        """
        full = self._full_path(path)

        try:
            info = self._fs.info(full)
        except FileNotFoundError:
            available = self._available_at_level(path)
            raise FileNotFoundInWorkspaceError(path, self._name, available)

        return FileStat(
            path=path,
            size=info.get("size", 0),
            file_type=info.get("type", "file"),
        )

    def du(self, path=""):
        """Get the total size of a directory or file in bytes.

        Args:
            path: Relative path. Defaults to workspace root (total size).

        Returns:
            Total size in bytes (int).

        Example:
            >>> ws.du()
            47200
            >>> ws.du("src/")
            12800
        """
        full = self._full_path(path)
        return self._fs.du(full)

    # ── workspace metadata ────────────────────────────────────────────

    def info(self):
        """Get metadata about the workspace.

        Uses ``list_bucket_tree()`` for authoritative file counts (not
        ``bucket_info()`` which has eventually-consistent counters).

        Returns:
            A WorkspaceInfo object with name, namespace, file_count, etc.

        Example:
            >>> ws.info()
            WorkspaceInfo('user/my-project', private, 23 files, 47.2 KB)
        """
        bi = bucket_info(self._bucket_id, token=self._token)

        items = list(list_bucket_tree(self._bucket_id, recursive=True, token=self._token))
        file_count = sum(1 for i in items if getattr(i, "type", None) == "file")
        file_items = [i for i in items if getattr(i, "type", None) == "file"]
        total_size = sum(getattr(i, "size", 0) for i in file_items)

        return WorkspaceInfo(
            name=self._name,
            namespace=self._namespace,
            bucket_id=self._bucket_id,
            private=bi.private,
            file_count=file_count,
            total_size=total_size,
            created_at=getattr(bi, "created_at", None),
        )

    # ── sync and caching ─────────────────────────────────────────────

    def sync(self, direction="pull"):
        """Sync the workspace with its local mirror.

        Requires ``mirror=True`` when the workspace was created. If no
        mirror exists, creates one automatically.

        Args:
            direction: One of "pull" (remote -> local), "push" (local ->
                remote), or "both". Defaults to "pull".

        Returns:
            Path to the local mirror directory.

        Example:
            >>> ws = Workspace("my-project", mirror=True)
            >>> local_path = ws.sync()
        """
        if self._mirror is None:
            self._mirror = LocalMirror(self._bucket_id, self._bucket_uri)
            self._mirror_enabled = True

        return self._mirror.sync(direction=direction)

    def invalidate(self):
        """Clear cached metadata and mark the local mirror as stale.

        Call this if you know the remote workspace was modified externally
        (by another agent or a human).
        """
        self._refresh_fs()
        if self._mirror:
            self._mirror.invalidate()

    # ── interop ───────────────────────────────────────────────────────

    def url(self, path=""):
        """Get the full ``hf://`` URI for a file or the workspace root.

        Useful for passing to external tools (pandas, other APIs) that
        accept HF URIs directly.

        Args:
            path: Relative path. Defaults to workspace root.

        Returns:
            Full ``hf://buckets/...`` URI string.

        Example:
            >>> ws.url("data/train.csv")
            'hf://buckets/user/my-project/data/train.csv'
        """
        bucket_rel = self._remote_rel_path(path) if path else ""
        if bucket_rel:
            return f"{self._bucket_uri}/{bucket_rel}"
        return self._bucket_uri

    @property
    def fs(self):
        """Access the underlying HfFileSystem (escape hatch).

        Returns the raw ``HfFileSystem`` instance for operations not
        covered by the Workspace API. Paths must be constructed manually
        when using this property.

        Returns:
            HfFileSystem instance.
        """
        return self._fs

    # ── class methods ─────────────────────────────────────────────────

    @classmethod
    def delete(cls, name, missing_ok=False, token=None):
        """Delete an entire workspace (bucket).

        This is irreversible. All files in the workspace are permanently
        deleted.

        Args:
            name: Workspace name (e.g. "my-project" or "org/name").
            missing_ok: If True, don't raise an error if the workspace
                doesn't exist. Defaults to False.
            token: HF API token.

        Example:
            >>> Workspace.delete("scratch-workspace", missing_ok=True)
        """
        try:
            delete_bucket(name, missing_ok=missing_ok, token=token)
        except Exception as e:
            if "404" in str(e) and missing_ok:
                return
            raise WorkspaceNotFoundError(name, detail=str(e))
