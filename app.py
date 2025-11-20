#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
简化版 财务记账 Telegram Bot（Polling + JSON 本地存储）

✅ 不需要公网 HTTPS / 域名
✅ 不需要 Flask / Webhook
✅ 记账 + 多国家费率/汇率 + 管理员系统 + 私聊客服转发 + 广播
"""

import os
import re
import threading
import json
import math
import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

# ========== 加载环境 ==========

load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")  # 可选：你的 Telegram ID（字符串），拥有永久管理员权限

# ========== 记账核心状态（多群组支持） ==========

DATA_DIR = Path("./data")
GROUPS_DIR = DATA_DIR / "groups"
LOG_DIR = DATA_DIR / "logs"
ADMINS_FILE = DATA_DIR / "admins.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
GROUPS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 群组状态缓存 {chat_id: state_dict}
groups_state: dict[int, dict] = {}


def get_default_state() -> dict:
    """返回默认群组状态（初始费率/汇率为0，需要管理员设置）"""
    return {
        "defaults": {
            "in": {"rate": 0.0, "fx": 0.0},   # 入金 默认费率/汇率
            "out": {"rate": 0.0, "fx": 0.0},  # 出金 默认费率/汇率
        },
        "countries": {},  # 不同国家单独设置
        "precision": {"mode": "truncate", "digits": 2},
        "bot_name": "全球国际支付",
        "recent": {"in": [], "out": []},  # 当天记录
        "summary": {"should_send_usdt": 0.0, "sent_usdt": 0.0},
        "last_date": "",
    }


def group_file_path(chat_id: int) -> Path:
    """获取群组状态文件路径"""
    return GROUPS_DIR / f"group_{chat_id}.json"


def load_group_state(chat_id: int) -> dict:
    """从JSON文件加载群组状态"""
    if chat_id in groups_state:
        return groups_state[chat_id]

    file_path = group_file_path(chat_id)
    if file_path.exists():
        try:
            with file_path.open("r", encoding="utf-8") as f:
                state = json.load(f)
            groups_state[chat_id] = state
            return state
        except Exception as e:
            print(f"⚠️ 加载群组状态文件失败: {e}")

    # 创建新群组状态
    state = get_default_state()
    groups_state[chat_id] = state
    save_group_state(chat_id)
    return state


def save_group_state(chat_id: int):
    """保存群组状态到JSON文件"""
    if chat_id not in groups_state:
        return
    file_path = group_file_path(chat_id)
    try:
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(groups_state[chat_id], f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ 保存群组状态文件失败: {e}")


# ========== 管理员缓存（从JSON文件加载） ==========

admins_cache: list[int] | None = None


def load_admins() -> list[int]:
    """从JSON文件加载管理员列表"""
    global admins_cache
    if admins_cache is not None:
        return admins_cache

    if ADMINS_FILE.exists():
        try:
            with ADMINS_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                admins_cache = data.get("admins", [])
                return admins_cache
        except Exception as e:
            print(f"⚠️ 加载管理员文件失败: {e}")

    # 初始化管理员（如果有OWNER_ID）
    admins_cache = []
    if OWNER_ID and OWNER_ID.isdigit():
        admins_cache.append(int(OWNER_ID))
    save_admins(admins_cache)
    return admins_cache


def save_admins(admin_list: list[int]):
    """保存管理员列表到JSON文件"""
    global admins_cache
    admins_cache = admin_list
    try:
        with ADMINS_FILE.open("w", encoding="utf-8") as f:
            json.dump({"admins": admin_list}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ 保存管理员文件失败: {e}")


def add_admin(user_id: int) -> bool:
    """添加管理员"""
    admins = load_admins()
    if user_id not in admins:
        admins.append(user_id)
        save_admins(admins)
        return True
    return False


def remove_admin(user_id: int) -> bool:
    """移除管理员"""
    admins = load_admins()
    if user_id in admins:
        admins.remove(user_id)
        save_admins(admins)
        return True
    return False


# ========== 工具函数 ==========

def trunc2(x: float) -> float:
    """先四舍五入到6位小数，再截断到2位小数，避免浮点误差"""
    rounded = round(float(x), 6)
    return math.floor(rounded * 100.0) / 100.0


def fmt_usdt(x: float) -> str:
    return f"{x:.2f} USDT"


def to_superscript(num: int) -> str:
    """将数字转换为上标，用于显示费率"""
    superscript_map = {
        "0": "⁰",
        "1": "¹",
        "2": "²",
        "3": "³",
        "4": "⁴",
        "5": "⁵",
        "6": "⁶",
        "7": "⁷",
        "8": "⁸",
        "9": "⁹",
        "-": "⁻",
    }
    return "".join(superscript_map.get(c, c) for c in str(num))


def now_ts() -> str:
    """北京时间 HH:MM"""
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(beijing_tz).strftime("%H:%M")


def today_str() -> str:
    """北京时间 YYYY-MM-DD"""
    beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(beijing_tz).strftime("%Y-%m-%d")


def check_and_reset_daily(chat_id: int) -> bool:
    """检查日期，如果日期变了（过了0点），清空账单"""
    state = load_group_state(chat_id)
    current_date = today_str()
    last_date = state.get("last_date", "")

    if last_date and last_date != current_date:
        # 日期变了，清空账单
        state["recent"]["in"] = []
        state["recent"]["out"] = []
        state["summary"]["should_send_usdt"] = 0.0
        state["summary"]["sent_usdt"] = 0.0
        state["last_date"] = current_date
        save_group_state(chat_id)
        return True
    elif not last_date:
        # 首次运行，设置日期
        state["last_date"] = current_date
        save_group_state(chat_id)

    return False


def log_path(chat_id: int, country: str | None, date_str: str) -> Path:
    folder = f"group_{chat_id}"
    if country:
        folder = f"{folder}/{country}"
    else:
        folder = f"{folder}/通用"
    p = LOG_DIR / folder
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{date_str}.log"


def append_log(path: Path, text: str):
    with path.open("a", encoding="utf-8") as f:
        f.write(text.strip() + "\n")


def push_recent(chat_id: int, kind: str, item: dict):
    state = load_group_state(chat_id)
    arr = state["recent"][kind]
    arr.insert(0, item)
    save_group_state(chat_id)


def resolve_params(chat_id: int, direction: str, country: str | None) -> dict:
    """根据国家 + 入/出 金，找到对应费率/汇率，没有就用默认"""
    state = load_group_state(chat_id)
    d = {"rate": None, "fx": None}
    countries = state["countries"]

    # 国家专属设置
    if country and country in countries:
        if direction in countries[country]:
            d["rate"] = countries[country][direction].get("rate", None)
            d["fx"] = countries[country][direction].get("fx", None)

    # 没有则回退默认
    if d["rate"] is None:
        d["rate"] = state["defaults"][direction]["rate"]
    if d["fx"] is None:
        d["fx"] = state["defaults"][direction]["fx"]

    return d


def parse_amount_and_country(text: str):
    """
    解析金额 & 国家：
    +10000 / 日本  -> (10000.0, '日本')
    -200  /US      -> (200.0, 'US')
    +3000          -> (3000.0, None)
    """
    m = re.match(r"^[\+\-]\s*([0-9]+(?:\.[0-9]+)?)", text.strip())
    if not m:
        return None, None
    amount = float(m.group(1))
    m2 = re.search(r"/\s*([^\s]+)$", text)
    country = m2.group(1) if m2 else None
    return amount, country


# ========== 管理员系统 ==========

def is_admin(user_id: int) -> bool:
    """机器人管理员：OWNER + JSON 中的管理员列表"""
    if OWNER_ID and OWNER_ID.isdigit() and int(OWNER_ID) == user_id:
        return True
    admin_list = load_admins()
    return user_id in admin_list


def list_admins() -> list[int]:
    return load_admins()


# ========== 群内汇总显示 ==========

def render_group_summary(chat_id: int) -> str:
    state = load_group_state(chat_id)
    bot = state["bot_name"]
    rec_in, rec_out = state["recent"]["in"], state["recent"]["out"]
    should = trunc2(state["summary"]["should_send_usdt"])
    sent = trunc2(state["summary"]["sent_usdt"])
    diff = trunc2(should - sent)
    rin, fin = state["defaults"]["in"]["rate"], state["defaults"]["in"]["fx"]
    rout, fout = state["defaults"]["out"]["rate"], state["defaults"]["out"]["fx"]

    lines: list[str] = []
    lines.append(f"【{bot} 账单汇总】\n")

    # 分离出金记录中的"下发"和普通出金
    normal_out = [r for r in rec_out if r.get("type") != "下发"]
    send_out = [r for r in rec_out if r.get("type") == "下发"]

    # 入金记录
    lines.append(f"已入账 ({len(rec_in)}笔)")
    if rec_in:
        for r in rec_in[:5]:
            raw = r.get("raw", 0)
            fx = r.get("fx", fin)
            rate = r.get("rate", rin)
            usdt = trunc2(r["usdt"])
            rate_percent = int(rate * 100)
            rate_sup = to_superscript(rate_percent)
            lines.append(f"{r['ts']} {raw}  {rate_sup}/ {fx} = {usdt}")
    lines.append("")

    # 出金记录
    lines.append(f"已出账 ({len(normal_out)}笔)")
    if normal_out:
        for r in normal_out[:5]:
            if "raw" in r:
                raw = r.get("raw", 0)
                fx = r.get("fx", fout)
                rate = r.get("rate", rout)
                usdt = trunc2(r["usdt"])
                rate_percent = int(rate * 100)
                rate_sup = to_superscript(rate_percent)
                lines.append(f"{r['ts']} {raw}  {rate_sup}/ {fx} = {usdt}")
    lines.append("")

    # 下发记录
    if send_out:
        lines.append(f"已下发 ({len(send_out)}笔)")
        for r in send_out[:5]:
            usdt = trunc2(abs(r["usdt"]))
            lines.append(f"{r['ts']} {usdt}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━")
    lines.append(f"⚙️ 当前费率：入 {rin*100:.0f}% ⇄ 出 {abs(rout)*100:.0f}%")
    lines.append(f"💱 固定汇率：入 {fin} ⇄ 出 {fout}")
    lines.append(f"📊 应下发：{fmt_usdt(should)}")
    lines.append(f"📤 已下发：{fmt_usdt(sent)}")
    lines.append(f"{'❗' if diff != 0 else '✅'} 未下发：{fmt_usdt(diff)}")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📚 **查看更多记录**：发送「更多记录」")
    return "\n".join(lines)


def render_full_summary(chat_id: int) -> str:
    """显示当天所有记录"""
    state = load_group_state(chat_id)
    bot = state["bot_name"]
    rec_in, rec_out = state["recent"]["in"], state["recent"]["out"]
    should = trunc2(state["summary"]["should_send_usdt"])
    sent = trunc2(state["summary"]["sent_usdt"])
    diff = trunc2(should - sent)
    rin, fin = state["defaults"]["in"]["rate"], state["defaults"]["in"]["fx"]
    rout, fout = state["defaults"]["out"]["rate"], state["defaults"]["out"]["fx"]

    lines: list[str] = []
    lines.append(f"【{bot} 完整账单】\n")

    # 分离出金记录中的"下发"和普通出金
    normal_out = [r for r in rec_out if r.get("type") != "下发"]
    send_out = [r for r in rec_out if r.get("type") == "下发"]

    # 入金
    lines.append(f"已入账 ({len(rec_in)}笔)")
    if rec_in:
        for r in rec_in:
            raw = r.get("raw", 0)
            fx = r.get("fx", fin)
            rate = r.get("rate", rin)
            usdt = trunc2(r["usdt"])
            rate_percent = int(rate * 100)
            rate_sup = to_superscript(rate_percent)
            lines.append(f"{r['ts']} {raw}  {rate_sup}/ {fx} = {usdt}")
    lines.append("")

    # 出金
    lines.append(f"已出账 ({len(normal_out)}笔)")
    if normal_out:
        for r in normal_out:
            if "raw" in r:
                raw = r.get("raw", 0)
                fx = r.get("fx", fout)
                rate = r.get("rate", rout)
                usdt = trunc2(r["usdt"])
                rate_percent = int(rate * 100)
                rate_sup = to_superscript(rate_percent)
                lines.append(f"{r['ts']} {raw}  {rate_sup}/ {fx} = {usdt}")
    lines.append("")

    # 下发
    if send_out:
        lines.append(f"已下发 ({len(send_out)}笔)")
        for r in send_out:
            usdt = trunc2(abs(r["usdt"]))
            lines.append(f"{r['ts']} {usdt}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━")
    lines.append(f"⚙️ 当前费率：入 {rin*100:.0f}% ⇄ 出 {abs(rout)*100:.0f}%")
    lines.append(f"💱 固定汇率：入 {fin} ⇄ 出 {fout}")
    lines.append(f"📊 应下发：{fmt_usdt(should)}")
    lines.append(f"📤 已下发：{fmt_usdt(sent)}")
    lines.append(f"{'❗' if diff != 0 else '✅'} 未下发：{fmt_usdt(diff)}")
    lines.append("━━━━━━━━━━━━━━")
    return "\n".join(lines)


# ========== Telegram 逻辑 ==========

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat

    # 私聊模式
    if chat.type == "private":
        if is_admin(user.id):
            await update.message.reply_text(
                "🤖 你好，我是财务记账机器人。\n\n"
                "📊 记账操作：\n"
                "  入金：+10000 或 +10000 / 日本\n"
                "  出金：-10000 或 -10000 / 日本\n"
                "  查看账单：+0 或 更多记录\n\n"
                "💰 USDT下发（仅管理员）：\n"
                "  下发35.04（记录下发并扣除应下发）\n"
                "  下发-35.04（撤销下发并增加应下发）\n\n"
                "🔄 撤销操作（仅管理员）：\n"
                "  回复账单消息 + 输入：撤销\n"
                "  （必须准确输入“撤销”二字）\n\n"
                "⚙️ 快速设置（仅管理员）：\n"
                "  重置默认值（一键设置推荐费率/汇率）\n"
                "  设置入金费率 10\n"
                "  设置入金汇率 153\n"
                "  设置出金费率 2\n"
                "  设置出金汇率 137\n\n"
                "🔧 高级设置（指定国家）：\n"
                "  设置日本入费率8\n"
                "  设置日本入汇率127\n\n"
                "👥 管理员管理：\n"
                "  设置机器人管理员（回复消息）\n"
                "  删除机器人管理员（回复消息）\n"
                "  显示机器人管理员"
            )
        else:
            await update.message.reply_text(
                "👋 你好！欢迎使用财务记账机器人\n\n"
                "💬 发送 /start 查看完整操作说明\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "📌 如何成为机器人管理员：\n"
                "  1️⃣ 先把机器人拉进群\n"
                "  2️⃣ 在群里发一条消息\n"
                "  3️⃣ 让已有管理员回复你的消息并发送：设置机器人管理员\n\n"
                "✅ 成为管理员后，你可以在群里使用所有记账指令。"
            )
    else:
        # 群聊模式
        await update.message.reply_text(
            "🤖 你好，我是财务记账机器人。\n\n"
            "📊 记账操作：\n"
            "  入金：+10000 或 +10000 / 日本\n"
            "  出金：-10000 或 -10000 / 日本\n"
            "  查看账单：+0 或 更多记录\n\n"
            "💰 USDT下发（仅管理员）：\n"
            "  下发35.04（记录下发并扣除应下发）\n"
            "  下发-35.04（撤销下发并增加应下发）\n\n"
            "🔄 撤销操作（仅管理员）：\n"
            "  回复账单消息 + 输入：撤销\n"
            "  （必须准确输入“撤销”二字）\n\n"
            "⚙️ 快速设置（仅管理员）：\n"
            "  重置默认值（一键设置推荐费率/汇率）\n"
            "  设置入金费率 10\n"
            "  设置入金汇率 153\n"
            "  设置出金费率 2\n"
            "  设置出金汇率 137\n\n"
            "🔧 高级设置（指定国家）：\n"
            "  设置日本入费率8\n"
            "  设置日本入汇率127\n\n"
            "👥 管理员管理：\n"
            "  设置机器人管理员（回复消息）\n"
            "  删除机器人管理员（回复消息）\n"
            "  显示机器人管理员"
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    chat_id = chat.id
    text = (update.message.text or update.message.caption or "").strip()
    ts, dstr = now_ts(), today_str()

    # ========== 私聊消息转发 ==========
    if chat.type == "private":
        private_log_dir = LOG_DIR / "private_chats"
        private_log_dir.mkdir(exist_ok=True)
        user_log_file = private_log_dir / f"user_{user.id}.log"

        log_entry = f"[{ts}] {user.full_name} (@{user.username or 'N/A'}): {text}\n"
        with user_log_file.open("a", encoding="utf-8") as f:
            f.write(log_entry)

        # 有 OWNER，且非 OWNER 发送 → 转发给 OWNER
        if OWNER_ID and OWNER_ID.isdigit():
            owner_id = int(OWNER_ID)

            # 非 OWNER 用户发来的消息
            if user.id != owner_id:
                try:
                    user_info = f"👤 {user.full_name}"
                    if user.username:
                        user_info += f" (@{user.username})"
                    user_info += f"\n🆔 User ID: {user.id}"

                    forward_msg = (
                        f"📨 收到私聊消息\n"
                        f"{user_info}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"{text}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💡 回复此消息可直接回复用户"
                    )

                    sent_msg = await context.bot.send_message(
                        chat_id=owner_id,
                        text=forward_msg,
                    )

                    # 存映射：OWNER 收到的消息ID -> 原始用户ID
                    if "private_msg_map" not in context.bot_data:
                        context.bot_data["private_msg_map"] = {}
                    context.bot_data["private_msg_map"][sent_msg.message_id] = user.id

                    await update.message.reply_text(
                        "✅ 您的消息已发送给客服\n"
                        "⏳ 请耐心等待回复"
                    )
                    return
                except Exception as e:
                    print(f"转发私聊消息失败: {e}")

            else:
                # OWNER 发来的消息
                # 1) 回复转发消息 → 回给对应用户
                if update.message.reply_to_message:
                    replied_msg_id = update.message.reply_to_message.message_id
                    if "private_msg_map" in context.bot_data:
                        target_user_id = context.bot_data["private_msg_map"].get(
                            replied_msg_id
                        )
                        if target_user_id:
                            try:
                                await context.bot.send_message(
                                    chat_id=target_user_id,
                                    text=f"💬 客服回复：\n\n{text}",
                                )
                                await update.message.reply_text("✅ 回复已发送")
                                # 记录到对方日志
                                target_log_file = private_log_dir / f"user_{target_user_id}.log"
                                reply_log_entry = f"[{ts}] OWNER回复: {text}\n"
                                with target_log_file.open("a", encoding="utf-8") as f:
                                    f.write(reply_log_entry)
                                return
                            except Exception as e:
                                await update.message.reply_text(f"❌ 发送失败: {e}")
                                return

                # 2) 广播 / 群发
                if text.startswith(("广播 ", "群发 ")):
                    broadcast_text = text.split(" ", 1)[1] if " " in text else ""
                    if not broadcast_text:
                        await update.message.reply_text(
                            "❌ 请输入广播内容\n\n使用示例：\n广播 今天下午三点有课程，记得参加哦～"
                        )
                        return

                    user_ids: list[int] = []
                    try:
                        if private_log_dir.exists():
                            for log_file in private_log_dir.glob("user_*.log"):
                                try:
                                    uid = int(log_file.stem.split("_")[1])
                                    if uid != owner_id:
                                        user_ids.append(uid)
                                except (ValueError, IndexError):
                                    continue
                    except Exception as e:
                        await update.message.reply_text(f"❌ 读取用户列表失败: {e}")
                        return

                    if not user_ids:
                        await update.message.reply_text("❌ 没有找到任何私聊用户")
                        return

                    await update.message.reply_text(
                        f"📢 开始广播...\n📊 目标用户数：{len(user_ids)}"
                    )

                    success, fail = 0, 0
                    for uid in user_ids:
                        try:
                            await context.bot.send_message(
                                chat_id=uid,
                                text=f"📢 系统通知：\n\n{broadcast_text}",
                            )
                            success += 1
                        except Exception as e:
                            fail += 1
                            print(f"广播失败 (用户 {uid}): {e}")

                    await update.message.reply_text(
                        f"✅ 广播完成！\n\n"
                        f"成功：{success} 人\n"
                        f"失败：{fail} 人\n"
                        f"总计：{len(user_ids)} 人"
                    )
                    return

                # 3) OWNER 普通私聊提示
                await update.message.reply_text(
                    "💡 使用提示：\n"
                    "• 回复转发的消息可以回复用户\n"
                    "• 在群组中使用记账功能\n\n"
                    "📢 广播示例：\n"
                    "广播 今天下午三点有课程"
                )
                return

        # 没配置 OWNER_ID 的情况：普通提示
        await update.message.reply_text(
            "已收到你的消息，稍后会有客服查看。\n\n"
            "如需使用财务记账功能，请把机器人拉进群并发送 /start 查看说明。"
        )
        return

    # ========== 群组消息处理 ==========

    check_and_reset_daily(chat_id)
    state = load_group_state(chat_id)

    # ---------- 撤销逻辑（回复账单消息 + 输入“撤销”） ----------
    if (
        text == "撤销"
        and update.message.reply_to_message
        and update.message.reply_to_message.from_user.is_bot
    ):
        if not is_admin(user.id):
            return

        replied_text = update.message.reply_to_message.text or ""
        # 当前展示格式：  12:34  10000  ¹⁰⁰⁰/ 153 = 58.82
        in_matches = re.findall(
            r"(\d{2}:\d{2})\s+([0-9]+(?:\.[0-9]+)?)\s+.*=\s*([0-9]+(?:\.[0-9]+)?)",
            replied_text,
        )
        out_matches = re.findall(
            r"(\d{2}:\d{2})\s+([0-9]+(?:\.[0-9]+)?)\s*$", replied_text, re.MULTILINE
        )

        in_match = in_matches[-1] if in_matches else None
        out_match = out_matches[-1] if out_matches else None

        if in_match:
            raw_amt = trunc2(float(in_match[1]))
            usdt_amt = trunc2(float(in_match[2]))

            state["summary"]["should_send_usdt"] = trunc2(
                state["summary"]["should_send_usdt"] - usdt_amt
            )
            state["recent"]["in"] = [
                r
                for r in state["recent"]["in"]
                if not (trunc2(r.get("raw", 0)) == raw_amt and trunc2(r.get("usdt", 0)) == usdt_amt)
            ]
            save_group_state(chat_id)

            append_log(
                log_path(chat_id, None, dstr),
                f"[撤销入金] 时间:{ts} 原金额:{raw_amt} USDT:{usdt_amt} 标记:无效操作",
            )
            await update.message.reply_text(
                f"✅ 已撤销入金记录\n📊 原金额：+{raw_amt} → {usdt_amt} USDT"
            )
            await update.message.reply_text(render_group_summary(chat_id))
            return

        elif out_match:
            usdt_amt = trunc2(float(out_match[1]))
            state["summary"]["should_send_usdt"] = trunc2(
                state["summary"]["should_send_usdt"] + usdt_amt
            )
            state["recent"]["out"] = [
                r for r in state["recent"]["out"] if trunc2(r.get("usdt", 0)) != usdt_amt
            ]
            save_group_state(chat_id)

            append_log(
                log_path(chat_id, None, dstr),
                f"[撤销下发] 时间:{ts} USDT:{usdt_amt} 标记:无效操作",
            )
            await update.message.reply_text(
                f"✅ 已撤销下发记录\n📊 原金额：{usdt_amt} USDT"
            )
            await update.message.reply_text(render_group_summary(chat_id))
            return

        else:
            await update.message.reply_text(
                "❌ 无法识别要撤销的操作\n💡 请回复包含入金或下发记录的账单消息"
            )
            return

    # ---------- 查看账单 ----------
    if text == "+0":
        await update.message.reply_text(render_group_summary(chat_id))
        return

    if text in ["更多记录", "查看更多记录", "更多账单", "显示历史账单"]:
        await update.message.reply_text(render_full_summary(chat_id))
        return

    # ---------- 管理员管理 ----------
    if text.startswith(
        ("设置管理员", "删除管理员", "显示管理员", "设置机器人管理员", "删除机器人管理员", "显示机器人管理员")
    ):
        admins = list_admins()

        # 显示
        if text.startswith(("显示管理员", "显示机器人管理员")):
            lines = ["👥 机器人管理员列表\n"]
            lines.append(f"⭐ 超级管理员：{OWNER_ID or '未设置'}\n")
            if admins:
                lines.append("📋 机器人管理员：")
                for admin_id in admins:
                    try:
                        member = await context.bot.get_chat_member(chat_id, admin_id)
                        u = member.user
                        name = u.full_name
                        username = f"@{u.username}" if u.username else ""
                        if username:
                            lines.append(f"• {name} ({username}) - ID: {admin_id}")
                        else:
                            lines.append(f"• {name} - ID: {admin_id}")
                    except Exception:
                        lines.append(f"• ID: {admin_id}")
            else:
                lines.append("暂无机器人管理员")
            await update.message.reply_text("\n".join(lines))
            return

        # 下面是设置/删除，要求操作者是管理员
        if not is_admin(user.id):
            await update.message.reply_text(
                "🚫 你没有权限设置机器人管理员。\n💡 只有机器人管理员可以执行此操作。"
            )
            return

        target = None
        # 优先使用 reply_to_message
        if update.message.reply_to_message:
            target = update.message.reply_to_message.from_user

        if not target:
            await update.message.reply_text(
                "❌ 请回复要设置/删除的用户消息\n\n示例：\n"
                "1️⃣ 回复对方消息并发送：设置机器人管理员\n"
                "2️⃣ 回复对方消息并发送：删除机器人管理员"
            )
            return

        if text.startswith(("设置管理员", "设置机器人管理员")):
            add_admin(target.id)
            await update.message.reply_text(
                f"✅ 已将 <a href=\"tg://user?id={target.id}\">{target.first_name}</a> 设置为机器人管理员。",
                parse_mode="HTML",
            )
        elif text.startswith(("删除管理员", "删除机器人管理员")):
            remove_admin(target.id)
            await update.message.reply_text(
                f"🗑️ 已移除 <a href=\"tg://user?id={target.id}\">{target.first_name}</a> 的机器人管理员权限。",
                parse_mode="HTML",
            )
        return

    # ---------- 查询国家点位 ----------
    if text.endswith("当前点位"):
        if not is_admin(user.id):
            return

        country = text.replace("当前点位", "").strip()
        if not country:
            await update.message.reply_text("❌ 请指定国家名称\n例如：美国当前点位")
            return

        countries = state["countries"]
        defaults = state["defaults"]

        # 入金
        in_rate = None
        in_fx = None
        if country in countries and "in" in countries[country]:
            in_rate = countries[country]["in"].get("rate")
            in_fx = countries[country]["in"].get("fx")
        if in_rate is None:
            in_rate = defaults["in"]["rate"]
            in_rate_source = "默认"
        else:
            in_rate_source = f"{country}专属"
        if in_fx is None:
            in_fx = defaults["in"]["fx"]
            in_fx_source = "默认"
        else:
            in_fx_source = f"{country}专属"

        # 出金
        out_rate = None
        out_fx = None
        if country in countries and "out" in countries[country]:
            out_rate = countries[country]["out"].get("rate")
            out_fx = countries[country]["out"].get("fx")
        if out_rate is None:
            out_rate = defaults["out"]["rate"]
            out_rate_source = "默认"
        else:
            out_rate_source = f"{country}专属"
        if out_fx is None:
            out_fx = defaults["out"]["fx"]
            out_fx_source = "默认"
        else:
            out_fx_source = f"{country}专属"

        lines = [
            f"📍【{country} 当前点位】\n",
            "📥 入金设置：",
            f"  • 费率：{in_rate*100:.0f}% ({in_rate_source})",
            f"  • 汇率：{in_fx} ({in_fx_source})\n",
            "📤 出金设置：",
            f"  • 费率：{abs(out_rate)*100:.0f}% ({out_rate_source})",
            f"  • 汇率：{out_fx} ({out_fx_source})",
        ]
        await update.message.reply_text("\n".join(lines))
        return

    # ---------- 重置默认值 ----------
    if text in ("重置默认值", "恢复默认值"):
        if not is_admin(user.id):
            return

        state["defaults"] = {
            "in": {"rate": 0.10, "fx": 153},
            "out": {"rate": 0.02, "fx": 137},
        }
        save_group_state(chat_id)
        await update.message.reply_text(
            "✅ 已重置为推荐默认值\n\n"
            "📥 入金设置：费率 10% / 汇率 153\n"
            "📤 出金设置：费率 2% / 汇率 137"
        )
        return

    # ---------- 简单设置命令（默认） ----------
    if text.startswith(("设置入金费率", "设置入金汇率", "设置出金费率", "设置出金汇率")):
        if not is_admin(user.id):
            return
        try:
            direction = ""
            key = ""
            val = 0.0
            display_val = ""

            if "入金费率" in text:
                direction, key = "in", "rate"
                val = float(text.replace("设置入金费率", "").strip()) / 100.0
                display_val = f"{val*100:.0f}%"
            elif "入金汇率" in text:
                direction, key = "in", "fx"
                val = float(text.replace("设置入金汇率", "").strip())
                display_val = str(val)
            elif "出金费率" in text:
                direction, key = "out", "rate"
                val = float(text.replace("设置出金费率", "").strip()) / 100.0
                display_val = f"{val*100:.0f}%"
            elif "出金汇率" in text:
                direction, key = "out", "fx"
                val = float(text.replace("设置出金汇率", "").strip())
                display_val = str(val)

            state["defaults"][direction][key] = val
            save_group_state(chat_id)

            type_name = "费率" if key == "rate" else "汇率"
            dir_name = "入金" if direction == "in" else "出金"
            await update.message.reply_text(
                f"✅ 已设置默认{dir_name}{type_name}\n📊 新值：{display_val}"
            )
        except ValueError:
            await update.message.reply_text(
                "❌ 格式错误，请输入有效数字\n例如：设置入金费率 10"
            )
        return

    # ---------- 高级设置命令（指定国家） ----------
    if text.startswith("设置") and not text.startswith(
        ("设置入金", "设置出金", "设置管理员", "设置机器人管理员")
    ):
        if not is_admin(user.id):
            return

        pattern = r"^设置\s*(.+?)(入|出)(费率|汇率)\s*(\d+(?:\.\d+)?)\s*$"
        m = re.match(pattern, text)
        if m:
            scope = m.group(1).strip()
            direction = "in" if m.group(2) == "入" else "out"
            key = "rate" if m.group(3) == "费率" else "fx"
            try:
                val = float(m.group(4))
                if key == "rate":
                    val /= 100.0

                if scope == "默认":
                    state["defaults"][direction][key] = val
                else:
                    state["countries"].setdefault(scope, {}).setdefault(direction, {})[
                        key
                    ] = val

                save_group_state(chat_id)
                type_name = "费率" if key == "rate" else "汇率"
                dir_name = "入金" if direction == "in" else "出金"
                display_val = f"{val*100:.0f}%" if key == "rate" else str(val)
                await update.message.reply_text(
                    f"✅ 已设置 {scope} {dir_name}{type_name}\n📊 新值：{display_val}"
                )
            except ValueError:
                await update.message.reply_text("❌ 数值格式错误")
            return

    # ---------- 入金 ----------
    if text.startswith("+"):
        if not is_admin(user.id):
            return
        amt, country = parse_amount_and_country(text)
        if amt is None:
            return
        p = resolve_params(chat_id, "in", country)

        if p["fx"] == 0:
            await update.message.reply_text("⚠️ 请先设置费率和汇率")
            return

        usdt = trunc2(amt * (1 - p["rate"]) / p["fx"])
        push_recent(
            chat_id,
            "in",
            {
                "ts": ts,
                "raw": amt,
                "usdt": usdt,
                "country": country,
                "fx": p["fx"],
                "rate": p["rate"],
            },
        )
        state["summary"]["should_send_usdt"] = trunc2(
            state["summary"]["should_send_usdt"] + usdt
        )
        save_group_state(chat_id)
        append_log(
            log_path(chat_id, country, dstr),
            f"[入金] 时间:{ts} 国家:{country or '通用'} 原始:{amt} "
            f"汇率:{p['fx']} 费率:{p['rate']*100:.2f}% 结果:{usdt}",
        )
        await update.message.reply_text(render_group_summary(chat_id))
        return

    # ---------- 出金 ----------
    if text.startswith("-"):
        if not is_admin(user.id):
            return
        amt, country = parse_amount_and_country(text)
        if amt is None:
            return
        p = resolve_params(chat_id, "out", country)

        if p["fx"] == 0:
            await update.message.reply_text("⚠️ 请先设置费率和汇率")
            return

        usdt = trunc2(amt * (1 + p["rate"]) / p["fx"])
        push_recent(
            chat_id,
            "out",
            {
                "ts": ts,
                "raw": amt,
                "usdt": usdt,
                "country": country,
                "fx": p["fx"],
                "rate": p["rate"],
            },
        )
        state["summary"]["sent_usdt"] = trunc2(
            state["summary"]["sent_usdt"] + usdt
        )
        save_group_state(chat_id)
        append_log(
            log_path(chat_id, country, dstr),
            f"[出金] 时间:{ts} 国家:{country or '通用'} 原始:{amt} "
            f"汇率:{p['fx']} 费率:{p['rate']*100:.2f}% 下发:{usdt}",
        )
        await update.message.reply_text(render_group_summary(chat_id))
        return

    # ---------- 下发USDT ----------
    if text.startswith("下发"):
        if not is_admin(user.id):
            return
        try:
            usdt_str = text.replace("下发", "").strip()
            usdt = trunc2(float(usdt_str))

            if usdt > 0:
                state["summary"]["should_send_usdt"] = trunc2(
                    state["summary"]["should_send_usdt"] - usdt
                )
                push_recent(chat_id, "out", {"ts": ts, "usdt": usdt, "type": "下发"})
                append_log(
                    log_path(chat_id, None, dstr),
                    f"[下发USDT] 时间:{ts} 金额:{usdt} USDT",
                )
            else:
                usdt_abs = trunc2(abs(usdt))
                state["summary"]["should_send_usdt"] = trunc2(
                    state["summary"]["should_send_usdt"] + usdt_abs
                )
                push_recent(chat_id, "out", {"ts": ts, "usdt": usdt, "type": "下发"})
                append_log(
                    log_path(chat_id, None, dstr),
                    f"[撤销下发] 时间:{ts} 金额:{usdt_abs} USDT",
                )

            save_group_state(chat_id)
            await update.message.reply_text(render_group_summary(chat_id))
        except ValueError:
            await update.message.reply_text(
                "❌ 格式错误，请输入有效的数字\n例如：下发35.04 或 下发-35.04"
            )
        return

    # 其他内容不处理（不回复）
    return


# ========== HTTP健康检查服务器 ==========

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/health"]:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # 静音访问日志
        pass


# ========== 初始化 & 启动 ==========

def init_bot():
    print("=" * 50)
    print("🚀 正在启动财务记账机器人 (Polling + JSON)...")
    print("=" * 50)

    if not BOT_TOKEN:
        print("❌ 错误：未找到 TELEGRAM_BOT_TOKEN 环境变量")
        raise SystemExit(1)

    print("✅ Bot Token 已加载")
    print(f"📊 数据目录: {DATA_DIR}")
    print(f"👑 超级管理员: {OWNER_ID or '未设置'}")

    # 启动 HTTP 健康检查
    port = int(os.getenv("PORT", "10000"))
    print(f"\n🌐 启动HTTP健康检查服务器（端口 {port}）...")

    def run_http_server():
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        print(f"✅ HTTP服务器已启动: http://0.0.0.0:{port}")
        server.serve_forever()

    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    print("\n🤖 配置 Telegram Bot (Polling 模式)...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(
        MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_text)
    )

    print("✅ Bot 处理器已注册")
    print("\n🎉 机器人正在运行，等待消息...")
    print("=" * 50)
    application.run_polling()


if __name__ == "__main__":
    init_bot()
