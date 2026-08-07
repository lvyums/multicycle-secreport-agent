"""全局配置管理 — 所有硬编码配置统一收口（pydantic-settings 从 .env 加载）"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：本文件所在目录的上级（sec_report_agent/）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(_PROJECT_ROOT, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 应用 ──
    app_name: str = "sec-report-agent"
    app_env: str = "dev"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # ── 数据库（MySQL8 Docker 默认；镜像不可用切 SQLite）──
    database_url: str = "sqlite:///./sec_report.db"

    # ── 缓存（redis 默认；无 Redis 切 memory）──
    cache_backend: str = "memory"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # ── LLM 配置（复用日志溯源卫士底座字段）──
    llm_api_key: str = ""
    llm_base_url: str = "https://raytoken.com.cn/v1"
    llm_model_name: str = "deepseek-v4-flash"
    llm_light_model_name: str = "deepseek-v4-flash"
    llm_temperature: float = 0.1
    llm_timeout: int = 60
    llm_retry_count: int = 2
    llm_retry_interval: float = 1.0
    llm_fallback_enabled: bool = True

    # ── 向量库配置（复用底座 vector_store）──
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-large"
    chroma_db_path: str = os.path.join(_PROJECT_ROOT, "vector_data", "chroma_db")
    top_k_retrieval: int = 5

    # ── 报告存储 ──
    report_root: str = os.path.join(_PROJECT_ROOT, "reports")
    vector_persist_dir: str = os.path.join(_PROJECT_ROOT, "vector_data")

    # ── 推送（V2.3：mock 默认保测试；real 需配 webhook 地址/密钥）──
    push_mode: str = "mock"                # mock | real
    dingtalk_webhook_url: str = ""         # 钉钉群机器人 webhook 地址
    dingtalk_webhook_secret: str = ""      # 钉钉加签密钥（非空才签名）
    wecom_webhook_url: str = ""            # 企微群机器人 webhook 地址
    wecom_webhook_key: str = ""            # 企微加签密钥（非空才签名）
    template_root: str = os.path.join(_PROJECT_ROOT, "template")

    # ── 风险阈值（规则引擎）──
    risk_high_alert_threshold: int = 100
    risk_high_vuln_unfixed_threshold: int = 10
    risk_closed_rate_threshold: float = 0.8

    # ── 调度（五周期 Cron）──
    cron_daily: str = "0 1 * * *"
    cron_weekly: str = "30 1 * * 1"
    cron_monthly: str = "0 2 1 * *"
    cron_quarterly: str = "30 2 1 1,4,7,10 *"
    cron_yearly: str = "0 3 1 1 *"
    schedule_enabled: bool = True

    # ── 报告生成配置 ──
    report_max_events: int = 20000        # 单任务最大处理事件数
    llm_max_input_chars: int = 6000       # 送入 LLM 的指标/上下文最大字符数

    # ── 安全（V2.2 上线硬门槛）──
    secret_key: str = "sec-report-dev-secret-change-me"   # 生产必须通过 env 注入强随机值
    login_fail_limit: int = 5             # 连续失败 N 次锁定
    login_lock_minutes: int = 15          # 锁定时长（分钟）
    pwd_min_length: int = 8               # 改密最小长度（含字母与数字）

    # ── 部署（V2.2）──
    cors_origins: str = "*"               # 逗号分隔白名单；生产必须显式配置
    max_concurrent_generation: int = 2    # 并发生成上限（防打爆 LLM 配额）
    recover_on_startup: bool = True       # 启动时重置遗留 PENDING/RUNNING 任务


settings = Settings()
