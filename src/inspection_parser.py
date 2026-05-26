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
NODE_BLOCK_RE = re.compile(
    r"^\[(?:SUCCESS|FAILURE|FAILED|ERROR)\]\s+(?P<node>[^:\r\n]+):\s*$",
    re.IGNORECASE | re.MULTILINE,
)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
KEY_VALUE_RE = re.compile(r"^\s*(?P<key>[^:]+?)\s*:\s*(?P<value>.*?)\s*$")


def parse_inspection_files(inspection_files: list[str]) -> dict[str, Any]:
    """Parse all inspection_rec.txt files and preserve their raw sections."""
    source_files = [str(Path(file_path)) for file_path in inspection_files]
    parsed_sections: list[dict[str, str]] = []

    for file_path in inspection_files:
        path = Path(file_path)
        text = _read_text(path)
        parsed_sections.extend(_split_sections(text=text, source_file=str(path)))

    nodes = _extract_resource_nodes(parsed_sections)

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
        "nodes": nodes,
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
            "resource_summary": _build_resource_summary(nodes),
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


def _extract_resource_nodes(parsed_sections: list[dict[str, str]]) -> list[dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}

    for section in parsed_sections:
        name = section["section_name"]
        content = section["content"]
        if name == "操作系统信息":
            _parse_os_section(content, nodes)
        elif name == "CPU型号信息":
            _parse_cpu_model_section(content, nodes)
        elif name == "CPU核数信息":
            _parse_cpu_core_section(content, nodes)
        elif name == "内存大小信息":
            _parse_memory_section(content, nodes)
        elif name == "磁盘空间大小":
            _parse_disk_section(content, nodes)
        elif name == "CPU近一天使用情况":
            _parse_cpu_daily_section(content, nodes)

    node_list = list(nodes.values())
    for node in node_list:
        _finalize_node_disk_summary(node)

    node_list.sort(key=lambda item: (str(item.get("ip") or ""), str(item.get("hostname") or "")))
    return node_list


def _default_node(identifier: str = "未采集") -> dict[str, Any]:
    ip = identifier if IP_RE.search(identifier) else "未采集"
    hostname = "未采集" if ip != "未采集" else identifier
    return {
        "ip": ip,
        "hostname": hostname,
        "role": "未采集",
        "os_version": "未采集",
        "architecture": "未采集",
        "os_summary": "未采集",
        "cpu_model": "未采集",
        "cpu_cores": "未采集",
        "threads_per_core": "未采集",
        "cores_per_socket": "未采集",
        "sockets": "未采集",
        "numa_nodes": "未采集",
        "bogo_mips": "未采集",
        "cpu_implementer": "未采集",
        "cpu_architecture": "未采集",
        "memory": {
            "total_mb": 0,
            "used_mb": 0,
            "free_mb": 0,
            "shared_mb": 0,
            "buff_cache_mb": 0,
            "available_mb": 0,
            "usage_percent": 0,
        },
        "disks": [],
        "disk_summary": {
            "max_disk_use_percent": 0,
            "data_disk_use_percent": 0,
            "max_disk_mount": "未采集",
        },
        "cpu_daily": {
            "avg_user": 0,
            "avg_system": 0,
            "avg_iowait": 0,
            "avg_idle": 0,
            "min_idle": 0,
            "max_iowait": 0,
        },
    }


def _get_node(nodes: dict[str, dict[str, Any]], identifier: str) -> dict[str, Any]:
    normalized = identifier.strip() or "未采集"
    key = normalized
    ip_match = IP_RE.search(normalized)
    if ip_match:
        key = ip_match.group(0)

    if key not in nodes:
        nodes[key] = _default_node(key)
    return nodes[key]


def _node_blocks(content: str) -> list[tuple[str, str]]:
    matches = list(NODE_BLOCK_RE.finditer(content))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        blocks.append((match.group("node").strip(), content[start:end].strip()))
    return blocks


def _parse_os_section(content: str, nodes: dict[str, dict[str, Any]]) -> None:
    for identifier, block in _node_blocks(content):
        node = _get_node(nodes, identifier)
        summary = _first_data_line(block)
        if not summary:
            continue

        node["os_summary"] = summary
        parts = summary.split()
        if len(parts) >= 3 and parts[0].lower() == "linux":
            node["hostname"] = parts[1] or node["hostname"]
            node["os_version"] = parts[2] or node["os_version"]
            if len(parts) >= 2:
                node["architecture"] = parts[-2] if parts[-1] == "GNU/Linux" else parts[-1]


def _parse_cpu_model_section(content: str, nodes: dict[str, dict[str, Any]]) -> None:
    for identifier, block in _node_blocks(content):
        node = _get_node(nodes, identifier)
        values = _parse_key_values(block)
        node["cpu_model"] = values.get("model name", node["cpu_model"])
        node["bogo_mips"] = values.get("BogoMIPS", node["bogo_mips"])
        node["cpu_implementer"] = values.get("CPU implementer", node["cpu_implementer"])
        node["cpu_architecture"] = values.get("CPU architecture", node["cpu_architecture"])
        if node["architecture"] == "未采集" and values.get("Architecture"):
            node["architecture"] = values["Architecture"]


def _parse_cpu_core_section(content: str, nodes: dict[str, dict[str, Any]]) -> None:
    for identifier, block in _node_blocks(content):
        node = _get_node(nodes, identifier)
        values = _parse_key_values(block)
        node["architecture"] = values.get("Architecture", node["architecture"])
        node["cpu_cores"] = _to_int(values.get("CPU(s)"), default=node["cpu_cores"])
        node["threads_per_core"] = values.get("Thread(s) per core", node["threads_per_core"])
        node["cores_per_socket"] = values.get("Core(s) per socket", node["cores_per_socket"])
        node["sockets"] = values.get("Socket(s)", node["sockets"])
        node["numa_nodes"] = values.get("NUMA node(s)", node["numa_nodes"])
        if values.get("Model name"):
            node["cpu_model"] = values["Model name"]
        if values.get("BogoMIPS"):
            node["bogo_mips"] = values["BogoMIPS"]


def _parse_memory_section(content: str, nodes: dict[str, dict[str, Any]]) -> None:
    for identifier, block in _node_blocks(content):
        node = _get_node(nodes, identifier)
        for line in block.splitlines():
            parts = line.split()
            if not parts or parts[0].rstrip(":").lower() != "mem":
                continue
            values = [_to_int(part, default=0) for part in parts[1:]]
            if len(values) < 6:
                continue
            total, used, free, shared, buff_cache, available = values[:6]
            usage_percent = round((used / total) * 100, 2) if total else 0
            node["memory"] = {
                "total_mb": total,
                "used_mb": used,
                "free_mb": free,
                "shared_mb": shared,
                "buff_cache_mb": buff_cache,
                "available_mb": available,
                "usage_percent": usage_percent,
            }
            break


def _parse_disk_section(content: str, nodes: dict[str, dict[str, Any]]) -> None:
    for identifier, block in _node_blocks(content):
        node = _get_node(nodes, identifier)
        disks: list[dict[str, Any]] = []
        for line in block.splitlines():
            parts = line.split()
            if len(parts) < 6 or parts[0].lower() == "filesystem":
                continue
            use_percent = _parse_percent(parts[4])
            if use_percent is None:
                continue
            disks.append(
                {
                    "filesystem": parts[0],
                    "size": parts[1],
                    "used": parts[2],
                    "avail": parts[3],
                    "use_percent": use_percent,
                    "mounted_on": parts[5],
                }
            )
        if disks:
            node["disks"] = disks


def _parse_cpu_daily_section(content: str, nodes: dict[str, dict[str, Any]]) -> None:
    for identifier, block in _node_blocks(content):
        node = _get_node(nodes, identifier)
        rows: list[dict[str, float]] = []
        for line in block.splitlines():
            row = _parse_sar_cpu_row(line)
            if row:
                rows.append(row)
        if not rows:
            continue

        node["cpu_daily"] = {
            "avg_user": _round_avg(row["user"] for row in rows),
            "avg_system": _round_avg(row["system"] for row in rows),
            "avg_iowait": _round_avg(row["iowait"] for row in rows),
            "avg_idle": _round_avg(row["idle"] for row in rows),
            "min_idle": round(min(row["idle"] for row in rows), 2),
            "max_iowait": round(max(row["iowait"] for row in rows), 2),
        }


def _parse_sar_cpu_row(line: str) -> dict[str, float] | None:
    parts = line.split()
    if not parts or "all" not in parts:
        return None

    all_index = parts.index("all")
    metrics = parts[all_index + 1 :]
    if len(metrics) < 6:
        return None
    try:
        return {
            "user": float(metrics[0]),
            "system": float(metrics[2]),
            "iowait": float(metrics[3]),
            "idle": float(metrics[5]),
        }
    except ValueError:
        return None


def _parse_key_values(block: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in block.splitlines():
        match = KEY_VALUE_RE.match(line)
        if not match:
            continue
        values[match.group("key").strip()] = match.group("value").strip()
    return values


def _first_data_line(block: str) -> str:
    for line in block.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _to_int(value: Any, default: Any = "未采集") -> Any:
    if value is None:
        return default
    match = re.search(r"-?\d+", str(value))
    if not match:
        return default
    return int(match.group(0))


def _parse_percent(value: str) -> int | None:
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else None


def _round_avg(values: Any) -> float:
    numbers = list(values)
    if not numbers:
        return 0
    return round(sum(numbers) / len(numbers), 2)


def _finalize_node_disk_summary(node: dict[str, Any]) -> None:
    disks = node.get("disks", [])
    if not disks:
        return

    max_disk = max(disks, key=lambda item: item.get("use_percent", 0))
    data_disks = [disk for disk in disks if disk.get("mounted_on") == "/data"]
    node["disk_summary"] = {
        "max_disk_use_percent": max_disk.get("use_percent", 0),
        "data_disk_use_percent": data_disks[0].get("use_percent", 0) if data_disks else 0,
        "max_disk_mount": max_disk.get("mounted_on") or "未采集",
    }


def _build_resource_summary(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    max_disk_values = [
        node.get("disk_summary", {}).get("max_disk_use_percent", 0)
        for node in nodes
        if node.get("disk_summary", {}).get("max_disk_use_percent", 0)
    ]
    min_idle_values = [
        node.get("cpu_daily", {}).get("min_idle", 0)
        for node in nodes
        if node.get("cpu_daily", {}).get("min_idle", 0)
    ]
    max_iowait_values = [
        node.get("cpu_daily", {}).get("max_iowait", 0)
        for node in nodes
        if node.get("cpu_daily", {}).get("max_iowait", 0)
    ]
    return {
        "node_count": len(nodes),
        "cluster_max_disk_use_percent": max(max_disk_values) if max_disk_values else 0,
        "cluster_min_cpu_idle": min(min_idle_values) if min_idle_values else 0,
        "cluster_max_iowait": max(max_iowait_values) if max_iowait_values else 0,
    }
