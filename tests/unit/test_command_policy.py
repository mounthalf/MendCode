from app.workspace.command_policy import CommandPolicy


def test_command_policy_allows_declared_command_in_allowed_root(tmp_path):
    policy = CommandPolicy(
        allowed_commands=["pytest -q"],
        allowed_root=tmp_path,
        timeout_seconds=60,
    )

    decision = policy.evaluate("pytest -q", tmp_path / "nested")

    assert decision.allowed is True
    assert decision.reason is None


def test_command_policy_rejects_unknown_command(tmp_path):
    policy = CommandPolicy(
        allowed_commands=["pytest -q"],
        allowed_root=tmp_path,
        timeout_seconds=60,
    )

    decision = policy.evaluate("make test", tmp_path)

    assert decision.allowed is False
    assert decision.reason == "command is not declared in verification_commands"


def test_command_policy_rejects_escaped_cwd(tmp_path):
    policy = CommandPolicy(
        allowed_commands=["pytest -q"],
        allowed_root=tmp_path,
        timeout_seconds=60,
    )

    decision = policy.evaluate("pytest -q", tmp_path.parent / "outside")

    assert decision.allowed is False
    assert decision.reason == "cwd escapes allowed workspace root"
