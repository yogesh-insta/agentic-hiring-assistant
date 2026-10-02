FROM node:24-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/tsconfig.json apps/web/styles.css ./
COPY apps/web/src ./src
COPY apps/web/index.html apps/web/interview.html ./
RUN npm install && npm run build

FROM golang:1.26-alpine AS gobuild
WORKDIR /src
COPY services/api/go.mod ./
COPY services/api/*.go ./
RUN go build -o /out/api .

FROM alpine:3.22
WORKDIR /app
COPY --from=gobuild /out/api /app/api
COPY --from=web /web/index.html /web/interview.html /web/
COPY --from=web /web/dist /web/dist
ENV WEB_DIR=/web
EXPOSE 8080
CMD ["/app/api"]
