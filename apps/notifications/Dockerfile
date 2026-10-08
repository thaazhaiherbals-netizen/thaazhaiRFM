# Built from the repository root so the service can read db/migrations/016:
#   docker build -f apps/notifications/Dockerfile .
# On Railway: root directory "/" and RAILWAY_DOCKERFILE_PATH=apps/notifications/Dockerfile.
FROM node:22-alpine

WORKDIR /app/apps/notifications
COPY apps/notifications/package.json apps/notifications/package-lock.json ./
RUN npm ci --omit=dev

COPY apps/notifications/src ./src
COPY db/migrations/016_order_notifications.sql /app/db/migrations/

ENV NODE_ENV=production
USER node
CMD ["node", "src/index.js"]
