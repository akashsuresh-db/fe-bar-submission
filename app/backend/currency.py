"""Display currency. The data layer stores INR; every amount the app shows is in US dollars."""

INR_PER_USD = 88.0


def usd(amount_inr: float | int | None, exact: bool = False) -> str:
    """Format an INR amount as US dollars: $1.23M, $45.6K, $789 (or $1,234.56 when exact)."""
    if amount_inr is None:
        return "—"
    v = float(amount_inr) / INR_PER_USD
    if exact:
        return f"${v:,.2f}"
    sign, a = ("-" if v < 0 else ""), abs(v)
    if a >= 1e6:
        return f"{sign}${a / 1e6:.2f}M"
    if a >= 1e3:
        return f"{sign}${a / 1e3:.1f}K"
    return f"{sign}${a:,.0f}"
