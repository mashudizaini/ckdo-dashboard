# ── Stage 1: Build React ─────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build


# ── Stage 2: Serve via Nginx ──────────────────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config: proxy /api → backend, serve React untuk semua route
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
