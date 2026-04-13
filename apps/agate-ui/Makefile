# Flowbuilder UI Makefile
.PHONY: dev-ui build-flowbuilder-ui-prd deploy-flowbuilder-ui-prd

# Development
dev-ui:
	cd apps/flowbuilder-ui && npm run dev

# Production Build & Deployment
build-flowbuilder-ui-prd:
	@echo "🏗️  Building UI for production..."
	@cd apps/flowbuilder-ui && \
		VITE_API_BASE=$${VITE_API_BASE:-http://localhost:8000} \
		VITE_AUTH_API_BASE=$${VITE_AUTH_API_BASE:-http://localhost:8002} \
		VITE_TIMEZONE=$${VITE_TIMEZONE:-America/Chicago} \
		npm run build
	@echo "✅ UI built successfully in apps/flowbuilder-ui/dist/"

deploy-flowbuilder-ui-prd:
	@echo "🚀 Deploying UI to S3..."
	@if [ -z "$$UI_BUCKET" ]; then \
		echo "Getting bucket name from Terraform..."; \
		UI_BUCKET=$$(cd infra/terraform && terraform output -raw flowbuilder_ui_bucket_name 2>/dev/null); \
		if [ -z "$$UI_BUCKET" ]; then \
			echo "❌ Error: Could not get Flowbuilder UI bucket name from Terraform"; \
			echo "Please run: cd infra/terraform && terraform apply"; \
			exit 1; \
		fi; \
	else \
		echo "Using UI_BUCKET=$$UI_BUCKET"; \
	fi; \
	echo "Syncing to s3://$$UI_BUCKET..."; \
	aws s3 sync apps/flowbuilder-ui/dist/ s3://$$UI_BUCKET/ --delete --cache-control "max-age=31536000,public" --exclude "index.html"; \
	aws s3 cp apps/flowbuilder-ui/dist/index.html s3://$$UI_BUCKET/index.html --cache-control "max-age=0,no-cache,no-store,must-revalidate"; \
	DIST_ID=$$(cd infra/terraform && terraform output -raw flowbuilder_ui_cloudfront_distribution_id 2>/dev/null); \
	if [ -n "$$DIST_ID" ]; then \
		echo "Invalidating CloudFront cache..."; \
		aws cloudfront create-invalidation --distribution-id $$DIST_ID --paths "/*" --query 'Invalidation.Id' --output text; \
	fi; \
	UI_URL=$$(cd infra/terraform && terraform output -raw flowbuilder_ui_url 2>/dev/null); \
	echo ""; \
	echo "✅ Flowbuilder UI deployed successfully!"; \
	echo "🌐 Access at: $$UI_URL"

