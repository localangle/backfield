FROM node:20-alpine

# Repository-root build context (see infra/docker-compose.yml) so workspace dep
# `file:../../packages/backfield-ui` resolves.
WORKDIR /app

# Install shared UI deps first so Vite can resolve imports from mounted
# packages/backfield-ui/src (e.g. @radix-ui/react-dropdown-menu).
COPY packages/backfield-ui/package.json packages/backfield-ui/package-lock.json ./packages/backfield-ui/
WORKDIR /app/packages/backfield-ui
RUN npm ci

WORKDIR /app
COPY packages/backfield-ui ./packages/backfield-ui
COPY apps/stylebook-ui/package.json apps/stylebook-ui/package-lock.json ./apps/stylebook-ui/

WORKDIR /app/apps/stylebook-ui
RUN npm ci

COPY apps/stylebook-ui .

EXPOSE 5175
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
