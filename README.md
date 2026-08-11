<div align="center">

# 📊 多周期网安报告智能体 (MultiCycle SecReport Agent)

**面向安全运营团队的多周期网络安全态势报告自动生成平台**

[![Version](https://img.shields.io/badge/version-v2.8.0-blue)]()
[![Backend](https://img.shields.io/badge/FastAPI-0.136-009688)]()
[![Frontend](https://img.shields.io/badge/Vue3-Element_Plus-42b883)]()
[![LLM](https://img.shields.io/badge/LLM-DeepSeek_V4_Flash-4f5d95)]()
[![RAG](https://img.shields.io/badge/RAG-ChromaDB-orange)]()
[![Tests](https://img.shields.io/badge/tests-419_passed-2ea44f)]()

**日报 / 周报 / 月报 / 季报 / 年报 五周期自动生成** · **7 类数据源真实对接** · **审核流转 / 推送归档 / 趋势分析 / 智能问答**

</div>

---

## 📑 目录

- [🚀 项目简介](#-项目简介)
- [✨ 核心功能（全部）](#-核心功能全部)
  - [报告生成](#报告生成模块)
  - [数据源对接](#数据源对接模块)
  - [AI 研判与知识库](#ai-研判与知识库模块)
  - [趋势洞察](#趋势洞察模块)
  - [审核与交付](#审核与交付模块)
  - [通知与协作](#通知与协作模块)
  - [运维深化](#运维深化模块)
  - [管理与安全](#管理与安全模块)
- [🏗️ 架构设计](#️-架构设计)
  - [五层架构](#五层架构)
  - [报告生成链路](#报告生成链路)
  - [项目目录结构](#项目目录结构)
- [⚡ 快速开始](#-快速开始)
- [🧩 全部功能说明](#-全部功能说明)
- [🐳 Docker 部署](#-docker-部署)
- [🔧 配置说明](#-配置说明)
- [🧪 测试](#-测试)
- [📚 文档索引](#-文档索引)
- [⚠️ 已知限制](#️-已知限制)
- [📄 License](#-license)

---

## 🚀 项目简介

多周期网安报告智能体帮助安全分析师从"写报告"中解放出来：系统自动从 **7 类数据源** 拉取告警/漏洞/情报数据，经统一清洗、指标聚合与 AI 研判，生成 **日报 / 周报 / 月报 / 季报 / 年报** 五类周期报告，并支持完整的 **审核流转 → 推送归档 → 趋势洞察 → 智能问答** 闭环。

**核心亮点：**

- 🗓️ **五周期自动生成**：窗口自动计算（上一自然周期），异步任务化 + 幂等复用 + 强制重跑 + **错过窗口检测与一键补跑**（停电/维护漏跑自动发现）
- 🔌 **数据源真实对接 + 健康看板**：网页端配置数据源（接口引导 + 测试连接 + 连通状态），ES / MySQL / 告警平台 API 真实对接；**健康看板**聚合最近 30 次任务成功率，数据源异常时联动提示"先排查数据源再判定安全态势"
- 🧠 **规则 + LLM 双通道研判**：规则引擎（零依赖可穷举测试）→ RAG 知识库 → LLM 推理，三级降级容错，LLM 故障报告照常生成
- 📈 **趋势分析 + 报告时间轴**：五周期指标序列可视化（ECharts 双轴图 + 环比摘要），竖向时间轴回溯历史报告；**趋势告警**自动识别环比突增（如月度告警量突增）
- 💬 **报告智能问答**：针对已生成报告提问（正文 + 知识库召回 + LLM 定制回答，引用来源可溯源）
- 📤 **审核推送交付**：DRAFT → REVIEWING → APPROVED → ARCHIVED 全状态机 + 审计、10 项指标版本对比、Markdown / Word / **批量 ZIP 周期归档**导出、钉钉 / 企微 / **邮件**真实推送（HMAC 加签 + 重试）
- 🔔 **站内通知中心**：报告就绪 / 推送失败 / 告警触发 / 审核结果四类事件，顶栏铃铛红点 + 已读管理
- 🛡️ **运维深化**：内置自检告警器（阈值 DB 热读、30min 防抖、趋势规则）、日志 JSON 结构化 + 脱敏、Prometheus 指标 + 就绪探针

---

## ✨ 核心功能（全部）

### 报告生成模块

| 能力 | 说明 |
|------|------|
| 五周期生成 | 日 / 周 / 月 / 季 / 年，窗口自动计算（上一自然周期，前闭后开） |
| 异步任务化 | 提交即返回，后台执行 + 前端 1s 轮询状态 |
| 幂等复用 | 同窗口已有成功任务直接复用并跳转预览；支持"强制重跑"（rerun） |
| 错过窗口补跑 | 自动检测最近 3 个已结束窗口无任务记录（停电/维护场景），一键 BACKFILL 补跑 |
| EMPTY 推送策略 | 三档可配：不推送 / 不推送+站内告警 / 正常推送（占位报告也推），防数据源异常误报 |
| 容错重试 | 数据源失败自动重试（指数退避），部分失败出 PARTIAL 报告；重启自动恢复中断任务 |

### 数据源对接模块

| 类型 | 对接方式 | 配置字段（网页端引导） |
|------|----------|------------------------|
| **ES 日志检索** | Elasticsearch REST（`/_cluster/health` 探测 + `/_search` 窗口检索 + search_after 翻页） | 集群地址 / 认证（basic·apikey）/ 索引模式 / 时间字段 / 附加 DSL |
| **API 告警平台** | 厂商平台 REST（认证 + 分页循环 + 时间窗口过滤） | 接口地址 / 认证（Bearer·APIKey·Basic）/ 时间字段 / 分页大小 |
| **漏洞台账 DB** | SQLAlchemy 连接 MySQL 等关系库（SELECT + 窗口过滤 + 字段映射） | 连接串 / 表名 / 时间字段 / 字段映射 |
| SYSLOG / EXCEL / INTEL / HISTORY | 本地文件 / 历史报告（字段补全） | 文件路径 / 格式 / 时间列映射 |

> 🔌 每个数据源支持**保存前测试连接**，列表展示**连通状态**（成功 / 失败 / 未测试）；双模式兼容：旧文件模式配置（读本地 mock 文件）与新真实对接配置并存，报告生成链路不受影响。
> 🩺 **健康看板（V2.8）**：按数据源聚合最近 30 个任务的成功率 / 最近拉取明细 / 状态灯（健康·警告·错误·未知），已删除配置的历史统计也保留展示。

### AI 研判与知识库模块

| 能力 | 说明 |
|------|------|
| 规则研判 | 风险阈值标记（指标 → P0-P3 / 高风险告警），零依赖、可穷举测试 |
| LLM 研判 | OpenAI 兼容接口（默认 raytoken / deepseek-v4-flash），失败自动降级，报告照常生成 |
| RAG 知识库 | 威胁情报库（攻击特征 / 处置建议）+ 报告规范库（指标口径），生成时按告警类型自动召回注入，页面增删改即同步向量库 |
| 报告智能问答 | 正文 + 知识库召回 + LLM 定制回答；引用来源显示（来源库 / 标题 / 摘要）；LLM 不可用时自动提取相关章节 |

### 趋势洞察模块

| 能力 | 说明 |
|------|------|
| 趋势分析 | 五周期指标时间序列（告警总量 / 高危 / 漏洞 / 未修复高危，可配置双轴），默认过滤 EMPTY 窗口；环比摘要卡 + 主副双图 + 明细表 |
| 报告时间轴 | 竖向时间轴按周期着色，卡片含状态 / 窗口 / 指标摘要，点击直达预览 |
| 趋势告警 | 规则引擎新增环比突增规则（如月度告警量突增 / 周度高危告警突增），取最近两期快照算环比，上期 0 本期 >0 必触发；默认停用防误报，运维可随时启用 |

### 审核与交付模块

| 能力 | 说明 |
|------|------|
| 版本状态机 | DRAFT → REVIEWING → APPROVED → ARCHIVED 全流程 + 审计日志 |
| 版本对比 | 10 项指标 diff + 章节文本 diff（环比变化一目了然） |
| 报告导出 | Markdown / Word（docx）单份下载（中文文件名）；**批量 ZIP 周期归档**（按周期 + 日期范围打包，V2.8） |
| 推送 | 钉钉 / 企微 / 邮件 / 本地归档；**real 模式**真实发送（钉钉 HMAC-SHA256 加签、企微 key 加签、SMTP SSL/STARTTLS、失败重试 2 次、PushLog 落库）；mock 模式开发期零外网验证 |

### 通知与协作模块

| 能力 | 说明 |
|------|------|
| 站内通知中心 | 新表 sys_notification，四类事件埋点：报告就绪 / 推送失败 / 告警触发 / 审核结果；支持全体广播与定向通知 |
| 铃铛红点 | 顶栏铃铛 30s 轮询未读数 + 通知面板（类型 / 级别 / 时间）+ 单条已读 / 全部已读 |
| 健壮性 | 通知写入失败不阻断业务主流程 |

### 运维深化模块

| 能力 | 说明 |
|------|------|
| 内置自检告警器 | 阈值 DB 热读（界面改规则免重启）、30min 防抖、触发 → 审计 + 钉钉 / 企微 / 邮件推送；规则含任务失败数 / LLM 降级率 / 推送失败数 / 趋势突增 |
| 可观测性 | `/health` 就绪探针（DB / 缓存 / 向量库三项明细，降级 503）、`/metrics` Prometheus 指标 |
| 日志治理 | JSON 结构化（Loki / ELK 零转换采集）+ 轮转 + 脱敏（敏感字段可配置） |
| 交付物 | Prometheus 告警规则 + Promtail 采集示例 + Systemd / Nginx 部署模板 + 备份恢复脚本 |

### 管理与安全模块

| 能力 | 说明 |
|------|------|
| RBAC | admin（全部）/ analyst（生成、审核、推送）/ viewer（只读），前端路由级拦截 |
| 调度 | 自研零依赖 asyncio 调度器，周期调度启停与手动触发 |
| 安全 | 登录失败锁定 / 强制改密 / 并发生成上限 / 审计日志页 / 数据备份方案 / 生产环境弱配置拒绝启动 |

---

## 🏗️ 架构设计

### 五层架构

```
api/routers ──▶ app/services ──▶ capability ──▶ infra ──▶ model
  (端点层)        (业务编排)      (能力层)      (基础设施)   (领域模型)
                 app/tasks
                 (异步任务)
```

- **api/routers**：auth / report / version / schedule / datasource / knowledge / config / publish / alert / trend / notification / audit 十二个路由
- **app/services + tasks**：报告生成 / 审核 / 问答 / 导出 / 趋势 / 通知 / 审计业务编排与异步任务
- **capability**：`adapter`（7 类数据源对接）/ `clean`（清洗）/ `judge`（规则+LLM 研判）/ `metric`（指标聚合）/ `rag`（知识库）/ `render`（模板渲染）/ `push`（推送策略）
- **infra**：db / vector（ChromaDB）/ cache / schedule / storage / trace / alert —— 全部抽象可替换，上层业务零感知

### 报告生成链路

```
数据源适配器 ──▶ 统一清洗 ──▶ 指标聚合 ──▶ 规则+LLM 研判 ──▶ RAG 召回注入 ──▶ 模板渲染
   (fetch)        (标准事件)   (总量/等级/类型/闭环率/环比)  (风险标注)     (攻击类型知识)   (Jinja2 MD)
```

### 项目目录结构

```
multicycle‑secreport‑agent/            # 仓库根（目录名含 U+2011 非断行连字符 ‑，复制路径请保留原字符）
├── README.md                          # 本文档
├── docker-compose.yml                 # MySQL 8 + Redis 7（可选依赖）
│
├── sec_report_agent/                  # ── 后端（FastAPI）──
│   ├── main.py                        # 应用入口（路由注册 + 告警器启动）
│   ├── Dockerfile                     # 生产镜像（多阶段构建 + 非 root + 健康检查）
│   ├── .env.example                   # 环境变量模板
│   ├── api/routers/                   # auth / report / version / schedule / datasource / knowledge / config / publish / alert / trend / notification / audit
│   ├── app/services/                  # report / version / qa / export / audit / auth / trend / notification 业务服务
│   ├── app/tasks/                     # report_task 异步生成任务
│   ├── capability/                    # adapter（7 类数据源）/ clean / judge / metric / rag / render / push / message
│   ├── infra/                         # db / vector / cache / schedule / storage / trace / alert
│   ├── model/                         # enum / entity / struct
│   ├── template/                      # 五周期报告模板（Jinja2）
│   ├── scripts/                       # 数据源初始化 / mock 数据 / 联调协议服务 / 清理脚本
│   ├── tests/                         # 419 个用例（test_v1x ~ test_v28）
│   ├── docs/deploy/                   # Systemd / Nginx / 备份恢复模板
│   └── .env                           # 环境配置（DATABASE_URL / LLM / PUSH_MODE）
│
└── frontend/                          # ── 前端（Vue 3 + Element Plus + Vite 6 + TS）──
    └── src/views/                     # Dashboard / Reports / ReportPreview / TrendView / TimelineView / Schedule / DataSources / Knowledge / ReportConfig / TaskLogs / UserManage / AlertRules / AuditLog / Login / ChangePwd / Forbidden
```

---

## ⚡ 快速开始

### 1. 前置

- Python 3.10+、Node 18+（前端依赖可复用兄弟项目 node_modules 或 `npm install`）

### 2. 启动基础设施（可选）

开发期可完全零依赖（SQLite + 内存缓存），需要 MySQL / Redis 时：

```bash
docker compose up -d          # MySQL 8 + Redis 7（健康检查就绪后）
```

### 3. 启动后端

```bash
cd sec_report_agent
pip install -r requirements.txt        # 首次
cp .env.example .env                   # 按需修改 DATABASE_URL / LLM / PUSH_MODE
python3 -m uvicorn main:app --host 127.0.0.1 --port 8001
```

> ⚠️ 前端 Vite 代理固定指向 **8001** 端口，后端请按此端口启动。

首次启动自动建表并幂等创建种子账号；**切换数据库后需初始化数据源**：

```bash
python3 scripts/init_datasources.py    # 幂等：生成 mock 数据 + 建 6 条数据源配置
```

### 4. 启动前端

```bash
cd frontend
npm run dev                  # http://127.0.0.1:5174（/api 自动代理到 8001）
```

### 5. 使用

浏览器打开 http://127.0.0.1:5174 → 登录 → 任务看板点"生成报告"（或"↻ 重跑"强制重新生成）→ 轮询完成后跳转预览 → 可提问、导出、审核、推送。数据源管理页可新增真实数据源（ES / 告警平台 API / MySQL）并测试连接，顶部健康看板实时查看各源成功率；调度配置页可查看错过窗口并一键补跑；报告页可批量导出 ZIP 周期归档；顶栏铃铛接收报告就绪 / 推送失败 / 告警等通知。

---

## 🧩 全部功能说明

| 前缀 | 说明 | 主要端点 |
|------|------|----------|
| `/api/auth` | 认证与用户 | login / me / users（CRUD）/ audit-logs / change-pwd |
| `/api/report` | 报告任务 | list / generate / status / detail / stats / qa / export / **export-batch** |
| `/api/version` | 版本与审核 | list / detail / content / audit / compare |
| `/api/schedule` | 调度 | list / trigger / toggle / next-run / **missed** / **backfill** |
| `/api/datasource` | 数据源管理 | meta（动态表单定义）/ list / create / update / toggle / test / delete / **health** |
| `/api/kb` | 知识库 | categories / list / create / toggle |
| `/api/config/report` | 报告选配 | get / save（章节开关 / 周期 / 自动推送 / EMPTY 策略） |
| `/api/publish` | 推送 | channels / push / records |
| `/api/alert/rules` | 告警规则 | list / update（阈值 / 开关，热生效） |
| `/api/trend` | 趋势洞察 | series / all-cycles / timeline |
| `/api/notification` | 站内通知 | list / unread-count / read / read-all |

统一响应结构：`{ code, message, data, traceId, timestamp }`；RBAC 通过 `Authorization: Bearer <token>` 鉴权。

---

## 🐳 Docker 部署

### 基础设施（docker-compose.yml）

```bash
docker compose up -d          # MySQL 8（utf8mb4 + healthcheck）+ Redis 7
```

| 服务 | 端口 | 说明 |
|------|------|------|
| mysql | 3306 | `sec_report` / `sec_report` / `sec_report_dev`，数据卷持久化 |
| redis | 6379 | 缓存（可选，`CACHE_BACKEND=memory` 可跳过） |

### 后端镜像（sec_report_agent/Dockerfile）

多阶段构建 + 非 root（uid 10001）+ 健康检查，`/app/reports` 与 `/app/vector_data` 数据目录持久化。部署模板见 `docs/deploy/`（Systemd 服务单元 + Nginx 反代 + 备份恢复 restore.md）。

---

## 🔧 配置说明

`.env` 关键项（模板见 `.env.example`）：

| 分组 | 变量 | 默认值 |
|------|------|--------|
| 服务 | `APP_ENV` / `DEBUG` / `PORT` | `dev` / `true` / `8000` |
| 存储 | `DATABASE_URL` | `mysql+pymysql://sec_report:sec_report_dev@127.0.0.1:3306/sec_report?charset=utf8mb4` |
| 缓存 | `CACHE_BACKEND` / `REDIS_URL` | `redis` / `redis://127.0.0.1:6379/0` |
| LLM | `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 空 / `https://raytoken.com.cn` / `deepseek-v4-flash` |
| 推送 | `PUSH_MODE` / `DINGTALK_WEBHOOK_URL` / `WECOM_WEBHOOK_URL` / `SMTP_*` | `mock` / 空 / 空 / 空（`real` 需配 webhook + 加签密钥 / SMTP 参数） |

> ⚠️ 路径配置基于项目根自动计算绝对路径（`settings._PROJECT_ROOT` 上溯 3 层），从任意目录运行均可正确解析。

---

## 🧪 测试

```bash
cd sec_report_agent
python3 -m pytest tests/ -q                                        # 419 用例全绿
python3 -m pytest tests/ -q --cov=api --cov=capability --cov=infra --cov=model --cov=common --cov=service --cov=app --cov-report=term
```

```
测试结果: 419/419 通过 ✅，覆盖率 92%（4500+ stmts）
```

**测试覆盖亮点**：

- 测试隔离：conftest 自动切换独立 SQLite 测试库 + mock 数据源，**不污染开发库**
- 数据源适配器：文件模式 + 真实对接双模式；HTTP 模式测试内自起协议服务（不依赖外部进程），覆盖认证 / 分页 / 时间窗口 / search_after 翻页 / 失败路径
- 知识库同步：台账 ↔ 向量库 CRUD 同步（fake store 隔离）
- 告警器 / 推送 / 可观测性：规则热更新、钉钉签名验签、mock 与 real 双模式、就绪探针降级、趋势规则环比评估
- V2.8 专项：站内通知（读/已读/权限）、错过窗口检测与补跑、数据源健康聚合、EMPTY 推送策略三档、批量导出 ZIP 内容校验

---

## 📚 文档索引

| 文档 | 内容 |
|------|------|
| `多周期网安报告智能体.md` | 主设计文档（五层架构 / SOLID / 设计模式） |
| `多周期网安报告智能体（MultiCycle SecReport Agent）详细设计文档.md` | 六层架构 / 7 类数据源 / 5 周期 / 接口规范 |
| `多周期网安报告智能体 迭代开发规划.md` | V1.0 ~ V2.8 版本路线 |
| `开发规划（V2.x 落地执行）.md` 等 | 各版本落地执行标准（技术栈定版 / 任务清单 / 验收；本地保留不入库） |
| `docs/deploy/` | Systemd / Nginx / 备份恢复模板 |

---

## ⚠️ 已知限制

- **LLM 依赖外网**：LLM 调用需可达 raytoken.com.cn（deepseek-v4-flash）；不可用时自动降级为规则 + 章节提取，报告生成不受阻
- **真实推送需配置**：`PUSH_MODE=real` 且配置钉钉 / 企微 webhook / SMTP 参数才真实发送；未配置时 mock 模式返回模拟成功（detail 标注 stub）
- **重型组件开发期不内置**：ES / Splunk 等重型组件开发期用本地协议服务验证对接代码（`scripts/dev/mock_data_services.py`），生产填真实地址即真连；Milvus 向量库（需 etcd + minio 三件套）开发期不用，使用 ChromaDB
- **仓库目录名**：含 U+2011 非断行连字符（`‑`），复制路径时请保留原字符

---

## 📄 License

内部项目，保留所有权利。
