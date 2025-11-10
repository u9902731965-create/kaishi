# 📘 AlwaysData部署指南

将Telegram财务Bot部署到AlwaysData的完整指南（Webhook模式 + PostgreSQL）

---

## 🎯 部署架构

- **应用类型**：Python WSGI（Flask）
- **Bot模式**：Webhook（而不是Polling）
- **数据库**：PostgreSQL
- **文件**：`app.py`（统一Flask应用）+ `wsgi.py`（WSGI入口）

---

## 📋 前期准备

### 1. 注册AlwaysData账号

访问：https://www.alwaysdata.com/
- 免费套餐提供100MB存储
- 包含PostgreSQL数据库
- 支持Python 3.11

### 2. 准备Telegram Bot Token

与BotFather对话获取Bot Token：
1. 在Telegram搜索 `@BotFather`
2. 发送 `/newbot` 创建新bot
3. 获取Bot Token（格式：`1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`）
4. 获取您的Telegram User ID（可以通过`@userinfobot`获取）

---

## 🚀 部署步骤

### 步骤1：创建PostgreSQL数据库

1. **登录AlwaysData控制面板**
2. **进入 `Databases > PostgreSQL`**
3. **点击 `Add a database`**
   - 数据库名格式：`your_account_dbname`
   - 例如：`david_financebot`
4. **创建数据库用户**（如果还没有）
   - 用户名：`your_account`
   - 密码：设置强密码
5. **记录连接信息**：
   ```
   Host: postgresql-your_account.alwaysdata.net
   Port: 5432
   Database: your_account_dbname
   User: your_account
   Password: your_password
   ```

### 步骤2：上传代码

#### 方法A：通过SSH（推荐）

```bash
# 1. 连接到AlwaysData SSH
ssh your_account@ssh-your_account.alwaysdata.net

# 2. 克隆代码仓库
cd ~/
git clone https://github.com/your-username/tron-calculator-rental.git
cd tron-calculator-rental

# 或者手动创建项目目录并上传文件
mkdir -p ~/financebot
cd ~/financebot
# 然后通过SFTP上传文件
```

#### 方法B：通过SFTP

使用FileZilla或其他SFTP客户端：
- 主机：`ssh-your_account.alwaysdata.net`
- 用户名：`your_account`
- 密码：您的SSH密码
- 上传所有文件到 `~/financebot/` 目录

**必须上传的文件**：
- `app.py` - 主应用
- `wsgi.py` - WSGI入口
- `database.py` - 数据库操作层
- `database_schema.sql` - 数据库schema
- `requirements.txt` - Python依赖
- `templates/` - HTML模板目录（如果有）
- `static/` - 静态文件目录（如果有）

### 步骤3：创建虚拟环境并安装依赖

```bash
# SSH连接到AlwaysData后执行

# 1. 进入项目目录
cd ~/financebot

# 2. 创建虚拟环境
python3 -m venv venv

# 3. 激活虚拟环境
source venv/bin/activate

# 4. 安装依赖
pip install -r requirements.txt

# 5. 验证安装
pip list
```

### 步骤4：初始化数据库

```bash
# SSH中执行

# 1. 设置环境变量
export DATABASE_URL="postgresql://your_account:your_password@postgresql-your_account.alwaysdata.net:5432/your_account_dbname"

# 2. 运行数据库初始化
python3 -c "from database import init_database; init_database()"

# 应该看到：✅ Database initialized successfully
```

### 步骤5：配置环境变量

1. **在AlwaysData控制面板**
2. **进入 `Web > Sites`**
3. **编辑您的站点配置**
4. **在"Environment variables"部分添加**：

```
TELEGRAM_BOT_TOKEN=你的Bot_Token
OWNER_ID=你的Telegram_User_ID
SESSION_SECRET=随机生成的密钥（建议64位）
WEBHOOK_URL=https://your-account.alwaysdata.net
DATABASE_URL=postgresql://user:pass@postgresql-account.alwaysdata.net:5432/dbname
FLASK_ENV=production
```

**生成SESSION_SECRET**：
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 步骤6：配置WSGI站点

1. **在AlwaysData控制面板**
2. **进入 `Web > Sites`**
3. **点击 `Add a site`**
4. **填写配置**：

   - **Addresses**: 
     - `your-account.alwaysdata.net`
     - 或自定义域名
   
   - **Type**: 
     - 选择 `Python WSGI`
   
   - **Application path**: 
     ```
     /home/your_account/financebot/wsgi.py
     ```
   
   - **Working directory**: 
     ```
     /home/your_account/financebot
     ```
   
   - **Virtualenv directory**: 
     ```
     /home/your_account/financebot/venv
     ```
   
   - **Environment variables**:
     - 添加上面列出的所有环境变量
   
   - **SSL**: 
     - 勾选 `Force HTTPS`
     - 自动使用Let's Encrypt证书

5. **点击 `Submit` 保存配置**

### 步骤7：设置Telegram Webhook

```bash
# SSH中执行，替换变量值

export BOT_TOKEN="你的Bot_Token"
export WEBHOOK_URL="https://your-account.alwaysdata.net/webhook/$BOT_TOKEN"

# 设置webhook
curl -X POST "https://api.telegram.org/bot$BOT_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"$WEBHOOK_URL\"}"

# 验证webhook设置
curl "https://api.telegram.org/bot$BOT_TOKEN/getWebhookInfo"
```

**成功响应示例**：
```json
{
  "ok": true,
  "result": {
    "url": "https://your-account.alwaysdata.net/webhook/1234567890:ABC...",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}
```

### 步骤8：重启站点

1. **在AlwaysData控制面板**
2. **进入 `Web > Sites`**
3. **点击您的站点旁边的重启图标** 🔄

---

## ✅ 验证部署

### 1. 检查应用状态

访问：`https://your-account.alwaysdata.net/health`

**成功响应**：
```json
{
  "status": "healthy",
  "database": "connected",
  "bot": "webhook_mode"
}
```

### 2. 测试Bot功能

在Telegram群组中：
1. 邀请Bot加入群组
2. 发送：`+1000`（记录入金）
3. Bot应该回复账单消息

### 3. 测试Web Dashboard

访问：Bot发送的"📊 查看账单明细"链接
- 应该显示交易记录
- 支持日期筛选

---

## 🔧 常见问题

### Q1: Webhook设置失败

**症状**：`curl getWebhookInfo` 显示 `url: ""`

**解决**：
1. 检查WEBHOOK_URL环境变量是否正确
2. 确保URL使用HTTPS（不是HTTP）
3. 确保Flask应用已启动
4. 重新运行setWebhook命令

### Q2: 数据库连接失败

**症状**：`psycopg2.OperationalError`

**解决**：
1. 检查DATABASE_URL格式是否正确
2. 确认数据库已创建
3. 验证用户名和密码
4. 检查PostgreSQL服务是否运行

### Q3: Bot不响应消息

**症状**：发送消息后没有反应

**解决**：
1. 检查webhook是否设置成功（getWebhookInfo）
2. 查看AlwaysData日志（`Logs`图标）
3. 确认TELEGRAM_BOT_TOKEN正确
4. 确认Bot有群组权限

### Q4: 环境变量不生效

**解决**：
1. 在AlwaysData控制面板重新保存环境变量
2. 重启站点
3. 通过SSH验证环境变量：
   ```bash
   source ~/financebot/venv/bin/activate
   python3 -c "import os; print(os.environ.get('TELEGRAM_BOT_TOKEN'))"
   ```

---

## 📊 监控和维护

### 查看日志

1. **应用日志**：
   - AlwaysData控制面板 → 点击站点旁的 `Logs` 图标
   - SSH: `tail -f ~/admin/logs/uwsgi/[id].log`

2. **错误日志**：
   - `~/admin/logs/uwsgi/[id].error.log`

### 数据库备份

AlwaysData自动每日备份数据库
- 控制面板 → `Backups` 查看

### 更新代码

```bash
# SSH连接后
cd ~/financebot
git pull origin main

# 重新安装依赖（如果requirements.txt有变化）
source venv/bin/activate
pip install -r requirements.txt

# 重启站点（在控制面板点击重启图标）
```

---

## 🌟 优化建议

### 1. 使用自定义域名

在 `Web > Sites` 添加您的域名：
- 添加CNAME记录指向 `your-account.alwaysdata.net`
- AlwaysData自动配置SSL

### 2. 启用PgBouncer连接池

编辑DATABASE_URL使用端口5433：
```
postgresql://user:pass@postgresql-account.alwaysdata.net:5433/dbname
```

### 3. 定期清理日志

创建cron任务自动清理旧数据：
```bash
# 每月清理3个月前的交易记录
DELETE FROM transactions WHERE created_at < NOW() - INTERVAL '3 months';
```

---

## 📞 获取帮助

- **AlwaysData文档**：https://help.alwaysdata.com/
- **Telegram Bot API**：https://core.telegram.org/bots/api
- **PostgreSQL文档**：https://www.postgresql.org/docs/

---

## 🎉 部署完成！

现在您的Telegram财务Bot已经成功部署到AlwaysData：
- ✅ 24/7运行
- ✅ PostgreSQL数据持久化
- ✅ 免费SSL证书
- ✅ 每日自动备份
- ✅ Web Dashboard查账功能

享受您的Bot吧！🚀
