-- AlwaysData PostgreSQL Database Schema
-- Telegram Finance Bot - 迁移到数据库版本

-- 群组配置表
CREATE TABLE IF NOT EXISTS groups (
    chat_id BIGINT PRIMARY KEY,
    group_name VARCHAR(255),
    in_rate DECIMAL(5,4) DEFAULT 0.00,
    in_fx DECIMAL(10,2) DEFAULT 0.00,
    out_rate DECIMAL(5,4) DEFAULT 0.00,
    out_fx DECIMAL(10,2) DEFAULT 0.00,
    in_fx_source VARCHAR(50) DEFAULT '手动设置',
    out_fx_source VARCHAR(50) DEFAULT '手动设置',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 交易记录表
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL REFERENCES groups(chat_id) ON DELETE CASCADE,
    transaction_type VARCHAR(20) NOT NULL,
    amount DECIMAL(15,2) NOT NULL,
    rate DECIMAL(5,4) NOT NULL,
    fx DECIMAL(10,2) NOT NULL,
    usdt DECIMAL(15,2) NOT NULL,
    country VARCHAR(100) DEFAULT '通用',
    timestamp VARCHAR(20) NOT NULL,
    message_id BIGINT,
    operator_id BIGINT,
    operator_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 管理员表
CREATE TABLE IF NOT EXISTS admins (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    is_owner BOOLEAN DEFAULT FALSE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 私聊用户表（用于广播功能）
CREATE TABLE IF NOT EXISTS private_chat_users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 国家配置表（支持不同国家不同费率/汇率）
CREATE TABLE IF NOT EXISTS group_country_configs (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL REFERENCES groups(chat_id) ON DELETE CASCADE,
    country VARCHAR(100) NOT NULL,
    in_rate DECIMAL(5,4),
    in_fx DECIMAL(10,2),
    out_rate DECIMAL(5,4),
    out_fx DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, country)
);

-- 创建索引以优化查询性能
CREATE INDEX IF NOT EXISTS idx_transactions_chat_timestamp ON transactions(chat_id, created_at);
CREATE INDEX IF NOT EXISTS idx_transactions_message_id ON transactions(message_id);
CREATE INDEX IF NOT EXISTS idx_transactions_type_chat ON transactions(transaction_type, chat_id);
CREATE INDEX IF NOT EXISTS idx_country_configs_chat ON group_country_configs(chat_id);

-- 自动更新 updated_at 的触发器
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_groups_updated_at ON groups;
CREATE TRIGGER update_groups_updated_at BEFORE UPDATE ON groups
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_country_configs_updated_at ON group_country_configs;
CREATE TRIGGER update_country_configs_updated_at BEFORE UPDATE ON group_country_configs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 示例查询（用于验证）
-- 查询某个群的所有交易记录
-- SELECT * FROM transactions WHERE chat_id = -1001234567890 ORDER BY created_at DESC;

-- 查询某个群的统计
-- SELECT 
--     transaction_type,
--     COUNT(*) as count,
--     SUM(usdt) as total_usdt
-- FROM transactions 
-- WHERE chat_id = -1001234567890
-- GROUP BY transaction_type;

-- 查询今日交易（北京时间）
-- SELECT * FROM transactions 
-- WHERE chat_id = -1001234567890 
-- AND created_at >= CURRENT_DATE
-- ORDER BY created_at DESC;
