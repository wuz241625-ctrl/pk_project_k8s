SHELL := /bin/bash

D7PAY_DIR := ops/tenants/d7pay
D7PAY_DEPLOY_SERVICES := api admin merchant admin-h5 merchant-h5 apkdownload

.PHONY: d7pay-preflight d7pay-render-config d7pay-deploy d7pay-deploy-service d7pay-healthcheck d7pay-rollback
.PHONY: $(addprefix d7pay-deploy-,$(D7PAY_DEPLOY_SERVICES))

d7pay-preflight:
	@bash $(D7PAY_DIR)/scripts/preflight.sh

d7pay-render-config:
	@bash $(D7PAY_DIR)/scripts/render-config.sh

d7pay-deploy:
	@bash $(D7PAY_DIR)/jenkins/deploy-d7pay.sh

d7pay-deploy-service:
	@if [ -z "$(SERVICE)" ]; then \
		echo "缺少 SERVICE，支持: $(D7PAY_DEPLOY_SERVICES)" >&2; \
		exit 1; \
	fi
	@D7PAY_DEPLOY_TARGETS="$(SERVICE)" bash $(D7PAY_DIR)/jenkins/deploy-d7pay.sh

d7pay-deploy-api d7pay-deploy-admin d7pay-deploy-merchant d7pay-deploy-admin-h5 d7pay-deploy-merchant-h5 d7pay-deploy-apkdownload:
	@D7PAY_DEPLOY_TARGETS="$(patsubst d7pay-deploy-%,%,$@)" bash $(D7PAY_DIR)/jenkins/deploy-d7pay.sh

d7pay-healthcheck:
	@bash $(D7PAY_DIR)/scripts/healthcheck.sh

d7pay-rollback:
	@bash $(D7PAY_DIR)/scripts/rollback.sh
