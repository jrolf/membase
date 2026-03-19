"""Compatibility layer for known huggingface_hub SDK issues.

Encapsulates workarounds so the rest of the codebase can call clean
functions without caring about which SDK version is installed or which
bugs are present.
"""

import fnmatch
from pathlib import PurePosixPath


def find_files_by_pattern(hffs, bucket_path, pattern):
    """Glob-like file search using find() + fnmatch.

    Works around the ``hffs.glob()`` maxdepth bug in SDK 1.7.x that
    raises a TypeError when recursive patterns are used on buckets.

    Falls back to ``hffs.glob()`` first; if that raises a TypeError,
    uses the manual find-and-filter approach.

    Args:
        hffs: An HfFileSystem instance.
        bucket_path: Full bucket path (e.g. "buckets/user/bucket-name").
        pattern: Glob pattern relative to the bucket root.
            Supports ``**/*.py``, ``src/*.py``, ``**/test_*.py``, etc.

    Returns:
        List of full file paths matching the pattern.

    Example:
        >>> find_files_by_pattern(hffs, "buckets/u/b", "**/*.py")
        ["buckets/u/b/src/main.py", "buckets/u/b/tests/test_main.py"]
    """
    full_pattern = f"{bucket_path}/{pattern}"

    try:
        results = hffs.glob(full_pattern)
        return [r for r in results if hffs.isfile(r)]
    except TypeError:
        pass

    return _manual_glob(hffs, bucket_path, pattern)


def _manual_glob(hffs, bucket_path, pattern):
    """Find files matching a glob pattern without using hffs.glob().

    Uses hffs.find() to get all files, then filters with fnmatch.

    Args:
        hffs: An HfFileSystem instance.
        bucket_path: Full bucket path.
        pattern: Glob pattern relative to the bucket root.

    Returns:
        List of matching full file paths.
    """
    prefix = f"{bucket_path}/"
    all_files = hffs.find(bucket_path)
    rel_files = [(f, f[len(prefix):]) for f in all_files if f.startswith(prefix)]

    if "**" in pattern:
        flat_pattern = pattern.replace("**/", "")
        return [
            full for full, rel in rel_files
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, flat_pattern)
        ]

    suffix_pattern = PurePosixPath(pattern).name
    dir_prefix = str(PurePosixPath(pattern).parent)
    matched = []

    for full, rel in rel_files:
        rel_path = PurePosixPath(rel)
        rel_dir = str(rel_path.parent)

        if dir_prefix == ".":
            if len(rel_path.parts) == 1 and fnmatch.fnmatch(rel_path.name, suffix_pattern):
                matched.append(full)
        elif rel_dir == dir_prefix and fnmatch.fnmatch(rel_path.name, suffix_pattern):
            matched.append(full)

    return matched


def ensure_nonempty_bytes(content_bytes):
    """Ensure content is at least 1 byte to avoid the Xet 0-byte bug.

    HF Buckets' Xet backend returns a 500 error when reading files that
    were uploaded with exactly 0 bytes. This function ensures we always
    write at least a newline.

    Args:
        content_bytes: The bytes to upload.

    Returns:
        The original bytes if non-empty, otherwise ``b"\\n"``.
    """
    if not content_bytes:
        return b"\n"
    return content_bytes
