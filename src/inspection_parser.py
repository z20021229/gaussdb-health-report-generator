"""Parse GaussDB inspection record files into structured YAML data."""

from __future__ import annotations

import re
import hashlib
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
GS_CHECK_RE = re.compile(r"^\s*(?P<name>Check[A-Za-z0-9_]+)\.*\s*(?P<status>OK|NG|NA)\s*$")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
TOP_YAML_LIMIT = 50
SUMMARY_LIMIT = 600


def parse_inspection_files(
    inspection_files: list[str],
    manifest: dict[str, Any] | None = None,
    output_dir: str | Path = "output",
) -> dict[str, Any]:
    """Parse all inspection_rec.txt files and preserve their raw sections."""
    source_files = [str(Path(file_path)) for file_path in inspection_files]
    parsed_sections: list[dict[str, str]] = []

    for file_path in inspection_files:
        path = Path(file_path)
        text = _read_text(path)
        parsed_sections.extend(_split_sections(text=text, source_file=str(path)))

    nodes = _extract_resource_nodes(parsed_sections)
    db_cluster_data = _extract_database_cluster_data(parsed_sections)
    maintenance_data = _extract_maintenance_data(parsed_sections, Path(output_dir))
    log_data = _extract_log_summaries(manifest or {})

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
            "ha_status": db_cluster_data["cluster"]["ha_status"],
            "ha_summary": db_cluster_data["cluster"]["ha_summary"],
            "replication_slots": db_cluster_data["cluster"]["replication_slots"],
            "replication_slot_summary": db_cluster_data["cluster"]["replication_slot_summary"],
            "gs_check_summary": maintenance_data["cluster"]["gs_check_summary"],
            "resource_summary": _build_resource_summary(nodes),
        },
        "database": {
            "version": db_cluster_data["database"]["version"],
            "running_status": db_cluster_data["database"]["running_status"],
            "databases": db_cluster_data["database"]["databases"],
            "large_tables": maintenance_data["database"]["large_tables"],
            "large_tables_summary": maintenance_data["database"]["large_tables_summary"],
            "index_suggestions": maintenance_data["database"]["index_suggestions"],
            "index_suggestions_summary": maintenance_data["database"]["index_suggestions_summary"],
            "unused_indexes": maintenance_data["database"]["unused_indexes"],
            "unused_indexes_summary": maintenance_data["database"]["unused_indexes_summary"],
            "table_bloat": maintenance_data["database"]["table_bloat"],
            "table_bloat_summary": maintenance_data["database"]["table_bloat_summary"],
        },
        "logs": {
            "fatal_log_summary": log_data["fatal_log_summary"],
            "panic_log_summary": log_data["panic_log_summary"],
            "fatal_log_files": log_data["fatal_log_files"],
            "panic_log_files": log_data["panic_log_files"],
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


def _extract_database_cluster_data(parsed_sections: list[dict[str, str]]) -> dict[str, Any]:
    running_records: list[dict[str, Any]] = []
    replication_slots: list[dict[str, Any]] = []
    ha_status: list[dict[str, Any]] = []
    databases: list[dict[str, Any]] = []
    version = "未采集"

    for section in parsed_sections:
        name = section["section_name"]
        content = section["content"]
        if name == "数据库运行状态检查":
            running_records.extend(_parse_running_status(content))
        elif name == "复制槽状态检查":
            replication_slots.extend(_parse_replication_slots(content))
        elif name == "集群高可用状态检查":
            ha_status.extend(_parse_ha_status(content))
        elif name == "数据库信息检查":
            databases.extend(_parse_database_info(content))

        if version == "未采集":
            version = _extract_database_version(content)

    return {
        "cluster": {
            "ha_status": ha_status,
            "ha_summary": _rows_summary("高可用状态", ha_status),
            "replication_slots": replication_slots,
            "replication_slot_summary": _rows_summary("复制槽", replication_slots),
        },
        "database": {
            "version": version,
            "running_status": {
                "records": running_records,
                "summary": _rows_summary("数据库运行状态", running_records),
            },
            "databases": databases,
        },
    }


def _parse_running_status(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _parse_psql_table(content):
        is_in_recovery = _value_or_unknown(row.get("is_in_recovery"))
        records.append(
            {
                "checktime": _value_or_unknown(row.get("checktime")),
                "uptime": _value_or_unknown(row.get("uptime")),
                "lsn": _value_or_unknown(row.get("lsn")),
                "insert_lsn": _value_or_unknown(row.get("insert_lsn")),
                "write_lsn": _value_or_unknown(row.get("write_lsn")),
                "conf_reload_time": _value_or_unknown(row.get("conf_reload_time")),
                "is_in_recovery": is_in_recovery,
                "role_hint": _role_hint(is_in_recovery),
            }
        )
    return records


def _parse_replication_slots(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _parse_psql_table(content):
        records.append(
            {
                "slot_name": _value_or_unknown(row.get("slot_name")),
                "slot_type": _value_or_unknown(row.get("slot_type")),
                "active": _value_or_unknown(row.get("active")),
                "delay_lsn": _value_or_unknown(row.get("delay_lsn")),
            }
        )
    return records


def _parse_ha_status(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _parse_psql_table(content):
        records.append(
            {
                "client_addr": _value_or_unknown(row.get("client_addr")),
                "sync_state": _value_or_unknown(row.get("sync_state")),
                "pg_xlog_location_diff": _value_or_unknown(row.get("pg_xlog_location_diff")),
            }
        )
    return records


def _parse_database_info(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _parse_psql_table(content):
        size_bytes = _to_int(row.get("size_bytes"), default=0)
        records.append(
            {
                "datname": _value_or_unknown(row.get("datname")),
                "size_bytes": size_bytes,
                "readable_size": _format_bytes(size_bytes),
                "age": _value_or_unknown(row.get("age")),
                "is_template": _value_or_unknown(row.get("is_template")),
                "allow_conn": _value_or_unknown(row.get("allow_conn")),
                "conn_limit": _value_or_unknown(row.get("conn_limit")),
            }
        )
    return records


def _parse_psql_table(content: str) -> list[dict[str, str]]:
    lines = [line.rstrip() for line in content.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if "|" not in line:
            continue
        if index + 1 >= len(lines) or not _looks_like_psql_separator(lines[index + 1]):
            continue

        headers = [item.strip() for item in line.split("|")]
        rows: list[dict[str, str]] = []
        for row_line in lines[index + 2 :]:
            stripped = row_line.strip()
            if re.match(r"^\(\d+\s+rows?\)$", stripped):
                break
            if "|" not in row_line or _looks_like_psql_separator(row_line):
                continue
            values = [item.strip() for item in row_line.split("|")]
            if len(values) != len(headers):
                continue
            rows.append(dict(zip(headers, values)))
        return rows
    return []


def _looks_like_psql_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and set(stripped) <= {"-", "+", " "}


def _role_hint(is_in_recovery: str) -> str:
    normalized = str(is_in_recovery).strip().lower()
    if normalized in {"f", "false", "0", "no", "n"}:
        return "主库"
    if normalized in {"t", "true", "1", "yes", "y"}:
        return "备库"
    return "未采集"


def _value_or_unknown(value: Any) -> Any:
    if value is None:
        return "未采集"
    stripped = str(value).strip()
    return stripped if stripped else "未采集"


def _rows_summary(label: str, rows: list[dict[str, Any]]) -> str:
    return f"已解析{len(rows)}条{label}记录" if rows else f"未采集到{label}记录"


def _format_bytes(value: Any) -> str:
    if not isinstance(value, int) or value <= 0:
        return "未采集"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = float(value)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.2f} {units[unit_index]}"


def _extract_database_version(content: str) -> str:
    patterns = [
        r"(?:GaussDB|openGauss|PostgreSQL)[^\r\n]{0,160}",
        r"(?:数据库版本|版本信息|version)\s*[:：]\s*([^\r\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, flags=re.IGNORECASE)
        if not match:
            continue
        if match.groups():
            return _value_or_unknown(match.group(1))
            return _value_or_unknown(match.group(0))
    return "未采集"


def _extract_maintenance_data(parsed_sections: list[dict[str, str]], output_dir: Path) -> dict[str, Any]:
    large_tables: list[dict[str, Any]] = []
    index_suggestions: list[dict[str, Any]] = []
    unused_indexes: list[dict[str, Any]] = []
    table_bloat: list[dict[str, Any]] = []
    gs_check_items: list[dict[str, Any]] = []

    for section in parsed_sections:
        name = section["section_name"]
        content = section["content"]
        if name == "大表检查":
            large_tables.extend(_parse_large_tables(content))
        elif name == "索引建议":
            index_suggestions.extend(_parse_index_suggestions(content))
        elif name == "未使用的索引":
            unused_indexes.extend(_parse_unused_indexes(content))
        elif name == "表膨胀检查":
            table_bloat.extend(_parse_table_bloat(content))
        elif name == "gs_check巡检信息":
            gs_check_items.extend(_parse_gs_check(content, output_dir))

    large_tables = sorted(large_tables, key=lambda item: item.get("bytes", 0), reverse=True)[:TOP_YAML_LIMIT]
    index_suggestions = sorted(
        index_suggestions,
        key=lambda item: (_to_int(item.get("seq_scan"), default=0), _size_to_bytes(item.get("table_size"))),
        reverse=True,
    )[:TOP_YAML_LIMIT]
    unused_indexes = sorted(
        unused_indexes,
        key=lambda item: _size_to_bytes(item.get("size") or item.get("index_size")),
        reverse=True,
    )[:TOP_YAML_LIMIT]
    table_bloat = sorted(
        table_bloat,
        key=lambda item: _to_float(item.get("dead_rate"), default=0),
        reverse=True,
    )[:TOP_YAML_LIMIT]

    return {
        "database": {
            "large_tables": large_tables,
            "large_tables_summary": _top_summary("大表", large_tables),
            "index_suggestions": index_suggestions,
            "index_suggestions_summary": _top_summary("索引建议", index_suggestions),
            "unused_indexes": unused_indexes,
            "unused_indexes_summary": "未发现未使用索引" if not unused_indexes else _top_summary("未使用索引", unused_indexes),
            "table_bloat": table_bloat,
            "table_bloat_summary": _top_summary("表膨胀", table_bloat),
        },
        "cluster": {
            "gs_check_summary": _build_gs_check_summary(gs_check_items),
        },
    }


def _parse_large_tables(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _parse_psql_table(content):
        records.append(
            {
                "datname": _value_or_unknown(row.get("datname")),
                "nspname": _value_or_unknown(row.get("nspname")),
                "relname": _value_or_unknown(row.get("relname")),
                "bytes": _to_int(row.get("bytes"), default=0),
                "relsize": _value_or_unknown(row.get("relsize")),
                "indexsize": _value_or_unknown(row.get("indexsize")),
            }
        )
    return records


def _parse_index_suggestions(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _parse_psql_table(content):
        records.append(
            {
                "tablename": _value_or_unknown(row.get("tablename")),
                "table_size": _value_or_unknown(row.get("table_size")),
                "seq_scan": _to_int(row.get("seq_scan"), default=0),
                "idx_scan": _to_int(row.get("idx_scan"), default=0),
                "rate": _value_or_unknown(row.get("rate")),
            }
        )
    return records


def _parse_unused_indexes(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _parse_psql_table(content):
        records.append(
            {
                "schemaname": _value_or_unknown(row.get("schemaname")),
                "relname": _value_or_unknown(row.get("relname")),
                "indexrelname": _value_or_unknown(row.get("indexrelname")),
                "idx_scan": _value_or_unknown(row.get("idx_scan")),
                "size": _value_or_unknown(row.get("index_size") or row.get("size")),
            }
        )
    return records


def _parse_table_bloat(content: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in _parse_psql_table(content):
        records.append(
            {
                "schemaname": _value_or_unknown(row.get("schemaname")),
                "relname": _value_or_unknown(row.get("relname")),
                "n_live_tup": _to_int(row.get("n_live_tup"), default=0),
                "n_dead_tup": _to_int(row.get("n_dead_tup"), default=0),
                "dead_rate": _value_or_unknown(row.get("dead_rate")),
            }
        )
    return records


def _parse_gs_check(content: str, output_dir: Path) -> list[dict[str, Any]]:
    cleaned = _strip_ansi(content)
    lines = cleaned.splitlines()
    check_positions: list[tuple[int, re.Match[str]]] = []
    for index, line in enumerate(lines):
        match = GS_CHECK_RE.match(line)
        if match:
            check_positions.append((index, match))

    items: list[dict[str, Any]] = []
    for index, (line_index, match) in enumerate(check_positions):
        next_index = check_positions[index + 1][0] if index + 1 < len(check_positions) else len(lines)
        detail = "\n".join(lines[line_index + 1 : next_index]).strip()
        status = match.group("status").upper()
        item = {
            "check_name": match.group("name"),
            "status": status,
            "detail_summary": _summarize_text(detail),
            "raw_detail_path": "",
        }
        if status == "NG" and len(detail) > SUMMARY_LIMIT:
            item["raw_detail_path"] = _write_raw_section(output_dir, item["check_name"], detail)
        items.append(item)
    return items


def _build_gs_check_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    ok_count = sum(1 for item in items if item.get("status") == "OK")
    ng_count = sum(1 for item in items if item.get("status") == "NG")
    na_count = sum(1 for item in items if item.get("status") == "NA")
    unknown_count = sum(1 for item in items if item.get("status") not in {"OK", "NG", "NA"})
    return {
        "ok_count": ok_count,
        "ng_count": ng_count,
        "na_count": na_count,
        "unknown_count": unknown_count,
        "ng_items": [
            {
                "check_name": item["check_name"],
                "status": item["status"],
                "detail_summary": item["detail_summary"],
                "raw_detail_path": item["raw_detail_path"],
            }
            for item in items
            if item.get("status") == "NG"
        ],
    }


def _extract_log_summaries(manifest: dict[str, Any]) -> dict[str, Any]:
    files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    fatal_files = list(files.get("fatal_logs") or [])
    panic_files = list(files.get("panic_logs") or [])
    return {
        "fatal_log_files": fatal_files,
        "panic_log_files": panic_files,
        "fatal_log_summary": _summarize_log_files(fatal_files, "fatal"),
        "panic_log_summary": _summarize_log_files(panic_files, "panic"),
    }


def _summarize_log_files(paths: list[str], log_type: str) -> str:
    if not paths:
        return "未发现日志文件"

    summaries: list[str] = []
    for path_text in paths:
        path = Path(path_text)
        if not path.exists():
            summaries.append(f"{path_text}: 未发现日志文件")
            continue
        content = _read_text(path).strip()
        if not content:
            if log_type == "fatal":
                summaries.append(f"{path_text}: 未发现 fatal 异常日志")
            else:
                summaries.append(f"{path_text}: 未发现 panic 异常日志")
            continue
        first_lines = content.splitlines()[:20]
        summaries.append(f"{path_text}:\n" + "\n".join(first_lines))
    return "\n\n".join(summaries)


def _top_summary(label: str, records: list[dict[str, Any]]) -> str:
    return f"已解析{len(records)}条{label}记录，YAML最多保留Top {TOP_YAML_LIMIT}" if records else f"未采集到{label}记录"


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def _summarize_text(text: str) -> str:
    if not text.strip():
        return "未采集"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact = "\n".join(lines[:20])
    return compact[:SUMMARY_LIMIT] + ("..." if len(compact) > SUMMARY_LIMIT else "")


def _write_raw_section(output_dir: Path, check_name: str, detail: str) -> str:
    raw_dir = output_dir / "raw_sections"
    raw_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(detail.encode("utf-8", errors="ignore")).hexdigest()[:10]
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", check_name)
    path = raw_dir / f"{safe_name}_{digest}.txt"
    path.write_text(detail, encoding="utf-8")
    return str(path)


def _to_float(value: Any, default: Any = "未采集") -> Any:
    if value is None:
        return default
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return default
    return float(match.group(0))


def _size_to_bytes(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip().lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmgtp]?b|bytes?)?", text)
    if not match:
        return 0
    number = float(match.group(1))
    unit = (match.group(2) or "b").lower()
    multipliers = {
        "b": 1,
        "byte": 1,
        "bytes": 1,
        "kb": 1024,
        "mb": 1024**2,
        "gb": 1024**3,
        "tb": 1024**4,
        "pb": 1024**5,
    }
    return int(number * multipliers.get(unit, 1))
