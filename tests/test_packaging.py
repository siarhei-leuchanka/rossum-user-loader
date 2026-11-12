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


def test_templates_contain_only_the_header_row():
    # Every row is loaded as-is, so an example row in a template would create a
    # real (junk) user if left in. Templates ship with the header only.
    import csv
    import openpyxl

    with open(PACKAGE_DIR / "data" / "user_load_template.csv", newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh, delimiter=";") if any(c.strip() for c in r)]
    assert len(rows) == 1 and "email" in rows[0]

    wb = openpyxl.load_workbook(ROOT / "templates" / "user_load_template.xlsx")
    for ws in wb.worksheets:
        data = [r for r in ws.iter_rows(values_only=True) if any(c not in (None, "") for c in r)]
        assert len(data) == 1 and "email" in data[0], f"sheet {ws.title!r} has rows besides the header"


def test_version_is_the_same_everywhere():
    # pipx upgrade only picks up a release whose version changed, so every
    # release must bump all three together.
    import rossum_user_loader

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    changelog = re.search(r"^## v(\S+)", (ROOT / "CHANGELOG.md").read_text(), re.M).group(1)
    assert pyproject == rossum_user_loader.__version__ == changelog
