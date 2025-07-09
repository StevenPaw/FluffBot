from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.helpers import mention_html

import os

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

OPTIONS = [
    "Spotter",
    "Suiter (Fullsuit)",
    "Suiter (Partsuit)",
    "Fotofur",
    "Abmelden"
]

# Dict zum Speichern der Teilnahme (message_id → {user_id → (option, user)})
poll_participation = {}
# Reihenfolge der Nutzer pro Nachricht merken
poll_order = {}

async def anmeldung_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Nur Gruppenadmins dürfen den Befehl nutzen
    chat = update.effective_chat
    user = update.effective_user

    admins = await context.bot.get_chat_administrators(chat.id)
    admin_ids = [admin.user.id for admin in admins]

    if user.id not in admin_ids:
        await update.message.reply_text("Nur Gruppen-Admins dürfen diese Anmeldung erstellen.")
        return

    title = " ".join(context.args) if context.args else "Anmeldung"
    keyboard = [
        [InlineKeyboardButton(opt, callback_data=f"vote|{opt}")]
        for opt in OPTIONS
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = await update.message.reply_text(
        f"<b>Anmeldung: {title}</b>\n\nNoch keine Teilnahme.",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

    # Initialisiere leere Teilnahme-Liste für diese Nachricht
    poll_participation[msg.message_id] = {}
    poll_order[msg.message_id] = []

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if not query.message:
        return

    data = query.data
    if not data.startswith("vote|"):
        return

    option = data.split("|", 1)[1]
    message_id = query.message.message_id

    # Sicherstellen, dass die Nachricht in unseren Listen ist
    if message_id not in poll_participation:
        poll_participation[message_id] = {}
        poll_order[message_id] = []

    participation = poll_participation[message_id]
    order = poll_order[message_id]

    # Wenn Benutzer vorher gewählt hatte: entfernen
    if user.id in participation:
        prev_opt, _ = participation[user.id]
        del participation[user.id]
        try:
            order.remove(user.id)
        except ValueError:
            pass

    # „Abmelden“ = nichts neu eintragen
    if option != "Abmelden":
        participation[user.id] = (option, user)
        order.append(user.id)

    # Listen nach Optionen sammeln
    user_lists = {opt: [] for opt in OPTIONS if opt != "Abmelden"}
    for uid in order:
        if uid in participation:
            opt, u = participation[uid]
            if opt in user_lists:
                tag = mention_html(u.id, f"@{u.username}" if u.username else u.first_name)
                user_lists[opt].append(tag)

    # Neue Nachricht bauen
    header = f"<b>{query.message.text_html.splitlines()[0]}</b>"
    lines = [header]

    for opt in OPTIONS:
        if opt == "Abmelden":
            continue
        users = user_lists.get(opt, [])
        if users:
            numbered_users = [f"{i+1}. {name}" for i, name in enumerate(users)]
            lines.append(f"\n<b>{opt}:</b>\n" + "\n".join(numbered_users))

    if len(lines) == 1:
        lines.append("\nNoch keine Teilnahme.")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=query.message.reply_markup
    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("anmeldung", anmeldung_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot läuft...")
    app.run_polling()

if __name__ == "__main__":
    main()
