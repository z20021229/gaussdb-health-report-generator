"""Parse GaussDB inspection record files into structured YAML data."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECTION_TITLE_RE = re.compile(r"^\s*#{3,}\s*(?P<title>[^#\r\n].*?)\s*#{3,}\s*$")
PREVIEW_LIMIT = 300
UNKNOWN_SECTION_NAME = "未识别章节"
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1")


def parse_inspection_files(inspection_files: list[str]) -> dict[str, Any]:
    """Parse all inspection_rec.txt files and preserve their raw sections."""
    source_files = [str(Path(file_path)) for file_path in inspection_files]
    parsed_sections: list[dict[str, str]] = []

    for file_path in inspection_files:
        path = Path(file_path)
        text = _read_text(path)
        parsed_sections.extend(_split_sections(text=text, source_file=str(path)))

    return {
        "report": {
            "title": "GaussDB 数据库健康诊断报告",
            "source_files": source_files,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inspection_date": "未采集",
        },
        "sections": {
            "parsed_sections": parsed_sections,
        },
        "nodes": [],
        "cluster": {
            "cluster_status": "未采集",
            "ha_status": [],
            "replication_slots": [],
            "gs_check_summary": {
                "ok_count": 0,
                "ng_count": 0,
                "na_count": 0,
                "ng_items": [],
            },
        },
        "database": {
            "version": "未采集",
            "running_status": {},
            "databases": [],
            "large_tables": [],
            "index_suggestions": [],
            "unused_indexes": [],
            "table_bloat": [],
        },
        "logs": {
            "fatal_log_summary": "未采集",
            "panic_log_summary": "未采集",
        },
        "risks": [],
        "conclusion": {
            "summary": [],
            "suggestions": [],
        },
    }


def _read_text(path: Path) -> str:
    last_error: UnicodeDecodeError | None = None
    for encoding in TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    return path.read_text()


def _split_sections(text: str, source_file: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_name: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        title = _extract_section_title(line)
        if title is not None:
            _append_section(sections, source_file, current_name, current_lines)
            current_name = title
            current_lines = []
            continue
        current_lines.append(line)

    _append_section(sections, source_file, current_name, current_lines)
    return sections


def _extract_section_title(line: str) -> str | None:
    match = SECTION_TITLE_RE.match(line)
    if not match:
        return None

    title = match.group("title").strip().strip("#").strip()
    return title or UNKNOWN_SECTION_NAME


def _append_section(
    sections: list[dict[str, str]],
    source_file: str,
    section_name: str | None,
    lines: list[str],
) -> None:
    content = "\n".join(lines).strip()
    if section_name is None and not content:
        return

    sections.append(
        {
            "source_file": source_file,
            "section_name": section_name or UNKNOWN_SECTION_NAME,
            "content": content,
            "content_preview": _preview(content),
        }
    )


def _preview(content: str) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    if len(compact) <= PREVIEW_LIMIT:
        return compact
    return f"{compact[:PREVIEW_LIMIT]}..."


def build_minimal_inspection_data(input_path: Path, template_path: Path) -> dict[str, Any]:
    """Backward-compatible minimal data builder for older callers."""
    data = parse_inspection_files([])
    data["report"]["source_package"] = str(input_path)
    data["report"]["template_file"] = str(template_path)
    return data
