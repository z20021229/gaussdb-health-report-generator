"""Inspection parsing entry points.

This first version intentionally does not parse customer data from the sample
package. Unknown business fields are represented as "未采集" or "未提供".
"""

from pathlib import Path
from typing import Any


def build_minimal_inspection_data(input_path: Path, template_path: Path) -> dict[str, Any]:
    """Build the minimal YAML-ready data structure for phase one."""
    return {
        "project": {
            "name": "GaussDB 数据库健康诊断报告",
            "phase": "phase-1-skeleton",
        },
        "source": {
            "input_file": str(input_path),
            "template_file": str(template_path),
        },
        "customer": {
            "name": "未提供",
        },
        "inspection": {
            "date": "未采集",
            "database_name": "未采集",
            "nodes": [],
        },
        "summary": {
            "conclusion": "未采集",
            "risk_count": 0,
        },
        "sections": {
            "system_overview": "未采集",
            "overall_status": "未采集",
            "high_availability": "未采集",
            "parameter_check": "未采集",
            "system_maintenance": "未采集",
        },
    }
