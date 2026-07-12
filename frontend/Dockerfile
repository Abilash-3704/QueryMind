# Local-dev image only: runs the Vite dev server (per spec §10.1 — "Vite dev server
# proxying to FastAPI"), not a production build. Production deploys straight to Vercel
# via `npm run build` (spec §10.4), no Docker involved there.
FROM node:20-slim

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

EXPOSE 5173

# --host so the dev server is reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
