from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class TemplateConfig(BaseModel):
    expected_metrics: list[str]
    thresholds: Dict[str, float]
    patterns: Dict[str, bool]
    params: Dict[str, float]


class AppYamlConfig(BaseModel):
    defaults: Dict[str, Any]
    templates: Dict[str, TemplateConfig]
    scoring: Dict[str, float]
    scenes: Dict[str, Any] = {"enabled": False, "definitions": []}


class Settings(BaseSettings):
    app_name: str = "Energy Pattern Analyzer"
    db_url: str = "sqlite:///./data/app.db"
    log_level: str = "INFO"
    config_path: str = "/app/config/app.yaml"

    class Config:
        env_prefix = ""


settings = Settings(
    db_url=os.getenv("DB_URL", "sqlite:///./data/app.db"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    config_path=os.getenv("CONFIG_PATH", "/app/config/app.yaml"),
)


def load_app_config() -> AppYamlConfig:
    path = Path(settings.config_path)
    if not path.exists():
        fallback = Path(__file__).resolve().parents[3] / "config" / "app.yaml"
        path = fallback
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return AppYamlConfig.model_validate(data)
