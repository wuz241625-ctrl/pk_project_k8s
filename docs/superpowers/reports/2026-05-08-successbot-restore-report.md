# SuccessBot 恢复验收报告

## 背景

上一次死代码清理把 `/order/successBot` 和 `SuccessBot` 一并删除。用户确认该机器人回调仍需使用，因此本次按最小范围恢复。

## 本次恢复内容

- 恢复 `/order/successBot` 路由。
- 恢复 `SuccessBot` 类。
- 恢复 AU C / NAGERCOIL ENBL 的机器人账单解析。
- 恢复通过 `callback.success_df()` 完成代付确认的链路。

## 未恢复内容

- 未恢复 `check_upi()`。
- 未恢复 `save_upi_to_history()`。
- 未恢复 EasyPaisa/JazzCash 旧 UPI 写入路径。

## 验收命令

```bash
rg -n "url\\('/order/successBot'|class SuccessBot|def check_upi|def save_upi_to_history" api/router.py api/application/pay/order.py -S
python3 -m py_compile api/router.py api/application/pay/order.py
git diff --check
npx gitnexus analyze --skip-agents-md --worker-timeout 120 --max-file-size 32768
```

## 验收结果

- 路由和 `SuccessBot` 类已恢复。
- `check_upi()` / `save_upi_to_history()` 未恢复。
- Python 编译通过；`api/router.py` 仍有历史 `\S` 转义 `SyntaxWarning`，不是本次新增。
- 空白检查通过。
- GitNexus 索引通过。
