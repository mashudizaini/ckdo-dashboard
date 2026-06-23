# ── Stage 1: Build React ──────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files dulu (layer cache)
COPY package*.json ./

# Install dependencies
RUN npm install --prefer-offline || npm install

# Copy source
COPY . .

# Build production bundle
RUN npm run build


# ── Stage 2: Serve via Nginx ──────────────────────────────────────────────────
FROM nginx:alpine

# Copy build output dari stage 1
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
