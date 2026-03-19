"""Tests for the formatting module — no network calls needed."""

from agentspace.formatting import format_ls, format_size, format_tree


class TestFormatSize:
    """Tests for the format_size helper."""

    def test_bytes(self):
        assert format_size(0) == "0 B"
        assert format_size(512) == "512 B"
        assert format_size(1023) == "1023 B"

    def test_kilobytes(self):
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"
        assert format_size(10240) == "10.0 KB"

    def test_megabytes(self):
        assert format_size(1048576) == "1.0 MB"
        assert format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        assert format_size(1073741824) == "1.0 GB"


class TestFormatTree:
    """Tests for the ASCII tree formatter."""

    def test_empty_workspace(self):
        result = format_tree([], "my-project", 0)
        assert "my-project/" in result
        assert "empty" in result

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
