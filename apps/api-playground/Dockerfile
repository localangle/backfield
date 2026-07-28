FROM node:20-alpine

# Repository-root build context (see infra/docker-compose.yml) so workspace dep
# `file:../../packages/backfield-ui` resolves.
WORKDIR /app

# Install shared UI deps first so Vite can resolve imports from mounted
# packages/backfield-ui/src (e.g. lucide-react).
COPY packages/backfield-ui/package.json packages/backfield-ui/package-lock.json ./packages/backfield-ui/
WORKDIR /app/packages/backfield-ui
RUN npm ci

WORKDIR /app
COPY packages/backfield-ui ./packages/backfield-ui
COPY apps/api-playground/package.json apps/api-playground/package-lock.json ./apps/api-playground/

WORKDIR /app/apps/api-playground
RUN npm ci

COPY apps/api-playground .

EXPOSE 5176
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
