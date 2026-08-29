"""Static guard for version-specific migration fixtures."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_FIXTURE = re.compile(
    r"^_?(?:version_(?:one|two|three|four|five|six|seven|eight|nine|[0-9]+)|v[0-9]+)_"
    r"(?:database|home|fixture)$"
)


def _migration_calls(function: ast.FunctionDef) -> tuple[ast.Call, ...]:
    return tuple(
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "migrate")
            or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "migrate"
            )
        )
    )


def test_version_specific_fixtures_always_pass_an_explicit_target() -> None:
    fixtures: dict[str, tuple[ast.Call, ...]] = {}
    for path in sorted(ROOT.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and VERSION_FIXTURE.fullmatch(node.name):
                fixtures[f"{path.name}:{node.name}"] = _migration_calls(node)

    assert fixtures
    for fixture, calls in fixtures.items():
        assert calls, f"{fixture} must construct its declared schema version directly"
        for call in calls:
            assert any(keyword.arg == "target_version" for keyword in call.keywords), (
                f"{fixture} must pass target_version explicitly"
            )
