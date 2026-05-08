"""退役的共享余额 worker。

EasyPaisa 和 JazzCash 的余额/限额查询已经分别由各自 monitor 负责。
保留这个入口只是为了让历史启动命令安全退出，避免再次产生重复官方查询。
"""

RETIRED_WORKER_NAME = "update_payment_balance"
RETIREMENT_MESSAGE = (
    "update_payment_balance 已退役：请使用 "
    "jobs/easypaisa/easypaisa_monitor.py 和 jobs/jazzcash/jazzcash_monitor.py "
    "维护钱包余额/限额缓存。"
)


def main():
    print(RETIREMENT_MESSAGE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
