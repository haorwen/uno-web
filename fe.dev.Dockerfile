FROM node:20-alpine as builder

WORKDIR /code

RUN npm install pnpm -g

# 设置 pnpm 使用国内镜像
RUN pnpm config set registry https://registry.npmmirror.com/
RUN pnpm config set electron_mirror https://npmmirror.com/mirrors/electron/

ADD ./UNO-client/package.json ./UNO-client/pnpm-lock.yaml /code/
RUN pnpm i

ADD ./UNO-client /code/
RUN pnpm build

FROM nginx:alpine
ADD nginx.dev.conf /etc/nginx/conf.d/default.conf
COPY --from=builder code/dist /usr/share/nginx/html
