FROM python:3.11-slim

WORKDIR /app

# 复制所有文件（包含 bot.py）
COPY . /app

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 创建数据文件夹
RUN mkdir -p /app/data/groups /app/data/logs/private_chats

# 将 start.sh 复制并赋权
RUN chmod +x /app/start.sh

EXPOSE 10000

ENV WEB_PORT=10000

CMD ["/bin/bash", "start.sh"]
