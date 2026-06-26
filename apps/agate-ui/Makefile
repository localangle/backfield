# Agate UI Makefile — local dev helpers and same-origin production builds.
.PHONY: dev build-prd

dev:
	npm run dev

# Same-origin production bundle for S3/CloudFront (relative API paths; session on /v1).
build-prd:
	@echo "Building Agate UI for production (same-origin API bases)..."
	npm run build
	@echo "Output: dist/ (sync to your static host; index.html with no-cache)"
