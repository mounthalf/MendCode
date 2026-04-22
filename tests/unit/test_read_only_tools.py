from pathlib import Path

from app.tools.read_only import read_file


def test_read_file_returns_full_content(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    target = workspace_path / "notes.txt"
    target.write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(workspace_path=workspace_path, relative_path="notes.txt")

    assert result.status == "passed"
    assert result.model_dump() == {
        "tool_name": "read_file",
        "status": "passed",
        "summary": "Read notes.txt",
        "payload": {
            "relative_path": "notes.txt",
            "start_line": 1,
            "end_line": 2,
            "total_lines": 2,
            "content": "alpha\nbeta\n",
            "truncated": False,
        },
        "error_message": None,
        "workspace_path": str(workspace_path),
    }


def test_read_file_returns_requested_line_range(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    target = workspace_path / "notes.txt"
    target.write_text("a\nb\nc\nd\n", encoding="utf-8")

    result = read_file(
        workspace_path=workspace_path,
        relative_path="notes.txt",
        start_line=2,
        end_line=3,
    )

    assert result.status == "passed"
    assert result.payload == {
        "relative_path": "notes.txt",
        "start_line": 2,
        "end_line": 3,
        "total_lines": 4,
        "content": "b\nc\n",
        "truncated": False,
    }


def test_read_file_returns_empty_file_as_passed(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "empty.txt").write_text("", encoding="utf-8")

    result = read_file(workspace_path=workspace_path, relative_path="empty.txt")

    assert result.status == "passed"
    assert result.payload == {
        "relative_path": "empty.txt",
        "start_line": 0,
        "end_line": 0,
        "total_lines": 0,
        "content": "",
        "truncated": False,
    }


def test_read_file_truncates_large_content(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    target = workspace_path / "notes.txt"
    target.write_text("abcdef", encoding="utf-8")

    result = read_file(
        workspace_path=workspace_path,
        relative_path="notes.txt",
        max_chars=3,
    )

    assert result.status == "passed"
    assert result.payload["content"] == "abc"
    assert result.payload["truncated"] is True


def test_read_file_rejects_missing_path(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    result = read_file(workspace_path=workspace_path, relative_path="missing.txt")

    assert result.status == "rejected"
    assert result.error_message == "path does not exist"


def test_read_file_rejects_non_positive_start_line(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(
        workspace_path=workspace_path,
        relative_path="notes.txt",
        start_line=0,
    )

    assert result.status == "rejected"
    assert result.error_message == "start_line must be greater than 0"


def test_read_file_rejects_non_positive_end_line(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(
        workspace_path=workspace_path,
        relative_path="notes.txt",
        end_line=0,
    )

    assert result.status == "rejected"
    assert result.error_message == "end_line must be greater than 0"


def test_read_file_rejects_start_line_after_end_line(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(
        workspace_path=workspace_path,
        relative_path="notes.txt",
        start_line=3,
        end_line=2,
    )

    assert result.status == "rejected"
    assert result.error_message == "start_line cannot be greater than end_line"


def test_read_file_rejects_negative_max_chars(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(
        workspace_path=workspace_path,
        relative_path="notes.txt",
        max_chars=-1,
    )

    assert result.status == "rejected"
    assert result.error_message == "max_chars must be greater than or equal to 0"


def test_read_file_rejects_start_line_beyond_file_length(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(
        workspace_path=workspace_path,
        relative_path="notes.txt",
        start_line=3,
    )

    assert result.status == "rejected"
    assert result.error_message == "start_line exceeds file length"


def test_read_file_rejects_end_line_beyond_file_length(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()
    (workspace_path / "notes.txt").write_text("alpha\nbeta\n", encoding="utf-8")

    result = read_file(
        workspace_path=workspace_path,
        relative_path="notes.txt",
        end_line=3,
    )

    assert result.status == "rejected"
    assert result.error_message == "end_line exceeds file length"
