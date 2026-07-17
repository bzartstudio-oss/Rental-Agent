"""Local installation health check — see
docs/35_Installation_and_Operations.md "Health Check".

Usage:
    python scripts/health_check.py [--json]

Every check reports one of PASS / WARN / FAIL. The process exits non-zero
only if at least one check FAILs (a WARN is informational — e.g. an unset
optional notification channel — and never blocks startup).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

_MIN_PYTHON = (3, 11)


@dataclass
class CheckResult:
    name: str
    status: str  # "PASS" | "WARN" | "FAIL"
    detail: str


def _check_python_version() -> CheckResult:
    current = sys.version_info[:2]
    if current >= _MIN_PYTHON:
        return CheckResult("python_version", "PASS", f"Python {sys.version.split()[0]} (>= {'.'.join(map(str, _MIN_PYTHON))} required)")
    return CheckResult("python_version", "FAIL", f"Python {sys.version.split()[0]} is older than the required {'.'.join(map(str, _MIN_PYTHON))}")


def _check_dependencies() -> CheckResult:
    required = ["flask", "requests", "playwright", "PIL", "bs4", "dateutil", "dotenv"]
    missing = []
    for module_name in required:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)
    if not missing:
        return CheckResult("dependencies", "PASS", f"All {len(required)} required packages importable")
    return CheckResult("dependencies", "FAIL", f"Missing packages: {', '.join(missing)}")


def _check_playwright_browsers() -> CheckResult:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            executable = Path(p.chromium.executable_path)
        if executable.exists():
            return CheckResult("playwright_browsers", "PASS", f"Chromium found at {executable}")
        return CheckResult("playwright_browsers", "FAIL", "Chromium executable not found — run 'python -m playwright install chromium'")
    except Exception as exc:  # noqa: BLE001 — health check must never crash on a missing optional piece
        return CheckResult("playwright_browsers", "FAIL", f"Playwright check failed: {exc}")


def _check_configuration() -> CheckResult:
    try:
        from src.web.configuration import WebConfiguration

        configuration = WebConfiguration.from_env()
        return CheckResult("configuration", "PASS", f"WebConfiguration loaded (host={configuration.host}, port={configuration.port})")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("configuration", "FAIL", f"Configuration failed to load: {exc}")


def _check_writable_data_directories() -> CheckResult:
    from src.core.config import DATA_DIR, OUTPUT_DIR

    problems = []
    for directory in (DATA_DIR, OUTPUT_DIR):
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".health_check_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            problems.append(f"{directory}: {exc}")
    if not problems:
        return CheckResult("writable_data_directories", "PASS", f"{DATA_DIR} and {OUTPUT_DIR} are writable")
    return CheckResult("writable_data_directories", "FAIL", "; ".join(problems))


def _check_database() -> CheckResult:
    try:
        from src.storage.database import Database

        db = Database()
        with db.transaction() as conn:
            conn.execute("SELECT 1")
        return CheckResult("database_accessibility", "PASS", f"Database at {db.db_path} is accessible")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("database_accessibility", "FAIL", f"Database is not accessible: {exc}")


def _check_migrations() -> CheckResult:
    try:
        from src.storage.database import Database

        db = Database()
        migrations_dir = db.migrations_dir
        discovered = {int(p.name.split("_", 1)[0]) for p in migrations_dir.glob("*.sql")}
        with db.transaction() as conn:
            applied = {row["version"] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        pending = discovered - applied
        if not pending:
            return CheckResult("migration_status", "PASS", f"All {len(applied)} migrations applied")
        return CheckResult("migration_status", "WARN", f"Pending migrations: {sorted(pending)} (will apply automatically on next Database() construction)")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("migration_status", "FAIL", f"Could not determine migration status: {exc}")


def _check_web_binding() -> CheckResult:
    from src.web.configuration import WebConfiguration

    configuration = WebConfiguration.from_env()
    if configuration.host in ("127.0.0.1", "localhost"):
        return CheckResult("web_binding", "PASS", f"Bound to localhost only ({configuration.host})")
    return CheckResult("web_binding", "WARN", f"Bound to {configuration.host} — network-exposed (WEB_ALLOW_NETWORK is set)")


def _check_connector_registry() -> CheckResult:
    try:
        import src.connectors.demo_platform  # noqa: F401
        import src.connectors.demo_platform_two  # noqa: F401
        import src.connectors.rentcast  # noqa: F401
        from src.connectors.sdk.registry import ConnectorRegistry

        names = ["demo_platform", "demo_platform_two", "rentcast"]
        registered = [n for n in names if ConnectorRegistry.is_registered(n)]
        if len(registered) == len(names):
            return CheckResult("connector_registry", "PASS", f"{len(registered)} connectors registered: {registered}")
        return CheckResult("connector_registry", "WARN", f"Only {registered} registered out of {names}")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("connector_registry", "FAIL", f"Connector registry check failed: {exc}")


def _check_provider_registry() -> CheckResult:
    try:
        import src.providers  # noqa: F401 — triggers data/ + ai/ self-registration
        from src.providers.registry import ProviderRegistry

        providers = ProviderRegistry.all()
        return CheckResult("provider_registry", "PASS", f"{len(providers)} provider(s) registered")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("provider_registry", "FAIL", f"Provider registry check failed: {exc}")


def _check_geographic_providers() -> CheckResult:
    try:
        import src.geography  # noqa: F401
        from src.geography.registry import GeoProviderRegistry

        if GeoProviderRegistry.is_registered("haversine"):
            return CheckResult("geographic_providers", "PASS", "haversine geo provider registered")
        return CheckResult("geographic_providers", "WARN", "haversine geo provider not registered")
    except Exception as exc:  # noqa: BLE001
        return CheckResult("geographic_providers", "FAIL", f"Geographic provider check failed: {exc}")


def _check_notification_channels() -> CheckResult:
    try:
        import src.notifications  # noqa: F401
        from src.notifications.registry import NotificationChannelRegistry

        channels = NotificationChannelRegistry.all()
        enabled = [c.channel_name for c in channels if c.is_enabled()]
        disabled = [c.channel_name for c in channels if not c.is_enabled()]
        detail = f"enabled={enabled}, not-yet-configured={disabled}"
        return CheckResult("notification_channels", "PASS" if enabled else "WARN", detail)
    except Exception as exc:  # noqa: BLE001
        return CheckResult("notification_channels", "FAIL", f"Notification channel check failed: {exc}")


def _check_storage_space() -> CheckResult:
    from src.core.config import DATA_DIR

    try:
        usage = shutil.disk_usage(DATA_DIR if DATA_DIR.exists() else Path(tempfile.gettempdir()))
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 0.5:
            return CheckResult("storage_availability", "FAIL", f"Only {free_gb:.2f} GiB free")
        if free_gb < 2:
            return CheckResult("storage_availability", "WARN", f"{free_gb:.2f} GiB free — getting low")
        return CheckResult("storage_availability", "PASS", f"{free_gb:.2f} GiB free")
    except OSError as exc:
        return CheckResult("storage_availability", "WARN", f"Could not determine free space: {exc}")


def run_all_checks() -> list[CheckResult]:
    return [
        _check_python_version(),
        _check_dependencies(),
        _check_playwright_browsers(),
        _check_configuration(),
        _check_writable_data_directories(),
        _check_database(),
        _check_migrations(),
        _check_web_binding(),
        _check_connector_registry(),
        _check_provider_registry(),
        _check_geographic_providers(),
        _check_notification_channels(),
        _check_storage_space(),
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="health_check", description="Verify the local Rental Intelligence Platform installation")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of a human-readable summary")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_all_checks()

    if args.json:
        print(json.dumps([{"name": r.name, "status": r.status, "detail": r.detail} for r in results], indent=2))
    else:
        for result in results:
            print(f"[{result.status}] {result.name}: {result.detail}")
        failed = [r for r in results if r.status == "FAIL"]
        warned = [r for r in results if r.status == "WARN"]
        print(f"\n{len(results) - len(failed) - len(warned)} passed, {len(warned)} warning(s), {len(failed)} failure(s)")

    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
