"""Risk analysis and conclusion generation for inspection data."""

from __future__ import annotations

from typing import Any


def analyze_inspection_data(data: dict[str, Any]) -> dict[str, Any]:
    """Analyze parsed inspection data and attach risks and conclusions."""
    analyzed = dict(data)
    analyzed.setdefault("cluster", {})
    analyzed.setdefault("database", {})
    analyzed.setdefault("logs", {})

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

    analyzed["risks"] = risks
    analyzed["risk_summary"] = _build_risk_summary(risks)
    analyzed["risk_details"] = _build_risk_details(risks)
    analyzed["report_risks"] = _build_report_risks(risks)
    analyzed["cluster"]["overall_status"] = _overall_status(risks)
    analyzed["conclusion"] = {
        "summary": _build_conclusion_summary(analyzed),
        "suggestions": _build_conclusion_suggestions(risks),
    }
    _update_textual_summaries(analyzed)
    return analyzed


def analyze_minimal(data: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for previous pipeline stages."""
    return analyze_inspection_data(data)


def _analyze_disk_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    nodes = data.get("nodes", [])
    seen_disk_info = False
    for node in nodes:
        disks = node.get("disks") or []
        if disks:
            seen_disk_info = True
        for disk in disks:
            use_percent = _to_number(disk.get("use_percent"))
            if use_percent is None:
                continue
            if use_percent >= 80:
                level = "风险"
                suggestion = "建议清理历史文件、归档日志或进行磁盘扩容。"
            elif use_percent >= 70:
                level = "关注"
                suggestion = "建议持续关注磁盘增长趋势，提前规划扩容。"
            else:
                continue
            risks.append(
                _risk(
                    level=level,
                    item="磁盘空间",
                    detail=f"节点{_node_label(node)} 挂载点 {disk.get('mounted_on', '未采集')} 使用率为 {use_percent}%。",
                    suggestion=suggestion,
                    source={
                        "node": _node_label(node),
                        "mount": disk.get("mounted_on", "未采集"),
                        "use_percent": use_percent,
                    },
                )
            )
    if nodes and not seen_disk_info:
        risks.append(
            _risk(
                level="关注",
                item="磁盘空间",
                detail="巡检结果中未采集到磁盘空间使用信息。",
                suggestion="建议补充磁盘使用率采集结果，确认各挂载点容量情况。",
                source={"field": "nodes[].disks"},
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
                    level="关注",
                    item="CPU 使用率",
                    detail=f"节点{_node_label(node)} 近一天平均空闲率为 {avg_idle}%，系统负载偏高。",
                    suggestion="建议排查高 CPU SQL、后台任务和系统负载。",
                    source={"node": _node_label(node), "avg_idle": avg_idle},
                )
            )
        if max_iowait is not None and max_iowait > 10:
            risks.append(
                _risk(
                    level="关注",
                    item="IO 等待",
                    detail=f"节点{_node_label(node)} 近一天最大 IO 等待为 {max_iowait}%。",
                    suggestion="建议关注 IO 性能、存储响应时间和数据库写入压力。",
                    source={"node": _node_label(node), "max_iowait": max_iowait},
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
            level = "风险"
            suggestion = "建议排查内存占用较高的数据库会话、系统进程，并评估内存扩容。"
        elif usage_percent >= 80:
            level = "关注"
            suggestion = "建议持续观察内存使用趋势。"
        else:
            continue
        risks.append(
            _risk(
                level=level,
                item="内存使用率",
                detail=f"节点{_node_label(node)} 当前内存使用率为 {usage_percent}%。",
                suggestion=suggestion,
                source={"node": _node_label(node), "usage_percent": usage_percent},
            )
        )
    return risks


def _analyze_cluster_status_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    cluster_status = str(data.get("cluster", {}).get("cluster_status", "未采集")).strip()
    if cluster_status.lower() == "normal":
        return []
    if cluster_status == "未采集":
        return [
            _risk(
                level="关注",
                item="集群总体状态",
                detail="巡检结果中未采集到集群总体状态信息。",
                suggestion="建议补充集群总体状态检查结果，确认主备和服务运行情况。",
                source={"field": "cluster.cluster_status"},
            )
        ]
    return [
        _risk(
            level="风险",
            item="集群总体状态",
            detail=f"当前集群总体状态为 {cluster_status}。",
            suggestion="建议优先核查集群服务状态、主备关系及相关告警。",
            source={"field": "cluster.cluster_status", "value": cluster_status},
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
                level=level,
                item="高可用同步",
                detail=(
                    f"同步地址 {record.get('client_addr', '未采集')} 当前状态为 "
                    f"{record.get('sync_state', '未采集')}，位点差异为 {record.get('pg_xlog_location_diff', '未采集')}。"
                ),
                suggestion="建议检查主备同步链路、复制延迟来源及网络/IO 负载情况。",
                source=record,
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
                    level="风险",
                    item="复制槽状态",
                    detail=f"复制槽 {record.get('slot_name', '未采集')} 未处于激活状态。",
                    suggestion="建议检查复制连接状态、从库同步链路及复制槽绑定关系。",
                    source=record,
                )
            )
            continue
        if delay is None or delay == 0:
            continue
        level = "风险" if delay > 1024 else "关注"
        risks.append(
            _risk(
                level=level,
                item="复制槽延迟",
                detail=f"复制槽 {record.get('slot_name', '未采集')} 当前延迟位点为 {record.get('delay_lsn', '未采集')}。",
                suggestion="建议检查复制链路延迟、主库写入压力及从库回放情况。",
                source=record,
            )
        )
    return risks


def _analyze_gs_check_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for item in data.get("cluster", {}).get("gs_check_summary", {}).get("ng_items", []):
        check_name = str(item.get("check_name", "未采集"))
        detail_summary = str(item.get("detail_summary", "未采集"))
        suggestion = _gs_check_suggestion(check_name)
        level = "风险" if _gs_check_high_risk(check_name, detail_summary) else "关注"
        risks.append(
            _risk(
                level=level,
                item="gs_check 巡检项",
                detail=f"{check_name} 检查结果为 NG。{detail_summary}",
                suggestion=suggestion,
                source={
                    "check_name": check_name,
                    "raw_detail_path": item.get("raw_detail_path", ""),
                },
            )
        )
    return risks


def _analyze_log_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    logs = data.get("logs", {})
    risks: list[dict[str, Any]] = []
    risks.extend(
        _analyze_single_log_summary(
            label="fatal 日志",
            summary=str(logs.get("fatal_log_summary", "未采集")),
            files=logs.get("fatal_log_files", []),
        )
    )
    risks.extend(
        _analyze_single_log_summary(
            label="panic 日志",
            summary=str(logs.get("panic_log_summary", "未采集")),
            files=logs.get("panic_log_files", []),
        )
    )
    return risks


def _analyze_single_log_summary(label: str, summary: str, files: list[str]) -> list[dict[str, Any]]:
    normalized = summary.strip()
    if "未发现异常日志" in normalized or ("未发现" in normalized and "异常日志" in normalized):
        return []
    if normalized == "未发现日志文件":
        return [
            _risk(
                level="关注",
                item=label,
                detail=f"{label}文件未找到。",
                suggestion="建议确认日志采集路径和巡检结果包内容是否完整。",
                source={"files": files},
            )
        ]
    if normalized:
        return [
            _risk(
                level="风险",
                item=label,
                detail=f"{label}存在异常内容摘要：{_short_text(normalized, 300)}",
                suggestion="建议结合日志摘要和原始文件进一步核查异常发生时间、影响范围及原因。",
                source={"files": files, "summary": _short_text(normalized, 500)},
            )
        ]
    return []


def _analyze_large_table_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    large_tables = data.get("database", {}).get("large_tables", [])
    if not large_tables:
        return []
    return [
        _risk(
            level="关注",
            item="大表容量",
            detail=f"巡检中识别到 {len(large_tables)} 条大表记录，需关注容量增长趋势。",
            suggestion="建议结合业务增长趋势评估归档、分区或历史数据清理策略。",
            source={"count": len(large_tables), "field": "database.large_tables"},
        )
    ]


def _analyze_index_suggestion_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions = data.get("database", {}).get("index_suggestions", [])
    if not suggestions:
        return []
    return [
        _risk(
            level="关注",
            item="索引优化",
            detail=f"巡检中识别到 {len(suggestions)} 条索引优化建议。",
            suggestion="建议结合高频 SQL、慢 SQL 和业务访问路径评估是否新增或调整索引。",
            source={"count": len(suggestions), "field": "database.index_suggestions"},
        )
    ]


def _analyze_unused_index_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    unused_indexes = data.get("database", {}).get("unused_indexes", [])
    if not unused_indexes:
        return []
    return [
        _risk(
            level="关注",
            item="未使用索引",
            detail=f"巡检中识别到 {len(unused_indexes)} 条未使用索引记录。",
            suggestion="建议核查未使用索引是否长期无访问，确认后再考虑清理，避免误删业务依赖索引。",
            source={"count": len(unused_indexes), "field": "database.unused_indexes"},
        )
    ]


def _analyze_table_bloat_risks(data: dict[str, Any]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for record in data.get("database", {}).get("table_bloat", []):
        dead_rate = _to_number(record.get("dead_rate"))
        if dead_rate is None or dead_rate < 20:
            continue
        level = "风险" if dead_rate >= 50 else "关注"
        risks.append(
            _risk(
                level=level,
                item="表膨胀",
                detail=(
                    f"对象 {record.get('schemaname', '未采集')}.{record.get('relname', '未采集')} "
                    f"死元组占比为 {record.get('dead_rate', '未采集')}。"
                ),
                suggestion="建议结合维护窗口执行 VACUUM / ANALYZE 或表维护操作。",
                source=record,
            )
        )
    return risks


def _overall_status(risks: list[dict[str, Any]]) -> str:
    if any(risk.get("level") == "风险" for risk in risks):
        return "风险"
    if any(risk.get("level") == "关注" for risk in risks):
        return "关注"
    return "良好"


def _build_conclusion_summary(data: dict[str, Any]) -> list[str]:
    cluster = data.get("cluster", {})
    database = data.get("database", {})
    logs = data.get("logs", {})
    nodes = data.get("nodes", [])
    gs_check = cluster.get("gs_check_summary", {})

    disk_summary = cluster.get("resource_summary", {}).get("cluster_max_disk_use_percent", "未采集")
    node_count = cluster.get("resource_summary", {}).get("node_count", len(nodes))
    min_idle = cluster.get("resource_summary", {}).get("cluster_min_cpu_idle", "未采集")
    max_iowait = cluster.get("resource_summary", {}).get("cluster_max_iowait", "未采集")
    risks = data.get("risks", [])
    risk_levels = _risk_level_counts(risks)

    summary = [
        f"本次巡检综合评估结果为“{cluster.get('overall_status', '未采集')}”，数据库整体运行状态{_summary_phrase(cluster.get('overall_status', '未采集'))}。",
        f"本次巡检覆盖 {node_count} 个节点，数据库运行状态记录共 {len(database.get('running_status', {}).get('records', []))} 条，实例与集群运行信息已完成采集。",
        f"高可用同步状态记录共 {len(cluster.get('ha_status', []))} 条，复制槽状态记录共 {len(cluster.get('replication_slots', []))} 条，相关状态已纳入巡检评估。",
        f"磁盘空间方面，当前全集群最高磁盘使用率为 {disk_summary}%，CPU 最低空闲率为 {min_idle}%，最大 IO 等待为 {max_iowait}%。",
        f"内存与 CPU 资源信息已完成节点级采集，可用于后续容量与性能趋势分析。",
        f"日志检查方面，fatal 日志检查结果为：{_log_summary_phrase(logs.get('fatal_log_summary', '未采集'))}；panic 日志检查结果为：{_log_summary_phrase(logs.get('panic_log_summary', '未采集'))}。",
        f"gs_check 巡检结果中，OK 项 {gs_check.get('ok_count', 0)} 个，NG 项 {gs_check.get('ng_count', 0)} 个，NA 项 {gs_check.get('na_count', 0)} 个，UNKNOWN 项 {gs_check.get('unknown_count', 0)} 个。",
        f"系统管理维护检查中，大表记录 {len(database.get('large_tables', []))} 条，索引建议 {len(database.get('index_suggestions', []))} 条，未使用索引 {len(database.get('unused_indexes', []))} 条，表膨胀记录 {len(database.get('table_bloat', []))} 条。",
        f"本次巡检共识别 {len(risks)} 条风险/关注项，其中风险 {risk_levels.get('风险', 0)} 条、关注 {risk_levels.get('关注', 0)} 条，报告后续章节将按类型展示全部问题明细和整改建议。",
    ]
    return summary


def _build_conclusion_suggestions(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for level in ["风险", "关注"]:
        for risk in risks:
            if risk.get("level") != level:
                continue
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
    return list(grouped.values())


def _update_textual_summaries(data: dict[str, Any]) -> None:
    database = data.get("database", {})
    cluster = data.get("cluster", {})
    database.setdefault("running_status", {})
    database["running_status"]["summary"] = _rows_summary("数据库运行状态", database["running_status"].get("records", []))
    cluster["ha_summary"] = _rows_summary("高可用状态", cluster.get("ha_status", []))
    cluster["replication_slot_summary"] = _rows_summary("复制槽", cluster.get("replication_slots", []))
    database["large_tables_summary"] = _top_summary("大表", database.get("large_tables", []))
    database["index_suggestions_summary"] = _top_summary("索引建议", database.get("index_suggestions", []))
    database["unused_indexes_summary"] = (
        "未发现未使用索引" if not database.get("unused_indexes") else _top_summary("未使用索引", database.get("unused_indexes", []))
    )
    database["table_bloat_summary"] = _top_summary("表膨胀", database.get("table_bloat", []))


def _build_risk_summary(risks: list[dict[str, Any]]) -> dict[str, Any]:
    item_summary = _build_risk_summary_by_item(risks)
    source_summary = _build_risk_summary_by_source(risks)
    return {
        "total_count": len(risks),
        "risk_count": sum(1 for risk in risks if risk.get("level") == "风险"),
        "warning_count": sum(1 for risk in risks if risk.get("level") == "关注"),
        "by_item": item_summary,
        "by_source": source_summary,
    }


def _build_risk_details(risks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    sorted_risks = _sort_full_risks(risks)
    details = {"risks": [], "warnings": []}
    for risk in sorted_risks:
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


def _build_report_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _sort_full_risks(risks)


def _build_risk_summary_by_item(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for risk in risks:
        item = str(risk.get("item", "未采集"))
        entry = grouped.setdefault(item, {"item": item, "risk_count": 0, "warning_count": 0, "total_count": 0})
        entry["total_count"] += 1
        if risk.get("level") == "风险":
            entry["risk_count"] += 1
        elif risk.get("level") == "关注":
            entry["warning_count"] += 1
    return sorted(grouped.values(), key=lambda item: (-item["risk_count"], -item["warning_count"], item["item"]))


def _build_risk_summary_by_source(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for risk in risks:
        source = _source_group_label(risk)
        entry = grouped.setdefault(source, {"source": source, "risk_count": 0, "warning_count": 0, "total_count": 0})
        entry["total_count"] += 1
        if risk.get("level") == "风险":
            entry["risk_count"] += 1
        elif risk.get("level") == "关注":
            entry["warning_count"] += 1
    return sorted(grouped.values(), key=lambda item: (-item["risk_count"], -item["warning_count"], item["source"]))


def _sort_full_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        risks,
        key=lambda risk: (
            -_level_rank(str(risk.get("level", ""))),
            _report_priority(risk),
            str(risk.get("item", "")),
            str(risk.get("detail", "")),
        ),
    )


def _report_priority(risk: dict[str, Any]) -> int:
    item = str(risk.get("item", ""))
    if item == "gs_check 巡检项":
        return 0
    if "日志" in item:
        return 1
    if item in {"集群总体状态", "高可用同步", "复制槽状态", "复制槽延迟"}:
        return 2
    if item in {"磁盘空间", "CPU 使用率", "IO 等待", "内存使用率"}:
        return 3
    if item in {"大表容量", "索引优化", "未使用索引", "表膨胀"}:
        return 4
    return 5


def _source_text(source: Any) -> str:
    if isinstance(source, str):
        return source
    if isinstance(source, dict):
        parts: list[str] = []
        for key in ["check_name", "node", "mount", "client_addr", "slot_name", "field", "raw_detail_path"]:
            value = source.get(key)
            if value not in (None, "", "未采集"):
                parts.append(f"{key}={value}")
        return "; ".join(parts)
    return ""


def _source_group_label(risk: dict[str, Any]) -> str:
    item = str(risk.get("item", "未采集"))
    source = risk.get("source")
    if item == "gs_check 巡检项" and isinstance(source, dict):
        check_name = str(source.get("check_name", "")).strip()
        return f"gs_check:{check_name}" if check_name else "gs_check"
    if item in {"fatal 日志", "panic 日志"}:
        return "日志检查"
    if item in {"集群总体状态", "高可用同步", "复制槽状态", "复制槽延迟"}:
        return "数据库高可用"
    if item in {"磁盘空间", "CPU 使用率", "IO 等待", "内存使用率"}:
        return "系统资源"
    if item in {"大表容量", "索引优化", "未使用索引", "表膨胀"}:
        return "系统管理维护"
    return item


def _risk_level_counts(risks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "风险": sum(1 for risk in risks if risk.get("level") == "风险"),
        "关注": sum(1 for risk in risks if risk.get("level") == "关注"),
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
    hostname = str(node.get("hostname", "")).strip()
    if ip and ip != "未采集":
        return ip
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
    keywords = ["permission", "权限", "安全", "sysadmin", "guc", "目录权限"]
    return any(keyword.lower() in text for keyword in keywords)


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


def _summary_phrase(status: str) -> str:
    if status == "良好":
        return "整体平稳"
    if status == "关注":
        return "存在需持续关注的检查项"
    if status == "风险":
        return "存在需要优先处理的风险项"
    return "信息未完整采集"


def _log_summary_phrase(summary: Any) -> str:
    text = str(summary or "未采集").strip()
    if "未发现异常日志" in text:
        return "未发现异常日志"
    if text == "未发现日志文件":
        return "未采集到日志文件"
    if text == "未采集":
        return "未采集"
    return "发现需进一步核查的日志内容"


def _rows_summary(label: str, rows: list[dict[str, Any]]) -> str:
    return f"已解析{len(rows)}条{label}记录" if rows else f"未采集到{label}记录"


def _top_summary(label: str, rows: list[dict[str, Any]]) -> str:
    return f"已识别{len(rows)}条{label}记录" if rows else f"未采集到{label}记录"


def _short_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit]}..."
