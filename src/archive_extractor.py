"""Archive extraction and manifest generation."""

from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
import os
import stat
from pathlib import Path
from typing import Any

try:
    import rarfile
except ImportError:  # pragma: no cover - covered by dependency checks in tests
    rarfile = None


MANIFEST_GROUPS = [
    "inspection_rec",
    "check_reports",
    "collectors",
    "fatal_logs",
    "panic_logs",
    "wdr_node",
    "wdr_cluster",
    "html",
    "logs",
    "txt",
    "archives",
    "others",
]

ARCHIVE_SUFFIXES = (".rar", ".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


class ArchiveExtractionError(RuntimeError):
    """Raised when an archive cannot be extracted in the current environment."""


def prepare_workdir(workdir: Path) -> Path:
    """Create and return the working directory used by the pipeline."""
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


def extract_package(input_path: str, workdir: str) -> dict[str, Any]:
    """Extract an inspection package recursively and return a file manifest.

    The implementation identifies files by generic file names, suffixes, and
    patterns only. It does not read customer-specific data from package content.
    """
    source = Path(input_path)
    if not source.exists():
        raise FileNotFoundError(f"input package does not exist: {source}")

    workdir_path = prepare_workdir(Path(workdir))
    extract_root = workdir_path / "extracted"
    if extract_root.exists():
        _remove_tree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)

    _extract_archive(source, extract_root)
    _extract_nested_archives(extract_root)

    manifest = _empty_manifest(source, extract_root)
    for path in sorted(p for p in extract_root.rglob("*") if p.is_file()):
        _classify_file(path, manifest["files"])

    return manifest


def _empty_manifest(source: Path, extract_root: Path) -> dict[str, Any]:
    return {
        "source_package": str(source),
        "extract_root": str(extract_root),
        "files": {group: [] for group in MANIFEST_GROUPS},
    }


def _remove_tree(path: Path) -> None:
    def handle_remove_error(function: Any, failed_path: str, _exc_info: Any) -> None:
        if not os.path.exists(failed_path):
            return
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)

    shutil.rmtree(path, onerror=handle_remove_error)


def _extract_nested_archives(extract_root: Path) -> None:
    extracted_archives: set[Path] = set()

    while True:
        archive_paths = [
            path
            for path in sorted(extract_root.rglob("*"))
            if path.is_file() and _is_archive(path) and path.resolve() not in extracted_archives
        ]
        if not archive_paths:
            break

        for archive_path in archive_paths:
            destination = archive_path.parent / f"{_safe_dir_name(archive_path.name)}.extracted"
            destination.mkdir(parents=True, exist_ok=True)
            _extract_archive(archive_path, destination)
            extracted_archives.add(archive_path.resolve())


def _extract_archive(archive_path: Path, destination: Path) -> None:
    name = archive_path.name.lower()

    if name.endswith((".tar.gz", ".tgz", ".tar", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
        _extract_tar(archive_path, destination)
        return

    if name.endswith(".zip"):
        _extract_zip(archive_path, destination)
        return

    if name.endswith(".rar"):
        _extract_rar(archive_path, destination)
        return

    raise ArchiveExtractionError(f"unsupported archive format: {archive_path}")


def _extract_tar(archive_path: Path, destination: Path) -> None:
    try:
        with tarfile.open(archive_path) as archive:
            for member in archive.getmembers():
                _ensure_safe_member(destination, member.name)
            archive.extractall(destination, filter="data")
    except (tarfile.TarError, OSError) as exc:
        raise ArchiveExtractionError(f"failed to extract tar archive {archive_path}: {exc}") from exc


def _extract_zip(archive_path: Path, destination: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                _ensure_safe_member(destination, member)
            archive.extractall(destination)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveExtractionError(f"failed to extract zip archive {archive_path}: {exc}") from exc


def _extract_rar(archive_path: Path, destination: Path) -> None:
    if rarfile is not None:
        try:
            with rarfile.RarFile(archive_path) as archive:
                for member in archive.infolist():
                    _ensure_safe_member(destination, member.filename)
                archive.extractall(destination)
                return
        except rarfile.RarCannotExec:
            pass
        except rarfile.Error as exc:
            raise ArchiveExtractionError(f"failed to extract rar archive {archive_path}: {exc}") from exc

    for command in _rar_commands():
        if _run_external_extractor(command, archive_path, destination):
            return

    raise ArchiveExtractionError(
        "failed to extract rar archive because no compatible extractor was found. "
        "Install 7-Zip, unrar, or bsdtar and make it available on PATH."
    )


def _rar_commands() -> list[list[str]]:
    commands: list[list[str]] = []
    for executable in _candidate_rar_tools():
        tool_name = executable.name.lower()
        if tool_name.startswith("7z"):
            commands.append([str(executable), "x", "-y", f"-o{{destination}}", "{archive}"])
        elif tool_name.startswith("unrar"):
            commands.append([str(executable), "x", "-y", "{archive}", "{destination}"])
        elif tool_name.startswith("bsdtar"):
            commands.append([str(executable), "-xf", "{archive}", "-C", "{destination}"])
    return commands


def _candidate_rar_tools() -> list[Path]:
    candidates = [
        shutil.which("7z"),
        shutil.which("7za"),
        shutil.which("unrar"),
        shutil.which("bsdtar"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    return [Path(candidate) for candidate in candidates if candidate and Path(candidate).exists()]


def _run_external_extractor(command: list[str], archive_path: Path, destination: Path) -> bool:
    prepared = [
        part.format(archive=str(archive_path), destination=str(destination)) for part in command
    ]
    completed = subprocess.run(
        prepared,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _ensure_safe_member(destination: Path, member_name: str) -> None:
    target = (destination / member_name).resolve()
    root = destination.resolve()
    if target != root and root not in target.parents:
        raise ArchiveExtractionError(f"archive member escapes extraction directory: {member_name}")


def _classify_file(path: Path, files: dict[str, list[str]]) -> None:
    path_text = str(path)
    name = path.name.lower()

    if _is_archive(path):
        files["archives"].append(path_text)
        if name.startswith("checkreport_") and _has_tar_gz_suffix(name):
            files["check_reports"].append(path_text)
        elif name.startswith("collector_") and _has_tar_gz_suffix(name):
            files["collectors"].append(path_text)
        return

    if name == "inspection_rec.txt":
        files["inspection_rec"].append(path_text)
        return

    if name == "fatal_log.log":
        files["fatal_logs"].append(path_text)
        return

    if name in {"panic_log.log", "pinic_log.log"}:
        files["panic_logs"].append(path_text)
        return

    if name.startswith("wdrnode_") and name.endswith((".html", ".htm")):
        files["wdr_node"].append(path_text)
        files["html"].append(path_text)
        return

    if name.startswith("wdrcluster_") and name.endswith((".html", ".htm")):
        files["wdr_cluster"].append(path_text)
        files["html"].append(path_text)
        return

    if name.endswith((".html", ".htm")):
        files["html"].append(path_text)
        return

    if name.endswith(".log"):
        files["logs"].append(path_text)
        return

    if name.endswith(".txt"):
        files["txt"].append(path_text)
        return

    files["others"].append(path_text)


def _is_archive(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in ARCHIVE_SUFFIXES)


def _has_tar_gz_suffix(name: str) -> bool:
    return name.endswith((".tar.gz", ".tgz"))


def _safe_dir_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)
