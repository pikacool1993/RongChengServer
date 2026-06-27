# Docker 部署命令

本文档记录本项目在 Ubuntu 服务器上使用 Docker Compose 部署、启动、更新和排查的常用命令。

项目服务：

- `api`：FastAPI 服务，容器名 `cdrc_app`，对外端口 `8000`
- `db`：MySQL 8，容器名 `mysql_db`
- `redis`：Redis 7，容器名 `rc_redis`

## 1. 进入项目目录

```bash
cd /你的项目目录/RongChengServer
```

如果不确定当前目录是否正确，可以检查：

```bash
ls
```

应能看到：

```text
Dockerfile
docker-compose.yml
app
requirements.txt
```

## 2. 准备环境变量

首次部署时复制 `.env.example`：

```bash
cp .env.example .env
```

编辑 `.env`：

```bash
nano .env
```

Docker Compose 部署时，建议使用容器服务名连接 MySQL 和 Redis：

```env
DATABASE_URL=mysql+pymysql://root:123456@db:3306/rc_db
REDIS_URL=redis://redis:6379/0
```

保存后退出：

- `Ctrl + O` 保存
- `Enter` 确认
- `Ctrl + X` 退出

## 3. 首次部署

首次构建镜像并后台启动：

```bash
docker compose up -d --build
```

查看容器状态：

```bash
docker compose ps
```

查看 API 日志：

```bash
docker compose logs -f api
```

本机测试 API 是否启动：

```bash
curl http://127.0.0.1:8000
```

后台管理页面：

```text
http://服务器公网IP:8000/admin-ui/orders
```

## 4. 只启动，不更新

如果容器已经创建过，只是想启动现有容器，不拉代码、不重建镜像：

```bash
docker compose start
```

如果不确定容器是否存在，但明确不想重新构建镜像：

```bash
docker compose up -d --no-build
```

只重启 API：

```bash
docker compose restart api
```

重启全部服务：

```bash
docker compose restart
```

## 5. 停止服务

停止全部容器，但保留容器和数据：

```bash
docker compose stop
```

停止并删除容器，但保留 MySQL 数据卷：

```bash
docker compose down
```

不要随便执行下面这个命令，除非确认要删除数据库数据：

```bash
docker compose down -v
```

## 6. 更新代码后发布

拉取最新代码：

```bash
git pull
```

重新构建并后台启动：

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

查看 API 日志：

```bash
docker compose logs -f api
```

## 7. 修改 .env 后生效

如果只改了 `.env`，通常不需要重新构建镜像，重建容器即可：

```bash
docker compose up -d --force-recreate
```

也可以只重建 API 容器：

```bash
docker compose up -d --force-recreate api
```

## 8. 日志查看

查看全部服务日志：

```bash
docker compose logs -f
```

查看 API 日志：

```bash
docker compose logs -f api
```

查看 MySQL 日志：

```bash
docker compose logs -f db
```

查看 Redis 日志：

```bash
docker compose logs -f redis
```

查看最近 200 行 API 日志：

```bash
docker compose logs --tail=200 api
```

## 9. 进入容器

进入 API 容器：

```bash
docker exec -it cdrc_app bash
```

进入 MySQL 容器：

```bash
docker exec -it mysql_db bash
```

进入 Redis 容器：

```bash
docker exec -it rc_redis sh
```

## 10. 数据库操作

进入 MySQL：

```bash
docker exec -it mysql_db mysql -uroot -p
```

输入 `docker-compose.yml` 中配置的密码：

```text
123456
```

选择数据库：

```sql
USE rc_db;
```

查看表：

```sql
SHOW TABLES;
```

查看订单数量：

```sql
SELECT COUNT(*) FROM orders;
```

退出 MySQL：

```sql
exit;
```

## 11. Redis 检查

进入 Redis CLI：

```bash
docker exec -it rc_redis redis-cli
```

测试 Redis：

```bash
ping
```

正常返回：

```text
PONG
```

退出：

```bash
exit
```

## 12. Nginx 反向代理

如果域名通过 Nginx 转发到 Docker API，常用配置如下：

```nginx
server {
    listen 80;
    server_name pikacool.cn www.pikacool.cn;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

测试 Nginx 配置：

```bash
sudo nginx -t
```

重载 Nginx：

```bash
sudo systemctl reload nginx
```

查看 Nginx 状态：

```bash
sudo systemctl status nginx
```

## 13. HTTPS 证书

安装 Certbot：

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
```

申请证书：

```bash
sudo certbot --nginx -d pikacool.cn -d www.pikacool.cn
```

测试自动续期：

```bash
sudo certbot renew --dry-run
```

## 14. 端口检查

查看服务器监听端口：

```bash
sudo ss -lntp
```

检查 API 端口：

```bash
curl http://127.0.0.1:8000
```

检查域名 HTTP：

```bash
curl -I http://pikacool.cn
```

检查域名 HTTPS：

```bash
curl -I https://pikacool.cn
```

## 15. 常见问题

### 15.1 容器没启动

```bash
docker compose ps
docker compose logs --tail=200 api
```

### 15.2 API 连不上数据库

检查 `.env`：

```env
DATABASE_URL=mysql+pymysql://root:123456@db:3306/rc_db
```

检查 MySQL 是否健康：

```bash
docker compose ps db
docker compose logs --tail=200 db
```

### 15.3 Redis 连不上

检查 `.env`：

```env
REDIS_URL=redis://redis:6379/0
```

检查 Redis：

```bash
docker compose ps redis
docker compose logs --tail=200 redis
```

### 15.4 域名打不开

依次检查：

```bash
curl http://127.0.0.1:8000
sudo nginx -t
sudo systemctl status nginx
curl -I http://pikacool.cn
```

还需要确认：

- 阿里云 DNS 已经把 `pikacool.cn` 解析到腾讯云服务器公网 IP
- 腾讯云安全组已放行 `80` 和 `443`
- 如果直接访问 `:8000`，腾讯云安全组也需要放行 `8000`

## 16. 推荐日常命令

日常只启动：

```bash
docker compose up -d --no-build
```

日常看日志：

```bash
docker compose logs -f api
```

更新发布：

```bash
git pull
docker compose up -d --build
docker compose logs -f api
```

只重启 API：

```bash
docker compose restart api
```
