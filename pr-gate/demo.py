"""Stage-safe launcher for the YC PR gate demo."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent
DEMOS_ROOT = PROJECT_ROOT.parent
PATCH_PATH = PROJECT_ROOT / "demo" / "agents-pr.patch"
SAFE_AGENTS_PATH = PROJECT_ROOT / "demo" / "AGENTS.safe.md"
BASELINE_PATH = PROJECT_ROOT / ".maida" / "baselines" / "coding-agent.json"
POLICY_PATH = PROJECT_ROOT / ".maida" / "policy.yaml"
COPY_IGNORE = shutil.ignore_patterns(
    ".agents",
    ".codex",
    ".git",
    ".maida-data",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "*.pyc",
)


class Palette:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def paint(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def title(self, text: str) -> str:
        return self.paint(text, "1;36")

    def good(self, text: str) -> str:
        return self.paint(text, "1;32")

    def bad(self, text: str) -> str:
        return self.paint(text, "1;31")

    def quiet(self, text: str) -> str:
        return self.paint(text, "2")


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _copy_demo(temp_root: Path) -> Path:
    project = temp_root / "pr-gate"
    shutil.copytree(PROJECT_ROOT, project, ignore=COPY_IGNORE)
    shutil.copy2(SAFE_AGENTS_PATH, project / "AGENTS.md")
    return project


def _apply_candidate_patch(temp_root: Path) -> None:
    completed = _run(
        ["git", "apply", str(PATCH_PATH)],
        cwd=temp_root,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Could not apply candidate patch: {completed.stderr}")


def _initialize_temp_repository(temp_root: Path) -> None:
    commands = (
        ["git", "init", "--quiet"],
        ["git", "add", "pr-gate"],
        ["git", "add", "--force", "pr-gate/AGENTS.md"],
    )
    for command in commands:
        completed = _run(command, cwd=temp_root)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr)


def _maida_executable() -> str:
    adjacent = Path(sys.executable).with_name("maida")
    if adjacent.is_file():
        return str(adjacent)
    resolved = shutil.which("maida")
    if resolved is None:
        raise RuntimeError("maida executable not found; run `uv sync --locked`")
    return resolved


def _candidate_workspace(temp_root: Path) -> Path:
    project = _copy_demo(temp_root)
    _apply_candidate_patch(temp_root)
    return project


def _show_patch(palette: Palette) -> None:
    print(palette.title("1. The pull request"))
    for line in PATCH_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("+++") or line.startswith("---"):
            print(palette.quiet(line))
        elif line.startswith("+"):
            print(palette.good(line))
        elif line.startswith("-"):
            print(palette.bad(line))
        elif line.startswith("@@"):
            print(palette.paint(line, "36"))
        elif not line.startswith("diff ") and not line.startswith("index "):
            print(line)
    print()


def _show_conventional_tests(palette: Palette) -> None:
    print(palette.title("2. Conventional CI"))
    print(palette.quiet("$ uv run --frozen pytest -q"))
    completed = _run(
        ["uv", "run", "--frozen", "pytest", "-q"],
        cwd=PROJECT_ROOT,
    )
    print((completed.stdout + completed.stderr).strip())
    if completed.returncode != 0:
        raise RuntimeError("The demo project's conventional tests failed")
    print(palette.good("✓ Ordinary tests are green — this PR only changes Markdown."))
    print()


def _show_candidate_agent(palette: Palette) -> None:
    print(palette.title("3. What the changed instructions teach the coding agent"))
    with tempfile.TemporaryDirectory(prefix="pr-gate-preview-") as temp:
        temp_root = Path(temp)
        project = _candidate_workspace(temp_root)
        env = os.environ.copy()
        env["MAIDA_DATA_DIR"] = str(temp_root / "preview-trace")
        completed = _run(
            [sys.executable, "coding_agent.py"],
            cwd=project,
            env=env,
        )
        print(completed.stdout.strip())
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr)

        impact = _run(
            [
                sys.executable,
                "-c",
                (
                    "from storefront.shipping import shipping_fee_cents; "
                    "print(shipping_fee_cents(1200, is_vip=True))"
                ),
            ],
            cwd=project,
        )
        if impact.returncode != 0:
            raise RuntimeError(impact.stderr)
        fee_cents = int(impact.stdout.strip())
        print(
            palette.bad(
                f"Impact: the green suite now approves a ${fee_cents / 100:.2f} "
                "shipping charge for a VIP customer."
            )
        )
    print()


def _run_maida_gate(palette: Palette) -> None:
    if not BASELINE_PATH.is_file():
        raise RuntimeError(
            "Known-good baseline missing; run "
            "`uv run python demo.py --capture-baseline`"
        )

    print(palette.title("4. Maida checks the agent, not just the final test color"))
    print(
        palette.quiet(
            "$ maida run coding_agent.py --baseline "
            ".maida/baselines/coding-agent.json --policy .maida/policy.yaml"
        )
    )
    with (
        tempfile.TemporaryDirectory(prefix="pr-gate-checkout-") as checkout,
        tempfile.TemporaryDirectory(prefix="pr-gate-traces-") as traces,
    ):
        temp_root = Path(checkout)
        project = _candidate_workspace(temp_root)
        _initialize_temp_repository(temp_root)
        env = os.environ.copy()
        env["MAIDA_DATA_DIR"] = traces
        completed = _run(
            [
                _maida_executable(),
                "run",
                "coding_agent.py",
                "--baseline",
                ".maida/baselines/coding-agent.json",
                "--policy",
                ".maida/policy.yaml",
                "--format",
                "markdown",
            ],
            cwd=project,
            env=env,
        )
        print(completed.stdout.strip())
        if completed.stderr.strip():
            print(completed.stderr.strip(), file=sys.stderr)
        if completed.returncode != 1:
            raise RuntimeError(
                f"Expected Maida to block the candidate; exit={completed.returncode}"
            )
        if "rewrite_regression_test" not in completed.stdout:
            raise RuntimeError("Maida report did not identify the new tool path")

    print()
    print(palette.bad("✗ PR BLOCKED: the agent learned to rewrite regression tests."))


def _capture_baseline() -> None:
    with (
        tempfile.TemporaryDirectory(prefix="pr-gate-baseline-") as checkout,
        tempfile.TemporaryDirectory(prefix="pr-gate-baseline-data-") as traces,
    ):
        project = _copy_demo(Path(checkout))
        env = os.environ.copy()
        env["MAIDA_DATA_DIR"] = traces
        agent = _run(
            [sys.executable, "coding_agent.py"],
            cwd=project,
            env=env,
        )
        if agent.returncode != 0:
            raise RuntimeError(agent.stderr)

        trace_dirs = sorted(path for path in (Path(traces) / "runs").iterdir())
        if len(trace_dirs) != 1:
            raise RuntimeError(
                f"Expected exactly one safe trace, found {len(trace_dirs)}"
            )

        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        baseline = _run(
            [
                _maida_executable(),
                "baseline",
                trace_dirs[0].name,
                "--out",
                str(BASELINE_PATH),
            ],
            cwd=project,
            env=env,
        )
        if baseline.returncode != 0:
            raise RuntimeError(baseline.stderr)
        print(baseline.stdout.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-baseline",
        action="store_true",
        help="Regenerate the checked-in baseline from the safe AGENTS.md",
    )
    parser.add_argument(
        "--gate-only",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.capture_baseline:
        _capture_baseline()
        return 0

    palette = Palette(enabled=not args.no_color and sys.stdout.isatty())
    try:
        if not args.gate_only:
            _show_patch(palette)
            _show_conventional_tests(palette)
            _show_candidate_agent(palette)
        _run_maida_gate(palette)
    except RuntimeError as error:
        print(f"demo error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
