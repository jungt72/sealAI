FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS build

# The base image is Alpine 3.23; every build package is version-bound.
RUN apk add --no-cache \
    python3=3.12.13-r0 \
    make=4.4.1-r3 \
    g++=15.2.0-r2 \
    vips-dev=8.17.3-r1

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build --chown=node:node /app /app
USER node
EXPOSE 1337
CMD ["npm", "run", "start"]
