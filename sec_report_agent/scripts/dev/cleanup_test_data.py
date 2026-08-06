"""清理测试污染数据（V2.0 tests/test_v20 曾直连开发 MySQL 造的 stub 版本）
安全策略：只删明显测试特征版本 + 关联审计日志，不动真实报告（id<=17 的态势报告）。
用法: python3 scripts/dev/cleanup_test_data.py
"""
import sys
sys.path.insert(0, ".")

from sqlalchemy import delete as sa_delete
from infra.db.session import SessionLocal
from model.entity.entities import ReportVersion, ReportTask, AuditLog, User, KnowledgeDoc

TEST_TITLE_PATTERNS = ("UT版本", "UT测试", "初稿", "基线", "目标", "路由测试", "推送内容", "对比测试", "审核测试")

db = SessionLocal()
try:
    rows = db.query(ReportVersion).all()
    removed = 0
    for v in rows:
        title = v.title or ""
        content = v.content_md or ""
        is_real = ("态势报告" in title) and len(content) > 60
        is_test = any(p in title for p in TEST_TITLE_PATTERNS) or (not is_real and len(content) < 60)
        if is_test and not is_real:
            db.execute(sa_delete(AuditLog).where(AuditLog.target_type == "ReportVersion", AuditLog.target_id == v.id))
            db.delete(v)
            removed += 1
    db.commit()
    print(f"已清理 {removed} 条测试版本（剩余 {len(rows) - removed} 条）")
    # 清理测试任务（trigger=TEST 且 window 2025 的批量任务；真实任务保留）
    tasks = db.query(ReportTask).all()
    t_removed = 0
    for t in tasks:
        if t.trigger_type == "TEST" and (t.window_start or "").startswith("2025"):
            db.execute(sa_delete(AuditLog).where(AuditLog.target_type == "ReportTask", AuditLog.target_id == t.id))
            db.delete(t)
            t_removed += 1
    db.commit()
    print(f"已清理 {t_removed} 条测试任务")
    # 清理非法 cycle 任务（API 联调误传假 cycle 如 cycle-xxx/vcyc-xxx 造的）
    from sqlalchemy import delete as sa_delete2
    VALID = {"DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "YEARLY"}
    bad_tasks = [t for t in db.query(ReportTask).all() if (t.cycle or "") not in VALID]
    c_removed = 0
    for t in bad_tasks:
        db.execute(sa_delete2(AuditLog).where(AuditLog.target_type == "ReportTask", AuditLog.target_id == t.id))
        db.execute(sa_delete2(ReportVersion).where(ReportVersion.task_id == t.id))
        db.execute(sa_delete2(AuditLog).where(AuditLog.target_type == "ReportVersion", AuditLog.target_id.in_(
            [v.id for v in db.query(ReportVersion).filter(ReportVersion.task_id == t.id).all()]
        )))
        db.delete(t)
        c_removed += 1
    db.commit()
    print(f"已清理 {c_removed} 条非法 cycle 任务")
    # 清理测试用户与 UT 文档（V2.0 RBAC 测试造的 utuserxxx / UT文档）
    u_removed = db.execute(sa_delete2(User).where(User.username.like("utuser%"))).rowcount
    k_removed = db.execute(sa_delete2(KnowledgeDoc).where(KnowledgeDoc.title.like("UT%"))).rowcount
    db.commit()
    print(f"已清理 {u_removed} 个测试用户、{k_removed} 条 UT 文档")
finally:
    db.close()
