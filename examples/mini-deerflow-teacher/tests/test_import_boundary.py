from __future__ import annotations

import ast
from pathlib import Path


HARNESS_ROOT = Path(__file__).parents[1] / "harness" / "mini_deerflow"
APP_PACKAGE = "app"


def forbidden_app_imports(source: str) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            violations.extend(
                alias.name
                for alias in node.names
                if alias.name == APP_PACKAGE or alias.name.startswith(f"{APP_PACKAGE}.")
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == APP_PACKAGE or node.module.startswith(f"{APP_PACKAGE}."):
                violations.append(node.module)
    return violations


def test_boundary_check_detects_forbidden_import() -> None:
    assert forbidden_app_imports("from app import gateway") == [APP_PACKAGE]
    assert forbidden_app_imports("import app.gateway") == ["app.gateway"]


def test_harness_does_not_import_app() -> None:
    violations = {
        str(path.relative_to(HARNESS_ROOT)): forbidden_app_imports(
            path.read_text(encoding="utf-8")
        )
        for path in HARNESS_ROOT.rglob("*.py")
        if forbidden_app_imports(path.read_text(encoding="utf-8"))
    }

    assert violations == {}
