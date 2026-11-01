# =============================================================================
# OVARA · frontend (Node.js + Express): página web que envía la imagen al backend
#
# Forma recomendada de ejecutarlo: junto con el backend, desde la carpeta OVARA
#     iniciar_demo.bat                      (todo en un paso)
#     docker compose up --build -d          (manual)  ->  http://localhost:3000
#
# Ejecutarlo solo, desde la carpeta OVARA (requiere un backend en el puerto 8000):
#   1) Construir:          docker build -t ovara-frontend:1.0.0 ./frontend
#   2) Ejecutar (Windows): docker run --rm -p 3000:3000 -e BACKEND_URL=http://host.docker.internal:8000 ^
#                              -v "%cd%\ejemplos:/ejemplos:ro" -e EJEMPLOS_DIR=/ejemplos ovara-frontend:1.0.0
#   3) Abrir:              http://localhost:3000
#   Pruebas unitarias:     docker run --rm ovara-frontend:1.0.0 npm test
# =============================================================================
FROM node:22-alpine

ENV NODE_ENV=production PORT=3000
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund && npm cache clean --force

COPY server.js ./
COPY public ./public
COPY test ./test

USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=4s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/api/version >/dev/null || exit 1

CMD ["node", "server.js"]
