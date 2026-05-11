# D7pay Go Worker K8s 切流验收报告

## 处理范围

- 新增 `pk-d7pay` namespace 的 Go worker 四个 Deployment 合同。
- 新增 API Web-only start 模板，切流后 Python jobs 退役。
- 同步 Go worker 所需 MySQL schema。
- 更新 D7pay Jenkins、SOP、build、runbook、验收、排错和托管文档。
- 修正并记录 Go worker 对无时区 `tradeTime/TRX_DTTM` 的巴基斯坦时间转 UTC 规则。

## 验收命令

```bash
python3 ops/tenants/d7pay/verify_release_contract.py
python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v
python3 - <<'PY'
import pathlib, yaml
for path in sorted(pathlib.Path('ops/tenants/d7pay/k8s').glob('*.yaml')):
    with path.open(encoding='utf-8') as handle:
        list(yaml.safe_load_all(handle))
print('yaml ok')
PY
bash -n ops/tenants/d7pay/runtime/api-start-web-only.sh
cd /Users/tear/pk-go-worker && go test ./... && go vet ./... && go build ./cmd/worker
cd /Users/tear/pk-go-worker && go test ./internal/collect -run TestParseStatementTimeTreatsNaiveTradeTimeAsPakistanAndReturnsUTC -v
npx gitnexus detect-changes --repo pk_project_k8s
```

## 结果

- `python3 ops/tenants/d7pay/verify_release_contract.py`：通过，输出 `D7pay release contract OK`。
- `python3 -m unittest ops.tenants.d7pay.tests.test_config_only_release -v`：通过，10 个测试全部 `ok`。
- D7pay K8s YAML 解析：通过，输出 `yaml ok`。
- `bash -n ops/tenants/d7pay/runtime/api-start-web-only.sh`：通过。
- `cd /Users/tear/pk-go-worker && go test ./... && go vet ./... && go build ./cmd/worker`：通过。
- `go test ./internal/collect -run TestParseStatementTimeTreatsNaiveTradeTimeAsPakistanAndReturnsUTC -v`：通过。
- `npx gitnexus detect-changes --repo pk_project_k8s --scope staged`：通过，17 个文件、20 个符号、0 个受影响流程、风险 low。
