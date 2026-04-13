FROM node:20-bookworm-slim

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
EXPOSE 5175
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
