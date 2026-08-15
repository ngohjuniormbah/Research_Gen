#!/usr/bin/env python
"""Export the OpenAPI schema to docs/openapi.json (a build artifact).

Usage:  python scripts/export_openapi.py [output_path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    # Import lazily so `--help`-style invocations stay cheap and imports are explicit.
    from app.main import create_app

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/openapi.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    spec = create_app().openapi()
    out.write_text(json.dumps(spec, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    paths = len(spec.get("paths", {}))
    print(f"wrote {out} ({paths} paths, openapi {spec.get('openapi')})")


if __name__ == "__main__":
    main()
