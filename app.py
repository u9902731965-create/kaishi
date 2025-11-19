# app.py
import os
import json
import asyncio
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from flask import Flask, request, jsonify

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ========================================
# 日志配置
# ========================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ========================================
# 环境变量 & 配置
# ========================================

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_ID = int(os.environ.get("OWNER_ID", "0") or 0)
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").strip()
PORT = int(os.environ.get("PORT", "5000"))

# JSON 文件数据库路径
DB_FILE = os.environ.get("JSON_DB_FILE", "data/db.json")

# 北京时间（UTC+8）
CST = timezone(timedelta(hours=8))

# 默认费率 & 汇率（可以按需要改成从环境变量读取）
DEFAULT_FEE_RATE = Decimal("0.20")   # 20%
DEFAULT_IN_RATE = Decimal("153.00")  # 入汇率
DEFAULT_OUT_RATE = Decimal("142.00")  # 出汇率

# Telegram Application & 事件循环
application: Application | None = None
bot_loop: asyncio.AbstractEventLoop | None = None

# ========================================
# JSON DB 工具函数
# 结构：
# {
#   "<chat_id>": {
#       "<YYYY-MM-DD>": [ record, ... ]
#   },
#   ...
# }
# record:
# {
#   "id": "<毫秒时间戳>",
#   "user_id": int,
#   "username": str | null,
#   "type": "in" | "out" | "send",
#   "amount": float,
#   "ts": ISO8601 str
# }
# ========================================

def ensure_db_dir():
    path = Path(DB_FILE)
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def load_db() -> dict:
    ensure_db_dir()
    if not Path(DB_FILE).exists():
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("加载 JSON 数据库失败: %s", e)
        return {}


def save_db(db: dict) -> None:
    ensure_db_dir()
    tmp = DB_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_FILE)


def get_today_key(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now(CST)
    return dt.strftime("%Y-%m-%d")


# ========================================
# 金额格式化：入账截断两位；出账/下发四舍五入两位
# ========================================

def format_in_amount(amount: Decimal | float | int) -> Decimal:
    d = Decimal(str(amount))
    return d.quantize(Decimal("0.00"), rounding=ROUND_DOWN)


def format_out_amount(amount: Decimal | float | int) -> Decimal:
    d = Decimal(str(amount))
    return d.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)


# ========================================
# 金额解析：支持 +100、+100.5、+1千、+1万、+10000、+1k、+1w 等
# ========================================

def parse_amount_text(text: str) -> Decimal | None:
    """
    把类似 "100", "100.5", "1千", "1万", "1k", "1w" 解析为 Decimal
    不管正负号，这里只解析数值大小；正负由外层决定。
    """
    t = text.strip()
    if not t:
        return None

    multiplier = Decimal("1")

    # 常见中文/英文单位
    if t.endswith(("千", "k", "K")):
        multiplier = Decimal("1000")
        t = t[:-1]
    elif t.endswith(("万", "w", "W")):
        multiplier = Decimal("10000")
        t = t[:-1]

    # 去掉多余空格
    t = t.strip()
    try:
        base = Decimal(t)
    except Exception:
        return None

    return base * multiplier


# ========================================
# 记录读写：新增记录、撤销、清空
# ========================================

def add_record(
    chat_id: int,
    user_id: int,
    username: str | None,
    kind: str,
    amount: Decimal,
    ts: datetime | None = None,
) -> dict:
    """
    kind: "in" | "out" | "send"
    amount: Decimal
    """
    if ts is None:
        ts = datetime.now(CST)

    db = load_db()
    chat_key = str(chat_id)
    day_key = get_today_key(ts)

    chat_data = db.setdefault(chat_key, {})
    day_records: list[dict] = chat_data.setdefault(day_key, [])

    record = {
        "id": str(int(ts.timestamp() * 1000)),
        "user_id": int(user_id),
        "username": username,
        "type": kind,
        "amount": float(amount),
        "ts": ts.isoformat(),
    }
    day_records.append(record)
    save_db(db)
    return record


def get_today_records(chat_id: int) -> list[dict]:
    db = load_db()
    chat_key = str(chat_id)
    day_key = get_today_key()
    return list(db.get(chat_key, {}).get(day_key, []))


def set_today_records(chat_id: int, records: list[dict]) -> None:
    db = load_db()
    chat_key = str(chat_id)
    day_key = get_today_key()
    chat_data = db.setdefault(chat_key, {})
    chat_data[day_key] = list(records)
    save_db(db)


def undo_last_record(chat_id: int) -> dict | None:
    """撤销今天最后一条记录"""
    db = load_db()
    chat_key = str(chat_id)
    day_key = get_today_key()

    chat_data = db.get(chat_key)
    if not chat_data:
        return None
    day_records = chat_data.get(day_key)
    if not day_records:
        return None

    record = day_records.pop()
    save_db(db)
    return record


def clear_today_records(chat_id: int) -> int:
    """清空今天所有记录，返回删除数量"""
    db = load_db()
    chat_key = str(chat_id)
    day_key = get_today_key()

    chat_data = db.get(chat_key)
    if not chat_data:
        return 0

    records = chat_data.get(day_key, [])
    count = len(records)
    chat_data[day_key] = []
    save_db(db)
    return count


# ========================================
# 汇总文本生成：已入账 / 已出账 / 已下发 + 当前统计
# ========================================

def build_summary_text(chat_id: int) -> str:
    records = get_today_records(chat_id)
    if not records:
        return "今天还没有任何记录，可以直接发送 +100 或 -50 这样的消息来记账。"

    # 按类型分组
    in_records = [r for r in records if r.get("type") == "in"]
    out_records = [r for r in records if r.get("type") == "out"]
    send_records = [r for r in records if r.get("type") == "send"]

    # ===== 已入账 =====
    lines_in: list[str] = []
    total_in_raw = Decimal("0")
    for r in in_records:
        amt_raw = Decimal(str(r.get("amount", 0)))
        total_in_raw += amt_raw
        amt_disp = format_in_amount(amt_raw)

        ts = r.get("ts", "")
        time_str = ""
        if ts:
            try:
                t = datetime.fromisoformat(ts)
                time_str = t.astimezone(CST).strftime("%H:%M")
            except Exception:
                pass

        lines_in.append(f"{time_str} {amt_disp}")

    total_in_disp = format_in_amount(total_in_raw)

    # ===== 已出账 =====
    lines_out: list[str] = []
    total_out_raw = Decimal("0")
    for r in out_records:
        amt_raw = Decimal(str(r.get("amount", 0)))
        total_out_raw += amt_raw
        amt_disp = format_out_amount(amt_raw)

        ts = r.get("ts", "")
        time_str = ""
        if ts:
            try:
                t = datetime.fromisoformat(ts)
                time_str = t.astimezone(CST).strftime("%H:%M")
            except Exception:
                pass

        lines_out.append(f"{time_str} {amt_disp}")

    total_out_disp = format_out_amount(total_out_raw)

    # ===== 已下发 =====
    lines_send: list[str] = []
    total_send_raw = Decimal("0")
    for r in send_records:
        amt_raw = Decimal(str(r.get("amount", 0)))
        total_send_raw += amt_raw
        amt_disp = format_out_amount(amt_raw)

        ts = r.get("ts", "")
        time_str = ""
        if ts:
            try:
                t = datetime.fromisoformat(ts)
                time_str = t.astimezone(CST).strftime("%H:%M")
            except Exception:
                pass

        lines_send.append(f"{time_str} {amt_disp}")

    total_send_disp = format_out_amount(total_send_raw)

    # ===== 费率 & 汇率 & 应下发 =====
    fee_rate = DEFAULT_FEE_RATE
    in_rate = DEFAULT_IN_RATE
    out_rate = DEFAULT_OUT_RATE

    # 这里示例：应下发 = 入账总额 * (1 - 手续费) / 出汇率
    # 你可以根据自己之前 SQL 版的公式微调
    # 假设 total_in_raw 是“本币金额”，先减手续费，再用出汇率换算成 USDT
    # 这里只是一个通用示例：
    # 先换成 USDT
    if in_rate > 0:
        in_usdt = total_in_raw / in_rate  # 入汇率换成 USDT
    else:
        in_usdt = Decimal("0")

    in_usdt_after_fee = in_usdt * (Decimal("1") - fee_rate)
    should_send = in_usdt_after_fee * out_rate  # 按出汇率再换成对方币，保持原习惯可改
    should_send_disp = format_out_amount(should_send)

    # 未下发 = 应下发 - 已下发
    un_send = should_send - total_send_raw
    un_send_disp = format_out_amount(un_send)

    # ===== 文本拼接 =====
    parts: list[str] = []

    # 已入账
    parts.append(f"已入账 ({len(in_records)}笔)")
    if lines_in:
        parts.extend(lines_in)
    else:
        parts.append("无")

    parts.append("")

    # 已出账
    parts.append(f"已出账 ({len(out_records)}笔)")
    if lines_out:
        parts.extend(lines_out)
    else:
        parts.append("无")

    parts.append("")

    # 已下发
    parts.append(f"已下发 ({len(send_records)}笔)")
    if lines_send:
        parts.extend(lines_send)
    else:
        parts.append("无")

    parts.append("")
    parts.append("━━━━━━━━━━━━━━━━━━━━")

    parts.append(f"⚙ 当前费率：入 {int(fee_rate * 100)}%  出 0%")
    parts.append(f"📊 固定汇率：入 {in_rate} → 出 {out_rate}")
    parts.append(f"📥 应下发：{should_send_disp} USDT")
    parts.append(f"📤 已下发：{total_send_disp} USDT")
    parts.append(f"⏳ 未下发：{un_send_disp} USDT")

    return "\n".join(parts)


# ========================================
# Telegram 处理函数
# ========================================

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 查看账单明细")],
        [KeyboardButton("撤销"), KeyboardButton("清空今天")],
    ],
    resize_keyboard=True,
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "欢迎使用多功能记账机器人（JSON版）\n\n"
        "直接发送：\n"
        "  • +100   （记入账）\n"
        "  • -50    （记出账）\n"
        "  • +1千 / +1万 / +10000  都可以识别\n\n"
        "特殊指令：\n"
        "  • 发送“撤销” 或 /undo  撤销今天最后一条记录\n"
        "  • 发送“清空今天” 或 /clear_today  清空今天所有记录\n"
        "  • 点击“📊 查看账单明细” 查看今天账单汇总\n"
    )
    await update.effective_message.reply_text(text, reply_markup=MAIN_KEYBOARD)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = build_summary_text(chat_id)
    await update.effective_message.reply_text(text, reply_markup=MAIN_KEYBOARD)


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    record = undo_last_record(chat_id)
    if not record:
        await update.effective_message.reply_text("今天没有可以撤销的记录。", reply_markup=MAIN_KEYBOARD)
        return

    kind = record.get("type")
    amt = Decimal(str(record.get("amount", 0)))
    if kind == "in":
        kind_text = "入账"
        amt_disp = format_in_amount(amt)
        sign = "+"
    elif kind == "out":
        kind_text = "出账"
        amt_disp = format_out_amount(amt)
        sign = "-"
    else:
        kind_text = "下发"
        amt_disp = format_out_amount(amt)
        sign = "-"

    msg = f"已撤销最近一条{kind_text}记录：{sign}{amt_disp}\n如需继续撤销，请再次发送 /undo 或 “撤销”。"
    await update.effective_message.reply_text(msg, reply_markup=MAIN_KEYBOARD)


async def cmd_clear_today(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    count = clear_today_records(chat_id)
    await update.effective_message.reply_text(
        f"已清空今天的记录，共 {count} 条。", reply_markup=MAIN_KEYBOARD
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    chat_id = update.effective_chat.id
    user = update.effective_user

    text = (msg.text or "").strip()

    # 快捷按钮：查看账单明细
    if text == "📊 查看账单明细":
        await cmd_summary(update, context)
        return

    # 撤销
    if text in {"撤销", "/undo"}:
        await cmd_undo(update, context)
        return

    # 清空今天
    if text in {"清空今天", "/clear_today"}:
        await cmd_clear_today(update, context)
        return

    # 下发：例如 “下发100” “下发 1000”
    if text.startswith("下发"):
        rest = text[2:].strip()
        if not rest:
            await msg.reply_text("格式示例：下发100 或 下发 1000", reply_markup=MAIN_KEYBOARD)
            return
        amt = parse_amount_text(rest)
        if amt is None or amt <= 0:
            await msg.reply_text("下发金额格式错误，请重新输入。", reply_markup=MAIN_KEYBOARD)
            return

        add_record(
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            kind="send",
            amount=amt,
        )
        await msg.reply_text(
            f"✅ 已记录一条下发：- {format_out_amount(amt)}",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    # +金额 / -金额
    if text.startswith(("+", "＋", "-", "－")):
        sign_char = text[0]
        body = text[1:].strip()
        if not body:
            await msg.reply_text("格式：+100 或 -50", reply_markup=MAIN_KEYBOARD)
            return

        amt = parse_amount_text(body)
        if amt is None or amt <= 0:
            await msg.reply_text("金额格式错误，请重新输入，例如：+100 或 -50", reply_markup=MAIN_KEYBOARD)
            return

        is_in = sign_char in {"+", "＋"}
        kind = "in" if is_in else "out"
        add_record(
            chat_id=chat_id,
            user_id=user.id,
            username=user.username,
            kind=kind,
            amount=amt,
        )

        if is_in:
            amt_disp = format_in_amount(amt)
            await msg.reply_text(
                f"✅ 已记录一条入账：+{amt_disp}",
                reply_markup=MAIN_KEYBOARD,
            )
        else:
            amt_disp = format_out_amount(amt)
            await msg.reply_text(
                f"✅ 已记录一条出账：-{amt_disp}",
                reply_markup=MAIN_KEYBOARD,
            )

        # 顺便附带今日统计简要
        summary = build_summary_text(chat_id)
        await msg.reply_text(summary, reply_markup=MAIN_KEYBOARD)
        return

    # 其它文本：简单提示
    await msg.reply_text(
        "无法识别的指令。\n\n"
        "记账示例：\n"
        "  • +100  （入账）\n"
        "  • -50   （出账）\n"
        "  • 下发100 （记录下发）\n\n"
        "也可以点击下面的按钮查看账单或撤销。",
        reply_markup=MAIN_KEYBOARD,
    )


# ========================================
# Telegram Bot 初始化 & Webhook 支持
# ========================================

async def setup_webhook(app: Application):
    if WEBHOOK_URL:
        url = WEBHOOK_URL.rstrip("/") + f"/webhook/{BOT_TOKEN}"
        await app.bot.set_webhook(url)
        logger.info("✅ Webhook 已设置为: %s", url)
    else:
        logger.info("未设置 WEBHOOK_URL，使用 polling 模式。")


def start_telegram_bot_in_thread():
    global application, bot_loop
    if not BOT_TOKEN:
        logger.error("环境变量 TELEGRAM_BOT_TOKEN 未设置，无法启动 Bot")
        return

    async def _init_app():
        global application
        application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .build()
        )

        # 注册处理器
        application.add_handler(CommandHandler("start", cmd_start))
        application.add_handler(CommandHandler("help", cmd_help))
        application.add_handler(CommandHandler("summary", cmd_summary))
        application.add_handler(CommandHandler("undo", cmd_undo))
        application.add_handler(CommandHandler("clear_today", cmd_clear_today))

        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
        )

        await application.initialize()
        await setup_webhook(application)
        await application.start()
        logger.info("✅ Telegram Bot 初始化完成")

        # 如果没有 Webhook，就使用 polling
        if not WEBHOOK_URL:
            await application.run_polling(stop_signals=None)
        else:
            # Webhook 模式下，事件循环保持运行
            while True:
                await asyncio.sleep(3600)

    def _runner():
        global bot_loop
        bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(bot_loop)
        bot_loop.run_until_complete(_init_app())

    t = threading.Thread(target=_runner, name="telegram-bot-thread", daemon=True)
    t.start()
    logger.info("🔄 已启动 Telegram Bot 后台线程")


# ========================================
# Flask 应用（Web Dashboard + Webhook 接收）
# ========================================

flask_app = Flask(__name__)


@flask_app.route("/", methods=["GET"])
def index():
    return "Telegram 财务 Bot (JSON版) 正在运行", 200


@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook_handler():
    """
    Telegram Webhook 接收入口：
    将 Update 投递到 Telegram Application 处理
    """
    global application, bot_loop
    if not WEBHOOK_URL:
        return "Webhook 未启用", 400
    if application is None or bot_loop is None:
        logger.error("Application 尚未初始化，无法处理 webhook 更新")
        return "Application not ready", 503

    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)

    # 在 Bot 事件循环中异步处理
    asyncio.run_coroutine_threadsafe(
        application.process_update(update),
        bot_loop,
    )
    return "OK", 200


# ========================================
# 主入口
# ========================================

def main():
    logger.info("==================================================")
    logger.info("🚀 启动Telegram财务Bot (JSON 文件数据库版本)...")
    logger.info("📋 环境变量检查：")
    logger.info("   PORT=%s", PORT)
    logger.info("   DATABASE_URL=未使用（JSON 模式）")
    logger.info("   TELEGRAM_BOT_TOKEN=%s", "已设置" if BOT_TOKEN else "未设置")
    logger.info("   OWNER_ID=%s", OWNER_ID)
    logger.info("   WEBHOOK_URL=%s", WEBHOOK_URL or "未设置")
    logger.info("   SESSION_SECRET=（如有自行管理）")
    logger.info("==================================================")

    # 启动 Telegram Bot 后台线程
    start_telegram_bot_in_thread()

    # 启动 Flask HTTP 服务
    flask_app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
