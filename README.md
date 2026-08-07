# 多周期网安报告智能体（MultiCycle SecReport Agent）

面向安全运营团队的多周期网络安全态势报告自动生成平台：支持 **日报 / 周报 / 月报 / 季报 / 年报** 五类周期报告的全自动生成、审核流转、推送归档，并内置 **报告智能问答** 与 **Markdown / Word 导出**，帮助分析师从"写报告"中解放出来。

> 当前版本：**V2.1**（生产加固 + 报告智能问答 + 导出）
> 仓库路径注意：目录名含 U+2011 非断行连字符（`‑`），复制路径时请保留原字符。

---

## 功能特性

**报告生成**
- 5 周期（日/周/月/季/年）自动生成，窗口自动计算（上一自然周期）
- 异步任务化：提交即返回，后台执行 + 前端 1s 轮询状态
- 幂等复用：同窗口已有成功任务直接复用并跳转预览；支持"强制重跑"
- 数据源失败自动重试（指数退避），部分失败出 PARTIAL 报告

**数据处理（7 类数据源）**
- SYSLOG / API / DB / EXCEL（xlsx）/ INTEL 情报（jsonl）/ HISTORY 历史 / IOC
- 统一清洗 → 标准事件 → 指标聚合（总量/等级分布/类型分布/闭环率/环比趋势）
- 内置 mock 数据生成器，零外部依赖即可完整体验链路

**AI 研判与问答**
- 规则引擎（风险阈值标记）+ LLM 研判双通道，LLM 失败自动降级，报告照常生成
- 知识库（RAG）：上传研判参考文档，生成时按告警类型自动召回注入
- **报告智能问答**：针对已生成报告提问（正文 + 知识库召回 + LLM；LLM 不可用时自动提取相关章节）
- 报告版本摘要、风险等级、趋势预测与安全建议

**审核与交付**
- 版本管理：DRAFT → REVIEWING → APPROVED → ARCHIVED 全状态机 + 审计日志
- 版本对比：10 项指标 diff + 章节文本 diff（环比变化一目了然）
- 报告导出：**Markdown / Word（docx）** 文件下载（中文文件名）
- 推送：钉钉 / 企微 / 邮件 / 本地归档（stub 实现，可替换真实 Webhook）

**管理与安全**
- RBAC 三角色：admin（全部）/ analyst（生成、审核、推送）/ viewer（只读）
- 数据源、知识库、报告选配、调度、用户管理零代码界面
- 任务日志（TraceID / 耗时 / 数据源统计）、周期调度启停与手动触发

---

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.10 + FastAPI + SQLAlchemy 2 + Pydantic v2 |
| 前端 | Vue 3 + Element Plus + Vite 6 + TypeScript |
| 存储 | MySQL 8（开发可用 SQLite 零依赖）/ ChromaDB 向量库 / Redis 缓存（可选） |
| 调度 | 自研零依赖 asyncio 调度器（接口预留 APScheduler 替换） |
| 渲染 | Jinja2 模板（MD）+ python-docx（Word 导出） |
| LLM | OpenAI 兼容接口（默认 raytoken / deepseek，按需配置） |

**设计原则**：四层解耦（api → service → capability → infra），基础设施（DB/向量/缓存/调度/推送）全部抽象可替换，上层业务零感知。

---

## 目录结构

```
multicycle‑secreport‑agent/
├── sec_report_agent/            # 后端（FastAPI）
│   ├── main.py                  # 应用入口（路由注册）
│   ├── api/routers/             # auth / report / schedule / version / publish / datasource / knowledge / config
│   ├── app/services/            # 业务服务（report / auth / qa / export ...）
│   ├── capability/              # data_adapter / metric / judge / rag / render / push
│   ├── infra/                   # db / vector / cache / schedule / storage / trace
│   ├── model/                   # enum / entity / struct
│   ├── template/                # 五周期报告模板（Jinja2）
│   ├── scripts/                 # mock 数据生成 / 数据源初始化 / 联调脚本
│   ├── tests/                   # 338 个用例（test_v1x / test_v20 / test_v21）
│   └── .env                     # 环境配置（DATABASE_URL / LLM 等）
├── frontend/                    # 前端（Vue 3 + Element Plus）
│   └── src/views/               # Dashboard / Reports / ReportPreview / Schedule / DataSources / Knowledge / ReportConfig / TaskLogs / UserManage / Login
└── docker-compose.yml           # MySQL 8 + Redis 7（可选依赖）
```

---

## 快速开始

### 1. 前置

- Python 3.10+、Node 18+（前端依赖可复用兄弟项目 node_modules 或 `npm install`）

### 2. 启动基础设施（可选）

开发期可完全零依赖（SQLite + 内存缓存），需要 MySQL/Redis 时：

```bash
docker compose up -d          # MySQL 8 + Redis 7
```

### 3. 启动后端

```bash
cd sec_report_agent
pip install -r requirements.txt        # 首次
cp .env.example .env                   # 按需修改 DATABASE_URL / LLM 配置
python3 -m uvicorn main:app --host 127.0.0.1 --port 8001
```

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

浏览器打开 http://127.0.0.1:5174 → 登录 → 任务看板点"生成报告"（或"↻ 重跑"强制重新生成）→ 轮询完成后跳转预览 → 可提问、导出、审核、推送。

---

## 默认账号与端口

| 项 | 值 |
|---|---|
| 前端 | http://127.0.0.1:5174 |
| 后端 | http://127.0.0.1:8001（`/health` 健康检查，`/docs` Swagger） |
| 管理员 | `admin` / `admin123` |
| 分析师 | `analyst` / `analyst123` |
| 只读访客 | `viewer` / `viewer123` |

---

## API 概览

| 前缀 | 说明 | 主要端点 |
|---|---|---|
| `/api/auth` | 认证与用户 | login / me / users（CRUD） |
| `/api/report` | 报告任务 | list / generate / status / detail / stats / **qa** / **export** |
| `/api/version` | 版本与审核 | list / detail / content / audit / compare |
| `/api/schedule` | 调度 | list / trigger / toggle / next-run |
| `/api/datasource` | 数据源管理 | meta / list / create / toggle / test |
| `/api/kb` | 知识库 | categories / list / create / toggle |
| `/api/config/report` | 报告选配 | get / save（章节开关 / 周期 / 自动推送） |
| `/api/publish` | 推送 | channels / push / records |

统一响应结构：`{ code, message, data, traceId, timestamp }`；RBAC 通过 `Authorization: Bearer <token>` 鉴权。

---

## 测试与质量

```bash
cd sec_report_agent
python3 -m pytest tests/ -q                    # 338 用例全绿
python3 -m pytest tests/ -q --cov=app --cov=api --cov=capability --cov=infra --cov=model --cov=common --cov-report=term
```

- 测试隔离：conftest 自动切换独立 SQLite 测试库 + mock 数据源，**不污染开发库**
- 覆盖率：**94%**（4062 stmts）
- 测试数据清理：`python3 scripts/dev/cleanup_test_data.py`（幂等删除测试特征数据）

---

## 文档索引

| 文档 | 内容 |
|---|---|
| `多周期网安报告智能体.md` | 主设计文档（四层架构 / SOLID / 设计模式） |
| `多周期网安报告智能体（MultiCycle SecReport Agent）详细设计文档.md` | 六层架构 / 7 类数据源 / 5 周期 / 接口规范 |
| `多周期网安报告智能体 迭代开发规划.md` | V1.0 ~ V2.1 版本路线 |
| `开发规划（落地执行版）.md` 等 | 各版本落地执行标准（技术栈定版 / 任务清单 / 验收） |

---

## 版本历史

| 版本 | 核心内容 |
|---|---|
| V1.0 | 框架底座 + 月报最小闭环（数据接入→指标→研判→渲染→API/调度/前端） |
| V1.1 | 月报完整交付（审核流转 / 推送 stub / 版本对比 / 环比） |
| V1.2 | 全周期模板（日/周/季/年）+ 新增 4 类数据源适配器 |
| V1.3 | 前端可视化零代码（数据源 / 知识库 / 报告选配 / 任务日志） |
| V2.0 | 生产加固：RBAC / 异步生成 / 容错重试 / 知识库 RAG / 覆盖率 94% |
| V2.1 | 报告智能问答 + Markdown/Word 导出 + 中文降级问答 |
| **V2.2** | **上线硬门槛：登录失败锁定 / 强制改密 / 任务恢复 / 并发生成上限 / Dockerfile+Systemd+Nginx 部署 / 数据备份** |

---

## License

内部项目，保留所有权利。
