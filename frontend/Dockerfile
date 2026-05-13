ARG REGISTRY_MIRROR=docker.m.daocloud.io/
FROM ${REGISTRY_MIRROR}node:20-alpine

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
CMD ["npm", "run", "dev"]
