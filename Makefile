SHELL := /bin/bash

D7PAY_DIR := ops/tenants/d7pay

.PHONY: d7pay-preflight d7pay-render-config d7pay-deploy d7pay-healthcheck d7pay-rollback

d7pay-preflight:
	@bash $(D7PAY_DIR)/scripts/preflight.sh

d7pay-render-config:
	@bash $(D7PAY_DIR)/scripts/render-config.sh

d7pay-deploy:
	@bash $(D7PAY_DIR)/jenkins/deploy-d7pay.sh

d7pay-healthcheck:
	@bash $(D7PAY_DIR)/scripts/healthcheck.sh

d7pay-rollback:
	@bash $(D7PAY_DIR)/scripts/rollback.sh
