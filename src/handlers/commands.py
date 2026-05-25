import os
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.game import (
    Game, Player, get_game, save_game, delete_game,
    setup_game, get_stats, get_leaderboard, add_game_played
)
from src.utils import mention, game_status_text, get_playable_indices, build_play_keyboard
from src.handlers.callbacks import send_turn_to_group

OWNER_ID = int(os.getenv("OWNER_ID", "0"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "pemilik")


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "❌ Perintah ini hanya bisa digunakan di grup!\n"
            "❌ This command can only be used in groups!"
        )
        return

    existing = get_game(chat_id)
    if existing and existing.status in ("waiting", "open", "playing"):
        await update.message.reply_text(
            "⚠️ Sudah ada game aktif! Gunakan /kill untuk menghentikannya.\n"
            "⚠️ There's already an active game here! Use /kill to stop it."
        )
        return

    game = Game(chat_id=chat_id, host_id=user.id, host_username=user.username or user.first_name)
    game.status = "waiting"
    game.players.append(Player(user.id, user.username or user.first_name))
    save_game(game)

    await update.message.reply_text(
        f"🃏 *Game UNO dibuat! / UNO Game created!*\n\n"
        f"👑 Host: {mention(user)}\n"
        f"👥 Pemain / Players: 1/10\n\n"
        f"Ketuk /join untuk ikut!\nTap /join to join!\n"
        f"Host ketuk /start untuk mulai / Host tap /start to begin.\n\n"
        f"📌 /open · /close · /kick · /kill",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Belum ada game! Gunakan /new\n❌ No game! Use /new")
        return
    if game.status == "playing":
        await update.message.reply_text("⚠️ Game sudah berlangsung! / Game already started!")
        return
    if game.status == "closed":
        await update.message.reply_text("🔒 Lobby ditutup! / Lobby is closed!")
        return
    if any(p.user_id == user.id for p in game.players):
        await update.message.reply_text("✅ Kamu sudah bergabung! / Already joined!")
        return
    if len(game.players) >= 10:
        await update.message.reply_text("❌ Game penuh (10/10)! / Game full!")
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

    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "🃏 *Bot UNO Telegram*\n\n"
            "Tambahkan bot ke grup dan gunakan /new untuk mulai!\n"
            "Add this bot to a group and use /new to start!\n\n"
            "/help - Lihat semua perintah",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if not game:
        await update.message.reply_text("❌ Belum ada game! /new")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host! / Only host can start!")
        return
    if game.status == "playing":
        await update.message.reply_text("⚠️ Game sudah berlangsung!")
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

    await update.message.reply_text(
        f"🎮 *GAME DIMULAI! / GAME STARTED!*\n\n"
        f"👥 Pemain:\n{player_list}\n\n"
        f"🃏 Kartu pertama / First card: *{top}*\n"
        f"🎨 Warna / Color: {game.current_color.value}",
        parse_mode=ParseMode.MARKDOWN
    )

    await send_turn_to_group(ctx, game)


async def cmd_leave(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif!")
        return
    if not any(p.user_id == user.id for p in game.players):
        await update.message.reply_text("❌ Kamu tidak sedang bermain!")
        return
    if game.host_id == user.id and game.status != "playing":
        await update.message.reply_text("⚠️ Kamu host! Gunakan /kill untuk hentikan game.")
        return

    was_current = (game.current_player and game.current_player.user_id == user.id)
    game.players = [p for p in game.players if p.user_id != user.id]

    if len(game.players) < 2 and game.status == "playing":
        winner = game.players[0] if game.players else None
        delete_game(chat_id)
        await update.message.reply_text(
            f"🏳️ @{user.username} keluar!\n"
            + (f"🏆 Pemenang / Winner: @{winner.username}" if winner else "Game berakhir!")
        )
        return

    if game.status == "playing" and was_current:
        game.current_player_index = game.current_player_index % len(game.players)

    save_game(game)
    await update.message.reply_text(f"🏳️ {mention(user)} keluar!", parse_mode=ParseMode.MARKDOWN)

    if game.status == "playing" and was_current:
        await send_turn_to_group(ctx, game)


async def cmd_close(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif!")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host!")
        return

    game.status = "closed"
    save_game(game)
    await update.message.reply_text("🔒 Lobby ditutup! / Lobby closed!")


async def cmd_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif!")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host!")
        return
    if game.status == "playing":
        await update.message.reply_text("⚠️ Game sudah berlangsung!")
        return

    game.status = "waiting"
    save_game(game)
    await update.message.reply_text("🔓 Lobby dibuka! Ketik /join untuk bergabung.")


async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game:
        await update.message.reply_text("❌ Tidak ada game aktif!")
        return

    if game.host_id != user.id and user.id != OWNER_ID:
        try:
            member = await ctx.bot.get_chat_member(chat_id, user.id)
            if member.status not in ("administrator", "creator"):
                await update.message.reply_text("❌ Hanya host atau admin grup!")
                return
        except Exception:
            await update.message.reply_text("❌ Hanya host!")
            return

    delete_game(chat_id)
    await update.message.reply_text(
        f"💀 Game dihentikan oleh {mention(user)}!\n💀 Game stopped!",
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
        await update.message.reply_text("❌ Hanya host!")
        return

    args = ctx.args
    if not args:
        await update.message.reply_text("❓ Usage: /kick @username")
        return

    target_username = args[0].lstrip("@").lower()
    target = next((p for p in game.players if p.username.lower() == target_username), None)

    if not target:
        await update.message.reply_text(f"❌ @{target_username} tidak ditemukan!")
        return
    if target.user_id == user.id:
        await update.message.reply_text("❌ Tidak bisa kick diri sendiri!")
        return

    was_current = (game.current_player and game.current_player.user_id == target.user_id)
    game.players = [p for p in game.players if p.user_id != target.user_id]

    if len(game.players) < 2 and game.status == "playing":
        winner = game.players[0] if game.players else None
        delete_game(chat_id)
        await update.message.reply_text(
            f"👢 @{target_username} dikick!\n"
            f"🏆 Game berakhir! Pemenang: @{winner.username if winner else '-'}"
        )
        return

    if game.status == "playing" and was_current:
        game.current_player_index = game.current_player_index % len(game.players)

    save_game(game)
    await update.message.reply_text(f"👢 @{target_username} dikick!")

    if game.status == "playing" and was_current:
        await send_turn_to_group(ctx, game)


async def cmd_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    game = get_game(chat_id)

    if not game or game.status != "playing":
        await update.message.reply_text("❌ Tidak ada game berlangsung!")
        return
    if game.host_id != user.id:
        await update.message.reply_text("❌ Hanya host!")
        return

    skipped = game.current_player
    game.next_turn()
    save_game(game)

    await update.message.reply_text(f"⏭ Giliran @{skipped.username} di-skip oleh host!")
    await send_turn_to_group(ctx, game)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🃏 *PERINTAH BOT UNO / UNO BOT COMMANDS*\n\n"
        "*Game:*\n"
        "/new — Buat game baru / Create game\n"
        "/join — Bergabung / Join\n"
        "/start — Mulai game (host) / Start (host)\n"
        "/leave — Keluar / Leave\n\n"
        "*Lobby:*\n"
        "/open — Buka lobby (host)\n"
        "/close — Tutup lobby (host)\n\n"
        "*Kontrol:*\n"
        "/skip — Skip giliran (host)\n"
        "/kick @user — Kick pemain (host)\n"
        "/kill — Hentikan game\n\n"
        "*Info:*\n"
        "/stats — Statistik & Leaderboard\n"
        "/pemilik — Info pemilik bot\n"
        "/help — Bantuan ini\n\n"
        "*Cara Main:*\n"
        "1️⃣ Bot kirim gambar kartu ke grup tiap giliran\n"
        "2️⃣ Pencet tombol nomor kartu yang mau dimainkan\n"
        "3️⃣ Cocokkan warna atau angka dengan kartu teratas\n"
        "4️⃣ Kartu terang = bisa dimainkan ✅ | Gelap = tidak ❌\n"
        "5️⃣ Habiskan semua kartu untuk menang! 🏆",
        parse_mode=ParseMode.MARKDOWN
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    stats = get_stats(user.id)
    lb = get_leaderboard(10)

    if stats:
        winrate = (stats["wins"] / stats["games"] * 100) if stats["games"] > 0 else 0
        personal = (
            f"📊 *Statistik kamu:*\n"
            f"🏆 Menang: {stats['wins']}\n"
            f"🎮 Main: {stats['games']}\n"
            f"📈 Winrate: {winrate:.1f}%\n\n"
        )
    else:
        personal = "📊 Kamu belum pernah main!\n\n"

    lb_text = "🏅 *Leaderboard Top 10:*\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, s in enumerate(lb):
        medal = medals[i] if i < 3 else f"{i+1}."
        lb_text += f"{medal} @{s['username']} — {s['wins']} menang\n"

    if not lb:
        lb_text += "Belum ada data"

    await update.message.reply_text(personal + lb_text, parse_mode=ParseMode.MARKDOWN)


async def cmd_pemilik(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"👑 *Pemilik Bot / Bot Owner*\n\n"
        f"@{OWNER_USERNAME}\n\n"
        f"Bot UNO Telegram — /help untuk perintah",
        parse_mode=ParseMode.MARKDOWN
    )
