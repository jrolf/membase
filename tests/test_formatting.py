"""Tests for the formatting module — no network calls needed."""

from membase.formatting import format_ls, format_size, format_tree

# ── format_size tests ─────────────────────────────────────────────────


class TestFormatSize:
    """Tests for the format_size helper."""

    def test_zero_bytes(self):
        assert format_size(0) == "0 B"

    def test_small_bytes(self):
        assert format_size(512) == "512 B"

    def test_boundary_below_kilobyte(self):
        assert format_size(1023) == "1023 B"

    def test_exact_kilobyte(self):
        assert format_size(1024) == "1.0 KB"

    def test_kilobytes(self):
        assert format_size(1536) == "1.5 KB"
        assert format_size(10240) == "10.0 KB"

    def test_boundary_below_megabyte(self):
        just_under = 1024 * 1024 - 1
        result = format_size(just_under)
        assert "KB" in result

    def test_exact_megabyte(self):
        assert format_size(1048576) == "1.0 MB"

    def test_megabytes(self):
        assert format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_boundary_below_gigabyte(self):
        just_under = 1024 * 1024 * 1024 - 1
        result = format_size(just_under)
        assert "MB" in result

    def test_exact_gigabyte(self):
        assert format_size(1073741824) == "1.0 GB"

    def test_large_gigabytes(self):
        assert format_size(10 * 1024 * 1024 * 1024) == "10.0 GB"

    def test_single_byte(self):
        assert format_size(1) == "1 B"


# ── format_tree tests ─────────────────────────────────────────────────


class TestFormatTree:
    """Tests for the ASCII tree formatter."""

    def test_empty_workspace(self):
        result = format_tree([], "my-project", 0)
        assert "my-project/" in result
        assert "empty" in result

    def test_empty_workspace_no_name(self):
        result = format_tree([], "", 0)
        assert "./" in result

    def test_flat_files(self):
        entries = [
            {"path": "README.md", "type": "file", "size": 200, "name": "README.md"},
            {"path": "main.py", "type": "file", "size": 1800, "name": "main.py"},
        ]
        result = format_tree(entries, "project", 2000)
        assert "project/" in result
        assert "README.md" in result
        assert "main.py" in result
        assert "2 files" in result

    def test_nested_files(self):
        entries = [
            {"path": "src/main.py", "type": "file", "size": 1800, "name": "main.py"},
            {"path": "src/utils.py", "type": "file", "size": 500, "name": "utils.py"},
            {"path": "README.md", "type": "file", "size": 200, "name": "README.md"},
        ]
        result = format_tree(entries, "project", 2500)
        assert "src/" in result
        assert "main.py" in result
        assert "3 files" in result

    def test_deeply_nested(self):
        entries = [
            {"path": "a/b/c/d.py", "type": "file", "size": 100, "name": "d.py"},
        ]
        result = format_tree(entries, "deep", 100)
        assert "a/" in result
        assert "d.py" in result
        assert "1 files" in result

    def test_directory_with_many_files_shows_summary(self):
        """Directories with >3 files should show a summary in their label."""
        entries = [
            {"path": "data/a.csv", "type": "file", "size": 100, "name": "a.csv"},
            {"path": "data/b.csv", "type": "file", "size": 200, "name": "b.csv"},
            {"path": "data/c.csv", "type": "file", "size": 300, "name": "c.csv"},
            {"path": "data/d.csv", "type": "file", "size": 400, "name": "d.csv"},
        ]
        result = format_tree(entries, "proj", 1000)
        assert "data/" in result
        assert "4 files" in result

    def test_uses_tree_connectors(self):
        entries = [
            {"path": "a.py", "type": "file", "size": 10, "name": "a.py"},
            {"path": "b.py", "type": "file", "size": 20, "name": "b.py"},
        ]
        result = format_tree(entries, "proj", 30)
        assert "├──" in result or "└──" in result

    def test_total_size_in_summary(self):
        entries = [
            {"path": "big.dat", "type": "file", "size": 5 * 1024 * 1024, "name": "big.dat"},
        ]
        result = format_tree(entries, "proj", 5 * 1024 * 1024)
        assert "5.0 MB" in result

    def test_dirs_sorted_before_files(self):
        """Directories should appear before files at the same level."""
        entries = [
            {"path": "z_file.py", "type": "file", "size": 10, "name": "z_file.py"},
            {"path": "a_dir/inner.py", "type": "file", "size": 10, "name": "inner.py"},
        ]
        result = format_tree(entries, "proj", 20)
        lines = result.split("\n")

        dir_line_idx = None
        file_line_idx = None
        for i, line in enumerate(lines):
            if "a_dir/" in line:
                dir_line_idx = i
            if "z_file.py" in line:
                file_line_idx = i

        assert dir_line_idx is not None
        assert file_line_idx is not None
        assert dir_line_idx < file_line_idx


# ── format_ls tests ───────────────────────────────────────────────────


class TestFormatLs:
    """Tests for the directory listing formatter."""

    def test_basic_listing(self):
        entries = [
            {"name": "main.py", "type": "file", "size": 1800},
            {"name": "utils", "type": "directory", "size": 0},
        ]
        result = format_ls(entries, "src/")
        assert "src/" in result
        assert "main.py" in result
        assert "utils/" in result

    def test_empty_directory(self):
        result = format_ls([], "empty/")
        assert "empty/" in result

    def test_no_path_defaults_to_dot_slash(self):
        result = format_ls([], "")
        assert "./" in result

    def test_dirs_sorted_before_files(self):
        entries = [
            {"name": "z.py", "type": "file", "size": 10},
            {"name": "adir", "type": "directory", "size": 0},
        ]
        result = format_ls(entries, "root/")
        lines = result.split("\n")
        dir_idx = next(i for i, line in enumerate(lines) if "adir/" in line)
        file_idx = next(i for i, line in enumerate(lines) if "z.py" in line)
        assert dir_idx < file_idx

    def test_file_sizes_are_formatted(self):
        entries = [
            {"name": "big.dat", "type": "file", "size": 2 * 1024 * 1024},
        ]
        result = format_ls(entries, "data/")
        assert "2.0 MB" in result

    def test_multiple_directories(self):
        entries = [
            {"name": "alpha", "type": "directory", "size": 0},
            {"name": "beta", "type": "directory", "size": 0},
        ]
        result = format_ls(entries, "root/")
        assert "alpha/" in result
        assert "beta/" in result
