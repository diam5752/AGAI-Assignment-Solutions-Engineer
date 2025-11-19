"""Shared utility functions for the automation package."""
import os
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def read_file(path: Path) -> str:
    """Read file content as UTF-8 text."""
    return path.read_text(encoding="utf-8")

def get_config_value(key: str, default: str = "") -> str:
    """Get configuration value from Streamlit secrets or environment variables.
    
    Checks Streamlit secrets first (for cloud deployment), then falls back
    to environment variables (for local development).
    """
    # Try Streamlit secrets first
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return str(st.secrets[key])
    except (ImportError, FileNotFoundError, KeyError):
        pass
    
    # Fall back to environment variables
    return os.getenv(key, default)

def load_env_file(path: Path) -> None:
    """Load environment variables from a file if it exists."""
    if not path.exists():
        return

    try:
        with path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue
                os.environ[key] = value.strip().strip('"').strip("'")
    except OSError as exc:
        logger.debug("Could not load env file %s: %s", path, exc)
