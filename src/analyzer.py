"""Risk analysis and report conclusions for GaussDB inspection data."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def analyze_inspection_data(data: dict[str, Any]) -> dict[str, Any]:
    """Analyze parsed inspection data and attach risks, summaries, and suggestions."""
    analyzed = deepcopy(data)
    analyzed.setdefault("cluster", {})
    analyzed.setdefault("database", {})
    analyzed.setdefault("logs", {})
    analyzed.setdefault("conclusion", {})

    _normalize_structured_data(analyzed)

    risks: list[dict[str, Any]] = []
    risks.extend(_analyze_disk_risks(analyzed))
    risks.extend(_analyze_cpu_risks(analyzed))
    risks.extend(_analyze_memory_risks(analyzed))
    risks.extend(_analyze_cluster_status_risks(analyzed))
    risks.extend(_analyze_ha_risks(analyzed))
    risks.extend(_analyze_replication_slot_risks(analyzed))
    risks.extend(_analyze_gs_check_risks(analyzed))
    risks.extend(_analyze_log_risks(analyzed))
    risks.extend(_analyze_large_table_risks(analyzed))
    risks.extend(_analyze_index_suggestion_risks(analyzed))
    risks.extend(_analyze_unused_index_risks(analyzed))
    risks.extend(_analyze_table_bloat_risks(analyzed))

    risks = _sort_risks(risks)
    analyzed["risks"] = risks
    analyzed["risk_summary"] = _build_risk_summary(risks)
    analyzed["risk_details"] = _build_risk_details(risks)
    analyzed["report_risks"] = list(risks)
    analyzed["cluster"]["overall_status"] = _overall_status(risks)

    _attach_gs_check_display_items(analyzed)
    analyzed["conclusion"] = {
        "summary": _build_conclusion_summary(analyzed),
        "suggestions": _build_conclusion_suggestions(risks),
    }
    _refresh_structured_summaries(analyzed)
    return analyzed


def analyze_minimal(data: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias."""
    return analyze_inspection_data(data)


def _normalize_structured_data(data: dict[str, Any]) -> None:
    database = data.setdefault("database", {})
    database["table_bloat"] = _dedupe_table_bloat(database.get("table_bloat", []))


def _dedupe_table_bloat(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for record in records:
        datname = str(record.get("datname", "") or "").strip()
        schemaname = str(record.get("schemaname", "") or "").strip()
        relname = str(record.get("relname", "") or "").strip()
        dead_rate = str(record.get("dead_rate", "") or "").strip()
        key = (datname, schemaname, relname, dead_rate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _analyze_disk_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    nodes = data.get("nodes", [])
    has_disk_info = False
    for node in nodes:
        disks = node.get("disks") or []
        has_disk_info = has_disk_info or bool(disks)
        for disk in disks:
            use_percent = _to_number(disk.get("use_percent"))
            if use_percent is None:
                continue
            if use_percent >= 80:
                risks.append(
                    _risk(
                        "风险",
                        "磁盘空间",
                        f"节点 {_node_label(node)} 挂载点 {disk.get('mounted_on', '未采集')} 使用率为 {use_percent}%。",
                        "建议清理历史文件、归档日志或进行磁盘扩容。",
                        {"node": _node_label(node), "mount": disk.get("mounted_on", "未采集"), "use_percent": use_percent},
                    )
                )
            elif use_percent >= 70:
                risks.append(
                    _risk(
                        "关注",
                        "磁盘空间",
                        f"节点 {_node_label(node)} 挂载点 {disk.get('mounted_on', '未采集')} 使用率为 {use_percent}%。",
                        "建议持续关注磁盘增长趋势，提前规划扩容。",
                        {"node": _node_label(node), "mount": disk.get("mounted_on", "未采集"), "use_percent": use_percent},
                    )
                )
    if nodes and not has_disk_info:
        risks.append(
            _risk(
                "关注",
                "磁盘空间",
                "巡检结果中未采集到磁盘空间使用信息。",
                "建议补充磁盘空间采集结果，确认各挂载点容量情况。",
                {"field": "nodes[].disks"},
            )
        )
    return risks


def _analyze_cpu_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for node in data.get("nodes", []):
        cpu_daily = node.get("cpu_daily") or {}
        avg_idle = _to_number(cpu_daily.get("avg_idle"))
        max_iowait = _to_number(cpu_daily.get("max_iowait"))
        if avg_idle is not None and avg_idle < 30:
            risks.append(
                _risk(
                    "关注",
                    "CPU 使用率",
                    f"节点 {_node_label(node)} 平均 idle 为 {avg_idle}%。",
                    "建议排查高 CPU SQL、后台任务和系统负载。",
                    {"node": _node_label(node), "avg_idle": avg_idle},
                )
            )
        if max_iowait is not None and max_iowait > 10:
            risks.append(
                _risk(
                    "关注",
                    "IO 等待",
                    f"节点 {_node_label(node)} 最大 iowait 为 {max_iowait}%。",
                    "建议关注 IO 性能、存储响应时间和数据库写入压力。",
                    {"node": _node_label(node), "max_iowait": max_iowait},
                )
            )
    return risks


def _analyze_memory_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for node in data.get("nodes", []):
        usage_percent = _to_number((node.get("memory") or {}).get("usage_percent"))
        if usage_percent is None:
            continue
        if usage_percent >= 90:
            risks.append(
                _risk(
                    "风险",
                    "内存使用率",
                    f"节点 {_node_label(node)} 当前内存使用率为 {usage_percent}%。",
                    "建议排查内存占用较高的数据库会话、系统进程，并评估内存扩容。",
                    {"node": _node_label(node), "usage_percent": usage_percent},
                )
            )
        elif usage_percent >= 80:
            risks.append(
                _risk(
                    "关注",
                    "内存使用率",
                    f"节点 {_node_label(node)} 当前内存使用率为 {usage_percent}%。",
                    "建议持续观察内存使用趋势。",
                    {"node": _node_label(node), "usage_percent": usage_percent},
                )
            )
    return risks


def _analyze_cluster_status_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    cluster_status = str(data.get("cluster", {}).get("cluster_status", "未采集") or "未采集").strip()
    if cluster_status.lower() == "normal":
        return []
    if cluster_status == "未采集":
        return [
            _risk(
                "关注",
                "集群总体状态",
                "巡检结果中未采集到集群整体状态信息。",
                "建议补充集群整体状态检查结果，确认服务状态及主备关系。",
                {"field": "cluster.cluster_status"},
            )
        ]
    return [
        _risk(
            "风险",
            "集群总体状态",
            f"当前集群总体状态为 {cluster_status}。",
            "建议优先核查集群服务状态、主备关系及相关告警。",
            {"field": "cluster.cluster_status", "value": cluster_status},
        )
    ]


def _analyze_ha_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for record in data.get("cluster", {}).get("ha_status", []):
        diff = _to_number(record.get("pg_xlog_location_diff"))
        if diff is None or diff == 0:
            continue
        level = "风险" if diff > 1024 else "关注"
        risks.append(
            _risk(
                level,
                "高可用同步",
                f"client_addr {record.get('client_addr', '未采集')} 当前同步状态为 {record.get('sync_state', '未采集')}，位点差异为 {record.get('pg_xlog_location_diff', '未采集')}。",
                "建议检查主备同步链路、复制延迟来源及网络或 IO 负载情况。",
                dict(record),
            )
        )
    return risks


def _analyze_replication_slot_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for record in data.get("cluster", {}).get("replication_slots", []):
        active = str(record.get("active", "")).strip().lower()
        delay = _to_number(record.get("delay_lsn"))
        if active in {"false", "0", "f"}:
            risks.append(
                _risk(
                    "风险",
                    "复制槽状态",
                    f"复制槽 {record.get('slot_name', '未采集')} 未处于激活状态。",
                    "建议检查复制连接状态、从库同步链路及复制槽绑定关系。",
                    dict(record),
                )
            )
            continue
        if delay is None or delay == 0:
            continue
        level = "风险" if delay > 1024 else "关注"
        risks.append(
            _risk(
                level,
                "复制槽延迟",
                f"复制槽 {record.get('slot_name', '未采集')} 当前延迟位点为 {record.get('delay_lsn', '未采集')}。",
                "建议检查复制链路延迟、主库写入压力及从库回放情况。",
                dict(record),
            )
        )
    return risks


def _analyze_gs_check_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for item in data.get("cluster", {}).get("gs_check_summary", {}).get("ng_items", []):
        check_name = str(item.get("check_name", "未采集"))
        detail_summary = str(item.get("detail_summary", "未采集"))
        risks.append(
            _risk(
                "风险" if _gs_check_high_risk(check_name, detail_summary) else "关注",
                "gs_check 巡检项",
                f"{check_name} 检查结果为 NG。{detail_summary}",
                _gs_check_suggestion(check_name),
                {"check_name": check_name, "raw_detail_path": item.get("raw_detail_path", "")},
            )
        )
    return risks


def _analyze_log_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    logs = data.get("logs", {})
    risks: list[dict[str, Any]] = []
    risks.extend(_analyze_single_log_summary("fatal 日志", str(logs.get("fatal_log_summary", "未采集")), logs.get("fatal_log_files", [])))
    risks.extend(_analyze_single_log_summary("panic 日志", str(logs.get("panic_log_summary", "未采集")), logs.get("panic_log_files", [])))
    return risks


def _analyze_single_log_summary(label: str, summary: str, files: list[str]) -> list[dict[str, Any]]:
    normalized = summary.strip()
    if normalized == "未发现日志文件":
        return [
            _risk(
                "关注",
                label,
                f"未获取到 {label} 文件。",
                "建议确认日志采集路径及巡检结果包内容是否完整。",
                {"files": files},
            )
        ]
    if "未发现" in normalized and "异常日志" in normalized:
        return []
    if normalized and normalized != "未采集":
        return [
            _risk(
                "风险",
                label,
                f"{label}存在异常摘要：{_short_text(normalized, 300)}",
                "建议结合日志摘要进一步核查异常发生时间、影响范围及根因。",
                {"files": files, "summary": _short_text(normalized, 500)},
            )
        ]
    return []


def _analyze_large_table_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    count = len(data.get("database", {}).get("large_tables", []))
    if not count:
        return []
    return [
        _risk(
            "关注",
            "大表容量",
            f"巡检中识别到 {count} 条大表记录。",
            "建议结合业务增长趋势评估归档、分区或历史数据清理策略。",
            {"count": count, "field": "database.large_tables"},
        )
    ]


def _analyze_index_suggestion_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    count = len(data.get("database", {}).get("index_suggestions", []))
    if not count:
        return []
    return [
        _risk(
            "关注",
            "索引优化",
            f"巡检中识别到 {count} 条索引优化建议。",
            "建议结合高频 SQL、慢 SQL 和业务访问路径评估是否新增或调整索引。",
            {"count": count, "field": "database.index_suggestions"},
        )
    ]


def _analyze_unused_index_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    count = len(data.get("database", {}).get("unused_indexes", []))
    if not count:
        return []
    return [
        _risk(
            "关注",
            "未使用索引",
            f"巡检中识别到 {count} 条未使用索引记录。",
            "建议核查未使用索引是否长期无访问，确认后再考虑清理，避免误删业务依赖索引。",
            {"count": count, "field": "database.unused_indexes"},
        )
    ]


def _analyze_table_bloat_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for record in data.get("database", {}).get("table_bloat", []):
        dead_rate = _to_number(record.get("dead_rate"))
        if dead_rate is None or dead_rate < 20:
            continue
        risks.append(
            _risk(
                "风险" if dead_rate >= 50 else "关注",
                "表膨胀",
                f"对象 {record.get('schemaname', '未采集')}.{record.get('relname', '未采集')} 死元组占比为 {record.get('dead_rate', '未采集')}。",
                "建议结合维护窗口执行 VACUUM / ANALYZE 或表维护操作。",
                dict(record),
            )
        )
    return risks


def _attach_gs_check_display_items(data: dict[str, Any]) -> None:
    gs_check = data.setdefault("cluster", {}).setdefault("gs_check_summary", {})
    gs_check["ng_display_items"] = [
        {
            "check_name": str(item.get("check_name", "未采集")),
            "status": str(item.get("status", "NG")),
            "detail_summary": str(item.get("detail_summary", "未采集")),
            "suggestion": _gs_check_suggestion(str(item.get("check_name", "未采集"))),
        }
        for item in gs_check.get("ng_items", [])
    ]


def _refresh_structured_summaries(data: dict[str, Any]) -> None:
    database = data.setdefault("database", {})
    cluster = data.setdefault("cluster", {})
    database.setdefault("running_status", {})
    database["running_status"]["summary"] = _rows_summary("数据库运行状态", database["running_status"].get("records", []))
    cluster["ha_summary"] = _rows_summary("高可用状态", cluster.get("ha_status", []))
    cluster["replication_slot_summary"] = _rows_summary("复制槽", cluster.get("replication_slots", []))
    database["large_tables_summary"] = _top_summary("大表", database.get("large_tables", []))
    database["index_suggestions_summary"] = _top_summary("索引建议", database.get("index_suggestions", []))
    database["unused_indexes_summary"] = "未发现未使用索引" if not database.get("unused_indexes") else _top_summary("未使用索引", database.get("unused_indexes", []))
    database["table_bloat_summary"] = _top_summary("表膨胀", database.get("table_bloat", []))


def _build_risk_summary(risks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_count": len(risks),
        "risk_count": sum(1 for item in risks if item.get("level") == "风险"),
        "warning_count": sum(1 for item in risks if item.get("level") == "关注"),
        "by_item": _build_risk_summary_by_item(risks),
        "by_source": _build_risk_summary_by_source(risks),
    }


def _build_risk_summary_by_item(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for risk in risks:
        item = str(risk.get("item", "未采集"))
        entry = grouped.setdefault(item, {"item": item, "risk_count": 0, "warning_count": 0, "total_count": 0})
        entry["total_count"] += 1
        if risk.get("level") == "风险":
            entry["risk_count"] += 1
        else:
            entry["warning_count"] += 1
    return sorted(grouped.values(), key=lambda row: (-row["risk_count"], -row["warning_count"], row["item"]))


def _build_risk_summary_by_source(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for risk in risks:
        source = _source_group_label(risk)
        entry = grouped.setdefault(source, {"source": source, "risk_count": 0, "warning_count": 0, "total_count": 0})
        entry["total_count"] += 1
        if risk.get("level") == "风险":
            entry["risk_count"] += 1
        else:
            entry["warning_count"] += 1
    return sorted(grouped.values(), key=lambda row: (-row["risk_count"], -row["warning_count"], row["source"]))


def _build_risk_details(risks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    details = {"risks": [], "warnings": []}
    for risk in risks:
        item = {
            "level": str(risk.get("level", "未采集")),
            "item": str(risk.get("item", "未采集")),
            "detail": str(risk.get("detail", "未采集")),
            "suggestion": str(risk.get("suggestion", "未采集")),
            "source": _source_text(risk.get("source")),
        }
        if risk.get("level") == "风险":
            details["risks"].append(item)
        else:
            details["warnings"].append(item)
    return details


def _build_conclusion_summary(data: dict[str, Any]) -> list[str]:
    cluster = data.get("cluster", {})
    database = data.get("database", {})
    logs = data.get("logs", {})
    risk_counts = _risk_level_counts(data.get("risks", []))
    return [
        f"本次巡检综合评估结果为“{cluster.get('overall_status', '未采集')}”。",
        f"数据库运行状态记录 {len(database.get('running_status', {}).get('records', []))} 条，高可用状态记录 {len(cluster.get('ha_status', []))} 条，复制槽记录 {len(cluster.get('replication_slots', []))} 条。",
        f"全集群最高磁盘使用率为 {cluster.get('resource_summary', {}).get('cluster_max_disk_use_percent', '未采集')}%。",
        f"fatal 日志检查结果：{_log_summary_phrase(logs.get('fatal_log_summary', '未采集'))}；panic 日志检查结果：{_log_summary_phrase(logs.get('panic_log_summary', '未采集'))}。",
        f"gs_check 巡检结果中，OK {cluster.get('gs_check_summary', {}).get('ok_count', 0)} 项，NG {cluster.get('gs_check_summary', {}).get('ng_count', 0)} 项，NA {cluster.get('gs_check_summary', {}).get('na_count', 0)} 项。",
        f"系统管理维护检查中，大表记录 {len(database.get('large_tables', []))} 条，索引建议 {len(database.get('index_suggestions', []))} 条，表膨胀记录 {len(database.get('table_bloat', []))} 条。",
        f"本次巡检共识别风险 {risk_counts['风险']} 条、关注 {risk_counts['关注']} 条。",
    ]


def _build_conclusion_suggestions(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for risk in risks:
        key = (str(risk.get("level")), str(risk.get("item")), str(risk.get("suggestion")))
        if key in grouped:
            grouped[key]["related_count"] += 1
            continue
        grouped[key] = {
            "level": risk.get("level", "未采集"),
            "item": risk.get("item", "未采集"),
            "suggestion": risk.get("suggestion", "未采集"),
            "related_count": 1,
        }
    suggestions = list(grouped.values())
    suggestions.sort(key=lambda row: (-_level_rank(str(row["level"])), str(row["item"])))
    return suggestions


def _sort_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        risks,
        key=lambda row: (
            -_level_rank(str(row.get("level", ""))),
            _risk_priority(str(row.get("item", ""))),
            str(row.get("detail", "")),
        ),
    )


def _risk_priority(item: str) -> int:
    if item == "gs_check 巡检项":
        return 0
    if "日志" in item:
        return 1
    if item in {"集群总体状态", "高可用同步", "复制槽状态", "复制槽延迟"}:
        return 2
    if item in {"磁盘空间", "CPU 使用率", "IO 等待", "内存使用率"}:
        return 3
    return 4


def _overall_status(risks: list[dict[str, Any]]) -> str:
    if any(item.get("level") == "风险" for item in risks):
        return "风险"
    if any(item.get("level") == "关注" for item in risks):
        return "关注"
    return "良好"


def _source_group_label(risk: dict[str, Any]) -> str:
    item = str(risk.get("item", "未采集"))
    source = risk.get("source")
    if item == "gs_check 巡检项" and isinstance(source, dict):
        return f"gs_check:{source.get('check_name', '未采集')}"
    if "日志" in item:
        return "日志检查"
    if item in {"集群总体状态", "高可用同步", "复制槽状态", "复制槽延迟"}:
        return "数据库高可用"
    if item in {"磁盘空间", "CPU 使用率", "IO 等待", "内存使用率"}:
        return "系统资源"
    if item in {"大表容量", "索引优化", "未使用索引", "表膨胀"}:
        return "系统管理维护"
    return item


def _source_text(source: Any) -> str:
    if isinstance(source, str):
        return source
    if not isinstance(source, dict):
        return ""
    parts: list[str] = []
    for key in ["check_name", "node", "mount", "client_addr", "slot_name", "field"]:
        value = source.get(key)
        if value not in (None, "", "未采集"):
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def _risk_level_counts(risks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "风险": sum(1 for item in risks if item.get("level") == "风险"),
        "关注": sum(1 for item in risks if item.get("level") == "关注"),
    }


def _level_rank(level: str) -> int:
    if level == "风险":
        return 2
    if level == "关注":
        return 1
    return 0


def _risk(level: str, item: str, detail: str, suggestion: str, source: Any) -> dict[str, Any]:
    return {
        "level": level,
        "item": item,
        "detail": detail,
        "suggestion": suggestion,
        "source": source,
    }


def _node_label(node: dict[str, Any]) -> str:
    ip = str(node.get("ip", "")).strip()
    if ip and ip != "未采集":
        return ip
    hostname = str(node.get("hostname", "")).strip()
    if hostname and hostname != "未采集":
        return hostname
    return "未采集"


def _to_number(value: Any) -> float | None:
    if value in (None, "", "未采集"):
        return None
    try:
        return float(str(value).strip().rstrip("%"))
    except ValueError:
        return None


def _gs_check_high_risk(check_name: str, detail_summary: str) -> bool:
    text = f"{check_name} {detail_summary}".lower()
    return any(keyword in text for keyword in ["permission", "权限", "安全", "sysadmin", "guc", "目录权限"])


def _gs_check_suggestion(check_name: str) -> str:
    if check_name == "CheckDirPermissions":
        return "建议根据安全规范核查目录权限，避免权限过宽。"
    if check_name == "CheckGUCValue":
        return "建议核查数据库参数值是否符合当前集群规模和运维规范。"
    if check_name == "CheckSysadminUser":
        return "建议核查 sysadmin 用户是否符合最小权限和安全管理要求。"
    if check_name == "CheckHashIndex":
        return "建议评估 hash index 使用情况、兼容性和维护风险。"
    return "建议结合 gs_check 原始结果进行核查和整改。"


def _rows_summary(label: str, rows: list[dict[str, Any]]) -> str:
    return f"已完成 {len(rows)} 条{label}记录检查。" if rows else f"未采集到{label}记录。"


def _top_summary(label: str, rows: list[dict[str, Any]]) -> str:
    return f"已识别 {len(rows)} 条{label}记录。" if rows else f"未采集到{label}记录。"


def _short_text(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    return compact if len(compact) <= limit else f"{compact[:limit]}..."


def _log_summary_phrase(summary: Any) -> str:
    text = str(summary or "未采集").strip()
    if text == "未发现日志文件":
        return "未获取到日志文件"
    if "未发现" in text and "异常日志" in text:
        return text
    if text == "未采集":
        return "未采集"
    return "发现需进一步核查的异常摘要"
