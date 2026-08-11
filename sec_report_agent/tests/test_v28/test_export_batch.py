"""V2.8 #7 批量导出/周期归档 — ZIP 打包 + 范围过滤"""

import io
import zipfile

import pytest


@pytest.fixture(autouse=True)
def _cleanup():
    # setup + teardown 都清 2099 段版本（防其他 test 文件先建残留，如 test_empty_push）
    from infra.db.session import SessionLocal
    from model.entity.entities import ReportVersion
    db = SessionLocal()
    try:
        db.query(ReportVersion).filter(ReportVersion.window_start.like("2099-%")).delete()
        db.commit()
    finally:
        db.close()
    yield
    db = SessionLocal()
    try:
        db.query(ReportVersion).filter(ReportVersion.window_start.like("2099-%")).delete()
        db.commit()
    finally:
        db.close()


def _add_version(ws, title, content):
    from infra.db.session import SessionLocal
    from model.entity.entities import ReportVersion
    db = SessionLocal()
    try:
        v = ReportVersion(
            task_id=990200, cycle="MONTHLY",
            window_start=ws, window_end="2099-03-01 00:00:00",
            version_no=1, version_type="AI_DRAFT", status="DRAFT",
            title=title, content_md=content, file_path="",
        )
        db.add(v)
        db.commit()
    finally:
        db.close()


def test_export_batch_zip(client):
    _add_version("2099-01-01 00:00:00", "一月月报", "# 一月内容")
    _add_version("2099-02-01 00:00:00", "二月月报", "# 二月内容")
    r = client.post("/api/report/export-batch",
                    json={"cycle": "MONTHLY", "from": "2099-01", "to": "2099-02"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/zip")
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert len(names) == 2, names
    assert any("一月" in n for n in names)
    assert any("二月" in n for n in names)
    total_md = "".join(zf.read(n).decode("utf-8") for n in names)
    assert "一月内容" in total_md and "二月内容" in total_md


def test_export_batch_range_filter(client):
    """from/to 过滤：只导出范围内的版本"""
    _add_version("2099-01-01 00:00:00", "一月", "# 一")
    _add_version("2099-03-01 00:00:00", "三月", "# 三")
    r = client.post("/api/report/export-batch",
                    json={"cycle": "MONTHLY", "from": "2099-02", "to": "2099-04"})
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert len(zf.namelist()) == 1
    assert "三月" in zf.namelist()[0]


def test_export_batch_empty(client):
    # 2099 段无 DAILY 版本 → 业务错误
    r = client.post("/api/report/export-batch",
                    json={"cycle": "DAILY", "from": "2099-01", "to": "2099-02"})
    assert r.status_code == 200
    assert r.json()["code"] != 0  # 无版本 → 业务错误
