"""Revenue helpers for demo-shop."""


def revenue(orders: list[dict]) -> float:
    """Sum of totals for paid orders (refunded and failed orders are excluded)."""
    return sum(o["total"] for o in orders if o["status"] == "paid")


def average_order_value(orders: list[dict]) -> float:
    paid = [o for o in orders if o["status"] == "paid"]
    return revenue(paid) / len(paid) if paid else 0.0
