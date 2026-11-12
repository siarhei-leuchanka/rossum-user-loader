"""Packaging guards: what ships in the wheel and what the package declares.

These catch problems that are invisible in an editable dev install (which runs
straight from ``src/``) but break a real ``pipx install``.
"""

import ast
import re
import shutil
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "src" / "rossum_user_loader"


def _package_files():
    return [
        p for p in PACKAGE_DIR.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    ]


@pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(),
    reason="needs a git checkout",
)
def test_no_package_file_is_gitignored():
    # The wheel builder (hatchling) drops files matching .gitignore even when
    # they are tracked, so an ignored package file silently vanishes from the
    # installed app. --no-index checks the rules themselves, ignoring tracking.
    files = [str(p.relative_to(ROOT)) for p in _package_files()]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-v", *files],
        cwd=ROOT, capture_output=True, text=True,
    )
    # Each line is "<source>:<line>:<pattern>\t<path>"; with -v git also reports
    # files whose last matching rule is a "!" re-include — those are NOT ignored.
    ignored = [
        line for line in result.stdout.splitlines()
        if not line.split("\t", 1)[0].split(":", 2)[2].startswith("!")
    ]
    assert not ignored, "Package files excluded by .gitignore:\n" + "\n".join(ignored)


def _declared_dependencies() -> set[str]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    names = set()
    for req in pyproject["project"]["dependencies"]:
        names.add(re.split(r"[\s;<>=!~\[(]", req, maxsplit=1)[0].lower().replace("_", "-"))
    return names


def _imported_top_level_modules() -> set[str]:
    modules = set()
    for path in PACKAGE_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    return modules


def test_every_third_party_import_is_a_declared_dependency():
    # A package imported directly must be declared, not just arrive as some
    # other dependency's dependency (it could be dropped or change under us).
    third_party = {
        m for m in _imported_top_level_modules()
        if m not in sys.stdlib_module_names and m not in ("rossum_user_loader", "__future__")
    }
    dist_by_module = metadata.packages_distributions()
    declared = _declared_dependencies()
    undeclared = {}
    for module in sorted(third_party):
        dists = {d.lower().replace("_", "-") for d in dist_by_module.get(module, [module])}
        if not dists & declared:
            undeclared[module] = sorted(dists)
    assert not undeclared, f"Imported but not declared in pyproject.toml: {undeclared}"
