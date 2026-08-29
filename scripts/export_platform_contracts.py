from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.schemas.platform.api_export import (
    FRONTEND_TYPE_EXPORT,
    check_frontend_type_export,
    write_frontend_type_export,
)
from src.schemas.platform.export import check_exported_contracts, write_contract_exports


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export deterministic platform JSON Schemas, C-010 OpenAPI, and frontend types."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when checked-in exports differ from the runtime contract models",
    )
    args = parser.parse_args()

    if args.check:
        drift = check_exported_contracts()
        frontend_drift = check_frontend_type_export()
        if drift or frontend_drift:
            print("Platform contract export drift detected:")
            for path in drift:
                print(f"- schemas/platform/{path}")
            if frontend_drift:
                print(f"- {FRONTEND_TYPE_EXPORT.relative_to(ROOT).as_posix()}")
            return 1
        print("Platform contract and generated frontend type exports are current.")
        return 0

    written = write_contract_exports()
    frontend = write_frontend_type_export()
    print(f"Wrote {len(written)} platform contract export files.")
    print(f"Wrote generated frontend types: {frontend.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
