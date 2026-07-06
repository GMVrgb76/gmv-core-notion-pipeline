"""Security release gate remains complete and fail-closed."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_quality_gate_contains_every_required_control() -> None:
    gate = (ROOT / "scripts" / "quality_gate.sh").read_text()
    for control in (
        "pytest",
        "ruff check",
        "pip check",
        "check_runtime_git_policy.py",
        "detect-secrets-hook",
        "git diff --check",
    ):
        assert control in gate


def test_exception_policy_has_owner_expiry_and_no_silent_baseline_rule() -> None:
    exceptions = (ROOT / "quality" / "LEGACY_EXCEPTIONS.md").read_text()
    policy = (ROOT / "quality" / "SECURITY_GATE_POLICY.md").read_text()
    assert "Owner:" in exceptions
    assert "Expiry:" in exceptions
    assert "never absorb" in policy
    assert "Expired" in policy


def test_negative_security_fixtures_are_covered() -> None:
    policy = (ROOT / "quality" / "SECURITY_GATE_POLICY.md").read_text()
    for finding in ("Unsafe subprocess", "credential", "protected-runtime-path", "broken dependency"):
        assert finding in policy
