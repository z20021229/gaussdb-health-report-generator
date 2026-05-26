"""Word report rendering helpers."""

from pathlib import Path
from typing import Any

from docx import Document


REPORT_SECTIONS = [
    ("封面", "GaussDB 数据库健康诊断报告"),
    ("巡检日期", "未采集"),
    ("目录", "第一章 总结\n第二章 系统概况\n第三章 总体情况\n第四章 高可用检查\n第五章 参数检查\n第六章 系统管理维护"),
    ("第一章 总结", "本章节内容暂未采集。"),
    ("第二章 系统概况", "本章节内容暂未采集。"),
    ("第三章 总体情况", "本章节内容暂未采集。"),
    ("第四章 高可用检查", "本章节内容暂未采集。"),
    ("第五章 参数检查", "本章节内容暂未采集。"),
    ("第六章 系统管理维护", "本章节内容暂未采集。"),
]


def render_docx(data: dict[str, Any], output_path: Path) -> Path:
    """Render a minimal Word report for the first runnable pipeline."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = Document()

    for index, (title, default_body) in enumerate(REPORT_SECTIONS):
        if index == 0:
            document.add_heading(default_body, level=0)
            document.add_paragraph("客户名称：未提供")
            document.add_paragraph("数据库名称：未采集")
            continue

        document.add_heading(title, level=1)
        body = _section_body(title, data, default_body)
        for line in body.splitlines():
            document.add_paragraph(line)

    document.save(output_path)
    return output_path


def _section_body(title: str, data: dict[str, Any], default_body: str) -> str:
    inspection = data.get("inspection", {})
    sections = data.get("sections", {})
    analysis = data.get("analysis", {})
    report = data.get("report", {})
    conclusion = data.get("conclusion", {})
    risk_details = data.get("risk_details") or {}
    cluster = data.get("cluster", {})

    if title == "巡检日期":
        return str(report.get("inspection_date") or inspection.get("date") or default_body)
    if title == "第一章 总结":
        summary = conclusion.get("summary") or []
        if summary:
            return "\n".join(str(item) for item in summary)
        return str(data.get("summary", {}).get("conclusion") or default_body)
    if title == "第二章 系统概况":
        if isinstance(sections.get("parsed_sections"), list):
            return f"已解析巡检章节数量：{len(sections['parsed_sections'])}"
        return str(sections.get("system_overview") or default_body)
    if title == "第三章 总体情况":
        lines = [f"总体状态：{cluster.get('overall_status', '未采集')}"]
        all_risks = list(risk_details.get("risks") or []) + list(risk_details.get("warnings") or [])
        if all_risks:
            lines.append("问题明细：")
            for risk in all_risks:
                lines.append(
                    f"[{risk.get('level', '未采集')}] {risk.get('item', '未采集')} - {risk.get('detail', '未采集')}"
                )
        return "\n".join(lines)
    if title == "第四章 高可用检查":
        return str(sections.get("high_availability") or default_body)
    if title == "第五章 参数检查":
        return str(sections.get("parameter_check") or default_body)
    if title == "第六章 系统管理维护":
        return str(sections.get("system_maintenance") or default_body)
    if title == "目录":
        return default_body
    return str(analysis.get("status") or default_body)
