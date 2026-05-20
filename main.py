import os
import time
import logging
import threading
from datetime import datetime, timezone
import telebot
from dotenv import load_dotenv
import storage
import status_parser

# ─── Config ──────────────────────────────────────────────────────────

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROUP_ID = os.getenv("TELEGRAM_GROUP_ID")

REPORT_INTERVAL_SECONDS = 10 * 60  # 10 minutes
MAX_MESSAGE_LENGTH = 4096

if not TOKEN or TOKEN == "your_bot_token_here":
    print("❌ Please set TELEGRAM_BOT_TOKEN in your .env file")
    exit(1)

if not GROUP_ID or GROUP_ID == "your_group_chat_id_here":
    print("❌ Please set TELEGRAM_GROUP_ID in your .env file")
    print("   Tip: add the bot to the group, then send /chatid to get the ID")
    exit(1)

GROUP_ID = int(GROUP_ID)
bot = telebot.TeleBot(TOKEN)


# ─── Formatting helpers ───────────────────────────────────────────────

def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_report(components, incidents) -> str:
    """Format the full periodic status report."""
    if not components and not incidents:
        return (
            f"✅ <b>Yapily Status — Всё работает нормально</b>\n"
            f"🕐 {now_str()}\n\n"
            f"Активных инцидентов и проблем не обнаружено."
        )

    lines = [
        f"🚨 <b>Yapily Status Report</b>",
        f"🕐 {now_str()}\n"
    ]

    if incidents:
        lines.append("━━━ <b>Активные инциденты</b> ━━━\n")
        for inc in incidents:
            lines.append(
                f"{inc['impact_emoji']} <b>{inc['name']}</b>\n"
                f"   📍 {inc['source']}\n"
                f"   📊 Статус: <code>{inc['status']}</code>\n"
                f"   🕐 Обновлено: {inc['updated_at'][:16].replace('T', ' ')}\n"
            )

    if components:
        lines.append("\n━━━ <b>Компоненты с проблемами</b> ━━━\n")

        platform_comps = [c for c in components if not c.get("country")]
        institution_comps = [c for c in components if c.get("country")]

        if platform_comps:
            lines.append("<b>Yapily Platform:</b>")
            for comp in platform_comps:
                lines.append(f"  {comp['emoji']} {comp['name']} — {comp['label']}")
            lines.append("")

        if institution_comps:
            by_country = {}
            for comp in institution_comps:
                by_country.setdefault(comp["country"], []).append(comp)

            lines.append("<b>Yapily Institutions:</b>")
            for country in sorted(by_country.keys()):
                comps = by_country[country]
                flag = comps[0].get("flag", "🌍")
                lines.append(f"\n  {flag} <b>{country}</b>")
                for comp in comps:
                    lines.append(f"    {comp['emoji']} {comp['name']} — {comp['label']}")
            lines.append("")

    return "\n".join(lines)


def format_new_incident_alert(incident) -> str:
    return (
        f"🔴 <b>НОВЫЙ ИНЦИДЕНТ</b>\n\n"
        f"<b>{incident['name']}</b>\n"
        f"📍 {incident['source']}\n"
        f"📊 Статус: <code>{incident['status']}</code>\n"
        f"💥 Влияние: <code>{incident['impact']}</code>\n"
        f"🕐 Создан: {incident['created_at'][:16].replace('T', ' ')}\n\n"
        f"🔗 <a href='{incident['page_url']}'>Перейти на страницу статуса</a>"
    )


def format_status_change_alert(incident, old_status) -> str:
    return (
        f"🔄 <b>ИЗМЕНЕНИЕ СТАТУСА</b>\n\n"
        f"<b>{incident['name']}</b>\n"
        f"📍 {incident['source']}\n"
        f"📊 <code>{old_status}</code> → <code>{incident['status']}</code>\n"
        f"🕐 Обновлено: {incident['updated_at'][:16].replace('T', ' ')}\n\n"
        f"🔗 <a href='{incident['page_url']}'>Перейти на страницу статуса</a>"
    )


def format_resolved_alert(incident_name, old_status) -> str:
    return (
        f"✅ <b>ИНЦИДЕНТ РАЗРЕШЁН</b>\n\n"
        f"<b>{incident_name}</b>\n"
        f"📊 Был: <code>{old_status}</code>\n\n"
        f"Инцидент больше не активен."
    )


# ─── Send helpers ─────────────────────────────────────────────────────

def send_to_group(text: str):
    """Send a message to the group, splitting automatically if it exceeds Telegram's 4096-char limit."""
    try:
        if len(text) <= MAX_MESSAGE_LENGTH:
            bot.send_message(GROUP_ID, text, parse_mode="HTML", disable_web_page_preview=True)
            return
        # Split at newline boundaries to avoid cutting mid-line
        parts = []
        while text:
            if len(text) <= MAX_MESSAGE_LENGTH:
                parts.append(text)
                break
            split_at = text.rfind('\n', 0, MAX_MESSAGE_LENGTH)
            if split_at <= 0:
                split_at = MAX_MESSAGE_LENGTH
            parts.append(text[:split_at])
            text = text[split_at:].lstrip('\n')
        for part in parts:
            bot.send_message(GROUP_ID, part, parse_mode="HTML", disable_web_page_preview=True)
    except Exception as e:
        print(f"⚠️ Failed to send message to group: {e}")


# ─── Bot commands ─────────────────────────────────────────────────────

@bot.message_handler(commands=['start', 'help'])
def send_help(message):
    bot.reply_to(
        message,
        "<b>🤖 Yapily Status Bot</b>\n\n"
        "Этот бот автоматически присылает в группу отчёт о состоянии "
        "платежных шлюзов Yapily каждые <b>10 минут</b>.\n\n"
        "<b>Команды:</b>\n"
        "/status — немедленный отчёт о текущих проблемах\n"
        "/help — эта справка\n\n"
        "<b>Цвета статусов:</b>\n"
        "🔴 Major Outage — серьёзный сбой\n"
        "🟡 Partial Outage / Degraded — частичные проблемы\n"
        "🟢 Operational — всё работает нормально",
        parse_mode="HTML"
    )


@bot.message_handler(commands=['status'])
def send_status(message):
    bot.send_chat_action(message.chat.id, 'typing')
    components, incidents, _ = status_parser.get_all_problems()
    msg = format_report(components, incidents)
    bot.reply_to(message, msg, parse_mode="HTML", disable_web_page_preview=True)


@bot.message_handler(commands=['chatid'])
def send_chat_id(message):
    """Helper command to get the current chat ID (useful for setup)."""
    bot.reply_to(message, f"Chat ID этой группы: <code>{message.chat.id}</code>", parse_mode="HTML")


# ─── Background thread ────────────────────────────────────────────────

def monitor_loop():
    """
    Main monitoring loop:
      - Every 10 minutes: sends a full status report to the group.
      - Immediately (between reports): sends instant alerts for new/changed/resolved incidents.
      - Skips diff and storage update entirely if any API call failed (preserves last known state).
    """
    print(f"🔄 Monitoring started. Report interval: {REPORT_INTERVAL_SECONDS // 60} minutes.")
    last_report_time = time.time()  # avoids sending a second report right after startup

    while True:
        try:
            old_incidents = storage.get_notified_incidents()  # {id: {"status": ..., "name": ...}}
            components, current_incidents_list, had_errors = status_parser.get_all_problems()
            current_incidents = {inc["id"]: inc for inc in current_incidents_list}

            if had_errors:
                print(f"⚠️ API fetch had errors at {now_str()} — skipping diff and storage update")
            else:
                # ── 1. Instant alerts for changes ────────────────────────
                for inc_id, inc in current_incidents.items():
                    if inc_id not in old_incidents:
                        send_to_group(format_new_incident_alert(inc))
                    elif old_incidents[inc_id]["status"] != inc["status"]:
                        send_to_group(format_status_change_alert(inc, old_incidents[inc_id]["status"]))

                for inc_id, old_data in old_incidents.items():
                    if inc_id not in current_incidents:
                        send_to_group(format_resolved_alert(old_data["name"], old_data["status"]))

                if old_incidents and not current_incidents and not components:
                    send_to_group(
                        f"✅ <b>Все шлюзы работают нормально</b>\n"
                        f"🕐 {now_str()}\n\n"
                        f"Активных инцидентов и проблем не обнаружено."
                    )

                storage.update_notified_incidents(
                    {inc_id: {"status": inc["status"], "name": inc["name"]}
                     for inc_id, inc in current_incidents.items()}
                )

                # ── 2. Periodic full report every 10 minutes ─────────────
                now = time.time()
                if now - last_report_time >= REPORT_INTERVAL_SECONDS:
                    report = format_report(components, current_incidents_list)
                    send_to_group(report)
                    last_report_time = now
                    print(f"📊 Report sent at {now_str()}")

        except Exception as e:
            print(f"⚠️ Monitor error: {e}")

        time.sleep(60)


# ─── Main ─────────────────────────────────────────────────────────────

def _fetch_initial_snapshot(max_retries=3, retry_delay=10):
    """Fetch current incidents for startup snapshot, retrying on API errors."""
    for attempt in range(max_retries):
        _, current, had_errors = status_parser.get_all_problems()
        if not had_errors:
            return {inc["id"]: {"status": inc["status"], "name": inc["name"]} for inc in current}
        if attempt < max_retries - 1:
            print(f"⚠️ API error on startup (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
            time.sleep(retry_delay)
    print("⚠️ Could not get clean snapshot on startup — bot may re-alert on existing incidents")
    return {inc["id"]: {"status": inc["status"], "name": inc["name"]} for inc in current}


if __name__ == '__main__':
    print(f"🤖 Yapily Status Bot starting...")
    print(f"   Group ID: {GROUP_ID}")

    # Clear any existing webhook or conflicting session
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception as e:
        print(f"⚠️ Could not remove webhook: {e}")

    # On first run: snapshot current incidents so we don't spam on startup
    initial_state = _fetch_initial_snapshot()
    storage.update_notified_incidents(initial_state)
    print(f"📋 Initial snapshot: {len(initial_state)} active incident(s)")

    # Start background monitor
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    # Send startup notification to group
    send_to_group(
        f"🤖 <b>Yapily Status Bot запущен</b>\n"
        f"🕐 {now_str()}\n\n"
        f"Мониторинг активирован. Отчёты каждые 10 минут.\n"
        f"Мгновенные уведомления о новых инцидентах: вкл ✅"
    )

    print("✅ Bot is running. Listening for commands...")
    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=30,
        logger_level=logging.WARNING,
    )
