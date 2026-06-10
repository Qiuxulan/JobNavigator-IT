from __future__ import annotations

import json

from pipelines.trend.common import export_role_taxonomy, load_role_taxonomy_rows, upsert_role_taxonomy


def main() -> None:
    rows = load_role_taxonomy_rows()
    export_role_taxonomy(rows)
    upsert_role_taxonomy(rows)
    print(json.dumps({"status": "ok", "roles": len(rows)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
