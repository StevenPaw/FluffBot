import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.helpers import mention_html
import json

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

DATA_FILE = "/app/data/anmeldung_data.json"

OPTIONS = [
    "Spotter",
    "Suiter (Fullsuit)",
    "Suiter (Partsuit)",
    "Fotofur",
    "Abmelden"
]

GUARDIAN_OPTIONS = {"Spotter", "Fotofur"}
PLAYER_OPTIONS = {"Suiter (Fullsuit)", "Suiter (Partsuit)"}

poll_participation = {}        # msg_id -> {user_id: (option, user)}
poll_order = {}                # msg_id -> [user_id]
poll_chat = {}                 # msg_id -> chat_id
poll_titles = {}               # msg_id -> title
anmeldung_status = {}          # msg_id -> bool
zugang_status = {}             # msg_id -> "all"|"guardians"|"suiter"
option_limits = {}             # msg_id -> {option: limit}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "poll_titles": poll_titles,
            "poll_chat": poll_chat,
            "poll_order": poll_order,
            "anmeldung_status": anmeldung_status,
            "zugang_status": zugang_status,
            "option_limits": option_limits,
        }, f)

def load_data():
    global poll_titles, poll_chat, poll_order, anmeldung_status, zugang_status, option_limits
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            poll_titles = data.get("poll_titles", {})
            poll_chat = data.get("poll_chat", {})
            poll_order = data.get("poll_order", {})
            anmeldung_status = data.get("anmeldung_status", {})
            zugang_status = data.get("zugang_status", {})
            option_limits = data.get("option_limits", {})
    except FileNotFoundError:
        pass

def get_allowed_options(mode: str):
    if mode == "guardians":
        return list(GUARDIAN_OPTIONS) + ["Abmelden"]
    elif mode == "suiter":
        return list(PLAYER_OPTIONS) + ["Abmelden"]
    return OPTIONS.copy()

def generate_keyboard(msg_id):
    if not anmeldung_status.get(str(msg_id), True):
        return None
    mode = zugang_status.get(str(msg_id), "all")
    allowed = get_allowed_options(mode)
    return InlineKeyboardMarkup([
    [InlineKeyboardButton(opt, callback_data=f"vote|{opt}|{str(msg_id)}")] for opt in allowed
])

async def fluff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Verfügbare Befehle:\n"
            "/fluff anmeldung [Titel]\n"
            "/fluff toggle\n"
            "/fluff zugang [all|guardians|suiter]\n"
            "/fluff limit [Option] [Zahl] (als Antwort auf eine Anmeldungsnachricht)\n"
            "/fluff limit [Option] none (um Limit zu entfernen)"
        )
        return

    subcommand = context.args[0].lower()
    args = context.args[1:]

    if subcommand == "anmeldung":
        await handle_anmeldung(update, context, args)
    elif subcommand == "toggle":
        await handle_toggle(update, context)
    elif subcommand == "zugang":
        await handle_zugang(update, context, args)
    elif subcommand == "limit":
        await handle_limit(update, context, args)
    else:
        await update.message.reply_text("Unbekannter Befehl. Nutze /fluff für Hilfe.")

async def handle_anmeldung(update: Update, context: ContextTypes.DEFAULT_TYPE, args):
    chat = update.effective_chat
    user = update.effective_user
    admins = await context.bot.get_chat_administrators(chat.id)
    if user.id not in [admin.user.id for admin in admins]:
        await update.message.reply_text("Nur Admins dürfen das.")
        return

    title = " ".join(args) if args else "Anmeldung"
    msg = await context.bot.send_message(
        chat_id=chat.id,
        text=f"<b>Anmeldung: {title}</b>\n\nNoch keine Teilnahme.",
        parse_mode="HTML"
    )

    mid = msg.message_id
    poll_participation[str(mid)] = {}
    poll_order[str(mid)] = []
    poll_chat[str(mid)] = chat.id
    poll_titles[str(mid)] = title
    anmeldung_status[str(mid)] = True
    zugang_status[str(mid)] = "all"
    option_limits[str(mid)] = {opt: None for opt in OPTIONS if opt != "Abmelden"}

    save_data()
    await msg.edit_reply_markup(reply_markup=generate_keyboard(mid))

async def handle_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Bitte antworte auf die Anmeldungsnachricht.")
        return
    msg_id = update.message.reply_to_message.message_id
    user = update.effective_user
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    if user.id not in [admin.user.id for admin in admins]:
        await update.message.reply_text("Nur Admins dürfen das.")
        return

    anmeldung_status[str(msg_id)] = not anmeldung_status.get(str(msg_id), True)
    status = "geöffnet" if anmeldung_status[str(msg_id)] else "geschlossen"
    await update.message.reply_text(f"Anmeldung wurde {status}.")
    save_data()
    await update_anmeldung_text(context.application, msg_id)

async def handle_zugang(update: Update, context: ContextTypes.DEFAULT_TYPE, args):
    if not update.message.reply_to_message:
        await update.message.reply_text("Bitte antworte auf die Anmeldungsnachricht.")
        return
    msg_id = update.message.reply_to_message.message_id
    user = update.effective_user
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    if user.id not in [admin.user.id for admin in admins]:
        await update.message.reply_text("Nur Admins dürfen das.")
        return

    if not args or args[0] not in ("all", "guardians", "suiter"):
        await update.message.reply_text("Nutzung: /fluff zugang all | guardians | suiter")
        return

    zugang_status[str(msg_id)] = args[0]
    await update.message.reply_text(f"Zugang geändert auf: <b>{args[0]}</b>", parse_mode="HTML")
    save_data()
    await update_anmeldung_text(context.application, msg_id)

async def handle_limit(update: Update, context: ContextTypes.DEFAULT_TYPE, args):
    if not update.message.reply_to_message or len(args) != 2:
        await update.message.reply_text("Nutzung: /fluff limit [Option] [Zahl|none] (als Antwort auf Anmeldungsnachricht)")
        return
    msg_id = update.message.reply_to_message.message_id
    option, value = args[0], args[1]
    if option not in OPTIONS or option == "Abmelden":
        await update.message.reply_text("Ungültige Option.")
        return

    if str(msg_id) not in option_limits:
        option_limits[str(msg_id)] = {opt: None for opt in OPTIONS if opt != "Abmelden"}

    if value.lower() == "none":
        option_limits[str(msg_id)][option] = None
        await update.message.reply_text(f"Limit für {option} entfernt.")
    else:
        try:
            limit = int(value)
            option_limits[str(msg_id)][option] = limit
            await update.message.reply_text(f"Limit für {option} auf {limit} gesetzt.")
        except ValueError:
            await update.message.reply_text("Ungültige Zahl.")
            return

    save_data()
    await update_anmeldung_text(context.application, msg_id)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if not query.message or not query.data.startswith("vote|"):
        return

    parts = query.data.split("|")
    if len(parts) != 3:
        return

    option, msg_id = parts[1], parts[2]

    if not anmeldung_status.get(msg_id, True):
        await query.answer("Die Anmeldung ist geschlossen.", show_alert=True)
        return

    allowed = get_allowed_options(zugang_status.get(msg_id, "all"))
    if option not in allowed:
        await query.answer("Diese Option ist aktuell nicht verfügbar.", show_alert=True)
        return

    participation = poll_participation.setdefault(str(msg_id), {})
    order = poll_order.setdefault(str(msg_id), [])

    if int(user.id) in participation:
        del participation[int(user.id)]
        if int(user.id) in order:
            order.remove(int(user.id))

    if option != "Abmelden":
        participation[int(user.id)] = (option, user)
        order.append(int(user.id))

    await update_anmeldung_text(context.application, int(msg_id))

async def update_anmeldung_text(app, msg_id, note: str = ""):
    str_id = str(msg_id)
    try:
        participation = poll_participation.get(str_id, {})
        order = poll_order.get(str_id, [])
        mode = zugang_status.get(str_id, "all")
        limits = option_limits.get(str_id, {})
        title = poll_titles.get(str_id, "Anmeldung")
        chat_id = poll_chat.get(str_id)
        user_lists = {opt: [] for opt in OPTIONS if opt != "Abmelden"}
        guardian_count = 0
        player_count = 0

        for uid in order:
            if uid in participation:
                opt, u = participation[uid]
                tag = mention_html(u.id, f"@{u.username}" if u.username else u.first_name)
                user_lists[opt].append(tag)
                if opt in GUARDIAN_OPTIONS:
                    guardian_count += 1
                elif opt in PLAYER_OPTIONS:
                    player_count += 1

        lines = [f"<b>Anmeldung: {title}</b>"]
        if not anmeldung_status.get(str_id, True):
            lines.append("\n<i>Anmeldung geschlossen</i>")

        for opt in OPTIONS:
            if opt == "Abmelden":
                continue
            users = user_lists[opt]
            if users:
                limit = limits.get(opt)
                limit = int(limit) if isinstance(limit, int) else None
                if limit:
                    head = f"<b>{opt} ({min(len(users), limit)}/{limit}):</b>"
                else:
                    head = f"<b>{opt} ({len(users)}):</b>"
                entries = []
                for i, name in enumerate(users):
                    if limit is not None and i >= limit:
                        entries.append(f"{i+1}. <i>{name}</i>")
                    else:
                        entries.append(f"{i+1}. {name}")
                lines.append("\n" + head + "\n" + "\n".join(entries))

        if len(lines) == 1:
            lines.append("\nNoch keine Teilnahme.")

        lines.append(f"\n<b>Verhältnis Spotter+Fotofur zu Suitern:</b> {guardian_count} : {player_count}")
        if note:
            lines.append(f"\n<i>{note}</i>")

        await app.bot.edit_message_text(
            "\n".join(lines),
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="HTML",
            reply_markup=generate_keyboard(msg_id)
        )
    except Exception as e:
        print(f"Fehler beim Aktualisieren: {e}")

if __name__ == "__main__":
    load_data()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("fluff", fluff_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
