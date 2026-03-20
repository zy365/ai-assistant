from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DashScope / 千问
    dashscope_api_key: str = "sk-f8257135e4434521a243cdba626d6c25"
    qwen_model: str = "qwen-max"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Redis
    redis_url: str = "redis://114.55.15.198:6379/0"
    redis_password: str = "tradingagents123"

    # PostgreSQL
    database_url: str = "postgresql://root:root@114.55.15.198:5432/ai-assistant"

    # Java 内部服务
    java_base_url: str = "https://test-textlive.top6xlc.com/yh/crm/ai"
    java_auth_url: str = "https://test-textlive.top6xlc.com/yh/crm/ai"

    # JWT
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    # 应用
    app_env: str = "development"
    log_level: str = "INFO"

    # 缓存 TTL（秒）
    perm_cache_ttl: int = 300   # 权限缓存 5 分钟
    tool_cache_ttl: int = 60    # Tool 定义缓存 60 秒

    dev_skip_auth: bool = True


settings = Settings()



# ── 开发调试开关 ──────────────────────────────────────────────
# DEV_SKIP_AUTH=true 时跳过所有权限验证，方便本地开发调试
# 生产环境务必设为 false 或不设置
# dev_skip_auth: bool = False
