from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

FORBIDDEN_RELEASE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".zip",
    ".tar",
    ".tar.gz",
    ".rar",
    ".7z",
    ".dump",
    ".backup",
    ".sql",
    ".sqlite3",
    ".db",
}

FORBIDDEN_RELEASE_NAMES = {
    ".DS_Store",
    "Thumbs.db",
}


def forbidden_release_reason(raw_path: str) -> str | None:
    normalized = raw_path.replace("\\", "/")

    while normalized.startswith("./"):
        normalized = normalized[2:]

    normalized = normalized.lstrip("/")
    path = PurePosixPath(normalized)

    if "__pycache__" in path.parts:
        return "python cache directory"

    name = path.name
    lower_name = name.lower()

    if name == ".env":
        return "environment secret file"

    if name.startswith(".env.") and name != ".env.example":
        return "environment secret file"

    if name in FORBIDDEN_RELEASE_NAMES:
        return "operating-system artifact"

    for forbidden_suffix in sorted(
        FORBIDDEN_RELEASE_SUFFIXES,
        key=len,
        reverse=True,
    ):
        if lower_name.endswith(forbidden_suffix):
            return f"forbidden release suffix: {forbidden_suffix}"

    return None


class Command(BaseCommand):
    help = (
        "Build a production release ZIP from tracked Git files only, "
        "after validating repository cleanliness and forbidden artifacts."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="Validate the Git release source without creating a ZIP.",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="",
            help=(
                "Optional output ZIP path. Defaults to "
                "release_artifacts/loomera-<commit>.zip."
            ),
        )

    def handle(self, *args, **options):
        project_root = Path(settings.BASE_DIR).resolve()

        self._ensure_git_repository(project_root)
        self._ensure_clean_worktree(project_root)

        tracked_files = self._tracked_files(project_root)
        violations = self._find_violations(tracked_files)

        if violations:
            formatted = "\n".join(f"- {path}: {reason}" for path, reason in violations)
            raise CommandError(
                "Forbidden tracked files were found:\n"
                f"{formatted}\n"
                "Remove them from Git tracking before building a release."
            )

        commit_id = self._git_output(
            project_root,
            "rev-parse",
            "--short=12",
            "HEAD",
        ).strip()

        self.stdout.write(
            self.style.SUCCESS(
                f"Release source validated: {len(tracked_files)} tracked files"
            )
        )
        self.stdout.write(f"Commit: {commit_id}")

        if options["check_only"]:
            self.stdout.write(self.style.SUCCESS("Release archive check passed."))
            return

        output_path = self._resolve_output_path(
            project_root=project_root,
            commit_id=commit_id,
            raw_output=options["output"],
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")

        temporary_path.unlink(missing_ok=True)

        try:
            self._run_git(
                project_root,
                "archive",
                "--format=zip",
                f"--output={temporary_path}",
                "HEAD",
            )

            self._validate_created_archive(temporary_path)
            os.replace(temporary_path, output_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

        self.stdout.write(self.style.SUCCESS(f"Release archive created: {output_path}"))

    def _ensure_git_repository(self, project_root: Path) -> None:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        if result.returncode != 0 or result.stdout.strip() != "true":
            raise CommandError("The project directory is not a valid Git worktree.")

    def _ensure_clean_worktree(self, project_root: Path) -> None:
        status = self._git_output(
            project_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ).strip()

        if status:
            raise CommandError(
                "Working tree is not clean. Commit or remove pending "
                "changes before building the release archive."
            )

    def _tracked_files(self, project_root: Path) -> list[str]:
        output = self._git_output(
            project_root,
            "ls-files",
            "-z",
        )
        return sorted(path for path in output.split("\0") if path)

    def _find_violations(
        self,
        tracked_files: list[str],
    ) -> list[tuple[str, str]]:
        violations: list[tuple[str, str]] = []

        for path in tracked_files:
            reason = forbidden_release_reason(path)
            if reason:
                violations.append((path, reason))

        return violations

    def _resolve_output_path(
        self,
        *,
        project_root: Path,
        commit_id: str,
        raw_output: str,
    ) -> Path:
        if raw_output:
            output_path = Path(raw_output).expanduser()
            if not output_path.is_absolute():
                output_path = project_root / output_path
        else:
            output_path = (
                project_root / "release_artifacts" / f"loomera-{commit_id}.zip"
            )

        output_path = output_path.resolve()

        if output_path.suffix.lower() != ".zip":
            raise CommandError("Release output must use the .zip suffix.")

        return output_path

    def _validate_created_archive(self, archive_path: Path) -> None:
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                invalid_members = []

                for member in archive.namelist():
                    reason = forbidden_release_reason(member)
                    if reason:
                        invalid_members.append((member, reason))

                corrupt_member = archive.testzip()
        except zipfile.BadZipFile as exc:
            raise CommandError(
                "The generated release archive is not a valid ZIP."
            ) from exc

        if corrupt_member:
            raise CommandError(
                "The generated release archive is corrupt: " f"{corrupt_member}"
            )

        if invalid_members:
            formatted = "\n".join(
                f"- {path}: {reason}" for path, reason in invalid_members
            )
            raise CommandError(
                "Forbidden files were found inside the generated archive:\n"
                f"{formatted}"
            )

    def _git_output(
        self,
        project_root: Path,
        *arguments: str,
    ) -> str:
        result = self._run_git(
            project_root,
            *arguments,
            capture_output=True,
        )
        return result.stdout

    def _run_git(
        self,
        project_root: Path,
        *arguments: str,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *arguments],
            cwd=project_root,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        if result.returncode != 0:
            error_text = (
                result.stderr.strip() if result.stderr else "Git command failed."
            )
            raise CommandError(f"Git operation failed: {error_text}")

        return result
