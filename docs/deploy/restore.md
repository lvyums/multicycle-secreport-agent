# 数据恢复说明（V2.2 D2）

备份产物位于 `backups/`：`sec_report_<时间戳>.sql.gz`（数据库）+ `files_<时间戳>.tar.gz`（报告文件/向量库）。

## 恢复步骤

### 1. 恢复数据库

```bash
cd backups
gunzip -c sec_report_20260807_020000.sql.gz | mysql -h127.0.0.1 -usec_report -psec_report_dev sec_report
```

### 2. 恢复文件卷（报告 + 向量库）

```bash
cd /opt/sec-report-agent/sec_report_agent
tar -xzf backups/files_20260807_020000.tar.gz
```

### 3. 重启服务

```bash
sudo systemctl restart sec-report-agent   # systemd 部署
# 或
docker compose restart app                 # 容器部署
```

## 验证

1. `curl http://127.0.0.1:8001/health` 返回 200
2. 登录系统 → 历史报告列表可见恢复前的任务与版本
3. 打开任一报告预览，内容完整
4. 抽查最新任务时间戳，确认数据是备份时刻的

## 注意

- 恢复会**覆盖**当前数据，生产操作前先备份当前状态
- 数据库与文件卷必须**同一时间点**的备份一起恢复（跨时间点会导致报告文件与任务记录不一致）
- 容器部署时：先恢复 MySQL 数据（`docker compose exec mysql ...`），再恢复 app 卷内文件
