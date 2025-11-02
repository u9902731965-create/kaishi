#!/bin/bash
# 启动脚本 - 同时运行Telegram Bot和Web应用

echo "🚀 启动Telegram财务Bot和Web查账系统..."

# 在后台启动Web应用
echo "🌐 启动Web查账系统 (端口 5000)..."
python web_app.py &
WEB_PID=$!

# 等待1秒确保Web应用启动
sleep 1

# 启动Telegram Bot（前台运行）
echo "🤖 启动Telegram Bot..."
python bot.py &
BOT_PID=$!

echo "✅ 两个服务已启动"
echo "   - Telegram Bot (PID: $BOT_PID)"
echo "   - Web应用 (PID: $WEB_PID)"

# 等待任一进程退出
wait -n

# 如果任一进程退出，杀死另一个
echo "❌ 检测到进程退出，正在关闭所有服务..."
kill $WEB_PID $BOT_PID 2>/dev/null

exit $?
