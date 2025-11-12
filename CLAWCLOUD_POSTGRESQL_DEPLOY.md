# 🚀 ClawCloud Run 完整部署指南（PostgreSQL版本）

## 📋 部署概述

**平台**：ClawCloud Run  
**数据库**：PostgreSQL  
**应用**：Telegram Bot（Webhook） + Web Dashboard  
**预计成本**：£4-5/月（在免费额度内）

---

## 🎯 第一步：注册 ClawCloud 账号

1. **访问**：https://console.run.claw.cloud

2. **注册方式**（推荐GitHub登录）：
   - 使用 GitHub 登录
   - **重要**：GitHub 账号需 >180 天可获得 £5/月永久免费额度
   - 验证邮箱

3. **确认免费额度**：
   - 登录后查看右上角余额
   - 应显示 £5.00 credits

---

## 🗄️ 第二步：创建 PostgreSQL 数据库

### 2.1 创建数据库实例

1. **进入数据库页面**：
   - 点击左侧菜单 **"Database"**
   - 点击右上角 **"Create Database"**

2. **配置数据库**：
   ```
   数据库类型：PostgreSQL
   版本：postgresql-14.8.0（或最新稳定版）
   名称：financebot-db （小写字母+数字，不支持特殊字符）
   ```

3. **资源配置**：
   ```
   CPU：0.5 核
   内存：512 MB
   存储：2 GiB
   副本数：1
   ```

4. **备份配置**（可选）：
   - 备份周期：每日
   - 保留天数：7 天
   - 开始时间：02:00（北京时间早上10:00）

5. **网络配置**：
   - **私有网络**：启用（应用和数据库在同一网络，更安全更快）
   - **公网访问**：禁用（不需要外部访问）

6. **点击 "Deploy"**

7. **等待部署**（约 30-60 秒）

### 2.2 获取数据库连接信息

**部署成功后，点击数据库实例查看详情**：

```
主机（Host）: financebot-db.internal.claw.cloud
端口（Port）: 5432
用户名（Username）: postgres
密码（Password）: xxxxxxxxxx （自动生成，点击"显示"查看）
数据库名（Database）: postgres
```

**⚠️ 重要**：复制保存密码，只显示一次！

### 2.3 构建 DATABASE_URL

将上述信息组合成 DATABASE_URL：

```
postgresql://用户名:密码@主机:端口/数据库名
```

**示例**：
```
postgresql://postgres:abc123xyz@financebot-db.internal.claw.cloud:5432/postgres
```

**保存这个 URL，部署应用时需要！**

---

## 🐳 第三步：部署应用

### 3.1 准备 Bot Token

1. **打开 Telegram**，搜索 `@BotFather`
2. 发送 `/newbot` 创建新 Bot
3. 按提示设置 Bot 名称
4. **保存 Bot Token**（格式：`123456:ABC-DEF...`）

### 3.2 获取您的 Telegram ID

1. **打开 Telegram**，搜索 `@userinfobot`
2. 点击 Start
3. **保存您的 User ID**（如：`7784416293`）

### 3.3 生成 SESSION_SECRET

**在本地终端执行**：

```bash
openssl rand -hex 32
```

**输出示例**：
```
a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
```

**保存这个字符串！**

### 3.4 创建应用

1. **进入应用页面**：
   - 点击左侧 **"App Launchpad"**
   - 点击右上角 **"Create App"**

2. **选择部署方式**：
   - **From GitHub**（推荐） 或 **From Docker Image**

### 选项 A：从 GitHub 部署（推荐）

1. **连接 GitHub**：
   - 选择 **"GitHub Integration"**
   - 授权 ClawCloud 访问您的 GitHub
   - 选择仓库：`lea499579-stack/telegram-finance-bot`
   - 选择分支：`main`

2. **构建配置**：
   ```
   Dockerfile 路径：./Dockerfile
   构建上下文：/
   ```

3. **应用配置**：
   ```
   应用名称：telegram-finance-bot
   部署模式：固定实例（Fixed Instances）
   实例数量：1
   ```

4. **资源配置**：
   ```
   CPU：0.5 核
   内存：1 GB
   存储：1 GB
   ```

5. **网络配置**：
   ```
   容器端口：5000 ⚠️ 重要：必须是 5000
   启用外部访问：✅ 开启
   协议：HTTP
   ```

### 选项 B：从 Docker Hub 部署

1. **应用配置**：
   ```
   应用名称：telegram-finance-bot
   镜像：usdiele/tron-calculator-rental:latest
   部署模式：固定实例
   实例数量：1
   ```

2. **资源/网络配置**：同选项 A

### 3.5 配置环境变量

**点击 "Environment Variables"，添加以下变量**：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `DATABASE_URL` | `postgresql://...` | 第二步获取的数据库连接 URL |
| `TELEGRAM_BOT_TOKEN` | `123456:ABC-DEF...` | Bot Token |
| `OWNER_ID` | `7784416293` | 您的 Telegram ID |
| `SESSION_SECRET` | `a1b2c3d4e5f6...` | 刚生成的 64 位字符串 |
| `WEBHOOK_URL` | `https://temp.com` | 临时值，部署后更新 |
| `PORT` | `5000` | ClawCloud 会自动设置，可不填 |

**⚠️ 注意**：`WEBHOOK_URL` 需要部署后获得域名再更新

### 3.6 部署应用

1. **点击右上角 "Deploy"**
2. **等待部署**（约 1-3 分钟）
3. **查看日志**：点击 "Logs" 确认启动成功

---

## 🔧 第四步：配置 Webhook

### 4.1 获取应用域名

部署成功后，ClawCloud 会分配域名，例如：

```
https://eu-central-1.run.claw.cloud/telegram-finance-bot-abc123
```

**复制完整域名！**

### 4.2 更新 WEBHOOK_URL

1. **进入应用设置**：
   - 点击应用名称
   - 点击 **"Environment Variables"**
   - 找到 `WEBHOOK_URL`
   - 更新为刚复制的域名

2. **点击 "Save"**

3. **重启应用**：
   - 点击右上角 **"Restart"**
   - 等待重启完成（约 30 秒）

### 4.3 验证 Webhook

**打开浏览器访问**：

```
https://您的域名/health
```

**应该显示**：

```json
{
  "status": "healthy",
  "mode": "Webhook",
  "database": "connected"
}
```

---

## ✅ 第五步：测试 Bot 功能

### 5.1 基础测试

1. **打开 Telegram**，找到您的 Bot
2. **发送**：`/start`
3. **Bot 应该回复欢迎消息**

### 5.2 群组测试

1. **将 Bot 添加到 Telegram 群组**
2. **给 Bot 管理员权限**
3. **设置您为管理员**：
   - 回复您自己的消息
   - 输入：`设置机器人管理员`

4. **测试交易记录**：
   ```
   设置入金费率 10
   设置入金汇率 153
   +10000
   ```

5. **查看账单**：
   ```
   +0
   ```

6. **点击 "📊 查看账单明细"**：
   - 应该打开 Web 查账界面
   - 显示刚才的交易记录

### 5.3 验证数据库

**在 ClawCloud 数据库页面**：

1. **点击数据库实例**
2. **点击 "Terminal" 或 "SQL Editor"**
3. **执行查询**：

```sql
SELECT * FROM groups;
SELECT * FROM transactions;
SELECT * FROM admins;
```

**应该能看到刚才创建的数据！**

---

## 📊 监控和维护

### 查看应用日志

1. **进入应用详情**
2. **点击 "Logs"**
3. **实时查看运行日志**

### 查看资源使用

1. **进入应用详情**
2. **查看 CPU/内存/网络 使用图表**
3. **根据需要调整资源配置**

### 数据库备份

**ClawCloud 自动备份（如已配置）**，手动备份：

1. **进入数据库详情**
2. **点击 "Backup"**
3. **点击 "Create Backup"**

---

## 🔍 故障排查

### Bot 无响应

**检查步骤**：

1. **查看应用日志**：
   ```
   [ERROR] Database connection failed
   → 检查 DATABASE_URL 是否正确
   
   [ERROR] Invalid token
   → 检查 TELEGRAM_BOT_TOKEN 是否正确
   
   [WARNING] Webhook setup failed
   → 检查 WEBHOOK_URL 是否已更新
   ```

2. **验证环境变量**：
   - 确认所有变量都已设置
   - 确认没有多余空格

3. **重启应用**：
   - 点击 "Restart"
   - 等待重启完成

### 数据库连接失败

**原因**：
- DATABASE_URL 格式错误
- 数据库未启动
- 网络配置问题

**解决**：

1. **检查数据库状态**：
   - 确认状态为 "Running"

2. **验证连接字符串**：
   ```
   格式：postgresql://用户名:密码@主机:端口/数据库名
   示例：postgresql://postgres:pass@db.claw.cloud:5432/postgres
   ```

3. **检查网络**：
   - 确认应用和数据库在同一私有网络

### Web 查账无法访问

**检查**：

1. **SESSION_SECRET 是否设置**
2. **容器端口是否为 5000**
3. **WEBHOOK_URL 是否已更新**

---

## 💰 成本估算

**免费额度**：£5/月

**预计消耗**：
- **PostgreSQL**（0.5核 + 512MB + 2GB存储）：约 £2/月
- **应用**（0.5核 + 1GB内存）：约 £2-3/月
- **流量**：可忽略

**总计**：约 £4-5/月 ✅ **完全在免费额度内！**

---

## 🎯 部署清单

- [ ] 注册 ClawCloud 账号（GitHub 登录）
- [ ] 验证 £5 免费额度
- [ ] 创建 PostgreSQL 数据库
- [ ] 保存 DATABASE_URL
- [ ] 准备 Bot Token 和 OWNER_ID
- [ ] 生成 SESSION_SECRET
- [ ] 创建应用并配置环境变量
- [ ] 配置资源（0.5核/1GB）
- [ ] 设置端口（5000）
- [ ] 部署应用
- [ ] 获取应用域名
- [ ] 更新 WEBHOOK_URL
- [ ] 重启应用
- [ ] 访问 /health 验证
- [ ] 在 Telegram 测试 Bot
- [ ] 测试 Web 查账功能
- [ ] 配置数据库备份

---

## 🔗 相关链接

- **ClawCloud 控制台**：https://console.run.claw.cloud
- **官方文档**：https://docs.run.claw.cloud
- **PostgreSQL 文档**：https://docs.run.claw.cloud/clawcloud-run/guide/database/postgresql
- **GitHub 仓库**：https://github.com/lea499579-stack/telegram-finance-bot

---

## 🎉 完成！

部署完成后：
- ✅ Bot 24/7 在线运行（Webhook 模式）
- ✅ PostgreSQL 数据库持久化存储
- ✅ Web Dashboard 实时查账
- ✅ 私聊消息自动转发
- ✅ 多群组独立记账
- ✅ 国家配置支持

**祝您使用愉快！** 🚀

---

## 📝 常见命令速查

```bash
# 群组管理
设置机器人管理员         # 设置管理员（回复用户消息）
移除机器人管理员         # 移除管理员（回复用户消息）

# 费率配置
设置入金费率 10         # 设置入金费率为 10%
设置入金汇率 153        # 设置入金汇率为 153
设置出金费率 2          # 设置出金费率为 2%
设置出金汇率 137        # 设置出金汇率为 137

# 交易记录
+10000                  # 记录入金 10000
-5000                   # 记录出金 5000
下发 1000              # 记录下发 1000 USDT

# 查询
+0                      # 查看今日账单（附Web查账链接）
撤销                    # 撤销最近一笔交易（回复交易消息）
清除数据               # 清除今日所有数据

# 国家配置（高级）
日本 设置入金费率 12   # 为"日本"设置独立费率
美国 设置出金汇率 140  # 为"美国"设置独立汇率
```
