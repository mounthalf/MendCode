# Agent MVP Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first user-facing Agent MVP entry: `mendcode fix "<problem>" --test "<command>"` creates an agent-style task, runs verification in an isolated worktree, extracts failure details, and reports traceable results.

**Architecture:** Keep the existing safe execution runner as the base. Extend `TaskSpec` with agent fields, add a small failure parser that consumes verification stdout/stderr, and add a CLI `fix` command that builds an internal task and prints agent-oriented output. Do not implement LLM patch generation or apply/discard in this slice.

**Tech Stack:** Python, Typer CLI, Pydantic schemas, existing worktree runner, pytest.

---

### Task 1: Agent Task Protocol

**Files:**
- Modify: `app/schemas/task.py`
- Test: `tests/unit/test_task_schema.py`

- [ ] **Step 1: Write failing tests**

Add tests proving `TaskSpec` accepts `problem_statement`, defaults `entry_artifacts` to `{}`, and defaults `max_attempts` to `3`.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_task_schema.py -q`

Expected: fails because `problem_statement` and `max_attempts` are not schema fields, and `entry_artifacts` is required.

- [ ] **Step 3: Implement minimal schema fields**

Add optional `problem_statement: str | None = None`, default `entry_artifacts`, and constrained `max_attempts`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_task_schema.py -q`

Expected: schema tests pass or only unrelated existing fixture drift remains visible.

### Task 2: Verification Failure Parser

**Files:**
- Create: `app/orchestrator/failure_parser.py`
- Create: `tests/unit/test_failure_parser.py`

- [ ] **Step 1: Write failing parser tests**

Cover pytest-style output:

```text
FAILED tests/test_calculator.py::test_add - AssertionError: assert -1 == 5
```

Expected parsed fields: failed node id, file path, test name, error summary.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_failure_parser.py -q`

Expected: fails because parser module does not exist.

- [ ] **Step 3: Implement minimal parser**

Parse stdout/stderr excerpts from the first non-passed verification command. Keep it regex-based and pytest-focused.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_failure_parser.py -q`

Expected: parser tests pass.

### Task 3: CLI Fix Entry

**Files:**
- Modify: `app/cli/main.py`
- Test: `tests/integration/test_cli.py`

- [ ] **Step 1: Write failing CLI test**

Create a temp git repo and invoke:

```bash
mendcode fix "修复 pytest 失败" --test "<python command emitting pytest-style failure>" --repo <repo>
```

Assert output includes `Agent Fix`, `problem_statement`, `run_id`, `failed_node`, and `trace_path`.

- [ ] **Step 2: Run test and verify RED**

Run: `python -m pytest tests/integration/test_cli.py::test_fix_command_runs_verification_and_reports_failure_insight -q`

Expected: fails because `fix` command does not exist.

- [ ] **Step 3: Implement minimal `fix` command**

Build an internal `TaskSpec` with `problem_statement`, `verification_commands`, `repo_path`, `max_attempts`, and safe default `allowed_tools`. Reuse `run_task_preview`; parse the verification result with `extract_failure_insight`; print a dedicated table.

- [ ] **Step 4: Run test and verify GREEN**

Run: `python -m pytest tests/integration/test_cli.py::test_fix_command_runs_verification_and_reports_failure_insight -q`

Expected: test passes.

### Task 4: Documentation Sync

**Files:**
- Modify: `MendCode_开发方案.md`
- Modify: `MendCode_问题记录.md`

- [ ] **Step 1: Record slice completion boundary**

Add a note that Phase A+B landed: protocol + CLI + failure log extraction. Mark LLM patch, retry, diff/apply/discard as next slices.

- [ ] **Step 2: Run final verification**

Run:

```bash
python -m pytest tests/unit/test_task_schema.py tests/unit/test_failure_parser.py tests/integration/test_cli.py -q
git diff --check
```

Expected: focused tests and whitespace check pass, except for any explicitly identified pre-existing unrelated fixture drift.

---

## Self-Review

- Spec coverage: covers Phase A and Phase B from the Agent MVP route.
- Scope intentionally excludes LLM patch generation, retry loop, and diff/apply/discard.
- No placeholders: each task names files, commands, and expected outcomes.
