from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any


GITHUB_ACTIONS_APP_ID = 15368


def fail(message: str) -> None:
    raise SystemExit(f"governance verification failed: {message}")


def gh_api(path: str) -> Any:
    result = subprocess.run(
        ["gh", "api", path],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        fail(result.stderr.strip() or f"GitHub API request failed: {path}")
    try:
        return json.loads(result.stdout) if result.stdout.strip() else None
    except json.JSONDecodeError as exc:
        fail(f"GitHub API returned invalid JSON for {path}: {exc}")


def enabled(value: Any) -> bool:
    return isinstance(value, dict) and value.get("enabled") is True


def main() -> None:
    if not os.getenv("GH_TOKEN"):
        fail("GH_TOKEN is required (for example: GH_TOKEN=$(gh auth token))")
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    expected_raw = os.getenv("EXPECTED_REQUIRED_CHECKS", "")
    expected = [item.strip() for item in expected_raw.split(",") if item.strip()]
    if "/" not in repository:
        fail("GITHUB_REPOSITORY must be owner/repository")
    if not expected:
        fail("EXPECTED_REQUIRED_CHECKS is required")

    protection = gh_api(f"repos/{repository}/branches/main/protection")
    repo = gh_api(f"repos/{repository}")

    status = protection.get("required_status_checks") or {}
    reviews = protection.get("required_pull_request_reviews")
    if status.get("strict") is not True:
        fail("required checks are not strict")
    if not enabled(protection.get("enforce_admins")):
        fail("administrators are not bound by protection")
    if not isinstance(reviews, dict):
        fail("pull requests are not required")
    if reviews.get("required_approving_review_count") != 0:
        fail("single-maintainer approval count must be zero")
    if not enabled(protection.get("required_linear_history")):
        fail("linear history is not required")
    if not enabled(protection.get("required_conversation_resolution")):
        fail("conversation resolution is not required")
    if enabled(protection.get("allow_force_pushes")):
        fail("force pushes are allowed")
    if enabled(protection.get("allow_deletions")):
        fail("branch deletion is allowed")

    checks = status.get("checks") or []
    actual = {(item.get("context"), item.get("app_id")) for item in checks}
    for name in expected:
        if (name, GITHUB_ACTIONS_APP_ID) not in actual:
            fail(f"{name} is missing or not bound to GitHub Actions")
    unexpected_apps = sorted(
        str(item.get("context")) for item in checks
        if item.get("app_id") != GITHUB_ACTIONS_APP_ID
    )
    if unexpected_apps:
        fail(f"checks are bound to unexpected applications: {', '.join(unexpected_apps)}")

    security = repo.get("security_and_analysis") or {}
    for name in ("secret_scanning", "secret_scanning_push_protection", "dependabot_security_updates"):
        if (security.get(name) or {}).get("status") != "enabled":
            fail(f"{name} is not enabled")
    if repo.get("allow_auto_merge") is not True:
        fail("automatic merge is not enabled")
    if repo.get("delete_branch_on_merge") is not True:
        fail("merged branches are not deleted")

    gh_api(f"repos/{repository}/vulnerability-alerts")
    gh_api(f"repos/{repository}/automated-security-fixes")
    print(json.dumps({
        "valid": True,
        "repository": repository,
        "required_checks": expected,
        "required_checks_app_id": GITHUB_ACTIONS_APP_ID,
        "administrators_enforced": True,
        "force_pushes": False,
        "deletions": False,
        "secret_scanning": True,
        "push_protection": True,
        "dependabot_security_updates": True,
    }, sort_keys=True))


if __name__ == "__main__":
    main()

