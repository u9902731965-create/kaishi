#!/bin/bash
# 启动脚本 - 统一Flask应用（PostgreSQL版本）

echo "🚀 启动Telegram财务Bot (PostgreSQL版本)..."
echo "📋 环境变量检查："
echo "   PORT=${PORT:-未设置}"
echo "   DATABASE_URL=${DATABASE_URL:+已设置}"
echo "   TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:+已设置}"
echo "   OWNER_ID=${OWNER_ID:-未设置}"
echo "   WEBHOOK_URL=${WEBHOOK_URL:-未设置}"
echo "   SESSION_SECRET=${SESSION_SECRET:+已设置}"

# 初始化数据库
echo ""
echo "🗄️  初始化数据库..."
python -c "import database; database.init_database()" 2>&1 || {
    echo "⚠️  数据库初始化失败，但继续启动..."
}

# 启动统一Flask应用（Bot Webhook + Web Dashboard）
echo ""
echo "🌐 启动Flask应用（Bot + Web Dashboard）..."
python app.py 2>&1 &
APP_PID=$!
echo "   - 应用 PID: $APP_PID"

echo ""
echo "✅ 应用已启动"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Web Dashboard: http://0.0.0.0:${PORT:-5000}"
echo "🤖 Telegram Bot: Webhook模式"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 健康检查函数
check_app_health() {
    if ! kill -0 $APP_PID 2>/dev/null; then
        echo "❌ Flask应用进程已退出，尝试重启..."
        python app.py 2>&1 &
        APP_PID=$!
        echo "   - 新的应用 PID: $APP_PID"
    fi
}

# 无限循环保持容器运行
echo ""
echo "🔄 进入监控循环（每30秒检查一次）..."
while true; do
    sleep 30
    check_app_health
done
