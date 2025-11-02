#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web查账系统 - Flask应用
功能：查看交易记录、日期筛选、按操作员分类、数据统计、交易回退
"""

import os
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from functools import wraps

app = Flask(__name__)

# 配置 - 强制要求SESSION_SECRET
SESSION_SECRET = os.getenv("SESSION_SECRET")
if not SESSION_SECRET:
    raise RuntimeError(
        "❌ 安全错误：SESSION_SECRET环境变量未设置！\n"
        "这是Web查账系统的加密密钥，必须设置强随机字符串。\n"
        "示例：export SESSION_SECRET=$(openssl rand -hex 32)"
    )

app.secret_key = SESSION_SECRET
TOKEN_SECRET = SESSION_SECRET
OWNER_ID = int(os.getenv("OWNER_ID", "7784416293"))
DATA_DIR = Path("./data")
GROUPS_DIR = DATA_DIR / "groups"

# ========== Token认证系统 ==========

def generate_token(chat_id: int, user_id: int, expires_hours: int = 24):
    """生成临时访问token"""
    expires_at = int((datetime.now() + timedelta(hours=expires_hours)).timestamp())
    data = f"{chat_id}:{user_id}:{expires_at}"
    signature = hmac.new(
        TOKEN_SECRET.encode(),
        data.encode(),
        hashlib.sha256
    ).hexdigest()
    return f"{data}:{signature}"

def verify_token(token: str):
    """验证token有效性"""
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return None
        
        chat_id, user_id, expires_at, signature = parts
        chat_id = int(chat_id)
        user_id = int(user_id)
        expires_at = int(expires_at)
        
        # 验证签名
        data = f"{chat_id}:{user_id}:{expires_at}"
        expected_signature = hmac.new(
            TOKEN_SECRET.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if signature != expected_signature:
            return None
        
        # 验证过期时间
        if datetime.now().timestamp() > expires_at:
            return None
        
        return {"chat_id": chat_id, "user_id": user_id}
    except:
        return None

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.args.get('token') or session.get('token')
        if not token:
            return "未授权访问", 403
        
        user_info = verify_token(token)
        if not user_info:
            return "Token无效或已过期", 403
        
        # 保存token到session
        session['token'] = token
        session['user_info'] = user_info
        
        return f(*args, **kwargs)
    return decorated_function

# ========== 数据读取函数 ==========

def load_group_data(chat_id: int):
    """加载群组数据"""
    file_path = GROUPS_DIR / f"group_{chat_id}.json"
    if not file_path.exists():
        return None
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def save_group_data(chat_id: int, data: dict):
    """保存群组数据"""
    GROUPS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = GROUPS_DIR / f"group_{chat_id}.json"
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_all_transactions(chat_id: int, start_date=None, end_date=None):
    """获取所有交易记录（支持日期筛选）"""
    data = load_group_data(chat_id)
    if not data:
        return []
    
    all_records = []
    
    # 处理入金记录
    for record in data.get("deposit_records", []):
        record_date = datetime.strptime(record["time"], "%Y-%m-%d %H:%M:%S")
        if start_date and record_date < start_date:
            continue
        if end_date and record_date > end_date:
            continue
        
        all_records.append({
            "type": "deposit",
            "time": record["time"],
            "amount": record["amount"],
            "fee_rate": record.get("fee_rate", data.get("deposit_fee_rate", 0)),
            "exchange_rate": record.get("fx", data.get("deposit_fx", 0)),
            "usdt": record["usdt"],
            "operator": record.get("operator", "未知"),
            "message_id": record.get("message_id"),
            "timestamp": record_date.timestamp()
        })
    
    # 处理出金记录
    for record in data.get("withdrawal_records", []):
        record_date = datetime.strptime(record["time"], "%Y-%m-%d %H:%M:%S")
        if start_date and record_date < start_date:
            continue
        if end_date and record_date > end_date:
            continue
        
        all_records.append({
            "type": "withdrawal",
            "time": record["time"],
            "amount": record["amount"],
            "fee_rate": record.get("fee_rate", data.get("withdrawal_fee_rate", 0)),
            "exchange_rate": record.get("fx", data.get("withdrawal_fx", 0)),
            "usdt": record["usdt"],
            "operator": record.get("operator", "未知"),
            "message_id": record.get("message_id"),
            "timestamp": record_date.timestamp()
        })
    
    # 处理下发记录
    for record in data.get("disbursement_records", []):
        record_date = datetime.strptime(record["time"], "%Y-%m-%d %H:%M:%S")
        if start_date and record_date < start_date:
            continue
        if end_date and record_date > end_date:
            continue
        
        all_records.append({
            "type": "disbursement",
            "time": record["time"],
            "amount": record["usdt"],
            "fee_rate": 0,
            "exchange_rate": 0,
            "usdt": record["usdt"],
            "operator": record.get("operator", "未知"),
            "message_id": record.get("message_id"),
            "timestamp": record_date.timestamp()
        })
    
    # 按时间倒序排序
    all_records.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return all_records

def calculate_statistics(records):
    """计算统计数据"""
    stats = {
        "total_deposit": 0,
        "total_deposit_usdt": 0,
        "total_withdrawal": 0,
        "total_withdrawal_usdt": 0,
        "total_disbursement": 0,
        "pending_disbursement": 0,
        "by_operator": {}
    }
    
    for record in records:
        operator = record["operator"]
        if operator not in stats["by_operator"]:
            stats["by_operator"][operator] = {
                "deposit_count": 0,
                "deposit_usdt": 0,
                "withdrawal_count": 0,
                "withdrawal_usdt": 0,
                "disbursement_count": 0,
                "disbursement_usdt": 0
            }
        
        if record["type"] == "deposit":
            stats["total_deposit"] += record["amount"]
            stats["total_deposit_usdt"] += record["usdt"]
            stats["by_operator"][operator]["deposit_count"] += 1
            stats["by_operator"][operator]["deposit_usdt"] += record["usdt"]
        
        elif record["type"] == "withdrawal":
            stats["total_withdrawal"] += record["amount"]
            stats["total_withdrawal_usdt"] += record["usdt"]
            stats["by_operator"][operator]["withdrawal_count"] += 1
            stats["by_operator"][operator]["withdrawal_usdt"] += record["usdt"]
        
        elif record["type"] == "disbursement":
            stats["total_disbursement"] += record["usdt"]
            stats["by_operator"][operator]["disbursement_count"] += 1
            stats["by_operator"][operator]["disbursement_usdt"] += record["usdt"]
    
    stats["pending_disbursement"] = stats["total_deposit_usdt"] - stats["total_withdrawal_usdt"] - stats["total_disbursement"]
    
    return stats

# ========== 路由 ==========

@app.route("/")
def index():
    """首页 - 重定向到dashboard"""
    token = request.args.get('token') or session.get('token')
    if token:
        return redirect(url_for('dashboard', token=token))
    return "请通过Telegram Bot获取访问链接", 403

@app.route("/dashboard")
@login_required
def dashboard():
    """查账仪表盘"""
    user_info = session.get('user_info')
    chat_id = user_info['chat_id']
    user_id = user_info['user_id']
    
    # 加载群组数据
    group_data = load_group_data(chat_id)
    if not group_data:
        return "未找到群组数据", 404
    
    # 获取当前配置
    config = {
        "deposit_fee_rate": group_data.get("deposit_fee_rate", 0),
        "deposit_fx": group_data.get("deposit_fx", 0),
        "withdrawal_fee_rate": group_data.get("withdrawal_fee_rate", 0),
        "withdrawal_fx": group_data.get("withdrawal_fx", 0)
    }
    
    return render_template(
        "dashboard.html",
        chat_id=chat_id,
        user_id=user_id,
        is_owner=(user_id == OWNER_ID),
        config=config
    )

@app.route("/api/transactions")
@login_required
def api_transactions():
    """获取交易记录API"""
    user_info = session.get('user_info')
    chat_id = user_info['chat_id']
    
    # 获取筛选参数
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    start_date = None
    end_date = None
    
    if start_date_str:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    if end_date_str:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d") + timedelta(days=1)
    
    # 获取交易记录
    records = get_all_transactions(chat_id, start_date, end_date)
    stats = calculate_statistics(records)
    
    return jsonify({
        "success": True,
        "records": records,
        "statistics": stats
    })

@app.route("/api/rollback", methods=["POST"])
@login_required
def api_rollback():
    """回退交易API（仅OWNER）"""
    user_info = session.get('user_info')
    user_id = user_info['user_id']
    chat_id = user_info['chat_id']
    
    # 仅OWNER可以回退
    if user_id != OWNER_ID:
        return jsonify({"success": False, "error": "无权限"}), 403
    
    # 获取参数
    data = request.json
    transaction_type = data.get("type")
    message_id = data.get("message_id")
    
    if not transaction_type or not message_id:
        return jsonify({"success": False, "error": "参数错误"}), 400
    
    # 加载群组数据
    group_data = load_group_data(chat_id)
    if not group_data:
        return jsonify({"success": False, "error": "未找到群组数据"}), 404
    
    # 执行回退
    removed = False
    
    if transaction_type == "deposit":
        records = group_data.get("deposit_records", [])
        for i, record in enumerate(records):
            if record.get("message_id") == message_id:
                removed_record = records.pop(i)
                group_data["total_deposit"] -= removed_record["amount"]
                group_data["total_deposit_usdt"] -= removed_record["usdt"]
                removed = True
                break
    
    elif transaction_type == "withdrawal":
        records = group_data.get("withdrawal_records", [])
        for i, record in enumerate(records):
            if record.get("message_id") == message_id:
                removed_record = records.pop(i)
                group_data["total_withdrawal"] -= removed_record["amount"]
                group_data["total_withdrawal_usdt"] -= removed_record["usdt"]
                removed = True
                break
    
    elif transaction_type == "disbursement":
        records = group_data.get("disbursement_records", [])
        for i, record in enumerate(records):
            if record.get("message_id") == message_id:
                removed_record = records.pop(i)
                group_data["disbursed_usdt"] -= removed_record["usdt"]
                removed = True
                break
    
    if not removed:
        return jsonify({"success": False, "error": "未找到该交易记录"}), 404
    
    # 保存数据
    save_group_data(chat_id, group_data)
    
    return jsonify({"success": True, "message": "交易已回退"})

@app.route("/health")
def health():
    """健康检查"""
    return "OK", 200

# ========== 运行 ==========

if __name__ == "__main__":
    port = int(os.getenv("WEB_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
