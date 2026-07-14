"""Thin script wrapper — delegates straight to ui/cli.py (docs/02_Folder_Guide.md).

Superseded by this the previous version of this file (a standalone OpenAI-API-key status
check, from before the V1.0 architecture existed) — see learning/architecture_notes.md
2026-07-14. AI integration is deferred to V2, so there is no longer anything for this
file to check; it now does what its docstring always said it eventually would.
"""

from __future__ import annotations

import sys

from src.ui.cli import main

if __name__ == "__main__":
    sys.exit(main())
