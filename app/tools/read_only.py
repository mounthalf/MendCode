from pathlib import Path

from app.tools.guard import resolve_workspace_file
from app.tools.schemas import ToolResult


def read_file(
    workspace_path: Path,
    relative_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    max_chars: int | None = None,
) -> ToolResult:
    try:
        target = resolve_workspace_file(workspace_path, relative_path)
        text = target.read_text(encoding="utf-8")
    except ValueError as exc:
        return ToolResult(
            tool_name="read_file",
            status="rejected",
            summary=f"Unable to read {relative_path}",
            payload={"relative_path": relative_path},
            error_message=str(exc),
            workspace_path=str(workspace_path),
        )
    except (UnicodeDecodeError, OSError) as exc:
        return ToolResult(
            tool_name="read_file",
            status="failed",
            summary=f"Unable to read {relative_path}",
            payload={"relative_path": relative_path},
            error_message=str(exc),
            workspace_path=str(workspace_path),
        )

    lines = text.splitlines(keepends=True)
    total_lines = len(lines)
    start = 1 if start_line is None else start_line
    end = total_lines if end_line is None else end_line
    content = "".join(lines[max(start - 1, 0) : end])
    truncated = False
    if max_chars is not None and len(content) > max_chars:
        content = content[:max_chars]
        truncated = True

    return ToolResult(
        tool_name="read_file",
        status="passed",
        summary=f"Read {relative_path}",
        payload={
            "relative_path": relative_path,
            "start_line": start,
            "end_line": end,
            "total_lines": total_lines,
            "content": content,
            "truncated": truncated,
        },
        error_message=None,
        workspace_path=str(workspace_path),
    )
