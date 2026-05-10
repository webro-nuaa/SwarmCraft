ARG REGISTRY_MIRROR=docker.1ms.run/
FROM ${REGISTRY_MIRROR}node:20-alpine

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
CMD ["npm", "run", "dev"]
