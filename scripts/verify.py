"""Run lint, format check and the test suite, saving every artifact for later inspection.

    python scripts/verify.py

Each run writes reports/verify-<UTC timestamp>/ containing the raw output of each step,
a JUnit XML file, and summary.json with exact commands, exit codes, versions and durations.
Exit status is non-zero if any step fails.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(name: str, cmd: list[str], out_dir: Path) -> dict:
    start = time.monotonic()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    duration = round(time.monotonic() - start, 2)
    log = out_dir / f"{name}.log"
    log.write_text(
        f"$ {' '.join(cmd)}\n\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
        encoding="utf-8",
    )
    status = "PASS" if proc.returncode == 0 else "FAIL"
    print(f"[{status}] {name:<8} {duration:>6.2f}s  -> {log.relative_to(ROOT)}")
    return {"step": name, "command": cmd, "exit_code": proc.returncode, "seconds": duration}


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "reports" / f"verify-{stamp}"
    out_dir.mkdir(parents=True)
    py = sys.executable

    steps = [
        ("lint", [py, "-m", "ruff", "check", "."]),
        ("format", [py, "-m", "ruff", "format", "--check", "."]),
        (
            "tests",
            [py, "-m", "pytest", "-v", "--tb=short", f"--junitxml={out_dir / 'junit.xml'}"],
        ),
    ]
    results = [_run(name, cmd, out_dir) for name, cmd in steps]

    summary = {
        "started_utc": stamp,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip(),
        "results": results,
        "passed": all(r["exit_code"] == 0 for r in results),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        f"\nartifacts: {out_dir.relative_to(ROOT)}  |  overall: "
        f"{'PASS' if summary['passed'] else 'FAIL'}"
    )
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
