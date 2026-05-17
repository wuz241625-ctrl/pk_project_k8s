# EasyPaisa Envelope Next Step Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 EasyPaisa 所有带 `phase` / `next_phase` 返回体的 `next_step`，让 App 不再猜下一步动作。

**Architecture:** 保持当前状态机、Redis、DB、上游调用顺序不变，只补 response envelope 字段。用 AST 扫描测试守护协议：任何直接返回的 `data` 字典只要含 `phase` 或 `next_phase`，就必须含 `next_step`。

**Tech Stack:** Python 3.12、pytest、AST 源码扫描、GitNexus。

---

### Task 1: 写失败测试

**Files:**
- Create: `api/tests/test_easypaisa_v19_envelope_next_step.py`

- [x] **Step 1: 新增 AST 扫描测试**

```python
import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "application/app/login/banks/easypaisa.py"


class ResponseReturnVisitor(ast.NodeVisitor):
    def __init__(self):
        self.function_stack = []
        self.missing_next_step = []

    def visit_AsyncFunctionDef(self, node):
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_FunctionDef(self, node):
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Return(self, node):
        value = node.value
        if not isinstance(value, ast.Dict):
            return
        for key, data_node in zip(value.keys, value.values):
            if not (isinstance(key, ast.Constant) and key.value == "data"):
                continue
            if not isinstance(data_node, ast.Dict):
                continue
            keys = [
                item.value
                for item in data_node.keys
                if isinstance(item, ast.Constant)
            ]
            if ("phase" in keys or "next_phase" in keys) and "next_step" not in keys:
                self.missing_next_step.append(
                    f"{self.function_stack[-1]}:{node.lineno}:{keys}"
                )


def test_all_phase_envelopes_include_next_step():
    tree = ast.parse(SOURCE.read_text())
    visitor = ResponseReturnVisitor()
    visitor.visit(tree)

    assert visitor.missing_next_step == []
```

- [x] **Step 2: 运行红灯**

Run: `cd api && python3 -m pytest tests/test_easypaisa_v19_envelope_next_step.py -q`

Expected: FAIL，列出缺少 `next_step` 的返回体。

执行记录：红灯通过，测试列出 16 个缺少 `next_step` 的返回体。

### Task 2: 补齐返回体

**Files:**
- Modify: `api/application/app/login/banks/easypaisa.py`

- [x] **Step 1: 给首次指纹采集入口补 next_step**

在 `_complete_login_step1_direct_success` 和 `verify_otp_http` 的首次指纹采集返回体中加入：

```python
'next_step': 'upload_fingerprint',
```

- [x] **Step 2: 给指纹失败与冷却返回补 next_step**

在 `_verify_otp_fallback_chain`、`_reuse_local_fingerprint_after_otp`、`verify_fingerprint_http` 的 `OTP_VERIFIED` 返回体中加入：

```python
'next_step': 'upload_fingerprint',
```

- [x] **Step 3: 给指纹验证成功与 secondLogin 冷却补 next_step**

`verify_fingerprint_http` 成功返回加入：

```python
'next_step': 'second_login',
```

`second_login_http` cooldown 返回加入：

```python
'next_step': 'second_login',
```

- [x] **Step 4: 给 PIN、查询账号、选账号返回补 next_step**

`change_pin_http` PIN 被拒返回加入 `next_step=change_pin`。

`query_accts_http` 成功返回加入 `next_step=select_accts`。

`select_accts_http` 成功返回加入 `next_step=ready`。

- [x] **Step 5: 给历史 fallback 返回补 next_step**

`_fallback_to_first_login` 的失败返回加入 `next_step=pre_login`，回退到 OTP 的返回加入 `next_step=verify_otp`。

### Task 3: 文档与验收

**Files:**
- Modify: `api/build.md`
- Modify: `api/err.md`
- Modify: `docs/superpowers/plans/2026-05-17-easypaisa-envelope-next-step-closure.md`

- [x] **Step 1: 更新构建文档**

在 `api/build.md` 增加 EasyPaisa envelope 验收命令：

```bash
cd api && python3 -m pytest tests/test_easypaisa_v19_envelope_next_step.py -q
```

- [x] **Step 2: 更新排错文档**

在 `api/err.md` 记录缺少 `next_step` 的症状、原因、修复、验证命令。

- [x] **Step 3: 运行验收**

Run:

```bash
cd api && python3 -m py_compile application/app/login/banks/easypaisa.py
cd api && python3 -m pytest tests/test_easypaisa_v19_envelope_next_step.py -q
cd api && python3 -m pytest tests/ -q -k easypaisa
git diff --check
```

Expected: 全部通过。

执行记录：

- `cd api && python3 -m py_compile application/app/login/banks/easypaisa.py`：通过。
- `cd api && python3 -m pytest tests/test_easypaisa_v19_envelope_next_step.py tests/test_easypaisa_v19_acceptance.py tests/test_easypaisa_v19_fingerprint.py -q`：20 passed。
- `cd api && python3 -m pytest tests/ -q -k easypaisa`：158 passed, 152 deselected。
- `git diff --check`：通过。

- [x] **Step 4: GitNexus detect、提交并推送**

Run:

```bash
git add api/application/app/login/banks/easypaisa.py api/tests/test_easypaisa_v19_envelope_next_step.py api/build.md api/err.md docs/superpowers/specs/2026-05-17-easypaisa-envelope-next-step-closure-design.md docs/superpowers/plans/2026-05-17-easypaisa-envelope-next-step-closure.md
git commit -m "fix(easypaisa): close envelope next step gaps"
git push origin d7pay
```

执行记录：

- GitNexus `detect_changes(scope=staged)`：risk_level=high；原因是 `easypaisa.py` 的多个登录入口返回体被触达。实际改动只补 response envelope 字段，不改状态推进、锁、Redis、DB 或上游调用。
- 提交：`fix(easypaisa): close envelope next step gaps`。
