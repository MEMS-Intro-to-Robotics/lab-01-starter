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

EXPECTED_COMMIT_SEQUENCE = (
    "Update README and add setup screenshots",
    "Start Git recovery record",
    "Add remote sync note",
    "Document remote-ahead recovery",
    "Add sync conflict baseline",
    "Edit sync state on GitHub",
    "Edit sync state on VM",
    "Document Git sync and conflict recovery",
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


def _commit_records(repo: Path) -> tuple[list[tuple[str, str]], str | None]:
    result = _run_git(repo, "log", "--format=%H%x09%s")
    if result.returncode != 0:
        return [], result.stderr.strip() or "git log failed"
    records: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        if "\t" in line:
            commit_hash, subject = line.split("\t", 1)
            records.append((commit_hash, subject))
    return records, None


def _normalize_subject(subject: str) -> str:
    """Compare commit subjects forgivingly: hand-typed messages routinely pick
    up case slips, doubled spaces, or a trailing period, none of which change
    which exercise step the commit represents."""
    return re.sub(r"\s+", " ", subject).strip().rstrip(".").casefold()


def check_git_history(repo: Path) -> list[str]:
    errors: list[str] = []
    if not (repo / ".git").exists():
        return ["Run the grading script inside the cloned Git repository; .git is missing"]

    records, error = _commit_records(repo)
    if error:
        return [f"Could not inspect Git history: {error}"]

    subjects = [_normalize_subject(subject) for _commit_hash, subject in records]
    expected = [_normalize_subject(subject) for subject in EXPECTED_COMMIT_SEQUENCE]
    missing = [original for original, norm in zip(EXPECTED_COMMIT_SEQUENCE, expected)
               if norm not in subjects]
    if missing:
        errors.append("Missing required Lab 1 commits: " + ", ".join(missing))
    else:
        # Only the rebase outcome is graded: Part 5.6 replays the VM edit on top
        # of the GitHub edit. Records are newest-first, so the GitHub edit must
        # sit at a higher index. The remaining commits may be made in any order
        # that reaches the same final state.
        github_edit = _normalize_subject("Edit sync state on GitHub")
        vm_edit = _normalize_subject("Edit sync state on VM")
        if subjects.index(github_edit) < subjects.index(vm_edit):
            errors.append(
                "'Edit sync state on VM' must sit on top of 'Edit sync state on GitHub'; "
                "recover with a rebase so the GitHub commit is preserved underneath"
            )

    subject_to_hash = {_normalize_subject(subject): commit_hash
                       for commit_hash, subject in records}
    expected_paths = {
        "Add remote sync note": "README.md",
        "Add sync conflict baseline": "sync_conflict.txt",
        "Edit sync state on GitHub": "sync_conflict.txt",
        "Edit sync state on VM": "sync_conflict.txt",
    }
    for subject, expected_path in expected_paths.items():
        commit_hash = subject_to_hash.get(_normalize_subject(subject))
        if commit_hash is None:
            continue
        changed = _run_git(repo, "show", "--format=", "--name-only", commit_hash)
        paths = set(changed.stdout.splitlines())
        if expected_path not in paths:
            errors.append(f"Commit '{subject}' does not modify {expected_path}")

    merges = _run_git(repo, "rev-list", "--min-parents=2", "HEAD")
    if merges.returncode != 0:
        errors.append("Could not check whether the Lab 1 history is linear")
    elif merges.stdout.strip():
        errors.append("Lab 1 history contains a merge commit; the required recovery ends with linear history")

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
