"""趋势/时间轴演示数据种子脚本（V2.6）

为五周期生成历史指标快照（metric_snapshot）+ 报告版本（report_version），
供趋势分析页 / 报告时间轴页联调展示。task_id=900001 专用（演示），重跑自动清旧。

用法:
    python3 scripts/dev/seed_trend_snapshots.py                # 全部周期，每周期 12 期
    python3 scripts/dev/seed_trend_snapshots.py --cycles MONTHLY,QUARTERLY
    python3 scripts/dev/seed_trend_snapshots.py --per-cycle 8
"""
import argparse
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")

from infra.db.session import SessionLocal
from model.entity.entities import MetricSnapshot, ReportVersion
from model.enum.enums import ReportCycle

DEMO_TASK_ID = 900001
CYCLE_LABEL = {c.value: c.label for c in ReportCycle}


# ── 窗口生成（前闭后开，与 app/tasks/report_task.calc_window 同构） ──

def _month_range(y: int, m: int) -> tuple[date, date]:
    """月初 → 下月 1 日"""
    if m == 12:
        return date(y, 12, 1), date(y + 1, 1, 1)
    return date(y, m, 1), date(y, m + 1, 1)


def _quarter_range(y: int, q: int) -> tuple[date, date]:
    """季初 → 下季首日"""
    m0 = (q - 1) * 3 + 1
    start = date(y, m0, 1)
    if m0 + 3 > 12:
        return start, date(y + 1, 1, 1)
    return start, date(y, m0 + 3, 1)


def _windows(cycle: str, count: int, today: date) -> list[tuple[date, date]]:
    """生成 count 个窗口 (start, end)，前闭后开，升序，今天往前推"""
    out: list[tuple[date, date]] = []
    if cycle == ReportCycle.DAILY.value:
        for i in range(count - 1, -1, -1):
            d = today - timedelta(days=i)
            out.append((d, d + timedelta(days=1)))
    elif cycle == ReportCycle.WEEKLY.value:
        monday = today - timedelta(days=today.weekday())
        for i in range(count - 1, -1, -1):
            ws = monday - timedelta(weeks=i)
            out.append((ws, ws + timedelta(days=7)))
    elif cycle == ReportCycle.MONTHLY.value:
        for i in range(count - 1, -1, -1):
            yy, mm = today.year, today.month - i
            while mm <= 0:
                mm += 12
                yy -= 1
            out.append(_month_range(yy, mm))
    elif cycle == ReportCycle.QUARTERLY.value:
        q = (today.month - 1) // 3 + 1
        for i in range(count - 1, -1, -1):
            qq, yy = q - i, today.year
            while qq <= 0:
                qq += 4
                yy -= 1
            out.append(_quarter_range(yy, qq))
    elif cycle == ReportCycle.YEARLY.value:
        for i in range(count - 1, -1, -1):
            y = today.year - i
            out.append((date(y, 1, 1), date(y + 1, 1, 1)))
    return out


# ── 指标生成（带治理趋势 + 随机波动 + 偶发 EMPTY） ──

def _metrics(rng: random.Random, cycle: str, idx: int, ws: date, we: date) -> dict:
    """idx=0 最近一期；告警数随 idx 增大而下降（治理成效可见）"""
    # 每 7 期插 1 个 EMPTY 窗口（alert.total=0 且 vuln.total=0），验证默认过滤
    if idx % 7 == 6:
        return {
            "alert": {"total": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
                      "close_rate": 0.0, "by_type": {}, "by_day": []},
            "vuln": {"total": 0, "unfixed": 0, "fixed": 0, "ignored": 0,
                     "unfixed_high": 0, "close_rate": 0.0, "top_assets": []},
            "top": [], "trend": [],
            "raw": {"event_count": 0, "vuln_count": 0},
        }

    base = rng.randint(40, 70)
    decay = max(0, idx * rng.randint(2, 5))          # 越旧越多（治理成效）
    at = max(2, base + decay + rng.randint(-3, 3))
    ah = max(0, round(at * rng.uniform(0.12, 0.2)))
    am = max(0, round(at * rng.uniform(0.3, 0.4)))
    al = max(0, at - ah - am - rng.randint(0, 2))
    ai = rng.randint(0, 5)
    closed = rng.randint(round(at * 0.5), at)
    vt = max(1, rng.randint(6, 18) + idx)
    vu = max(0, vt - rng.randint(0, 4))
    vuh = max(0, round(vt * rng.uniform(0.1, 0.25)))
    days = max(1, (we - ws).days + 1)
    step = max(1, days // 12)
    by_day = []
    for d in range(0, days, step):
        day = ws + timedelta(days=d)
        by_day.append({"date": day.isoformat(),
                       "total": max(0, at // max(1, days // step)),
                       "high": max(0, ah // max(1, days // step))})
    return {
        "alert": {"total": at, "high": ah, "medium": am, "low": al, "info": ai,
                  "close_rate": round(closed / at, 4),
                  "by_type": {"暴力破解": rng.randint(0, am), "SQL注入": rng.randint(0, am),
                              "Web扫描": rng.randint(0, al), "异常登录": rng.randint(0, al)},
                  "by_day": by_day},
        "vuln": {"total": vt, "unfixed": vu, "fixed": vt - vu, "ignored": 0,
                 "unfixed_high": vuh, "close_rate": round((vt - vu) / vt, 4),
                 "top_assets": [{"asset_ip": f"10.0.{rng.randint(1, 9)}.{rng.randint(2, 254)}",
                                 "count": rng.randint(1, 4)} for _ in range(3)]},
        "top": [],
        "trend": [],
        "raw": {"event_count": at + ai, "vuln_count": vt},
    }


def seed(cycles: list[str], per_cycle: int) -> None:
    db = SessionLocal()
    rng = random.Random(20260808)                    # 固定种子，可复现
    today = date.today()
    try:
        # 清旧：演示数据 task_id=900001 专用
        old_v = db.query(ReportVersion).filter(ReportVersion.task_id == DEMO_TASK_ID).count()
        old_s = db.query(MetricSnapshot).filter(MetricSnapshot.task_id == DEMO_TASK_ID).count()
        db.query(MetricSnapshot).filter(MetricSnapshot.task_id == DEMO_TASK_ID).delete()
        db.query(ReportVersion).filter(ReportVersion.task_id == DEMO_TASK_ID).delete()
        db.commit()

        total_v = total_s = 0
        for cycle in cycles:
            wins = _windows(cycle, per_cycle, today)
            for idx, (ws, we) in enumerate(reversed(wins)):   # idx=0 最近一期
                metrics = _metrics(rng, cycle, idx, ws, we)
                # 与真实落库一致：前闭后开 [start, end)，'YYYY-MM-DD HH:MM:SS'
                ws_str, we_str = f"{ws.isoformat()} 00:00:00", f"{we.isoformat()} 00:00:00"
                snap = MetricSnapshot(task_id=DEMO_TASK_ID, cycle=cycle,
                                      window_start=ws_str, window_end=we_str,
                                      metrics_json=metrics)
                db.add(snap)
                db.flush()                                     # 拿 snap.id
                ver = ReportVersion(task_id=DEMO_TASK_ID, cycle=cycle,
                                    window_start=ws_str, window_end=we_str,
                                    version_no=1, version_type="AI_DRAFT", status="PUBLISHED",
                                    title=f"{CYCLE_LABEL[cycle]}{ws.isoformat()} 趋势演示报告",
                                    content_md="# 趋势演示报告（种子数据，可删除）",
                                    file_path="", metric_snapshot_id=snap.id,
                                    operator="seed", remark="V2.6 趋势演示")
                db.add(ver)
                total_s += 1
                total_v += 1
            db.commit()
            print(f"  {cycle:<10} {len(wins)} 期（{wins[0][0]} ~ {wins[-1][1]}）")

        print(f"完成：{len(cycles)} 周期，快照 {total_s} 条 + 版本 {total_v} 条（task_id={DEMO_TASK_ID}）")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="趋势/时间轴演示数据种子")
    parser.add_argument("--cycles", default=",".join(c.value for c in ReportCycle),
                        help="周期列表，逗号分隔，默认五周期全种")
    parser.add_argument("--per-cycle", type=int, default=12, help="每周期期数，默认 12")
    args = parser.parse_args()
    cycles = [c.strip().upper() for c in args.cycles.split(",") if c.strip()]
    print(f"种子开始：{cycles} × {args.per_cycle} 期（task_id={DEMO_TASK_ID}）")
    seed(cycles, args.per_cycle)
