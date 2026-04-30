#!/usr/bin/env python3
import argparse
import os
import pathlib
import sys


RESERVED_DOMAIN_MARKERS = ("awekay.com", "example.com", ".example")


def require_env(name):
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"缺少环境变量: {name}")
    return value


def reject_reserved(name, value, allow_placeholder):
    if allow_placeholder:
        return
    if any(marker in value for marker in RESERVED_DOMAIN_MARKERS):
        raise SystemExit(f"{name} 必须替换为 D7pay 客户自有域名，当前值不能用于发布: {value}")


def render(source_path, allow_placeholder=False):
    api_domain = require_env("API_DOMAIN")
    reject_reserved("API_DOMAIN", api_domain, allow_placeholder)
    api_scheme = os.environ.get("API_PUBLIC_SCHEME", "http")
    values = {
        "API_PAY_URL": f"{api_scheme}://{api_domain}/api/order/",
        "API_OSPAY_API_HOST": f"{api_scheme}://{api_domain}/api",
        "API_WEBSOCKET_ALLOW_HOST": os.environ.get("API_WEBSOCKET_ALLOW_HOST", api_domain),
        "ADMIN_API_URL": os.environ.get("ADMIN_API_URL", "http://api:9000"),
        "MERCHANT_API_URL": os.environ.get("MERCHANT_API_URL", "http://api:9000"),
    }

    lines = []
    for line in pathlib.Path(source_path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        matched = False
        for key, value in values.items():
            if stripped.startswith(f"{key}:"):
                indent = line[: len(line) - len(line.lstrip())]
                lines.append(f"{indent}{key}: {value}")
                matched = True
                break
        if not matched:
            lines.append(line)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="渲染 D7pay runtime ConfigMap")
    parser.add_argument(
        "--source",
        default="ops/tenants/d7pay/k8s/runtime-configmap.yaml",
        help="源 ConfigMap 模板路径",
    )
    parser.add_argument("--output", default="-", help="输出路径；使用 - 输出到 stdout")
    parser.add_argument("--allow-placeholder", action="store_true", help="允许 example.com 占位域名，仅用于本地合同校验")
    args = parser.parse_args()

    text = render(args.source, allow_placeholder=args.allow_placeholder)
    if args.output == "-":
        sys.stdout.write(text)
    else:
        output_path = pathlib.Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
