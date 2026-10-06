"""Task group 1: the dev scripts are the ground truth for tests and checks.

These tests lock the contract between ``README.md``, ``SPECS/TECH.md`` and the
actual scripts: both scripts must exist, be executable, and run what the
README claims they run.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _script(name: str) -> Path:
    return REPO_ROOT / "scripts" / name


def test_scripts_directory_contains_test_and_hooks() -> None:
    assert _script("test").is_file(), "scripts/test must exist"
    assert _script("hooks").is_file(), "scripts/hooks must exist"


def test_scripts_are_executable() -> None:
    import os

    assert os.access(_script("test"), os.X_OK), "scripts/test must be executable"
    assert os.access(_script("hooks"), os.X_OK), "scripts/hooks must be executable"


def test_scripts_test_runs_the_pytest_suite() -> None:
    contents = _script("test").read_text()
    assert "pytest" in contents, "scripts/test must run pytest"


def test_scripts_hooks_runs_lint_and_type_checks() -> None:
    contents = _script("hooks").read_text()
    assert "ruff" in contents, "scripts/hooks must run ruff (lint)"
    assert "mypy" in contents, "scripts/hooks must run mypy (type checks)"


def test_readme_documents_both_dev_scripts() -> None:
    readme = (REPO_ROOT / "README.md").read_text()
    assert "scripts/test" in readme, "README must document scripts/test"
    assert "scripts/hooks" in readme, "README must document scripts/hooks"


def test_readme_matches_what_the_scripts_run() -> None:
    """README and scripts must stay in sync (SPECS/TECH.md repo hygiene)."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert "pytest" in readme, "README must show the pytest command scripts/test runs"
    assert "ruff" in readme, "README must show the ruff command scripts/hooks runs"
    assert "mypy" in readme, "README must show the mypy command scripts/hooks runs"
