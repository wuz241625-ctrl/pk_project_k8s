EMERGENCY_STOP = -2
NO_ORDERS = -1
NO_AVAILABLE_ACCOUNTS = 0
ALL_FAILED = 1


def should_return_account_to_pool(preallocated_mode: bool) -> bool:
    return not preallocated_mode


def classify_round_state(success_count: int, processed_count: int) -> str:
    if processed_count == EMERGENCY_STOP:
        return "emergency_stop"
    if success_count > 0:
        return "success"
    if processed_count == NO_ORDERS:
        return "no_orders"
    if processed_count == NO_AVAILABLE_ACCOUNTS:
        return "no_available_accounts"
    return "all_failed"
