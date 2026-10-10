"""Shared dashboard secrets lookup; CLI workers retain environment-only config."""
import os
from pathlib import Path
import tomllib

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

LOCAL_SECRETS = Path(__file__).resolve().parent / '.streamlit' / 'secrets.toml'


def get_setting(name: str) -> str:
    """Use native Streamlit secrets in an app session, then environment fallback.

    This helper does not export or print configuration values. Outside a
    Streamlit session, preserve the scheduled worker's environment-only behaviour.
    """
    if get_script_run_ctx(suppress_warning=True) is not None:
        try:
            # Read the standard local file without exporting its root keys into
            # os.environ. Empty placeholders must not overwrite env fallbacks.
            if LOCAL_SECRETS.is_file():
                with LOCAL_SECRETS.open('rb') as handle:
                    value = tomllib.load(handle).get(name, '')
            else:
                value = st.secrets.get(name, '')
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:
            # Missing/unreadable secrets must not expose their contents in errors.
            pass
    return os.getenv(name, '').strip()
