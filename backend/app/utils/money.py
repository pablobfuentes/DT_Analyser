from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def to_decimal(value: str | float | int | Decimal | None, default: Decimal | None = None) -> Decimal | None:
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return default


def quantize_price(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def quantize_quantity(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def calculate_gross_pnl(direction: str, avg_entry: Decimal, avg_exit: Decimal, quantity: Decimal) -> Decimal:
    if direction == "LONG":
        return (avg_exit - avg_entry) * quantity
    return (avg_entry - avg_exit) * quantity


def calculate_net_pnl(gross_pnl: Decimal, fees: Decimal | None) -> Decimal:
    fee = fees or Decimal("0")
    return gross_pnl - fee


def pnl_mismatch(calculated: Decimal, reported: Decimal | None, tolerance: Decimal) -> bool:
    if reported is None:
        return False
    return abs(calculated - reported) > tolerance
