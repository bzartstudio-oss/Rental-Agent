"""`WebConfiguration` — process-wide web-layer settings, loaded from the
environment. See docs/32_Web_Dashboard.md "Configuration"/"Localhost Binding".

Mirrors `core/config.py`'s own "paths + .env loading, nothing per-run" shape —
this is not a per-request object, one instance per process.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from src.core.config import DATA_DIR, OUTPUT_DIR, PROJECT_ROOT

_SECRET_KEY_PATH = DATA_DIR / ".web_secret_key"


def _load_or_create_secret_key() -> str:
    """A stable secret key across restarts (so sessions/CSRF tokens survive a
    server restart), generated once and stored outside version control
    (`data/` is gitignored — see docs/02_Folder_Guide.md) rather than
    hardcoded or regenerated every process start.
    """
    env_value = os.environ.get("WEB_SECRET_KEY")
    if env_value:
        return env_value

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _SECRET_KEY_PATH.exists():
        return _SECRET_KEY_PATH.read_text(encoding="utf-8").strip()

    key = secrets.token_hex(32)
    _SECRET_KEY_PATH.write_text(key, encoding="utf-8")
    return key


@dataclass
class WebConfiguration:
    """`host` defaults to localhost-only — "Default binding should be
    localhost only. Require explicit configuration to expose the application
    on the network" (the mission's own words). Setting `WEB_ALLOW_NETWORK=1`
    is the one explicit opt-in that changes the default bind host to
    `0.0.0.0`; nothing else in this module widens it implicitly.
    """

    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False
    secret_key: str = field(default_factory=_load_or_create_secret_key)
    max_content_length: int = 5 * 1024 * 1024  # 5 MiB — generous for a form post, not for an upload service
    project_root: Path = PROJECT_ROOT
    output_dir: Path = OUTPUT_DIR
    data_dir: Path = DATA_DIR
    # Both default False so plain local HTTP development is unaffected —
    # opt in explicitly once a deployment actually terminates HTTPS in front
    # of this app. See docs/45_Deployment_Guide.md "Production Safety".
    secure_cookies: bool = False
    trust_proxy: bool = False
    # v2.7 Milestone 2.7.3 — off by default so plain local dev/tests are
    # byte-identical to before; opt in explicitly with WEB_ENABLE_SCHEDULER=1
    # once a deployment wants unattended monitoring. See
    # docs/45_Deployment_Guide.md "Background Jobs and Monitoring" and
    # docs/46_Version_2.7_Planning.md Milestone 2.7.3.
    enable_scheduler: bool = False
    scheduler_interval_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "WebConfiguration":
        allow_network = os.environ.get("WEB_ALLOW_NETWORK", "").strip() in {"1", "true", "yes"}
        host = os.environ.get("WEB_HOST") or ("0.0.0.0" if allow_network else "127.0.0.1")
        # $PORT is the convention several hosting platforms (Render, Railway, Heroku)
        # inject automatically; WEB_PORT remains the explicit, platform-agnostic override.
        port = int(os.environ.get("WEB_PORT") or os.environ.get("PORT", "5000"))
        debug = os.environ.get("WEB_DEBUG", "").strip() in {"1", "true", "yes"}
        secure_cookies = os.environ.get("WEB_SECURE_COOKIES", "").strip() in {"1", "true", "yes"}
        trust_proxy = os.environ.get("WEB_TRUST_PROXY", "").strip() in {"1", "true", "yes"}
        enable_scheduler = os.environ.get("WEB_ENABLE_SCHEDULER", "").strip() in {"1", "true", "yes"}
        try:
            scheduler_interval_seconds = float(os.environ.get("WEB_SCHEDULER_INTERVAL_SECONDS", "60"))
        except ValueError:
            scheduler_interval_seconds = 60.0
        return cls(
            host=host, port=port, debug=debug, secure_cookies=secure_cookies, trust_proxy=trust_proxy,
            enable_scheduler=enable_scheduler, scheduler_interval_seconds=scheduler_interval_seconds,
        )
