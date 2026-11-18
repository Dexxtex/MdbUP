# syntax=docker/dockerfile:1.7

# MdbUP — immagine del frontend: build Node 20 + runtime Nginx 1.27 (non-root).
#
# Build (contesto = frontend/):
#   docker build -t mdbup-frontend:local frontend/
#
# Prerequisiti forniti dalla lane frontend: package.json, package-lock.json
# e gli script npm `build` (vite build). Nessun segreto entra nell'immagine:
# l'applicazione parla solo con /api sullo stesso host (vedi deploy/Caddyfile).

# ---------------------------------------------------------------------------
# Stage 1 — build statica con Vite.
# ---------------------------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# Il lockfile è obbligatorio: build riproducibili e cache npm in CI.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — runtime: solo gli asset statici, serviti da Nginx.
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Configurazione completa (SPA fallback, /healthz, compressione, cache asset).
COPY nginx.conf /etc/nginx/nginx.conf
RUN rm -f /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

# UID/GID 101 = utente `nginx` dell'immagine ufficiale. La porta 8080 non è
# privilegiata: nessun bisogno di root. /var/cache/nginx e /var/run sono tmpfs
# nel compose, perché il rootfs è read-only.
USER 101:101

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
