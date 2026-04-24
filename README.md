# MendCode

一款面向本地代码仓的可验证修复型 Code Agent。

MendCode 的目标形态是终端 TUI 工作台：用户输入 `mendcode` 进入聊天式界面，用自然语言描述问题，Agent 动态调用工具，在隔离 worktree 中完成修复、验证和工程审查收尾。

## Current Capabilities

- Python project skeleton with `pyproject.toml`
- CLI health check and task file inspection
- Transitional `mendcode fix "<problem>" --test "<command>"` entry for agent-style verification runs
- `task run` fixed-flow compatibility demo inside a per-run git worktree
- Command-policy guarded verification execution with timeout and trace output
- Pytest-style failure insight extraction for failed verification output
- FastAPI health endpoint
- JSONL trace output for task runs

## Product Direction

The final user-facing entry is planned to be:

```bash
mendcode
```

The TUI should provide:

- chat-first natural language task input
- Guided Mode permission defaults
- model-driven MendCode Action loop
- worktree-isolated patching
- summary-first tool progress
- verification-gated completion
- diff/log/trace review before apply or discard

The current CLI commands are implementation slices and compatibility surfaces, not the final product shape.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

## CLI

Transitional agent-style verification:

```bash
mendcode fix "pytest 失败了，请定位并修复" --repo . --test "python -m pytest -q"
```

Compatibility and smoke commands:

```bash
mendcode version
mendcode health
mendcode task validate data/tasks/demo.json
mendcode task show data/tasks/demo.json
mendcode task run data/tasks/demo.json
```

In this nested worktree development setup, `python -m app.cli.main ...` is the authoritative invocation path. The `mendcode ...` examples remain valid for normal installed usage, but the branch-accurate commands are:

```bash
python -m app.cli.main version
python -m app.cli.main health
python -m app.cli.main fix "pytest 失败了，请定位并修复" --repo . --test "python -m pytest -q"
python -m app.cli.main task validate data/tasks/demo.json
python -m app.cli.main task show data/tasks/demo.json
python -m app.cli.main task run data/tasks/demo.json
```

`fix` creates a per-run workspace under `.worktrees/preview-<id>/`, runs the supplied verification command, extracts pytest-style failure details, and records trace output. It is a transitional slice toward the TUI Agent.

`task run` remains as a fixed-flow compatibility demo using structured `entry_artifacts`.

## API

```bash
uvicorn app.api.server:app --reload
```
