"""YAML configuration loader with deep merge support."""

import os
import yaml


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base. Override values win."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_mlit_api_key() -> str:
    """MLIT DPF API キーを取得する。

    優先順位:
      1. Streamlit secrets (st.secrets["MLIT_API_KEY"])
      2. 環境変数 MLIT_API_KEY
      3. /mnt/c/ClaudeWork/mlit-mcp-setup/mlit-dpf-mcp/.env
    """
    # 1. Streamlit secrets
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "MLIT_API_KEY" in st.secrets:
            return st.secrets["MLIT_API_KEY"]
    except Exception:
        pass

    # 2. 環境変数
    env_key = os.environ.get("MLIT_API_KEY")
    if env_key:
        return env_key

    # 3. .env ファイル
    env_path = "/mnt/c/ClaudeWork/mlit-mcp-setup/mlit-dpf-mcp/.env"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("MLIT_API_KEY="):
                    return line.split("=", 1)[1]

    return ""


def load_default_config() -> dict:
    """default.yaml のみを読み込む（Webアプリ動的 config 構築用）。"""
    config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
    default_path = os.path.join(config_dir, "default.yaml")

    with open(default_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # API key 埋め込み
    if "dpf" not in config:
        config["dpf"] = {}
    config["dpf"]["api_key"] = get_mlit_api_key()

    return config


def load_config(municipality_config_path: str) -> dict:
    """Load default config, then deep-merge municipality-specific config."""
    config = load_default_config()

    with open(municipality_config_path, "r", encoding="utf-8") as f:
        override = yaml.safe_load(f)

    config = deep_merge(config, override)
    # API key は load_default_config で既に埋め込み済み
    return config
