FROM node:20-alpine

WORKDIR /app/apps/api-playground

COPY apps/api-playground/package.json apps/api-playground/package-lock.json ./
RUN npm ci

COPY apps/api-playground .

EXPOSE 5176
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
