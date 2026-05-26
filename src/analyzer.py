"""Risk analysis entry points for parsed inspection data."""

from typing import Any


def analyze_minimal(data: dict[str, Any]) -> dict[str, Any]:
    """Attach a minimal risk analysis result without inventing findings."""
    analyzed = dict(data)
    analyzed["analysis"] = {
        "status": "未采集",
        "risks": [],
        "note": "第一阶段仅生成项目骨架，尚未执行真实风险分析。",
    }
    return analyzed
