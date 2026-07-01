FROM node:18-alpine

# Repository-root build context (see infra/docker-compose.yml) so workspace dep
# `file:../../packages/backfield-ui` resolves.
WORKDIR /app

# Install shared UI deps first so Vite can resolve imports from mounted
# packages/backfield-ui/src (e.g. @radix-ui/react-dropdown-menu).
COPY packages/backfield-ui/package.json packages/backfield-ui/package-lock.json* ./packages/backfield-ui/
WORKDIR /app/packages/backfield-ui
RUN npm install

WORKDIR /app
COPY packages/backfield-ui ./packages/backfield-ui
COPY apps/agate-ui/package.json apps/agate-ui/package-lock.json* ./apps/agate-ui/

WORKDIR /app/apps/agate-ui
RUN npm install

COPY apps/agate-ui .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
