"""初始化脚本 — 幂等：生成 mock 数据文件 + 创建六条数据源配置（MySQL/任意库可用）"""
import sys
sys.path.insert(0, ".")

from capability.adapter.mock_data_gen import ensure_mock_files
from infra.db.session import SessionLocal, init_db
from infra.db.repositories import DataSourceConfigRepo

init_db()
paths = ensure_mock_files(force=True)  # force: 全年窗口覆盖，保证五周期数据
print("mock files:", {k: v.split("/")[-1] for k, v in paths.items()})

db = SessionLocal()
try:
    # 幂等：按 name 查重
    existing = {c.name: c for c in DataSourceConfigRepo.list_all(db)}
    specs = [
        ("mock-syslog", "SYSLOG", {"file_path": paths["syslog"]}, "Syslog 模拟日志源(SSH爆破/Web攻击等)"),
        ("mock-api", "API", {"file_path": paths["api"]}, "告警平台模拟 API(JSON)"),
        ("mock-db", "DB", {"file_path": paths["vuln"]}, "资产漏洞台账模拟(CSV)"),
        ("mock-intel-xlsx", "EXCEL", {"file_path": paths["intel"]}, "威胁情报台账模拟(Excel)"),
        ("mock-intel-ioc", "INTEL", {"file_path": paths["ioc"]}, "外部威胁情报 IOC 模拟(JSONL)"),
        ("mock-history", "HISTORY", {"cycle": "MONTHLY"}, "历史报告环比源(读指标快照)"),
    ]
    for name, stype, cfg, desc in specs:
        if name in existing:
            print(f"跳过(已存在): {name}")
            continue
        c = DataSourceConfigRepo.create(db, name=name, type=stype, status="enabled",
                                        config_json=cfg, description=desc)
        print(f"创建: {name} id={c.id}")
    print("数据源配置:", [c.name for c in DataSourceConfigRepo.list_all(db)])
finally:
    db.close()
print("INIT DONE")
