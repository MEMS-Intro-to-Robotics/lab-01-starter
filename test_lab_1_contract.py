"""Fixture tests for the Lab 1 grading script.

These tests prove that the grader accepts a complete submission and rejects
incomplete and malformed submissions. They do not grade student work directly.
"""

from __future__ import annotations

from pathlib import Path
import shutil
import struct
import subprocess
import zlib

import pytest

import test_lab_1 as grader


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _write_png(path: Path) -> None:
    width = 2
    height = 2
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _row in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _commit(repo: Path, message: str, *paths: str) -> None:
    _git(repo, "add", *paths)
    _git(repo, "commit", "-m", message)


def _build_complete_submission(root: Path) -> Path:
    remote = root / "remote.git"
    repo = root / "submission"
    subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True, text=True)
    subprocess.run(["git", "init", "--initial-branch=main", str(repo)], check=True, capture_output=True, text=True)
    _git(repo, "config", "user.name", "Lab Student")
    _git(repo, "config", "user.email", "student@example.com")
    _git(repo, "remote", "add", "origin", str(remote))

    shutil.copy2(Path(grader.__file__), repo / "test_lab_1.py")
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n*.pyc\n", encoding="utf-8")
    (repo / "README.md").write_text("# Lab 1: VM, Git, and Docker — Student\n\n## Contents\n", encoding="utf-8")
    _commit(repo, "Initial starter", "test_lab_1.py", ".gitignore", "README.md")

    docs = repo / "docs"
    docs.mkdir()
    for filename in grader.EXPECTED_SCREENSHOTS[:3]:
        _write_png(docs / filename)
    (repo / "README.md").write_text("# Lab 1: VM, Git, and Docker — Student\n\n## Contents\n- docs\n", encoding="utf-8")
    _commit(repo, "Update README and add setup screenshots", "README.md", "docs")

    report = "\n".join(grader.REQUIRED_REPORT_TEXT) + "\n"
    (repo / "git_recovery.md").write_text(report, encoding="utf-8")
    _commit(repo, "Start Git recovery record", "git_recovery.md")

    with (repo / "README.md").open("a", encoding="utf-8") as stream:
        stream.write("- Git synchronization and recovery practice\n")
    _commit(repo, "Add remote sync note", "README.md")

    with (repo / "git_recovery.md").open("a", encoding="utf-8") as stream:
        stream.write(("Observed a remote-ahead state and verified the branch labels before "
                      "using a fast-forward pull. ") * 4)
    _commit(repo, "Document remote-ahead recovery", "git_recovery.md")

    (repo / "sync_conflict.txt").write_text("sync-state: BASE\n", encoding="utf-8")
    _commit(repo, "Add sync conflict baseline", "sync_conflict.txt")
    (repo / "sync_conflict.txt").write_text("sync-state: REMOTE change made on GitHub\n", encoding="utf-8")
    _commit(repo, "Edit sync state on GitHub", "sync_conflict.txt")
    (repo / "sync_conflict.txt").write_text("sync-state: reconciled GitHub and VM changes\n", encoding="utf-8")
    _commit(repo, "Edit sync state on VM", "sync_conflict.txt")

    for filename in grader.EXPECTED_SCREENSHOTS[3:]:
        _write_png(docs / filename)
    with (repo / "git_recovery.md").open("a", encoding="utf-8") as stream:
        stream.write(("The rejected push showed that both branches contained unique work. "
                      "I inspected the graph, resolved the conflict, and verified synchronization. ") * 4)
    _commit(repo, "Document Git sync and conflict recovery", "git_recovery.md", "docs")
    _git(repo, "push", "-u", "origin", "main")
    _git(repo, "fetch", "origin")
    return repo


def _all_errors(repo: Path) -> list[str]:
    return (
        grader.check_required_files(repo)
        + grader.check_report_and_resolution(repo)
        + grader.check_git_history(repo)
        + grader.check_repository_hygiene(repo)
    )


def test_grader_accepts_known_good_submission(tmp_path: Path) -> None:
    repo = _build_complete_submission(tmp_path)
    assert _all_errors(repo) == []


def test_grader_rejects_incomplete_submission(tmp_path: Path) -> None:
    repo = tmp_path / "incomplete"
    repo.mkdir()
    (repo / "README.md").write_text("# Incomplete\n", encoding="utf-8")
    errors = _all_errors(repo)
    assert any("Missing required file" in error for error in errors)
    assert any(".git is missing" in error for error in errors)


def test_grader_rejects_malformed_submission(tmp_path: Path) -> None:
    repo = _build_complete_submission(tmp_path)
    (repo / "sync_conflict.txt").write_text(
        "<<<<<<< HEAD\nsync-state: REMOTE\n=======\nsync-state: LOCAL\n>>>>>>> commit\n",
        encoding="utf-8",
    )
    (repo / "git_recovery.md").write_text("# Git Synchronization and Recovery Record\n", encoding="utf-8")
    errors = grader.check_report_and_resolution(repo)
    assert any("conflict markers" in error for error in errors)
    assert any("missing required headings" in error for error in errors)


def test_contract_suite_uses_pytest_fixture(tmp_path: Path) -> None:
    assert tmp_path.is_dir()
