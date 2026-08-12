from __future__ import annotations

import tomllib
from pathlib import Path


root = Path(__file__).resolve().parents[1]
declared = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
manifest = [
    line.strip()
    for line in (root / "requirements-audit.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]
if manifest != declared:
    raise SystemExit(
        "requirements-audit.txt must exactly match project.dependencies; "
        "regenerate it from pyproject.toml"
    )
print(f"dependency audit manifest valid: {len(manifest)} direct dependencies")

