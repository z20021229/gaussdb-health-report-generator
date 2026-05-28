"""Word report rendering helpers for the GaussDB inspection report."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt


CHAPTER_TITLES = [
    "第一章 总结",
    "第二章 系统概况",
    "第三章 总体情况",
    "第四章 高可用检查",
    "第五章 参数检查",
    "第六章 系统管理维护",
    "附录 原始依据与截图",
]

DEFAULT_IMAGE_WIDTH = Inches(6)


def render_docx(data: dict[str, Any], output_path: Path) -> Path:
    """Render a client-facing Word report with tables and evidence images."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    _configure_document(document)

    _render_cover(document, data)
    _render_toc(document)
    _render_summary(document, data)
    _render_system_overview(document, data)
    _render_overall_status(document, data)
    _render_ha_checks(document, data)
    _render_parameter_checks(document, data)
    _render_maintenance_checks(document, data)
    _render_appendix(document, data)

    document.save(output_path)
    return output_path


def _configure_document(document: Document) -> None:
    section = document.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(0.9)
    section.right_margin = Inches(0.9)

    normal_style = document.styles["Normal"]
    normal_style.font.name = "Microsoft YaHei"
    normal_style.font.size = Pt(10.5)


def _render_cover(document: Document, data: dict[str, Any]) -> None:
    report = data.get("report", {})

    title = str(report.get("title") or "GaussDB 数据库健康诊断报告")
    customer_name = str(report.get("customer_name") or "未提供")
    inspector = str(report.get("inspector") or "未提供")
    inspection_date = str(report.get("inspection_date") or "未采集")
    generated_date = _display_date(report.get("generated_at"))

    title_para = document.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title)
    title_run.bold = True
    title_run.font.size = Pt(24)

    document.add_paragraph("")
    for label, value in [
        ("客户名称", customer_name),
        ("巡检人", inspector),
        ("巡检日期", inspection_date),
        ("生成日期", generated_date),
    ]:
        para = document.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.add_run(f"{label}：{value}")

    document.add_page_break()


def _render_toc(document: Document) -> None:
    _add_heading(document, "目录", level=1)
    for title in CHAPTER_TITLES:
        document.add_paragraph(title)
    document.add_page_break()


def _render_summary(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第一章 总结", level=1)

    _add_heading(document, "1.1 总体结论", level=2)
    cluster = data.get("cluster", {})
    document.add_paragraph(f"总体状态：{cluster.get('overall_status', '未采集')}")
    for summary_line in data.get("conclusion", {}).get("summary", []) or ["未采集"]:
        document.add_paragraph(str(summary_line))

    risk_summary = data.get("risk_summary", {})
    _add_heading(document, "1.2 问题统计汇总", level=2)
    _add_key_value_table(
        document,
        [
            ("问题总数", risk_summary.get("total_count", 0)),
            ("风险级数量", risk_summary.get("risk_count", 0)),
            ("关注级数量", risk_summary.get("warning_count", 0)),
        ],
    )

    _add_heading(document, "1.3 按检查项汇总", level=2)
    by_item_rows = [
        [
            item.get("item", "未采集"),
            item.get("risk_count", 0),
            item.get("warning_count", 0),
            item.get("total_count", 0),
        ]
        for item in risk_summary.get("by_item", [])
    ]
    _add_table(
        document,
        ["检查项", "风险数量", "关注数量", "合计"],
        by_item_rows or [["未采集", 0, 0, 0]],
    )

    _add_heading(document, "1.4 风险级问题明细", level=2)
    _add_risk_table(document, data.get("risk_details", {}).get("risks", []))

    _add_heading(document, "1.5 关注级问题明细", level=2)
    _add_risk_table(document, data.get("risk_details", {}).get("warnings", []))

    _add_heading(document, "1.6 整改建议汇总", level=2)
    suggestion_rows = [
        [
            index,
            item.get("level", "未采集"),
            item.get("item", "未采集"),
            item.get("suggestion", "未采集"),
            item.get("related_count", 0),
        ]
        for index, item in enumerate(data.get("conclusion", {}).get("suggestions", []), start=1)
    ]
    _add_table(
        document,
        ["序号", "风险级别", "检查项", "整改建议", "关联问题数量"],
        suggestion_rows or [[1, "未采集", "未采集", "未采集", 0]],
    )
    document.add_page_break()


def _render_system_overview(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第二章 系统概况", level=1)
    nodes = data.get("nodes", [])
    database = data.get("database", {})

    _add_heading(document, "2.1 操作系统版本检查", level=2)
    os_rows = [
        [
            _node_label(node),
            node.get("hostname", "未采集"),
            node.get("os_version", "未采集"),
            node.get("architecture", "未采集"),
            node.get("os_summary", "未采集"),
        ]
        for node in nodes
    ]
    _add_table(
        document,
        ["节点", "主机名", "操作系统版本", "架构", "操作系统信息摘要"],
        os_rows or [["未采集", "未采集", "未采集", "未采集", "未采集"]],
    )
    _insert_section_images(document, data, ["操作系统信息"])

    _add_heading(document, "2.2 数据库版本检查", level=2)
    document.add_paragraph(f"数据库版本：{database.get('version', '未采集')}")
    _insert_section_images(document, data, ["数据库版本检查", "数据库信息检查"])

    _add_heading(document, "2.3 CPU 核数信息", level=2)
    cpu_rows = [
        [
            _node_label(node),
            node.get("cpu_model", "未采集"),
            node.get("cpu_cores", "未采集"),
            node.get("threads_per_core", "未采集"),
            node.get("cores_per_socket", "未采集"),
            node.get("sockets", "未采集"),
            node.get("numa_nodes", "未采集"),
        ]
        for node in nodes
    ]
    _add_table(
        document,
        ["节点", "CPU 型号", "CPU 核数", "每核线程数", "每 Socket 核数", "Socket 数", "NUMA 节点数"],
        cpu_rows or [["未采集", "未采集", "未采集", "未采集", "未采集", "未采集", "未采集"]],
    )
    _insert_section_images(document, data, ["CPU核数信息"])

    _add_heading(document, "2.4 内存信息", level=2)
    memory_rows = [
        [
            _node_label(node),
            node.get("memory", {}).get("total_mb", 0),
            node.get("memory", {}).get("used_mb", 0),
            node.get("memory", {}).get("free_mb", 0),
            node.get("memory", {}).get("available_mb", 0),
            node.get("memory", {}).get("usage_percent", 0),
        ]
        for node in nodes
    ]
    _add_table(
        document,
        ["节点", "总内存(MB)", "已用(MB)", "空闲(MB)", "可用(MB)", "使用率(%)"],
        memory_rows or [["未采集", 0, 0, 0, 0, 0]],
    )
    _insert_section_images(document, data, ["内存大小信息"])
    document.add_page_break()


def _render_overall_status(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第三章 总体情况", level=1)
    cluster = data.get("cluster", {})
    nodes = data.get("nodes", [])

    _add_heading(document, "3.1 巡检项总体结果", level=2)
    _add_table(
        document,
        ["巡检项", "巡检结果", "情况描述"],
        _overall_status_rows(data),
    )

    _add_heading(document, "3.2 集群运行情况", level=2)
    cluster_status = cluster.get("cluster_status", "未采集")
    document.add_paragraph(f"集群运行状态：{cluster_status}")
    _insert_section_images(document, data, ["集群状态", "集群运行"])

    _add_heading(document, "3.3 磁盘空间概况", level=2)
    disk_rows: list[list[Any]] = []
    for node in nodes:
        for disk in node.get("disks", []):
            disk_rows.append(
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
    _add_table(
        document,
        ["节点", "文件系统", "总容量", "已用", "可用", "使用率(%)", "挂载点"],
        disk_rows or [["未采集", "未采集", "未采集", "未采集", "未采集", "未采集", "未采集"]],
    )
    _insert_section_images(document, data, ["磁盘空间大小"])
    document.add_page_break()


def _render_ha_checks(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第四章 高可用检查", level=1)
    cluster = data.get("cluster", {})
    database = data.get("database", {})
    nodes = data.get("nodes", [])

    _add_heading(document, "4.1 集群高可用状态检查", level=2)
    ha_rows = [
        [
            index,
            row.get("client_addr", "未采集"),
            row.get("sync_state", "未采集"),
            row.get("pg_xlog_location_diff", "未采集"),
        ]
        for index, row in enumerate(cluster.get("ha_status", []), start=1)
    ]
    _add_table(
        document,
        ["序号", "client_addr", "sync_state", "pg_xlog_location_diff"],
        ha_rows or [[1, "未采集", "未采集", "未采集"]],
    )
    _insert_section_images(document, data, ["集群高可用状态检查"])

    _add_heading(document, "4.2 CPU 一天使用信息", level=2)
    cpu_daily_rows = [
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
    ]
    _add_table(
        document,
        ["节点", "avg_user", "avg_system", "avg_iowait", "avg_idle", "min_idle", "max_iowait"],
        cpu_daily_rows or [["未采集", 0, 0, 0, 0, 0, 0]],
    )
    _insert_section_images(document, data, ["CPU近一天使用情况"])

    _add_heading(document, "4.3 数据库运行状态", level=2)
    running_rows = [
        [
            index,
            row.get("checktime", "未采集"),
            row.get("uptime", "未采集"),
            row.get("lsn", "未采集"),
            row.get("insert_lsn", "未采集"),
            row.get("write_lsn", "未采集"),
            row.get("conf_reload_time", "未采集"),
            row.get("is_in_recovery", "未采集"),
            row.get("role_hint", "未采集"),
        ]
        for index, row in enumerate(database.get("running_status", {}).get("records", []), start=1)
    ]
    _add_table(
        document,
        [
            "序号",
            "checktime",
            "uptime",
            "lsn",
            "insert_lsn",
            "write_lsn",
            "conf_reload_time",
            "is_in_recovery",
            "role_hint",
        ],
        running_rows or [[1, "未采集", "未采集", "未采集", "未采集", "未采集", "未采集", "未采集", "未采集"]],
    )
    _insert_section_images(document, data, ["数据库运行状态检查"])

    _add_heading(document, "4.4 复制槽状态", level=2)
    slot_rows = [
        [
            index,
            row.get("slot_name", "未采集"),
            row.get("slot_type", "未采集"),
            row.get("active", "未采集"),
            row.get("delay_lsn", "未采集"),
        ]
        for index, row in enumerate(cluster.get("replication_slots", []), start=1)
    ]
    _add_table(
        document,
        ["序号", "slot_name", "slot_type", "active", "delay_lsn"],
        slot_rows or [[1, "未采集", "未采集", "未采集", "未采集"]],
    )
    _insert_section_images(document, data, ["复制槽状态检查"])
    document.add_page_break()


def _render_parameter_checks(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第五章 参数检查", level=1)
    cluster = data.get("cluster", {})
    database = data.get("database", {})
    logs = data.get("logs", {})

    _add_heading(document, "5.1 函数运行状态检查", level=2)
    document.add_paragraph("函数运行状态检查结果如下：")
    _insert_section_images(document, data, ["函数运行状态检查"])

    _add_heading(document, "5.2 gs_check 巡检信息", level=2)
    gs_check = cluster.get("gs_check_summary", {})
    _add_key_value_table(
        document,
        [
            ("OK 数量", gs_check.get("ok_count", 0)),
            ("NG 数量", gs_check.get("ng_count", 0)),
            ("NA 数量", gs_check.get("na_count", 0)),
            ("UNKNOWN 数量", gs_check.get("unknown_count", 0)),
        ],
    )
    ng_rows = [
        [
            index,
            item.get("check_name", "未采集"),
            item.get("status", "未采集"),
            item.get("detail_summary", "未采集"),
            item.get("raw_detail_path", ""),
        ]
        for index, item in enumerate(gs_check.get("ng_items", []), start=1)
    ]
    _add_table(
        document,
        ["序号", "检查项", "状态", "问题摘要", "原始依据路径"],
        ng_rows or [[1, "未采集", "未采集", "未采集", ""]],
    )
    _insert_section_images(document, data, ["gs_check巡检信息"])

    _add_heading(document, "5.3 数据库信息检查", level=2)
    database_rows = [
        [
            index,
            item.get("datname", "未采集"),
            item.get("size_bytes", 0),
            item.get("readable_size", "未采集"),
            item.get("age", "未采集"),
            item.get("is_template", "未采集"),
            item.get("allow_conn", "未采集"),
            item.get("conn_limit", "未采集"),
        ]
        for index, item in enumerate(database.get("databases", []), start=1)
    ]
    _add_table(
        document,
        ["序号", "数据库名", "容量(bytes)", "可读容量", "age", "is_template", "allow_conn", "conn_limit"],
        database_rows or [[1, "未采集", 0, "未采集", "未采集", "未采集", "未采集", "未采集"]],
    )
    _insert_section_images(document, data, ["数据库信息检查"])

    _add_heading(document, "5.4 日志检查", level=2)
    document.add_paragraph(f"fatal 日志摘要：{logs.get('fatal_log_summary', '未采集')}")
    document.add_paragraph(f"panic 日志摘要：{logs.get('panic_log_summary', '未采集')}")
    document.add_paragraph(
        f"fatal 日志文件：{', '.join(logs.get('fatal_log_files', [])) or '未采集'}"
    )
    document.add_paragraph(
        f"panic 日志文件：{', '.join(logs.get('panic_log_files', [])) or '未采集'}"
    )
    document.add_page_break()


def _render_maintenance_checks(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "第六章 系统管理维护", level=1)
    database = data.get("database", {})

    _add_heading(document, "6.1 大表检查", level=2)
    large_table_rows = [
        [
            index,
            item.get("datname", "未采集"),
            item.get("nspname", "未采集"),
            item.get("relname", "未采集"),
            item.get("bytes", 0),
            item.get("relsize", "未采集"),
            item.get("indexsize", "未采集"),
        ]
        for index, item in enumerate(database.get("large_tables", []), start=1)
    ]
    _add_table(
        document,
        ["序号", "datname", "nspname", "relname", "bytes", "relsize", "indexsize"],
        large_table_rows or [[1, "未采集", "未采集", "未采集", 0, "未采集", "未采集"]],
    )
    _insert_section_images(document, data, ["大表检查"])

    _add_heading(document, "6.2 未使用的索引", level=2)
    unused_indexes = database.get("unused_indexes", [])
    if unused_indexes:
        unused_rows = [
            [
                index,
                item.get("schemaname", "未采集"),
                item.get("relname", "未采集"),
                item.get("indexrelname", "未采集"),
                item.get("idx_scan", "未采集"),
                item.get("size", "未采集"),
            ]
            for index, item in enumerate(unused_indexes, start=1)
        ]
        _add_table(
            document,
            ["序号", "schemaname", "relname", "indexrelname", "idx_scan", "size"],
            unused_rows,
        )
    else:
        document.add_paragraph(database.get("unused_indexes_summary", "未采集"))
    _insert_section_images(document, data, ["未使用的索引"])

    _add_heading(document, "6.3 索引建议", level=2)
    suggestion_rows = [
        [
            index,
            item.get("tablename", "未采集"),
            item.get("table_size", "未采集"),
            item.get("seq_scan", 0),
            item.get("idx_scan", 0),
            item.get("rate", "未采集"),
        ]
        for index, item in enumerate(database.get("index_suggestions", []), start=1)
    ]
    _add_table(
        document,
        ["序号", "tablename", "table_size", "seq_scan", "idx_scan", "rate"],
        suggestion_rows or [[1, "未采集", "未采集", 0, 0, "未采集"]],
    )
    _insert_section_images(document, data, ["索引建议"])

    _add_heading(document, "6.4 表膨胀检查", level=2)
    bloat_rows = [
        [
            index,
            item.get("schemaname", "未采集"),
            item.get("relname", "未采集"),
            item.get("n_live_tup", 0),
            item.get("n_dead_tup", 0),
            item.get("dead_rate", "未采集"),
        ]
        for index, item in enumerate(database.get("table_bloat", []), start=1)
    ]
    _add_table(
        document,
        ["序号", "schemaname", "relname", "n_live_tup", "n_dead_tup", "dead_rate"],
        bloat_rows or [[1, "未采集", "未采集", 0, 0, "未采集"]],
    )
    _insert_section_images(document, data, ["表膨胀检查"])
    document.add_page_break()


def _render_appendix(document: Document, data: dict[str, Any]) -> None:
    _add_heading(document, "附录 原始依据与截图", level=1)
    report = data.get("report", {})
    evidence = data.get("evidence_images", {})

    raw_sections_dir = ""
    for item in cluster_ng_items(data):
        raw_path = str(item.get("raw_detail_path", "")).strip()
        if raw_path:
            raw_sections_dir = str(Path(raw_path).parent)
            break

    document.add_paragraph(f"source_package：{report.get('source_package', '未采集')}")
    document.add_paragraph(
        f"source_files：{', '.join(report.get('source_files', [])) or '未采集'}"
    )
    document.add_paragraph(
        f"extracted_manifest 路径：{report.get('extracted_manifest_path', '未采集')}"
    )
    document.add_paragraph(
        f"evidence_images_manifest 路径：{evidence.get('manifest_path', '未采集')}"
    )
    document.add_paragraph(f"raw_sections 路径：{raw_sections_dir or '未采集'}")

    _add_heading(document, "HTML/WDR 截图状态", level=2)
    html_items = [
        item for item in evidence.get("items", []) if item.get("type") == "html_screenshot"
    ]
    html_rows = [
        [
            index,
            item.get("source_file", "未采集"),
            item.get("type", "未采集"),
            item.get("status", "未采集"),
            item.get("error", ""),
        ]
        for index, item in enumerate(html_items, start=1)
    ]
    _add_table(
        document,
        ["序号", "来源文件", "类型", "状态", "错误信息"],
        html_rows or [[1, "未采集", "html_screenshot", "未采集", "未找到 HTML/WDR 截图记录"]],
    )

    _add_heading(document, "截图失败项", level=2)
    failed_items = [item for item in evidence.get("items", []) if item.get("status") != "success"]
    failed_rows = [
        [
            index,
            item.get("source_file", "未采集"),
            item.get("type", "未采集"),
            item.get("status", "未采集"),
            item.get("error", ""),
        ]
        for index, item in enumerate(failed_items, start=1)
    ]
    _add_table(
        document,
        ["序号", "来源文件", "类型", "状态", "错误信息"],
        failed_rows or [[1, "未采集", "未采集", "success", "无失败项"]],
    )


def _add_heading(document: Document, text: str, level: int) -> None:
    heading = document.add_heading(level=level)
    run = heading.add_run(text)
    run.bold = True


def _add_table(document: Document, headers: list[str], rows: list[list[Any]]) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        para = cell.paragraphs[0]
        run = para.add_run(str(header))
        run.bold = True

    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = "" if value is None else str(value)


def _add_key_value_table(document: Document, rows: list[tuple[str, Any]]) -> None:
    _add_table(document, ["项目", "内容"], [[key, value] for key, value in rows])


def _add_risk_table(document: Document, risks: list[dict[str, Any]]) -> None:
    rows = [
        [
            index,
            risk.get("item", "未采集"),
            risk.get("detail", "未采集"),
            risk.get("suggestion", "未采集"),
            risk.get("source", "未采集"),
        ]
        for index, risk in enumerate(risks, start=1)
    ]
    _add_table(
        document,
        ["序号", "检查项", "问题描述", "整改建议", "来源依据"],
        rows or [[1, "未采集", "未采集", "未采集", "未采集"]],
    )


def _insert_section_images(document: Document, data: dict[str, Any], section_names: list[str]) -> None:
    matches = _matching_section_images(data, section_names)
    if not matches:
        document.add_paragraph("未找到该检查项原始截图")
        return

    for item in matches:
        document.add_paragraph("检查结果：")
        image_path = Path(str(item.get("image_path", "")))
        if image_path.exists():
            document.add_picture(str(image_path), width=DEFAULT_IMAGE_WIDTH)
            document.add_paragraph(f"来源文件：{item.get('source_file', '未采集')}")
        else:
            document.add_paragraph(f"截图文件不存在：{item.get('image_path', '未采集')}")


def _matching_section_images(data: dict[str, Any], section_names: list[str]) -> list[dict[str, Any]]:
    evidence_items = (data.get("evidence_images") or {}).get("items") or []
    matches: list[dict[str, Any]] = []
    for item in evidence_items:
        if item.get("status") != "success":
            continue
        if item.get("type") != "section_text":
            continue
        section_name = str(item.get("section_name", ""))
        if any(name and (section_name == name or name in section_name) for name in section_names):
            matches.append(item)
    return matches


def _overall_status_rows(data: dict[str, Any]) -> list[list[Any]]:
    cluster = data.get("cluster", {})
    nodes = data.get("nodes", [])
    database = data.get("database", {})
    gs_check = cluster.get("gs_check_summary", {})

    return [
        [
            "系统资源",
            "已检查",
            f"节点数量 {cluster.get('resource_summary', {}).get('node_count', len(nodes))}",
        ],
        [
            "磁盘空间",
            cluster.get("overall_status", "未采集"),
            f"全集群最高磁盘使用率 {cluster.get('resource_summary', {}).get('cluster_max_disk_use_percent', '未采集')}%",
        ],
        [
            "CPU 使用",
            "已检查",
            f"CPU 最低 idle {cluster.get('resource_summary', {}).get('cluster_min_cpu_idle', '未采集')}%",
        ],
        [
            "内存使用",
            "已检查",
            f"已采集 {len(nodes)} 个节点的内存信息",
        ],
        [
            "数据库运行状态",
            "已检查",
            database.get("running_status", {}).get("summary", "未采集"),
        ],
        [
            "高可用状态",
            "已检查",
            cluster.get("ha_summary", "未采集"),
        ],
        [
            "复制槽状态",
            "已检查",
            cluster.get("replication_slot_summary", "未采集"),
        ],
        [
            "gs_check",
            "已检查",
            f"OK {gs_check.get('ok_count', 0)} / NG {gs_check.get('ng_count', 0)} / NA {gs_check.get('na_count', 0)} / UNKNOWN {gs_check.get('unknown_count', 0)}",
        ],
        [
            "系统管理维护",
            "已检查",
            f"大表 {len(database.get('large_tables', []))}，索引建议 {len(database.get('index_suggestions', []))}，表膨胀 {len(database.get('table_bloat', []))}",
        ],
    ]


def _display_date(value: Any) -> str:
    if not value:
        return datetime.now().strftime("%Y-%m-%d")
    text = str(value).strip()
    if "T" in text:
        return text.split("T", 1)[0]
    return text[:10] or datetime.now().strftime("%Y-%m-%d")


def _node_label(node: dict[str, Any]) -> str:
    ip = str(node.get("ip", "")).strip()
    if ip and ip != "未采集":
        return ip
    hostname = str(node.get("hostname", "")).strip()
    if hostname and hostname != "未采集":
        return hostname
    return "未采集"


def cluster_ng_items(data: dict[str, Any]) -> Iterable[dict[str, Any]]:
    return ((data.get("cluster") or {}).get("gs_check_summary") or {}).get("ng_items", [])
