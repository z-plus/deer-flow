from __future__ import annotations

import ast
from pathlib import Path


HARNESS_ROOT = Path(__file__).parents[1] / "src" / "mini_deerflow" / "harness"


def forbidden_app_imports(source: str) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            violations.extend(alias.name for alias in node.names if alias.name == "mini_deerflow.app" or alias.name.startswith("mini_deerflow.app."))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "mini_deerflow.app" or node.module.startswith("mini_deerflow.app."):
                violations.append(node.module)
    return violations


def test_boundary_check_detects_forbidden_import() -> None:
    assert forbidden_app_imports("from mini_deerflow.app import gateway") == ["mini_deerflow.app"]
    assert forbidden_app_imports("import mini_deerflow.app.gateway") == ["mini_deerflow.app.gateway"]


def test_harness_does_not_import_app() -> None:
    violations = {
        str(path.relative_to(HARNESS_ROOT)): forbidden_app_imports(path.read_text(encoding="utf-8"))
        for path in HARNESS_ROOT.rglob("*.py")
        if forbidden_app_imports(path.read_text(encoding="utf-8"))
    }

    assert violations == {}

