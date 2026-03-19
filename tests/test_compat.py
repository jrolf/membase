"""Tests for the compatibility / workaround layer."""

from agentspace._compat import ensure_nonempty_bytes


class TestEnsureNonemptyBytes:
    """Tests for the 0-byte file workaround."""

    def test_empty_bytes_get_newline(self):
        assert ensure_nonempty_bytes(b"") == b"\n"

    def test_nonempty_bytes_pass_through(self):
        assert ensure_nonempty_bytes(b"hello") == b"hello"

    def test_single_byte_passes(self):
        assert ensure_nonempty_bytes(b"\n") == b"\n"

    def test_none_treated_as_empty(self):
        """None is falsy, so it should get the newline treatment."""
        assert ensure_nonempty_bytes(None) == b"\n"
