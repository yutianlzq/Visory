from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.schemas.platform.export import check_exported_contracts, write_contract_exports


def main() -> int:
    parser = argparse.ArgumentParser(description="Export deterministic platform contract JSON Schemas.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when checked-in exports differ from the runtime contract models",
    )
    args = parser.parse_args()

    if args.check:
        drift = check_exported_contracts()
        if drift:
            print("Platform contract export drift detected:")
            for path in drift:
                print(f"- {path}")
            return 1
        print("Platform contract exports are current.")
        return 0

    written = write_contract_exports()
    print(f"Wrote {len(written)} platform contract export files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
