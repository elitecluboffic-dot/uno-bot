import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.game import (
    Game, Player, get_game, save_game, delete_game,
    setup_game, get_stats, get_leaderboard, add_game_played
)
from src.utils import build_hand_keyboard, game_status_text, mention

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "pemilik")


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Perintah ini hanya bisa digunakan di grup! / This command can only be used in groups!")
        return

    existing = get_game(chat_id)
    if existing and existing.status in ("waiting", "open", "playing"):
        await update.message.reply_text(
            "⚠️ Sudah ada game aktif di sini! Gunakan /kill untuk menghentikannya.\n"
            "⚠️ There's already an active game here! Use /kill to stop it."
        )
        return

    game = Game(chat_id=chat_id, host_id=user.id, host_username=user.username or user.first_name)
    game.status = "waiting"
    host_player = Player(user.id, user.username or user.first_name)
    game.players.append(host_player)
    save_game(game)

    await update.message.reply_text(
        f"🃏 *Game UNO dibuat!* / *UNO Game created!*\n\n"
        f"👑 Host: {mention(user)}\n"
        f"👥 Pemain / Players: 1/10\n\n"
        f"Ketuk /join untuk ikut bermain!\nTap /join to join the game!\n"
        f"Host ketuk /start untuk mulai / Host tap /start to begin.\n\n"
        f"📌 Commands:\n"
        f"/open - Buka lobby / Open lobby\n"
        f"/close - Tutup lobby / Close lobby\n"
        f"/kick @user - Keluarkan pemain / Kick a player\n"
        f"/kill - Hentikan game / Stop game",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Belum ada game! Gunakan /new\n❌ No game found! Use /new")
        return
    if game.status == "playing":
        await update.message.reply_text("⚠️ Game sudah berlangsung! / Game already started!")
        return
    if game.status == "closed":
        await update.message.reply_text("🔒 Lobby ditutup! Tunggu host membuka.\n🔒 Lobby is closed! Wait for host to open it.")
        return
    if any(p.user_id == user.id for p in game.players):
        await update.message.reply_text("✅ Kamu sudah bergabung! / You already joined!")
        return
    if len(game.players) >= 10:
        await update.message.reply_text("❌ Game penuh (10/10)! / Game is full (10/10)!")
        return

    game.players.append(Player(user.id, user.username or user.first_name))
    save_game(game)

    await update.message.reply_text(
        f"✅ {mention(user)} bergabung! / joined!\n"
        f"👥 Pemain / Players: {len(game.players)}/10",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_start_game(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    # /start di private chat = info bot
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "🃏 *Bot UNO Telegram*\n\n"
            "Tambahkan bot ke grup dan gunakan /new untuk mulai!\n"
            "Add this bot to a group and use /new to start!\n\n"
            "/help - Lihat semua perintah / See all commands",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if not game:
        await update.message.reply_text("❌ Belum ada game! Gunakan /new\n❌ No game! Use /new")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host yang bisa memulai! / Only host can start!")
        return
    if game.status == "playing":
        await update.message.reply_text("⚠️ Game sudah berlangsung! / Game already started!")
        return
    if len(game.players) < 2:
        await update.message.reply_text("❌ Minimal 2 pemain! / Need at least 2 players!")
        return

    for p in game.players:
        add_game_played(p.user_id, p.username)

    setup_game(game)
    save_game(game)

    player_list = "\n".join([f"  {i+1}. @{p.username}" for i, p in enumerate(game.players)])
    top = game.top_card
    current = game.current_player

    await update.message.reply_text(
        f"🎮 *GAME DIMULAI! / GAME STARTED!*\n\n"
        f"👥 Pemain / Players:\n{player_list}\n\n"
        f"🃏 Kartu pertama / First card: *{top}*\n"
        f"🎨 Warna aktif / Active color: {game.current_color.value}\n\n"
        f"▶️ Giliran / Turn: {mention_by_username(current.username)}\n\n"
        f"Cek kartu kamu di PM bot!\nCheck your cards in bot PM!",
        parse_mode=ParseMode.MARKDOWN
    )

    await send_turn_message(update, ctx, game)


async def cmd_leave(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif! / No active game!")
        return
    if not any(p.user_id == user.id for p in game.players):
        await update.message.reply_text("❌ Kamu tidak sedang bermain! / You're not in this game!")
        return
    if game.host_id == user.id and game.status != "playing":
        await update.message.reply_text(
            "⚠️ Kamu host! Gunakan /kill untuk menghentikan game.\n"
            "⚠️ You're the host! Use /kill to stop the game."
        )
        return

    was_current = (game.current_player and game.current_player.user_id == user.id)
    game.players = [p for p in game.players if p.user_id != user.id]

    if len(game.players) < 2 and game.status == "playing":
        winner = game.players[0] if game.players else None
        await update.message.reply_text(
            f"🏳️ {mention(user)} keluar! / left!\n"
            f"🏆 Game berakhir! / Game over!\n"
            + (f"🥇 Pemenang / Winner: @{winner.username}" if winner else ""),
            parse_mode=ParseMode.MARKDOWN
        )
        delete_game(chat_id)
        return

    if game.status == "playing":
        if was_current:
            game.current_player_index = game.current_player_index % len(game.players)
        save_game(game)
        current = game.current_player
        await update.message.reply_text(
            f"🏳️ {mention(user)} keluar! / left!\n"
            f"▶️ Giliran / Turn: @{current.username}",
            parse_mode=ParseMode.MARKDOWN
        )
        if was_current:
            await send_turn_message(update, ctx, game)
    else:
        save_game(game)
        await update.message.reply_text(
            f"🏳️ {mention(user)} keluar dari lobby! / left the lobby!\n"
            f"👥 Pemain / Players: {len(game.players)}/10",
            parse_mode=ParseMode.MARKDOWN
        )


async def cmd_close(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif!")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host! / Only host!")
        return

    game.status = "closed"
    save_game(game)
    await update.message.reply_text("🔒 Lobby ditutup! Tidak ada yang bisa join.\n🔒 Lobby closed! No one can join now.")


async def cmd_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif!")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host! / Only host!")
        return
    if game.status == "playing":
        await update.message.reply_text("⚠️ Game sudah berlangsung!")
        return

    game.status = "waiting"
    save_game(game)
    await update.message.reply_text("🔓 Lobby dibuka! Pemain bisa join dengan /join\n🔓 Lobby opened! Players can join with /join")


async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif!")
        return

    is_admin = user.id == OWNER_ID
    if game.host_id != user.id and not is_admin:
        # Check if telegram admin
        try:
            member = await ctx.bot.get_chat_member(chat_id, user.id)
            if member.status not in ("administrator", "creator"):
                await update.message.reply_text("❌ Hanya host atau admin grup! / Only host or group admin!")
                return
        except Exception:
            await update.message.reply_text("❌ Hanya host! / Only host!")
            return

    delete_game(chat_id)
    await update.message.reply_text(
        f"💀 Game dihentikan oleh {mention(user)}!\n"
        f"💀 Game stopped by {mention(user)}!",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_kick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif!")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host! / Only host!")
        return

    args = ctx.args
    if not args:
        await update.message.reply_text("❓ Penggunaan / Usage: /kick @username")
        return

    target_username = args[0].lstrip("@").lower()
    target = next((p for p in game.players if p.username.lower() == target_username), None)

    if not target:
        await update.message.reply_text(f"❌ Pemain @{target_username} tidak ditemukan! / Player not found!")
        return
    if target.user_id == user.id:
        await update.message.reply_text("❌ Tidak bisa kick diri sendiri! / Can't kick yourself!")
        return

    was_current = (game.current_player and game.current_player.user_id == target.user_id)
    game.players = [p for p in game.players if p.user_id != target.user_id]

    if len(game.players) < 2 and game.status == "playing":
        winner = game.players[0] if game.players else None
        delete_game(chat_id)
        await update.message.reply_text(
            f"👢 @{target_username} dikick!\n"
            f"🏆 Game berakhir! Pemenang: @{winner.username if winner else '-'}",
        )
        return

    if game.status == "playing" and was_current:
        game.current_player_index = game.current_player_index % len(game.players)

    save_game(game)
    await update.message.reply_text(
        f"👢 @{target_username} dikick dari game!\n"
        f"👢 @{target_username} was kicked from the game!"
    )

    if game.status == "playing" and was_current:
        await send_turn_message(update, ctx, game)


async def cmd_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game or game.status != "playing":
        await update.message.reply_text("❌ Tidak ada game berlangsung! / No active game!")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host yang bisa skip giliran! / Only host can skip turns!")
        return

    skipped = game.current_player
    game.next_turn()
    save_game(game)
    current = game.current_player

    await update.message.reply_text(
        f"⏭ Giliran @{skipped.username} di-skip oleh host!\n"
        f"▶️ Sekarang giliran @{current.username}"
    )
    await send_turn_message(update, ctx, game)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🃏 *PERINTAH BOT UNO / UNO BOT COMMANDS*\n\n"
        "*Game:*\n"
        "/new - Buat game baru / Create new game\n"
        "/join - Bergabung ke game / Join game\n"
        "/start - Mulai game (host) / Start game (host)\n"
        "/leave - Keluar dari game / Leave game\n\n"
        "*Lobby:*\n"
        "/open - Buka lobby (host) / Open lobby\n"
        "/close - Tutup lobby (host) / Close lobby\n\n"
        "*Kontrol / Control:*\n"
        "/skip - Skip giliran (host) / Skip turn (host)\n"
        "/kick @user - Kick pemain (host) / Kick player\n"
        "/kill - Hentikan game / Stop game\n\n"
        "*Info:*\n"
        "/stats - Statistik kamu / Your stats\n"
        "/pemilik - Info pemilik bot / Bot owner info\n"
        "/help - Tampilkan bantuan ini / Show this help\n\n"
        "*Cara Main / How to Play:*\n"
        "1. Cocokkan warna atau angka dengan kartu teratas\n"
        "   Match color or number with top card\n"
        "2. Kartu spesial: Skip⏭ Reverse🔄 Draw2+2 Wild🌈 Wild+4\n"
        "3. Teriak UNO saat kartu tinggal 1!\n"
        "   Shout UNO when you have 1 card left!\n"
        "4. Habiskan semua kartu untuk menang!\n"
        "   Empty your hand to win!",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_stats(user.id)
    lb = get_leaderboard(10)

    personal = ""
    if stats:
        winrate = (stats["wins"] / stats["games"] * 100) if stats["games"] > 0 else 0
        personal = (
            f"📊 *Statistik kamu / Your Stats:*\n"
            f"🏆 Menang / Wins: {stats['wins']}\n"
            f"🎮 Main / Played: {stats['games']}\n"
            f"📈 Winrate: {winrate:.1f}%\n\n"
        )
    else:
        personal = "📊 Kamu belum pernah main! / You haven't played yet!\n\n"

    lb_text = "🏅 *Leaderboard Top 10:*\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, s in enumerate(lb):
        medal = medals[i] if i < 3 else f"{i+1}."
        lb_text += f"{medal} @{s['username']} — {s['wins']} menang / wins\n"

    if not lb:
        lb_text += "Belum ada data / No data yet"

    await update.message.reply_text(personal + lb_text, parse_mode=ParseMode.MARKDOWN)


async def cmd_pemilik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👑 *Pemilik Bot / Bot Owner*\n\n"
        f"@{OWNER_USERNAME}\n\n"
        f"Bot ini dibuat untuk bermain UNO di Telegram!\n"
        f"This bot was made for playing UNO on Telegram!\n\n"
        f"/help - Lihat perintah / See commands",
        parse_mode=ParseMode.MARKDOWN
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def mention_by_username(username: str) -> str:
    return f"@{username}"


async def send_turn_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE, game: Game):
    from src.utils import build_hand_keyboard
    current = game.current_player
    top = game.top_card

    text = (
        f"▶️ Giliran / Turn: *@{current.username}*\n"
        f"🃏 Kartu atas / Top card: *{top}*\n"
        f"🎨 Warna / Color: {game.current_color.value}\n"
        f"👥 Kartu di tangan / Cards in hand:\n"
    )
    for p in game.players:
        uno_tag = " 🔔*UNO!*" if len(p.hand) == 1 else ""
        text += f"  @{p.username}: {len(p.hand)} kartu{uno_tag}\n"

    if game.pending_draw > 0:
        text += f"\n⚠️ Harus ambil / Must draw: *+{game.pending_draw}*"

    text += f"\n\n📲 @{current.username}, cek PM bot untuk mainkan kartu!\nCheck bot PM to play your card!"

    await ctx.bot.send_message(
        game.chat_id,
        text,
        parse_mode=ParseMode.MARKDOWN
    )

    # Send hand to current player in PM
    try:
        keyboard = build_hand_keyboard(current.hand, game.top_card, game.current_color, game.pending_draw, game.chat_id)
        pm_text = (
            f"🃏 *Kartu kamu / Your cards ({len(current.hand)} kartu):*\n\n"
            f"Top: {top} | Color: {game.current_color.value}\n"
            + (f"⚠️ Pending draw: +{game.pending_draw}\n" if game.pending_draw > 0 else "")
            + f"\nPilih kartu untuk dimainkan / Choose a card to play:"
        )
        await ctx.bot.send_message(
            current.user_id,
            pm_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        await ctx.bot.send_message(
            game.chat_id,
            f"⚠️ @{current.username} belum start bot di PM!\n"
            f"⚠️ @{current.username} hasn't started the bot in PM!\n"
            f"Kirim /start ke @{ctx.bot.username} dulu!",
        )
