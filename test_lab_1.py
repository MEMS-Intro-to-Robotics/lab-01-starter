#!/usr/bin/env python3
"""Automated submission checks for Lab 1: VM, Git, and Docker.

Run from the repository root with ``pytest -v``. These tests check objective
submission requirements. Human graders evaluate the screenshots and the quality
of the reasoning in ``git_recovery.md``.
"""

from __future__ import annotations

from pathlib import Path
import re
import struct
import subprocess


REPO_ROOT = Path(__file__).resolve().parent

EXPECTED_SCREENSHOTS = (
    "vm_desktop.png",
    "version_check.png",
    "ssh_github_test.png",
    "ros2_check.png",
    "talker_listener.png",
)

REQUIRED_REPORT_TEXT = (
    "# Git Synchronization and Recovery Record",
    "## Case 1: Remote Ahead",
    "Prediction before fetch:",
    "What `git status` reported before and after fetch:",
    "Relevant graph output:",
    "Recovery command and why it was safe:",
    "## Case 2: Diverged with a Conflict",
    "Prediction before push:",
    "Push rejection diagnosis:",
    "Conflict observed and resolution chosen:",
    "Why the recovery preserved both lines of work:",
    "## Final Verification",
    "Final `git status`:",
    "Final graph output:",
)

STARTER_MARKERS = ("[Your Name]", "Replace this paragraph", "YOUR_NETID")
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()[:24]
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def check_required_files(repo: Path) -> list[str]:
    errors: list[str] = []
    required = (
        "README.md",
        ".gitignore",
        "git_recovery.md",
        "sync_conflict.txt",
        "test_lab_1.py",
    )
    for relative in required:
        path = repo / relative
        if not path.is_file():
            errors.append(f"Missing required file: {relative}")
        elif path.stat().st_size == 0:
            errors.append(f"Required file is empty: {relative}")

    docs = repo / "docs"
    if not docs.is_dir():
        errors.append("Missing required directory: docs/")
        return errors

    for filename in EXPECTED_SCREENSHOTS:
        path = docs / filename
        if not path.is_file():
            errors.append(f"Missing required screenshot: docs/{filename}")
            continue
        dimensions = _png_dimensions(path)
        if dimensions is None or dimensions[0] < 1 or dimensions[1] < 1:
            errors.append(f"docs/{filename} is not a valid PNG image")
    return errors


def check_report_and_resolution(repo: Path) -> list[str]:
    errors: list[str] = []
    readme_path = repo / "README.md"
    if readme_path.is_file():
        readme = _read_text(readme_path)
        for marker in STARTER_MARKERS:
            if marker in readme:
                errors.append(f"README.md still contains starter text: {marker}")

    report_path = repo / "git_recovery.md"
    if report_path.is_file():
        report = _read_text(report_path)
        missing = [item for item in REQUIRED_REPORT_TEXT if item not in report]
        if missing:
            errors.append("git_recovery.md is missing required headings or prompts: " + ", ".join(missing))
        if len(re.findall(r"\b[\w'-]+\b", report)) < 80:
            errors.append("git_recovery.md is too short to contain the required run record")

    conflict_path = repo / "sync_conflict.txt"
    if conflict_path.is_file():
        conflict = _read_text(conflict_path)
        if any(marker in conflict for marker in CONFLICT_MARKERS):
            errors.append("sync_conflict.txt still contains Git conflict markers")
        lines = [line.strip() for line in conflict.splitlines() if line.strip()]
        if len(lines) != 1 or not lines[0].startswith("sync-state:"):
            errors.append("sync_conflict.txt must contain one resolved line beginning with 'sync-state:'")
        elif lines[0] in {
            "sync-state: BASE",
            "sync-state: REMOTE change made on GitHub",
            "sync-state: LOCAL change made on VM",
        }:
            errors.append(
                "sync_conflict.txt still contains an unresolved exercise state: "
                "keeping the BASE, GitHub, or VM line verbatim is choosing a side, "
                "not resolving. Replace it with one new line beginning with "
                "'sync-state:' that says how you reconciled the two edits"
            )
    return errors


def _scaffold_head(repo: Path) -> str | None:
    """The newest commit Classroom 50 created when the student accepted, i.e.
    the state the student started from. Returns None when it cannot be
    identified, in which case the caller skips the baseline comparison rather
    than inventing a failure."""
    result = _run_git(repo, "log", "--format=%H%x09%s", "--reverse")
    if result.returncode != 0:
        return None
    scaffold = None
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        commit_hash, subject = line.split("\t", 1)
        if subject.startswith("[Classroom 50]") or subject.strip() == "Initial commit":
            scaffold = commit_hash
        else:
            break
    return scaffold


def _paths_touched_since(repo: Path, scaffold: str | None) -> set[str]:
    """Every path changed by the student's own commits."""
    span = f"{scaffold}..HEAD" if scaffold else "HEAD"
    result = _run_git(repo, "log", "--format=", "--name-only", span)
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def check_git_history(repo: Path) -> list[str]:
    """Grade the end state of the repository, not the commit choreography.

    Lab 1's deliverables are the edited files and the pushed history. Which
    commit subject carries which change, and in what order, is deliberately not
    graded: a student who reached the same final state with their own commit
    messages did the lab. Whether the recovery was reasoned about correctly is
    graded from git_recovery.md by a human.
    """
    errors: list[str] = []
    if not (repo / ".git").exists():
        return ["Run the grading script inside the cloned Git repository; .git is missing"]

    scaffold = _scaffold_head(repo)
    touched = _paths_touched_since(repo, scaffold)

    # The README must differ from the state the student was given. Any edit
    # counts: the point is that the work reached the repository, not that it
    # was split across commits in a prescribed way.
    if scaffold is not None:
        diff = _run_git(repo, "diff", "--quiet", scaffold, "HEAD", "--", "README.md")
        if diff.returncode == 0:
            errors.append(
                "README.md is unchanged from the starter; edit it and push your changes"
            )
        elif diff.returncode != 1:
            errors.append("Could not compare README.md against the starter")

    for relative, label in (
        ("git_recovery.md", "git_recovery.md"),
        ("sync_conflict.txt", "sync_conflict.txt"),
    ):
        if relative not in touched:
            errors.append(f"No commit in this repository adds or changes {label}")

    if not any(path.startswith("docs/") and not path.endswith(".gitkeep")
               for path in touched):
        errors.append("No commit in this repository adds the docs/ screenshots")

    head = _run_git(repo, "rev-parse", "HEAD")
    remote = _run_git(repo, "rev-parse", "--verify", "refs/remotes/origin/main")
    if remote.returncode != 0:
        errors.append("origin/main is unavailable; run 'git fetch origin' before grading")
    elif head.returncode != 0 or head.stdout.strip() != remote.stdout.strip():
        errors.append("HEAD and origin/main differ; push your final commit, then run 'git fetch origin'")
    return errors


def check_repository_hygiene(repo: Path) -> list[str]:
    errors: list[str] = []
    result = _run_git(repo, "ls-files")
    if result.returncode != 0:
        return ["Could not inspect tracked files with 'git ls-files'"]

    forbidden_names = {"__pycache__", ".pytest_cache", ".DS_Store", "Thumbs.db"}
    tracked = [Path(line) for line in result.stdout.splitlines() if line]
    prohibited = [
        path.as_posix()
        for path in tracked
        if set(path.parts) & forbidden_names or path.suffix in {".pyc", ".pyo"}
    ]
    if prohibited:
        errors.append("Generated artifacts are tracked: " + ", ".join(prohibited))
    return errors


def _assert_no_errors(errors: list[str]) -> None:
    assert not errors, "\n- " + "\n- ".join(errors)


def test_required_files_and_screenshots() -> None:
    _assert_no_errors(check_required_files(REPO_ROOT))


def test_report_and_conflict_resolution() -> None:
    _assert_no_errors(check_report_and_resolution(REPO_ROOT))


def test_required_git_history_and_synchronization() -> None:
    _assert_no_errors(check_git_history(REPO_ROOT))


def test_repository_hygiene() -> None:
    _assert_no_errors(check_repository_hygiene(REPO_ROOT))
