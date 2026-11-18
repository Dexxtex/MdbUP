"""Guardrail for the modular-monolith dependency direction."""

from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_core_layers_do_not_import_the_http_layer() -> None:
    forbidden = {"app.api", "app.api.errors", "app.api.schemas"}
    offenders: list[str] = []
    for folder in ("services", "domain", "connectors", "integrations", "jobs", "repositories"):
        for path in (APP / folder).rglob("*.py"):
            for name in _imports(path):
                if any(name == item or name.startswith(item + ".") for item in forbidden):
                    offenders.append(f"{path.relative_to(APP)} -> {name}")
    assert offenders == []


def test_routers_do_not_import_data_or_task_layers() -> None:
    forbidden = ("app.repositories", "app.jobs", "app.connectors")
    offenders: list[str] = []
    for path in (APP / "api" / "routers").glob("*.py"):
        for name in _imports(path):
            if any(name == item or name.startswith(item + ".") for item in forbidden):
                offenders.append(f"{path.relative_to(APP)} -> {name}")
    assert offenders == []


def test_routers_do_not_contain_raw_sql() -> None:
    offenders: list[str] = []
    for path in (APP / "api" / "routers").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        if 'text("SELECT' in source or "text('SELECT" in source:
            offenders.append(str(path.relative_to(APP)))
    assert offenders == []
