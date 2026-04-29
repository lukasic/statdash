from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    statdash_url: str = "http://localhost:8000"
    statdash_api_token: str

    mcp_transport: str = "stdio"  # "stdio" for local, "sse" for remote/k8s
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8080


settings = McpSettings()
