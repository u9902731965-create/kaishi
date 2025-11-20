# app.py
import os
from bot import init_bot

if __name__ == "__main__":
    print("=" * 50)
    print("🚀 启动财务记账机器人 (JSON 本地文件 + Polling 模式)")
    print("=" * 50)

    # 可选：确保 PORT 有默认值（给 Render / UptimeRobot 健康检查用）
    if "PORT" not in os.environ:
        os.environ["PORT"] = "10000"

    init_bot()
