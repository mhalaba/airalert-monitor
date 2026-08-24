FROM node:20-alpine AS build
WORKDIR /app
# Adres API wbudowywany w bundel w czasie buildu (NEXT_PUBLIC_* jest statyczny)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY package.json ./
RUN npm install
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=build /app /app
EXPOSE 3000
CMD ["npm", "run", "start"]
