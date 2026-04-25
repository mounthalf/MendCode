# Agent Session And Single Turn TUI Design

## Purpose

This spec defines the next development slice for MendCode after the Agent loop
route refactor. The goal is to stabilize the repair result model first, then
build a minimal single-turn TUI that can later grow into multi-turn chat.

The work follows the current product direction in
`MendCode_TUI产品基调与交互方案.md`: chat-first, summary-first, worktree-isolated,
verification-gated, and user-controlled final landing.

## Scope

This slice includes:

- Agent repair result structures for TUI consumption.
- Attempt tracking for failed patch and verification flows.
- A single-turn `AgentSession` abstraction.
- A minimal `mendcode` no-argument terminal entry.
- Checklist updates across the three roadmap documents when each item lands.

This slice excludes:

- Real OpenAI, Anthropic, or OpenAI-compatible provider adapters.
- True multi-turn model reasoning.
- Applying changes back to the main workspace.
- Commit or push automation.
- Full diff viewer.
- Complex TUI layout or background jobs.

## Architecture

### `ReviewSummary`

`ReviewSummary` is the stable object the TUI reads at the end of a run. It should
not expose provider internals or raw trace internals as its main interface.

Fields:

- `status`: `verified`, `failed`, or `needs_user_confirmation`
- `workspace_path`: isolated worktree path, if one exists
- `trace_path`: JSONL trace path
- `changed_files`: list of changed files with basic diff stats when available
- `verification_status`: `passed`, `failed`, `rejected`, or `not_run`
- `summary`: short human-readable result
- `recommended_actions`: list such as `view_diff`, `view_trace`, `discard`, `apply`

Rules:

- `status` can be `verified` only when verification passed after the relevant
  patch or tool sequence.
- `apply` may appear as a recommended action only after verification passed.
- TUI rendering must use `ReviewSummary` instead of reaching into low-level step
  payloads.

### `AttemptRecord`

`AttemptRecord` captures one repair attempt. This gives the system a way to
explain failed model output without losing evidence.

Fields:

- `index`: attempt number starting at 1
- `patch_summary`: files intended to change
- `patch_status`: `not_proposed`, `applied`, `failed`
- `verification_status`: `passed`, `failed`, `rejected`, `not_run`
- `error_message`: failure detail, if any
- `trace_event_ids` or trace metadata sufficient to find evidence in JSONL

Rules:

- A failed patch proposal creates an attempt record.
- A patch that applies but fails verification creates an attempt record.
- Exceeding `max_attempts` stops the loop and produces a failed review summary.
- Failed attempts stay in the worktree trace; the main workspace is untouched.

### `AgentSession`

`AgentSession` is the bridge between future multi-turn chat and the current
single-turn implementation.

Fields:

- `repo_path`
- `permission_mode`
- `workspace_path`
- `trace_path`
- `turns`
- `attempts`
- `review_summary`

First API:

```python
session = AgentSession(repo_path=Path("."), permission_mode="guided")
turn = session.run_turn(
    user_message="pytest failed, fix it",
    verification_commands=["python -m pytest -q"],
)
```

Rules:

- First implementation runs a single turn.
- The session stores turns in a list so future multi-turn chat can append to the
  same session.
- `run_turn()` delegates action generation to the provider boundary and
  execution to `AgentLoop`.
- `AgentSession` owns shaping the final `ReviewSummary`.
- `AgentSession` does not call real network providers in this slice.

### Minimal Single-Turn TUI

`mendcode` with no subcommand starts a minimal terminal interaction:

```text
MendCode
repo: /path/to/repo
branch: main
status: dirty, 3 modified
mode: guided

Type your task:
>
```

After the user enters one task, the TUI runs one session turn and renders:

- tool step summaries
- failure insight when available
- location step summary when available
- review summary
- action labels

First-cut actions:

- `v`: view diff summary
- `t`: show trace path
- `d`: discard by leaving the worktree as the disposable artifact
- `a`: show "apply is not implemented in this slice"

The first TUI can use Typer prompt and Rich rendering. It should not introduce a
heavy TUI framework until the data model is stable.

## Data Flow

```text
mendcode
-> repo scan
-> user enters one task
-> AgentSession.run_turn()
-> ScriptedAgentProvider creates actions
-> AgentLoop executes in worktree
-> failure insight and location actions run when verification fails
-> AttemptRecord list is updated
-> ReviewSummary is built
-> TUI renders summary and action labels
```

## Error Handling

- Provider failure returns a failed observation and a failed review summary.
- Invalid action remains a rejected observation.
- Patch apply failure creates an `AttemptRecord` and stops unless another attempt
  is available.
- Verification failure creates an `AttemptRecord`.
- If `max_attempts` is exhausted, the session stops and recommends `view_trace`
  and `discard`.
- Main workspace apply is not available in this slice.

## Testing Strategy

Unit tests:

- `ReviewSummary` builds `verified` only after passing verification.
- `ReviewSummary` builds `failed` when the latest relevant observation failed.
- `AttemptRecord` is created for failed patch apply.
- `AttemptRecord` is created for patch-applied verification failure.
- `AgentSession.run_turn()` stores one turn and preserves session state.
- `AgentSession.run_turn()` leaves the main workspace unchanged.

Integration tests:

- `mendcode fix ...` still works through the session-compatible path if migrated.
- `mendcode` no-argument path accepts one input and renders repo context.
- The single-turn path renders review summary fields.
- The single-turn path does not apply to the main workspace.

Verification commands:

```bash
python -m pytest -q
python -m ruff check .
```

## Development Order

1. Add `ReviewSummary`.
2. Add `AttemptRecord`.
3. Add `AgentSession` with one-turn support.
4. Migrate `mendcode fix` to use `AgentSession` where practical.
5. Add `mendcode` no-argument single-turn interaction.
6. Update the three checklist documents after each completed feature.

## Acceptance Criteria

- A single session turn can run in an isolated worktree.
- The main workspace is not modified.
- Failed patch or failed verification attempts are recorded.
- The final result exposes a `ReviewSummary`.
- `mendcode` no-argument mode accepts one task and renders a review summary.
- The implementation remains compatible with future multi-turn chat by storing
  turns in a session object.
