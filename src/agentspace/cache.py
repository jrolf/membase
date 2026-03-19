"""Local mirror and metadata cache management.

Handles syncing a remote bucket to a local temporary directory for fast
repeated reads and searches. The sync cost is ~1.3s for a 28-file workspace;
subsequent local operations complete in <1ms.
"""

import os
import tempfile


class LocalMirror:
    """Manages a local filesystem mirror of a remote bucket.

    The mirror is a temporary directory that stays in sync with the remote
    bucket. After the initial sync, all reads and searches can operate on
    the local copy — eliminating network round-trips entirely.

    The mirror is not a full clone: it is a cache that can be invalidated
    and re-synced at any time.

    Args:
        bucket_id: The bucket identifier (e.g. "user/bucket-name").
        bucket_uri: The full hf:// URI (e.g. "hf://buckets/user/bucket").

    Attributes:
        local_dir: Path to the local mirror directory, or None if not synced.
        is_synced: Whether the mirror has been synced at least once.
    """

    def __init__(self, bucket_id, bucket_uri):
        self.bucket_id = bucket_id
        self.bucket_uri = bucket_uri
        self.local_dir = None
        self.is_synced = False

    def sync(self, direction="pull"):
        """Sync between the local mirror and the remote bucket.

        Args:
            direction: One of "pull" (remote -> local), "push" (local -> remote),
                or "both" (pull then push). Defaults to "pull".

        Returns:
            The local directory path.

        Raises:
            ValueError: If direction is not one of the allowed values.
        """
        from huggingface_hub import sync_bucket

        if direction not in ("pull", "push", "both"):
            raise ValueError(f"direction must be 'pull', 'push', or 'both', got {direction!r}")

        if self.local_dir is None:
            self.local_dir = tempfile.mkdtemp(prefix="agentspace_")

        if direction in ("pull", "both"):
            sync_bucket(self.bucket_uri, self.local_dir)
            self.is_synced = True

        if direction in ("push", "both"):
            sync_bucket(self.local_dir, self.bucket_uri)

        return self.local_dir

    def invalidate(self):
        """Mark the local mirror as stale.

        The mirror directory is kept (to avoid re-creating it), but
        ``is_synced`` is set to False so the next operation knows to
        re-sync.
        """
        self.is_synced = False

    def ensure_synced(self):
        """Sync the mirror if it has not been synced yet.

        Returns:
            The local directory path.
        """
        if not self.is_synced:
            return self.sync(direction="pull")
        return self.local_dir

    def list_local_files(self, suffix=None):
        """List files in the local mirror, optionally filtered by suffix.

        Args:
            suffix: If provided, only return files ending with this suffix
                (e.g. ".py").

        Returns:
            List of relative file paths (relative to the mirror root).
        """
        if not self.local_dir or not self.is_synced:
            return []

        files = []
        for root, _dirs, filenames in os.walk(self.local_dir):
            for fname in filenames:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, self.local_dir)
                if suffix is None or rel_path.endswith(suffix):
                    files.append(rel_path)

        return sorted(files)

    def cleanup(self):
        """Remove the local mirror directory and all its contents."""
        if self.local_dir and os.path.exists(self.local_dir):
            import shutil
            shutil.rmtree(self.local_dir, ignore_errors=True)
            self.local_dir = None
            self.is_synced = False
