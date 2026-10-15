"""Portable development checks; use the same Python environment as the bot."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    commands = {
        "test": [["pytest", *sys.argv[2:]]],
        "hooks": [["ruff", "check", "."], ["ruff", "format", "--check", "."], ["mypy"]],
        "check": [
            ["ruff", "check", "."],
            ["ruff", "format", "--check", "."],
            ["mypy"],
            ["pytest", "-q"],
        ],
    }
    if mode not in commands:
        raise SystemExit("Usage: python scripts/dev.py [test|hooks|check]")
    os.chdir(ROOT)
    env = {**os.environ, "PYTHONUTF8": "1"}
    venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python = str(venv_python) if venv_python.is_file() else sys.executable
    for command in commands[mode]:
        print("Running " + " ".join(command), flush=True)
        result = subprocess.run([python, "-m", *command], env=env, check=False)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
