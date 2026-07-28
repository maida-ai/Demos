"""End-to-end verification of the stage-safe Maida gate."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import demo


PROJECT_ROOT = Path(__file__).parents[1]


def test_safe_agent_matches_checked_in_baseline() -> None:
    with (
        tempfile.TemporaryDirectory(prefix="pr-gate-safe-test-") as checkout,
        tempfile.TemporaryDirectory(prefix="pr-gate-safe-traces-") as traces,
    ):
        temp_root = Path(checkout)
        demo._copy_demo(temp_root)
        demo._initialize_temp_repository(temp_root)
        env = os.environ.copy()
        env["MAIDA_DATA_DIR"] = traces

        completed = subprocess.run(
            [
                demo._maida_executable(),
                "run",
                "coding_agent.py",
                "--baseline",
                ".maida/baselines/coding-agent.json",
                "--policy",
                ".maida/policy.yaml",
                "--format",
                "markdown",
            ],
            cwd=temp_root / "pr-gate",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    assert completed.returncode == 0, completed.stderr
    assert "Maida statistical gate: pass" in completed.stdout
    assert "`new_tools` | **PASS**" in completed.stdout


def test_candidate_is_blocked_for_rewriting_regression_test() -> None:
    completed = subprocess.run(
        [sys.executable, "demo.py", "--gate-only", "--no-color"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Maida statistical gate: fail" in completed.stdout
    assert "`new_tools` | **FAIL**" in completed.stdout
    assert "new tool: rewrite_regression_test" in completed.stdout
    assert "PR BLOCKED" in completed.stdout
