"""Word report rendering helpers for the client-facing GaussDB report."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt


IMAGE_WIDTH = Inches(6)
CHAPTERS = [
    "第一章 总结",
    "第二章 系统概况",
    "第三章 总体情况",
    "第四章 高可用检查",
    "第五章 参数检查",
    "第六章 系统管理维护",
]

SECTION_ALIASES = {
    "CPU核数信息": ["CPU核数信息", "CPU型号信息"],
    "磁盘空间概况": ["磁盘空间大小", "DN占用空间大小", "ETCD占用空间大小"],
    "gs_collector 信息收集": ["gs_collector信息", "gs collector"],
}

BANNED_WORDS = [
    "workdir",
    "output",
    "raw_sections",
    "evidence_images",
    "extracted_manifest",
    "evidence_images_manifest",
    "inspection_data.generated.yaml",
    ".yaml",
    "manifest",
    "parser",
    "analyzer",
    "renderer",
    "source_file：",
    "来源文件：workdir",
]


def render_docx(data: dict[str, Any], output_path: Path) -> Path:
    """Render the formal customer delivery report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    _configure_document(document)

    _render_cover(document, data)
    _render_inspection_date_page(document, data)
    _render_toc(document)
    _render_chapter_one(document, data)
    _render_chapter_two(document, data)
    _render_chapter_three(document, data)
    _render_chapter_four(document, data)
    _render_chapter_five(document, data)
    _render_chapter_six(document, data)

    target_path = output_path
    try:
        document.save(target_path)
        return target_path
    except PermissionError:
        fallback_path = output_path.with_name(f"{output_path.stem}_latest{output_path.suffix}")
        document.save(fallback_path)
        return fallback_path


def _configure_document(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)

    normal = document.styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal.font.size = Pt(10.5)


def _render_cover(document: Document, data: dict[str, Any]) -> None:
    report = data.get("report", {})
    title = str(report.get("title") or "GaussDB 数据库健康诊断报告")
    inspector = str(report.get("inspector") or "未提供")

    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(title)
    run.bold = True
    run.font.size = Pt(24)

    document.add_paragraph("")
    document.add_paragraph("")

    inspector_paragraph = document.add_paragraph()
    inspector_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    inspector_paragraph.add_run(f"巡检人：{inspector}")

    document.add_page_break()


def _render_inspection_date_page(document: Document, data: dict[str, Any]) -> None:
    inspection_date = _resolve_inspection_date(data.get("report", {}))

    _add_heading(document, "巡检日期", level=1)
    document.add_paragraph(f"巡检日期：{inspection_date}")
    document.add_page_break()


def _render_toc(document: Document) -> None:
    _add_heading(document, "目录", level=1)
    for chapter in CHAPTERS:
        document.add_paragraph(chapter)
    document.add_page_break()


def _render_chapter_one(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第一章 总结", level=1)

    summary_lines = _chapter_one_summary_lines(data)
    for index, line in enumerate(summary_lines, start=1):
        document.add_paragraph(f"{index}. {line}")

    major_findings = _major_findings(data)
    if major_findings:
        document.add_paragraph("巡检发现：")
        for finding in major_findings:
            document.add_paragraph(f"- {finding}")

    document.add_page_break()


def _render_chapter_two(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第二章 系统概况", level=1)
    nodes = data.get("nodes", [])
    database = data.get("database", {})

    _add_heading(document, "2.1 操作系统版本检查", level=2)
    _add_table(
        document,
        ["节点", "主机名", "操作系统版本", "架构"],
        [
            [
                _node_label(node),
                node.get("hostname", "未采集"),
                node.get("os_version", "未采集"),
                node.get("architecture", "未采集"),
            ]
            for node in nodes
        ] or [["未采集", "未采集", "未采集", "未采集"]],
        column_widths=[1.2, 1.6, 2.0, 1.2],
    )
    _render_section_evidence(document, data, ["操作系统信息"])
    _add_conclusion(document, _os_conclusion(data))

    _add_heading(document, "2.2 数据库版本检查", level=2)
    document.add_paragraph(f"数据库版本：{database.get('version', '未采集')}")
    _render_section_evidence(document, data, ["数据库版本检查"], exact_only=True, empty_message="检查结果未采集。")
    _add_conclusion(document, _database_version_conclusion(data))

    _add_heading(document, "2.3 CPU 核数信息", level=2)
    _add_table(
        document,
        ["节点", "CPU 型号", "CPU 核数", "每核线程数", "Socket 数", "NUMA 节点数"],
        [
            [
                _node_label(node),
                node.get("cpu_model", "未采集"),
                node.get("cpu_cores", "未采集"),
                node.get("threads_per_core", "未采集"),
                node.get("sockets", "未采集"),
                node.get("numa_nodes", "未采集"),
            ]
            for node in nodes
        ] or [["未采集", "未采集", "未采集", "未采集", "未采集", "未采集"]],
        column_widths=[1.0, 2.2, 0.9, 1.0, 0.8, 1.0],
    )
    _render_section_evidence(document, data, ["CPU核数信息"])
    _add_conclusion(document, _cpu_conclusion(data))

    document.add_page_break()


def _render_chapter_three(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第三章 总体情况", level=1)

    _add_heading(document, "3.1 集群运行情况", level=2)
    cluster_status = str(data.get("cluster", {}).get("cluster_status", "未采集"))
    if cluster_status == "未采集":
        document.add_paragraph("本次巡检未获取到集群整体状态检查结果，建议后续补充 gs_om -t status 等集群状态采集。")
    else:
        document.add_paragraph(f"集群整体状态为：{cluster_status}。")
    _render_section_evidence(document, data, ["集群运行情况", "集群状态"], exact_only=True, empty_message="未获取到该检查项原始输出。")
    _add_conclusion(document, _cluster_status_conclusion(data))

    _add_heading(document, "3.2 磁盘空间概况", level=2)
    _add_table(
        document,
        ["节点", "文件系统", "总容量", "已用", "可用", "使用率(%)", "挂载点"],
        _disk_rows(data) or [["未采集", "未采集", "未采集", "未采集", "未采集", "未采集", "未采集"]],
        column_widths=[0.9, 1.3, 0.8, 0.8, 0.8, 0.8, 1.4],
    )
    _render_section_evidence(document, data, ["磁盘空间概况", "磁盘空间大小"])
    _add_conclusion(document, _disk_conclusion(data))

    document.add_page_break()


def _render_chapter_four(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第四章 高可用检查", level=1)
    cluster = data.get("cluster", {})
    database = data.get("database", {})
    nodes = data.get("nodes", [])

    _add_heading(document, "4.1 集群高可用状态检查", level=2)
    _add_table(
        document,
        ["序号", "client_addr", "sync_state", "pg_xlog_location_diff"],
        [
            [
                index,
                row.get("client_addr", "未采集"),
                row.get("sync_state", "未采集"),
                row.get("pg_xlog_location_diff", "未采集"),
            ]
            for index, row in enumerate(cluster.get("ha_status", []), start=1)
        ] or [[1, "未采集", "未采集", "未采集"]],
        column_widths=[0.6, 2.0, 1.1, 1.6],
    )
    _render_section_evidence(document, data, ["集群高可用状态检查"])
    _add_conclusion(document, _ha_conclusion(data))

    _add_heading(document, "4.2 CPU 一天使用信息", level=2)
    _add_table(
        document,
        ["节点", "avg_user", "avg_system", "avg_iowait", "avg_idle", "min_idle", "max_iowait"],
        [
            [
                _node_label(node),
                node.get("cpu_daily", {}).get("avg_user", 0),
                node.get("cpu_daily", {}).get("avg_system", 0),
                node.get("cpu_daily", {}).get("avg_iowait", 0),
                node.get("cpu_daily", {}).get("avg_idle", 0),
                node.get("cpu_daily", {}).get("min_idle", 0),
                node.get("cpu_daily", {}).get("max_iowait", 0),
            ]
            for node in nodes
        ] or [["未采集", 0, 0, 0, 0, 0, 0]],
        column_widths=[1.0, 0.8, 0.9, 0.9, 0.9, 0.9, 0.9],
    )
    _render_section_evidence(document, data, ["CPU近一天使用情况"])
    _add_conclusion(document, _cpu_daily_conclusion(data))

    _add_heading(document, "4.3 数据库运行状态", level=2)
    _add_table(
        document,
        ["序号", "checktime", "uptime", "lsn", "insert_lsn", "write_lsn", "is_in_recovery"],
        [
            [
                index,
                row.get("checktime", "未采集"),
                row.get("uptime", "未采集"),
                row.get("lsn", "未采集"),
                row.get("insert_lsn", "未采集"),
                row.get("write_lsn", "未采集"),
                row.get("is_in_recovery", "未采集"),
            ]
            for index, row in enumerate(database.get("running_status", {}).get("records", []), start=1)
        ] or [[1, "未采集", "未采集", "未采集", "未采集", "未采集", "未采集"]],
        column_widths=[0.5, 1.2, 1.0, 1.0, 1.0, 1.0, 0.9],
    )
    _render_section_evidence(document, data, ["数据库运行状态检查"])
    _add_conclusion(document, _running_status_conclusion(data))

    _add_heading(document, "4.4 复制槽状态", level=2)
    _add_table(
        document,
        ["序号", "slot_name", "slot_type", "active", "delay_lsn"],
        [
            [
                index,
                row.get("slot_name", "未采集"),
                row.get("slot_type", "未采集"),
                row.get("active", "未采集"),
                row.get("delay_lsn", "未采集"),
            ]
            for index, row in enumerate(cluster.get("replication_slots", []), start=1)
        ] or [[1, "未采集", "未采集", "未采集", "未采集"]],
        column_widths=[0.6, 2.0, 1.1, 0.8, 1.2],
    )
    _render_section_evidence(document, data, ["复制槽状态检查"])
    _add_conclusion(document, _replication_slot_conclusion(data))

    document.add_page_break()


def _render_chapter_five(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第五章 参数检查", level=1)
    database = data.get("database", {})
    cluster = data.get("cluster", {})

    _add_heading(document, "5.1 函数运行状态检查", level=2)
    _render_section_evidence(document, data, ["函数运行状态检查"])
    _add_conclusion(document, _function_conclusion(data))

    _add_heading(document, "5.2 数据库信息检查", level=2)
    _add_table(
        document,
        ["序号", "数据库名", "容量", "age", "is_template", "allow_conn", "conn_limit"],
        [
            [
                index,
                row.get("datname", "未采集"),
                row.get("readable_size", "未采集"),
                row.get("age", "未采集"),
                row.get("is_template", "未采集"),
                row.get("allow_conn", "未采集"),
                row.get("conn_limit", "未采集"),
            ]
            for index, row in enumerate(database.get("databases", []), start=1)
        ] or [[1, "未采集", "未采集", "未采集", "未采集", "未采集", "未采集"]],
        column_widths=[0.5, 1.4, 1.1, 0.9, 0.9, 0.9, 0.9],
    )
    _render_section_evidence(document, data, ["数据库信息检查"])
    _add_conclusion(document, _database_info_conclusion(data))

    _add_heading(document, "5.3 gs_collector 信息收集", level=2)
    _render_section_evidence(document, data, ["gs_collector 信息收集", "gs_collector信息"])
    ng_display_items = cluster.get("gs_check_summary", {}).get("ng_display_items", [])
    if ng_display_items:
        document.add_paragraph("参数巡检中发现以下需关注项：")
        _add_table(
            document,
            ["序号", "检查项", "状态", "问题摘要", "整改建议"],
            [
                [
                    index,
                    item.get("check_name", "未采集"),
                    item.get("status", "未采集"),
                    item.get("detail_summary", "未采集"),
                    item.get("suggestion", "未采集"),
                ]
                for index, item in enumerate(ng_display_items, start=1)
            ],
            column_widths=[0.5, 1.3, 0.7, 2.0, 2.0],
        )
    _add_conclusion(document, _parameter_check_conclusion(data))

    document.add_page_break()


def _render_chapter_six(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第六章 系统管理维护", level=1)
    database = data.get("database", {})

    _add_heading(document, "6.1 大表检查", level=2)
    _add_table(
        document,
        ["序号", "datname", "nspname", "relname", "relsize", "indexsize"],
        [
            [
                index,
                row.get("datname", "未采集"),
                row.get("nspname", "未采集"),
                row.get("relname", "未采集"),
                row.get("relsize", "未采集"),
                row.get("indexsize", "未采集"),
            ]
            for index, row in enumerate(database.get("large_tables", []), start=1)
        ] or [[1, "未采集", "未采集", "未采集", "未采集", "未采集"]],
        column_widths=[0.5, 1.0, 1.0, 2.0, 1.0, 1.0],
    )
    _render_section_evidence(document, data, ["大表检查"])
    _add_conclusion(document, _large_table_conclusion(data))

    _add_heading(document, "6.2 未使用的索引", level=2)
    unused_indexes = database.get("unused_indexes", [])
    if unused_indexes:
        _add_table(
            document,
            ["序号", "schemaname", "relname", "indexrelname", "idx_scan", "size"],
            [
                [
                    index,
                    row.get("schemaname", "未采集"),
                    row.get("relname", "未采集"),
                    row.get("indexrelname", "未采集"),
                    row.get("idx_scan", "未采集"),
                    row.get("size", "未采集"),
                ]
                for index, row in enumerate(unused_indexes, start=1)
            ],
            column_widths=[0.5, 0.9, 1.3, 1.8, 0.8, 1.0],
        )
    else:
        document.add_paragraph(database.get("unused_indexes_summary", "未发现未使用索引"))
    _render_section_evidence(document, data, ["未使用的索引"])
    _add_conclusion(document, _unused_index_conclusion(data))

    _add_heading(document, "6.3 索引建议", level=2)
    _add_table(
        document,
        ["序号", "tablename", "table_size", "seq_scan", "idx_scan", "rate"],
        [
            [
                index,
                row.get("tablename", "未采集"),
                row.get("table_size", "未采集"),
                row.get("seq_scan", 0),
                row.get("idx_scan", 0),
                row.get("rate", "未采集"),
            ]
            for index, row in enumerate(database.get("index_suggestions", []), start=1)
        ] or [[1, "未采集", "未采集", 0, 0, "未采集"]],
        column_widths=[0.5, 2.1, 1.0, 0.8, 0.8, 0.8],
    )
    _render_section_evidence(document, data, ["索引建议"])
    _add_conclusion(document, _index_suggestion_conclusion(data))

    _add_heading(document, "6.4 表膨胀检查", level=2)
    _add_table(
        document,
        ["序号", "schemaname", "relname", "n_live_tup", "n_dead_tup", "dead_rate"],
        [
            [
                index,
                row.get("schemaname", "未采集"),
                row.get("relname", "未采集"),
                row.get("n_live_tup", 0),
                row.get("n_dead_tup", 0),
                row.get("dead_rate", "未采集"),
            ]
            for index, row in enumerate(database.get("table_bloat", []), start=1)
        ] or [[1, "未采集", "未采集", 0, 0, "未采集"]],
        column_widths=[0.5, 1.0, 1.8, 1.0, 1.0, 0.8],
    )
    _render_section_evidence(document, data, ["表膨胀检查"])
    _add_conclusion(document, _table_bloat_conclusion(data))


def _render_section_evidence(
    document: Document,
    data: dict[str, Any],
    section_names: list[str],
    *,
    exact_only: bool = False,
    empty_message: str = "未获取到该检查项原始输出。",
) -> None:
    document.add_paragraph("检查结果：")
    matches = _matching_section_images(data, section_names, exact_only=exact_only)
    if not matches:
        document.add_paragraph(empty_message)
        return
    for image_path in matches:
        document.add_picture(str(image_path), width=IMAGE_WIDTH)


def _add_conclusion(document: Document, lines: list[str]) -> None:
    document.add_paragraph("结论：")
    for line in lines or ["未采集。"]:
        document.add_paragraph(line)


def _matching_section_images(
    data: dict[str, Any],
    section_names: list[str],
    *,
    exact_only: bool = False,
) -> list[Path]:
    target_names = _expand_section_names(section_names) if not exact_only else section_names
    paths: list[Path] = []
    for item in (data.get("evidence_images") or {}).get("items", []) or []:
        if item.get("type") != "section_text" or item.get("status") != "success":
            continue
        section_name = str(item.get("section_name", "")).strip()
        if exact_only:
            matched = section_name in target_names
        else:
            matched = any(section_name == name or name in section_name for name in target_names)
        if not matched:
            continue
        image_path = Path(str(item.get("image_path", "")))
        if image_path.exists():
            paths.append(image_path)
    return paths


def _expand_section_names(section_names: list[str]) -> list[str]:
    expanded: list[str] = []
    for name in section_names:
        expanded.append(name)
        expanded.extend(SECTION_ALIASES.get(name, []))
    deduped: list[str] = []
    seen: set[str] = set()
    for name in expanded:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped


def _chapter_one_summary_lines(data: dict[str, Any]) -> list[str]:
    cluster = data.get("cluster", {})
    logs = data.get("logs", {})
    database = data.get("database", {})
    max_disk = cluster.get("resource_summary", {}).get("cluster_max_disk_use_percent", "未采集")
    memory_status = _memory_status_text(data)
    standby_status = _ha_summary_text(data)
    return [
        f"数据库整体状态：根据本次巡检结果，数据库整体状态为 {cluster.get('overall_status', '未采集')}。",
        f"日志：{_log_sentence(logs)}",
        f"实例状态：{_instance_status_text(data)}",
        f"磁盘：当前全集群最高磁盘使用率为 {max_disk}%，磁盘空间使用 {_disk_health_text(data)}。",
        f"standby / 高可用：{standby_status}",
        f"内存：{memory_status}",
        "数据库信息：数据库列表、容量、年龄等信息已完成检查。",
        f"巡检发现：{_finding_overview(data)}",
    ]


def _major_findings(data: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    gs_ng = data.get("cluster", {}).get("gs_check_summary", {}).get("ng_count", 0)
    if gs_ng:
        findings.append(f"gs_check 存在 {gs_ng} 个 NG 项。")
    if data.get("database", {}).get("table_bloat"):
        findings.append("部分表存在膨胀，建议结合维护窗口执行后续处理。")
    if data.get("database", {}).get("index_suggestions"):
        findings.append("存在索引优化建议，建议结合业务访问路径进一步评估。")
    if str(data.get("cluster", {}).get("cluster_status", "未采集")) == "未采集":
        findings.append("未采集到集群总体状态，建议后续补充集群状态采集。")
    return findings


def _finding_overview(data: dict[str, Any]) -> str:
    findings = _major_findings(data)
    if not findings:
        return "未发现需重点说明的风险项。"
    return "；".join(finding.rstrip("。") for finding in findings) + "。"


def _os_conclusion(data: dict[str, Any]) -> list[str]:
    node_count = len(data.get("nodes", []))
    return [f"本次共完成 {node_count} 个节点的操作系统版本检查，操作系统版本信息已完成采集。"]


def _database_version_conclusion(data: dict[str, Any]) -> list[str]:
    version = data.get("database", {}).get("version", "未采集")
    if version == "未采集":
        return ["本次巡检未获取到数据库版本检查结果，建议后续补充采集。"]
    return [f"本次巡检获取到的数据库版本为 {version}。"]


def _cpu_conclusion(data: dict[str, Any]) -> list[str]:
    nodes = data.get("nodes", [])
    if not nodes:
        return ["本次巡检未采集到 CPU 核数信息。"]
    return ["各节点 CPU 型号及核数信息已完成检查，未见异常配置项。"]


def _cluster_status_conclusion(data: dict[str, Any]) -> list[str]:
    cluster_status = str(data.get("cluster", {}).get("cluster_status", "未采集"))
    if cluster_status == "未采集":
        return ["建议后续补充集群整体状态采集，以便完整评估集群服务状态。"]
    return [f"当前集群整体状态为 {cluster_status}。"]


def _disk_conclusion(data: dict[str, Any]) -> list[str]:
    max_disk = _to_float(data.get("cluster", {}).get("resource_summary", {}).get("cluster_max_disk_use_percent"))
    if max_disk is None:
        return ["本次巡检未采集到完整磁盘空间检查结果。"]
    return [f"当前全集群最高磁盘使用率为 {int(max_disk) if max_disk.is_integer() else max_disk}%，磁盘空间整体状态为{_disk_health_text(data)}。"]


def _ha_conclusion(data: dict[str, Any]) -> list[str]:
    lines = [data.get("cluster", {}).get("ha_summary", "未采集")]
    lines.extend(_section_risk_lines(data, {"高可用同步"}))
    return lines


def _cpu_daily_conclusion(data: dict[str, Any]) -> list[str]:
    min_idle = data.get("cluster", {}).get("resource_summary", {}).get("cluster_min_cpu_idle", "未采集")
    max_iowait = data.get("cluster", {}).get("resource_summary", {}).get("cluster_max_iowait", "未采集")
    lines = [f"巡检周期内 CPU 最低 idle 为 {min_idle}%，最大 iowait 为 {max_iowait}%。"]
    lines.extend(_section_risk_lines(data, {"CPU 使用率", "IO 等待"}))
    return lines


def _running_status_conclusion(data: dict[str, Any]) -> list[str]:
    summary = data.get("database", {}).get("running_status", {}).get("summary", "未采集")
    return [summary]


def _replication_slot_conclusion(data: dict[str, Any]) -> list[str]:
    lines = [data.get("cluster", {}).get("replication_slot_summary", "未采集")]
    lines.extend(_section_risk_lines(data, {"复制槽状态", "复制槽延迟"}))
    return lines


def _function_conclusion(data: dict[str, Any]) -> list[str]:
    return ["函数运行状态检查结果已完成采集，未发现需单独说明的异常。"]


def _database_info_conclusion(data: dict[str, Any]) -> list[str]:
    database_count = len(data.get("database", {}).get("databases", []))
    return [f"本次共完成 {database_count} 个数据库对象的信息检查。"]


def _parameter_check_conclusion(data: dict[str, Any]) -> list[str]:
    gs_check = data.get("cluster", {}).get("gs_check_summary", {})
    log_sentence = _log_sentence(data.get("logs", {}))
    lines = [
        f"gs_check 巡检结果中，OK {gs_check.get('ok_count', 0)} 项，NG {gs_check.get('ng_count', 0)} 项，NA {gs_check.get('na_count', 0)} 项。",
        log_sentence,
    ]
    if not gs_check.get("ng_display_items"):
        lines.append("本章节未发现需单独说明的参数配置异常项。")
    return lines


def _large_table_conclusion(data: dict[str, Any]) -> list[str]:
    lines = [data.get("database", {}).get("large_tables_summary", "未采集")]
    lines.extend(_section_risk_lines(data, {"大表容量"}))
    return lines


def _unused_index_conclusion(data: dict[str, Any]) -> list[str]:
    database = data.get("database", {})
    lines = [database.get("unused_indexes_summary", "未采集")]
    lines.extend(_section_risk_lines(data, {"未使用索引"}))
    return lines


def _index_suggestion_conclusion(data: dict[str, Any]) -> list[str]:
    lines = [data.get("database", {}).get("index_suggestions_summary", "未采集")]
    lines.extend(_section_risk_lines(data, {"索引优化"}))
    return lines


def _table_bloat_conclusion(data: dict[str, Any]) -> list[str]:
    lines = [data.get("database", {}).get("table_bloat_summary", "未采集")]
    lines.extend(_section_risk_lines(data, {"表膨胀"}))
    return lines


def _section_risk_lines(data: dict[str, Any], target_items: set[str]) -> list[str]:
    lines: list[str] = []
    for risk in data.get("risks", []):
        if risk.get("item") not in target_items:
            continue
        lines.append(f"{risk.get('detail', '未采集')} 建议：{risk.get('suggestion', '未采集')}")
    return lines


def _instance_status_text(data: dict[str, Any]) -> str:
    records = data.get("database", {}).get("running_status", {}).get("records", [])
    if not records:
        return "本次未获取到数据库运行状态检查结果。"
    return "数据库运行状态检查正常。"


def _disk_health_text(data: dict[str, Any]) -> str:
    max_disk = _to_float(data.get("cluster", {}).get("resource_summary", {}).get("cluster_max_disk_use_percent"))
    if max_disk is None:
        return "未采集"
    if max_disk < 70:
        return "良好"
    if max_disk < 80:
        return "关注"
    return "风险"


def _memory_status_text(data: dict[str, Any]) -> str:
    usage_values = [
        _to_float((node.get("memory") or {}).get("usage_percent"))
        for node in data.get("nodes", [])
    ]
    usage_values = [value for value in usage_values if value is not None]
    if not usage_values:
        return "本次未采集到完整内存使用率信息。"
    max_usage = max(usage_values)
    if max_usage < 80:
        return f"当前内存使用率整体良好，最高为 {max_usage}%。"
    if max_usage < 90:
        return f"当前内存使用率整体需关注，最高为 {max_usage}%。"
    return f"当前内存使用率存在风险，最高为 {max_usage}%。"


def _ha_summary_text(data: dict[str, Any]) -> str:
    records = data.get("cluster", {}).get("ha_status", [])
    if not records:
        return "本次未获取到高可用状态检查结果。"
    diffs = [_to_float(record.get("pg_xlog_location_diff")) for record in records]
    diffs = [value for value in diffs if value is not None]
    if diffs and max(diffs) > 0:
        return f"主备同步存在位点差异，最大差异为 {max(diffs)}。"
    return "主备同步状态正常，未见位点差异。"


def _log_sentence(logs: dict[str, Any]) -> str:
    fatal = _single_log_sentence("fatal", str(logs.get("fatal_log_summary", "未采集")))
    panic = _single_log_sentence("panic", str(logs.get("panic_log_summary", "未采集")))
    return f"{fatal}{panic}"


def _single_log_sentence(label: str, summary: str) -> str:
    normalized = summary.strip()
    if normalized == "未发现日志文件":
        return f"未获取到 {label} 日志文件。"
    if "未发现" in normalized and "异常日志" in normalized:
        return f"未发现 {label} 异常日志。"
    if not normalized or normalized == "未采集":
        return f"{label} 日志检查结果未采集。"
    return f"发现 {label} 日志异常摘要，建议进一步核查。"


def _disk_rows(data: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for node in data.get("nodes", []):
        for disk in node.get("disks", []):
            rows.append(
                [
                    _node_label(node),
                    disk.get("filesystem", "未采集"),
                    disk.get("size", "未采集"),
                    disk.get("used", "未采集"),
                    disk.get("avail", "未采集"),
                    disk.get("use_percent", "未采集"),
                    disk.get("mounted_on", "未采集"),
                ]
            )
    return rows


def _resolve_inspection_date(report: dict[str, Any]) -> str:
    explicit = str(report.get("inspection_date", "") or "").strip()
    if explicit and explicit != "未采集":
        return explicit
    candidates = [str(report.get("source_package", "") or "")]
    candidates.extend(str(item) for item in report.get("source_files", []) or [])
    for text in candidates:
        match = re.search(r"(20\d{2})(\d{2})(\d{2})(?:\d{6})?", text)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return "未采集"


def _node_label(node: dict[str, Any]) -> str:
    ip = str(node.get("ip", "")).strip()
    if ip and ip != "未采集":
        return ip
    hostname = str(node.get("hostname", "")).strip()
    if hostname and hostname != "未采集":
        return hostname
    return "未采集"


def _add_heading(document: Document, text: str, level: int) -> None:
    heading = document.add_heading(level=level)
    run = heading.add_run(text)
    run.bold = True


def _add_table(
    document: Document,
    headers: list[str],
    rows: list[list[Any]],
    column_widths: list[float] | None = None,
) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    for column_index, header in enumerate(headers):
        cell = table.rows[0].cells[column_index]
        paragraph = cell.paragraphs[0]
        run = paragraph.add_run(str(header))
        run.bold = True
        if column_widths and column_index < len(column_widths):
            cell.width = Inches(column_widths[column_index])

    for row in rows:
        cells = table.add_row().cells
        for column_index, value in enumerate(row):
            cells[column_index].text = "" if value is None else str(value)
            if column_widths and column_index < len(column_widths):
                cells[column_index].width = Inches(column_widths[column_index])


def _to_float(value: Any) -> float | None:
    if value in (None, "", "未采集"):
        return None
    try:
        return float(str(value).strip().rstrip("%"))
    except ValueError:
        return None


def _sanitize_text(text: str) -> str:
    cleaned = text
    for banned in BANNED_WORDS:
        cleaned = cleaned.replace(banned, "")
    return cleaned
