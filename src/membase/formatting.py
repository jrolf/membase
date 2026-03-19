"""Output formatting for agent consumption.

Every function here produces compact, information-dense text designed to
minimize context window token cost while maximizing the agent's ability
to reason about workspace structure.
"""


def format_size(size_bytes):
    """Format a byte count as a compact human-readable string.

    Args:
        size_bytes: Integer byte count.

    Returns:
        Compact size string like "1.2 KB", "3.4 MB", or "512 B".

    Example:
        >>> format_size(1234)
        '1.2 KB'
        >>> format_size(0)
        '0 B'
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def format_tree(entries, workspace_name="", total_size=0):
    """Build an ASCII tree representation of workspace contents.

    Produces a compact, readable tree similar to the Unix ``tree`` command,
    with file sizes and directory summaries. Designed to give an agent a
    full structural overview of a workspace in minimal tokens.

    Args:
        entries: List of dicts with keys ``name``, ``type`` ("file" or
            "directory"), ``size`` (int, for files), and ``path`` (relative
            path from workspace root). Must be sorted by path.
        workspace_name: Name to display as the tree root.
        total_size: Total workspace size in bytes (for the summary line).

    Returns:
        Multi-line string with the ASCII tree.

    Example:
        >>> entries = [
        ...     {"path": "README.md", "type": "file", "size": 200},
        ...     {"path": "src/main.py", "type": "file", "size": 1800},
        ... ]
        >>> print(format_tree(entries, "my-project", 2000))
        my-project/
        ├── README.md (200 B)
        └── src/
            └── main.py (1.8 KB)
        <BLANKLINE>
        2 files, 2.0 KB total
    """
    if not entries:
        root_label = f"{workspace_name}/" if workspace_name else "./"
        return f"{root_label}\n(empty workspace)"

    tree = _build_tree_dict(entries)
    root_label = f"{workspace_name}/" if workspace_name else "./"
    lines = [root_label]
    _render_tree(tree, lines, prefix="")

    file_count = sum(1 for e in entries if e.get("type") == "file")
    size_str = format_size(total_size) if total_size else _sum_sizes(entries)
    lines.append("")
    lines.append(f"{file_count} files, {size_str} total")

    return "\n".join(lines)


def _sum_sizes(entries):
    """Sum file sizes from entries and return a formatted string."""
    total = sum(e.get("size", 0) for e in entries if e.get("type") == "file")
    return format_size(total)


def _build_tree_dict(entries):
    """Convert a flat list of file entries into a nested dict structure.

    Each key is a directory or file name. Files map to their entry dict.
    Directories map to another nested dict.
    """
    tree = {}
    for entry in entries:
        parts = entry["path"].split("/")
        node = tree
        for part in parts[:-1]:
            if part not in node:
                node[part] = {}
            node = node[part]
        node[parts[-1]] = entry
    return tree


def _render_tree(tree, lines, prefix):
    """Recursively render a tree dict into ASCII tree lines."""
    def sort_key(item):
        name, value = item
        is_leaf = not isinstance(value, dict) or "type" in value
        return (is_leaf, name)

    items = sorted(tree.items(), key=sort_key)
    dirs = [(k, v) for k, v in items if isinstance(v, dict) and "type" not in v]
    files = [(k, v) for k, v in items if not isinstance(v, dict) or "type" in v]

    all_items = dirs + files
    for i, (name, value) in enumerate(all_items):
        is_last = (i == len(all_items) - 1)
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        if isinstance(value, dict) and "type" not in value:
            child_files = _count_files_in_subtree(value)
            child_size = _sum_sizes_in_subtree(value)
            if child_files > 0 and child_files <= 3:
                lines.append(f"{prefix}{connector}{name}/")
            elif child_files > 3:
                lines.append(
                    f"{prefix}{connector}{name}/ "
                    f"({child_files} files, {format_size(child_size)})"
                )
            else:
                lines.append(f"{prefix}{connector}{name}/")
            _render_tree(value, lines, prefix + extension)
        else:
            size_str = format_size(value.get("size", 0)) if isinstance(value, dict) else ""
            if size_str:
                lines.append(f"{prefix}{connector}{name} ({size_str})")
            else:
                lines.append(f"{prefix}{connector}{name}")


def _count_files_in_subtree(tree):
    """Count files recursively in a tree dict."""
    count = 0
    for value in tree.values():
        if isinstance(value, dict) and "type" not in value:
            count += _count_files_in_subtree(value)
        else:
            count += 1
    return count


def _sum_sizes_in_subtree(tree):
    """Sum file sizes recursively in a tree dict."""
    total = 0
    for value in tree.values():
        if isinstance(value, dict) and "type" not in value:
            total += _sum_sizes_in_subtree(value)
        elif isinstance(value, dict):
            total += value.get("size", 0)
    return total


def format_ls(entries, path=""):
    """Format a directory listing as a compact table.

    Produces a token-efficient listing with name, size, and type
    information — similar to ``ls -lh`` but more compact.

    Args:
        entries: List of dicts with ``name``, ``type``, and ``size`` keys.
        path: The directory path being listed (for the header).

    Returns:
        Multi-line formatted string.

    Example:
        >>> entries = [
        ...     {"name": "main.py", "type": "file", "size": 1800},
        ...     {"name": "utils/", "type": "directory", "size": 0},
        ... ]
        >>> print(format_ls(entries, "src/"))
        src/
          main.py          1.8 KB
          utils/
    """
    header = f"{path}" if path else "./"
    lines = [header]

    dirs_first = sorted(entries, key=lambda e: (e.get("type") != "directory", e.get("name", "")))

    for entry in dirs_first:
        name = entry.get("name", "")
        entry_type = entry.get("type", "file")
        size = entry.get("size", 0)

        if entry_type == "directory":
            lines.append(f"  {name}/")
        else:
            size_str = format_size(size)
            lines.append(f"  {name:<20s} {size_str}")

    return "\n".join(lines)
