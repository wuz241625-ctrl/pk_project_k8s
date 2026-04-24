def _truncate(value, max_len=12):
    """Truncate long strings to 'first8...last4' format."""
    s = str(value)
    if len(s) <= max_len:
        return s
    return s[:8] + "..." + s[-4:]


def build_otherpay_option(row):
    option = {
        "id": row["id"],
        "name": row.get("name"),
        "merchant_id": row.get("merchant_id"),
    }

    parts = []
    if option["name"]:
        parts.append(str(option["name"]))
    if option["merchant_id"]:
        parts.append(_truncate(option["merchant_id"]))
    parts.append(f"#{option['id']}")

    option["label"] = " | ".join(parts)
    return option
