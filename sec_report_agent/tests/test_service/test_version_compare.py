"""版本对比服务测试 — 指标 diff + 章节文本 diff"""
import sys
sys.path.insert(0, ".")

from app.services.version_service import VersionCompareService


class _FakeSnap:
    def __init__(self, metrics):
        self.metrics_json = metrics


class _FakeVer:
    def __init__(self, vid, metrics, content, title="报告", cycle="MONTHLY",
                 ws="2026-07-01 00:00:00", we="2026-08-01 00:00:00"):
        self.id = vid
        self.title = title
        self.cycle = cycle
        self.window_start = ws
        self.window_end = we
        self.created_at = "2026-08-06 17:00:00"
        self.metric_snapshot_id = vid
        self.content_md = content
        self._metrics = metrics


class _FakeDB:
    """模拟 db.get(MetricSnapshot, id) 与 ReportVersionRepo.get(db, id)"""

    def __init__(self, versions):
        self._versions = {v.id: v for v in versions}

    def get(self, model, vid):
        if model.__name__ == "MetricSnapshot":
            v = self._versions.get(vid)
            return _FakeSnap(v._metrics) if v else None
        return self._versions.get(vid)


def _metrics(total, high, close_rate):
    return {"alert": {"total": total, "high": high, "medium": 0, "low": 0,
                      "info": 0, "close_rate": close_rate},
            "vuln": {"total": 0, "unfixed": 0, "unfixed_high": 0, "close_rate": 0}}


def test_metric_diff_detects_changes():
    base = _FakeVer(1, _metrics(100, 10, 0.5), "# 报告\n\n## 一、总体态势\n\n基线")
    target = _FakeVer(2, _metrics(150, 20, 0.6), "# 报告\n\n## 一、总体态势\n\n变化后")
    db = _FakeDB([base, target])
    r = VersionCompareService.compare(db, 1, 2)
    diff = {f"{m['group']}.{m['field']}": m for m in r["metricDiff"]}
    assert diff["alert.total"]["base"] == 100
    assert diff["alert.total"]["target"] == 150
    assert diff["alert.total"]["delta"] == 50
    assert diff["alert.total"]["pct"] == 50.0
    assert diff["alert.high"]["changed"] is True


def test_metric_diff_unchanged_fields():
    base = _FakeVer(1, _metrics(100, 10, 0.5), "x")
    target = _FakeVer(2, _metrics(100, 10, 0.5), "y")
    db = _FakeDB([base, target])
    r = VersionCompareService.compare(db, 1, 2)
    assert all(m["changed"] is False for m in r["metricDiff"])


def test_text_diff_sections():
    base_md = "# 报告\n\n## 一、总体态势\n\n基线内容行1\n基线内容行2\n\n## 二、告警分析\n\n旧告警"
    target_md = "# 报告\n\n## 一、总体态势\n\n基线内容行1\n新内容行\n\n## 三、新增章节\n\n新章节内容"
    r = VersionCompareService._text_diff(base_md, target_md)
    names = {s["section"] for s in r["sections"]}
    assert "一、总体态势" in names
    assert "二、告警分析" in names
    assert "三、新增章节" in names
    assert r["totalAdded"] >= 2
    assert r["totalRemoved"] >= 1


def test_compare_missing_version():
    base = _FakeVer(1, _metrics(1, 0, 0), "x")
    db = _FakeDB([base])
    try:
        VersionCompareService.compare(db, 1, 999)
        assert False, "应抛 NotFoundError"
    except Exception as e:
        assert "版本不存在" in str(e)
