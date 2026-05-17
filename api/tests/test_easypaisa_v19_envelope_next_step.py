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
