# membase

[![PyPI version](https://img.shields.io/pypi/v/membase.svg)](https://pypi.org/project/membase/)
[![Python versions](https://img.shields.io/pypi/pyversions/membase.svg)](https://pypi.org/project/membase/)
[![CI](https://github.com/jrolf/membase/actions/workflows/ci.yml/badge.svg)](https://github.com/jrolf/membase/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**A fast, ergonomic workspace in the cloud for AI agents.**

membase gives AI agents a filesystem interface backed by
[Hugging Face Storage Buckets](https://huggingface.co/docs/hub/storage-buckets)
— designed from the ground up for tool-calling agents that need to read, write,
search, and organize files in persistent cloud storage.

```python
import membase as mb

ws = mb.Workspace("my-project")
ws.write("hello.txt", "Hello from membase.")
print(ws.read("hello.txt"))
```

## How It Works

Under the hood, membase wraps Hugging Face's **Storage Buckets** — a mutable,
non-versioned object store built on top of the
[Xet](https://huggingface.co/docs/hub/storage-backends#xet-storage-backend)
storage backend. Buckets behave like cloud directories with:

- **Chunk-level deduplication** — similar files share storage automatically
- **Global addressing** — every file has an `hf://buckets/...` URI
- **Fine-grained permissions** — private by default, optionally public
- **No versioning overhead** — mutations are immediate, no commits needed

membase wraps all of this behind a simple filesystem API so agents never
deal with URIs, authentication plumbing, or SDK quirks directly.

## Why membase?

AI agents already have great filesystem tools on local machines — `Read`,
`Write`, `Glob`, `Grep`. But when agents need **persistent, shareable,
cloud-native storage**, they get raw APIs designed for human developers:
long bucket URIs, manual grep loops, no batching, no parallelism.

membase closes this gap with:

- **One line to start.** `ws = mb.Workspace("my-project")` — auth is automatic,
  the bucket is created if needed.
- **Familiar vocabulary.** `read`, `write`, `ls`, `glob`, `grep`, `tree`,
  `mv`, `cp`, `rm` — the same operations agents already know.
- **Parallel reads.** Multi-file operations use 16 concurrent workers by
  default — 16x faster than sequential reads.
- **Batched writes.** `write_many()` sends any number of files in a single
  network call (~700ms whether it's 1 file or 200).
- **Token-efficient output.** Short paths, compact tree views, bounded search
  results — designed to minimize context window cost.
- **Agent-friendly errors.** Exceptions include suggestions for what to do
  next, so agents can self-correct.

## Installation

```bash
pip install membase
```

Requires Python 3.9+ and a [Hugging Face](https://huggingface.co/join) account.

## Authentication

membase requires a Hugging Face API token with **write** permissions. Here's
how to set it up:

### Step 1: Create a token

1. Go to [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
2. Click **"Create new token"**
3. Choose **"Write"** access (required to create and modify workspaces)
4. Copy the token — it starts with `hf_`

### Step 2: Make the token available

There are three ways to provide your token. Pick whichever fits your workflow.

**Option A — Environment variable** (recommended for servers and CI):

```bash
export HF_TOKEN=hf_your_token_here
```

**Option B — CLI login** (recommended for local development):

```bash
pip install huggingface_hub
huggingface-cli login
```

This stores the token in `~/.cache/huggingface/token` so you never have to
set it again on this machine.

**Option C — Pass it directly** (recommended for scripts and agents):

```python
import membase as mb

ws = mb.Workspace("my-project", token="hf_your_token_here")
```

### Verifying your setup

```python
import membase as mb

# This will create a test workspace (or connect to an existing one)
ws = mb.Workspace("hello-test")
ws.write("test.txt", "It works!")
print(ws.read("test.txt"))  # → "It works!"
```

If you see `"It works!"`, you're all set. If you get an authentication error,
double-check that your token has **write** access.

## Quick Start

### Create a workspace and write files

```python
import membase as mb

ws = mb.Workspace("my-project")

# Write a single file (parent directories created automatically)
ws.write("src/main.py", "def main():\n    print('hello')\n")

# Write multiple files in one network call (~700ms total)
ws.write_many({
    "src/__init__.py": "",
    "src/utils.py": "def helper():\n    pass\n",
    "tests/test_main.py": "def test_main():\n    assert True\n",
})
```

### Explore the workspace

```python
# ASCII tree view
print(ws.tree())

# List a directory
for entry in ws.ls("src/"):
    print(entry)

# Find files by pattern
py_files = ws.glob("**/*.py")

# Walk the directory tree (like os.walk)
for dirpath, dirs, files in ws.walk():
    for f in files:
        print(f"{dirpath}/{f}" if dirpath else f)
```

### Search file contents

```python
# Search across all Python files (parallel — 16x faster than sequential)
results = ws.grep("def main", include="*.py")
for match in results:
    print(f"{match.path}:{match.line_number}: {match.line}")
```

### Read and edit files

```python
# Read a file
content = ws.read("src/main.py")

# Read just the first 10 lines of a large file
head = ws.read("data/large.csv", head=10)

# Find-and-replace (no need to read the whole file into context)
ws.edit("src/main.py", old="print('hello')", new="print('goodbye')")
```

### Download files to local disk

```python
# Download a single file for local processing
ws.download("data/results.csv", "/tmp/results.csv")
```

### Discover existing workspaces

```python
import membase as mb

# List all workspaces visible to your token
for workspace in mb.list_workspaces():
    print(workspace)
```

### Use with pandas

```python
import pandas as pd

# pandas reads HF bucket URIs natively
df = pd.read_csv(ws.url("data/train.csv"))
```

## API Reference

### Module-level

| Function | Description |
|---|---|
| `mb.Workspace(name, ...)` | Open or create a workspace |
| `mb.list_workspaces(namespace=...)` | List available workspaces |
| `mb.Workspace.delete(name)` | Permanently delete a workspace |

### File I/O

| Method | Description |
|---|---|
| `ws.read(path)` | Read a file as string |
| `ws.read(path, head=N)` | Read first N lines |
| `ws.read(path, binary=True)` | Read as bytes |
| `ws.read_many(paths)` | Read multiple files in parallel |
| `ws.write(path, content)` | Create or overwrite a file |
| `ws.write_many({path: content})` | Write multiple files (one network call) |
| `ws.edit(path, old=..., new=...)` | Find-and-replace within a file |
| `ws.append(path, content)` | Append to a file |
| `ws.download(remote, local)` | Download a file to local disk |

### Exploration

| Method | Description |
|---|---|
| `ws.ls(path)` | List directory contents |
| `ws.tree()` | ASCII tree of the workspace |
| `ws.walk()` | Walk directory tree (like `os.walk`) |
| `ws.glob(pattern)` | Find files by pattern |
| `ws.grep(pattern)` | Search inside file contents |
| `ws.exists(path)` | Check if a path exists |
| `ws.is_file(path)` | Check if path is a file |
| `ws.is_dir(path)` | Check if path is a directory |
| `ws.stat(path)` | File metadata (size, type) |
| `ws.du(path)` | Total size in bytes |

### File Operations

| Method | Description |
|---|---|
| `ws.rm(path)` | Delete a file or directory |
| `ws.mv(src, dst)` | Move or rename |
| `ws.cp(src, dst)` | Copy within workspace |

### Workspace Management

| Method | Description |
|---|---|
| `ws.info()` | Workspace metadata (file count, size) |
| `ws.sync()` | Sync with local mirror |
| `ws.invalidate()` | Clear cached metadata |
| `ws.url(path)` | Get `hf://` URI for interop |
| `ws.fs` | Access raw HfFileSystem |

## Design Principles

- **Token-efficient.** Every API surface minimizes context window cost.
- **Network-aware.** Parallel reads, batched writes, aggressive caching.
- **One dependency.** Only `huggingface_hub` is required.
- **Agent-first.** Structured returns, compact repr, actionable errors.

## Troubleshooting

**"Permission denied" or 401 error:**
Your token doesn't have write access. Create a new token at
[huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)
with **Write** permissions.

**"Cannot reach Hugging Face" or connection timeout:**
Check your internet connection. If you're behind a proxy, set the
`HTTPS_PROXY` environment variable.

**Stale data after external modifications:**
If another agent or human modified the workspace externally, call
`ws.invalidate()` to clear cached metadata.

**Slow grep on large workspaces (200+ files):**
Use local mirror mode for repeated searches:

```python
ws = mb.Workspace("large-project", mirror=True)
ws.sync()  # one-time ~1.3s sync
ws.grep("pattern")  # now searches locally in <1ms
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT — see [LICENSE](LICENSE) for details.
