# membase

**A fast, ergonomic workspace in the cloud for AI agents.**

membase gives AI agents a filesystem interface backed by
[Hugging Face Storage Buckets](https://huggingface.co/docs/hub/storage-buckets)
— designed from the ground up for tool-calling agents that need to read, write,
search, and organize files in persistent cloud storage.

```python
from membase import Workspace

ws = Workspace("my-project")
ws.write("hello.txt", "Hello from membase.")
print(ws.read("hello.txt"))
```

## Why membase?

AI agents already have great filesystem tools on local machines — `Read`,
`Write`, `Glob`, `Grep`. But when agents need **persistent, shareable,
cloud-native storage**, they get raw APIs designed for human developers:
long bucket URIs, manual grep loops, no batching, no parallelism.

membase closes this gap with:

- **One line to start.** `ws = Workspace("my-project")` — auth is automatic,
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

Requires Python 3.9+ and a [Hugging Face account](https://huggingface.co/join)
with an API token.

### Authentication

membase discovers credentials automatically:

```bash
# Option 1: environment variable
export HF_TOKEN=hf_your_token_here

# Option 2: CLI login (stores token locally)
pip install huggingface_hub
huggingface-cli login
```

## Quick Start

### Create a workspace and write files

```python
from membase import Workspace

ws = Workspace("my-project")

# Write a single file (parent directories created automatically)
ws.write("src/main.py", "def main():\n    print('hello')\n")

# Write multiple files in one network call
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
```

### Search file contents

```python
# Search across all Python files
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

## API Overview

| Operation | Method | Description |
|---|---|---|
| Read | `ws.read(path)` | Read a file as string |
| Write | `ws.write(path, content)` | Create or overwrite a file |
| Batch write | `ws.write_many({path: content, ...})` | Write multiple files (one network call) |
| Edit | `ws.edit(path, old=..., new=...)` | Find-and-replace within a file |
| Append | `ws.append(path, content)` | Append to an existing file |
| List | `ws.ls(path)` | List directory contents |
| Tree | `ws.tree()` | ASCII tree of the workspace |
| Glob | `ws.glob(pattern)` | Find files by pattern |
| Grep | `ws.grep(pattern)` | Search inside file contents |
| Exists | `ws.exists(path)` | Check if a path exists |
| Stat | `ws.stat(path)` | File metadata (size, modified time) |
| Delete | `ws.rm(path)` | Delete a file or directory |
| Move | `ws.mv(src, dst)` | Move or rename |
| Copy | `ws.cp(src, dst)` | Copy within workspace |
| Info | `ws.info()` | Workspace metadata |

## Design Principles

- **Token-efficient.** Every API surface minimizes context window cost.
- **Network-aware.** Parallel reads, batched writes, aggressive caching.
- **One dependency.** Only `huggingface_hub` is required.
- **Agent-first.** Structured returns, compact repr, actionable errors.

## License

MIT — see [LICENSE](LICENSE) for details.
