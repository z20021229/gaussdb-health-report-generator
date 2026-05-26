from pathlib import Path

import yaml

from src.analyzer import analyze_inspection_data


def test_analyzer_generates_disk_risk_for_high_usage() -> None:
    data = _base_data()
    data["nodes"][0]["disks"] = [{"mounted_on": "/data", "use_percent": 85}]
    analyzed = analyze_inspection_data(data)
    assert any(r["item"] == "磁盘空间" and r["level"] == "风险" for r in analyzed["risks"])


def test_analyzer_generates_disk_attention_for_medium_usage() -> None:
    data = _base_data()
    data["nodes"][0]["disks"] = [{"mounted_on": "/data", "use_percent": 75}]
    analyzed = analyze_inspection_data(data)
    assert any(r["item"] == "磁盘空间" and r["level"] == "关注" for r in analyzed["risks"])


def test_analyzer_generates_gs_check_risk() -> None:
    data = _base_data()
    data["cluster"]["gs_check_summary"]["ng_items"] = [
        {
            "check_name": "CheckDirPermissions",
            "status": "NG",
            "detail_summary": "目录权限存在异常",
            "raw_detail_path": "output/raw_sections/check.txt",
        }
    ]
    analyzed = analyze_inspection_data(data)
    assert any(r["item"] == "gs_check 巡检项" for r in analyzed["risks"])


def test_analyzer_sets_good_overall_status_when_no_risk() -> None:
    data = _base_data()
    data["cluster"]["cluster_status"] = "normal"
    analyzed = analyze_inspection_data(data)
    assert analyzed["cluster"]["overall_status"] == "良好"


def test_analyzer_real_sample_contains_summary_and_risks() -> None:
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "output" / "inspection_data.generated.yaml").read_text(encoding="utf-8"))
    analyzed = analyze_inspection_data(data)
    assert "overall_status" in analyzed["cluster"]
    assert isinstance(analyzed["risks"], list)
    assert isinstance(analyzed["conclusion"]["summary"], list)
    assert isinstance(analyzed["conclusion"]["suggestions"], list)
    for risk in analyzed["risks"]:
        for key in ["level", "item", "detail", "suggestion", "source"]:
            assert key in risk


def _base_data() -> dict:
    return {
        "nodes": [
            {
                "ip": "10.0.0.1",
                "hostname": "node1",
                "memory": {"usage_percent": 0},
                "disks": [{"mounted_on": "/data", "use_percent": 20}],
                "cpu_daily": {"avg_idle": 80, "max_iowait": 1},
            }
        ],
        "cluster": {
            "cluster_status": "normal",
            "ha_status": [],
            "replication_slots": [],
            "gs_check_summary": {
                "ok_count": 0,
                "ng_count": 0,
                "na_count": 0,
                "unknown_count": 0,
                "ng_items": [],
            },
            "resource_summary": {"node_count": 1, "cluster_max_disk_use_percent": 0, "cluster_min_cpu_idle": 80, "cluster_max_iowait": 1},
        },
        "database": {
            "running_status": {"records": []},
            "large_tables": [],
            "index_suggestions": [],
            "unused_indexes": [],
            "table_bloat": [],
        },
        "logs": {
            "fatal_log_summary": "未发现 fatal 异常日志",
            "panic_log_summary": "未发现 panic 异常日志",
            "fatal_log_files": [],
            "panic_log_files": [],
        },
        "risks": [],
        "conclusion": {"summary": [], "suggestions": []},
    }
