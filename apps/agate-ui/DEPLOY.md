# Flowbuilder UI – Production deployment

Build the production bundle and deploy to S3, then invalidate CloudFront. Requires Terraform to have created the Flowbuilder UI bucket and CloudFront distribution; see root [DEPLOY.md](../../DEPLOY.md).

## Build

Point the build at your production API and Auth API URLs:

```bash
make build-flowbuilder-ui-prd \
  VITE_API_BASE=https://flowbuilder-api.agate.localangle.co \
  VITE_AUTH_API_BASE=https://auth-api.agate.localangle.co
```

Optional: `VITE_TIMEZONE=America/Chicago` (default).

## Deploy

```bash
make deploy-flowbuilder-ui-prd
```

This syncs `apps/flowbuilder-ui/dist/` to the Terraform-created S3 bucket and invalidates CloudFront. The bucket and distribution ID come from Terraform outputs.

## DNS

Point your UI domain (e.g. `flowbuilder.agate.localangle.co`) to the CloudFront domain from Terraform output `flowbuilder_ui_cloudfront_domain`.
