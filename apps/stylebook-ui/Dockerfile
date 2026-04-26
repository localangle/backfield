FROM node:18-alpine

# Repository-root build context (see infra/docker-compose.yml) so workspace dep
# `file:../../packages/backfield-ui` resolves.
WORKDIR /app

COPY packages/backfield-ui ./packages/backfield-ui
COPY apps/stylebook-ui/package.json apps/stylebook-ui/package-lock.json* ./apps/stylebook-ui/

WORKDIR /app/apps/stylebook-ui
RUN npm install

COPY apps/stylebook-ui .

EXPOSE 5175
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
