"""Print category item counts from ListOFservicesforInvoices_v.1.2.xlsx."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.services.category_tasks import categories_status


def main() -> None:
    print(json.dumps(categories_status(), indent=2))


if __name__ == "__main__":
    main()
