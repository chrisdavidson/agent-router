"""demo-shop order service (demo fixture for agent-router)."""

import json
from pathlib import Path

from util_totals import revenue

DATA = Path(__file__).resolve().parents[1] / "data" / "orders.json"


def load_orders() -> list[dict]:
    return json.loads(DATA.read_text())["orders"]


def failed_orders(orders: list[dict]) -> list[str]:
    return [o["id"] for o in orders if o["status"] == "failed"]


def main() -> None:
    orders = load_orders()
    print(f"{len(orders)} orders, revenue {revenue(orders):.2f} USD")
    print("failed:", ", ".join(failed_orders(orders)))


if __name__ == "__main__":
    main()
