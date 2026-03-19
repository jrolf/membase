# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.1] - 2026-03-19

### Added

- Initial release of membase.
- `Workspace` class backed by Hugging Face Storage Buckets.
- Core file operations: `read`, `write`, `edit`, `append`, `rm`, `mv`, `cp`.
- Batch operations: `write_many` (single network call), `read_many` (parallel).
- Exploration: `ls`, `tree`, `glob`, `exists`, `stat`, `du`.
- Content search: `grep` with parallel reads (16 workers, ~16x speedup).
- Local mirror mode for fast repeated searches.
- Agent-friendly error messages with self-correction hints.
- Token-efficient output formatting (compact tree, bounded grep results).
- Automatic cache invalidation after writes.
- Workarounds for known SDK issues (glob bug, 0-byte files, stale cache).
- 30 unit tests covering formatting, errors, search, and compatibility.
- GitHub Actions workflow for automatic PyPI publishing on push to main.

[Unreleased]: https://github.com/jrolf/membase/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/jrolf/membase/releases/tag/v0.0.1
