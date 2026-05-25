from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.game import get_game, save_game, delete_game, draw_card, add_win, add_game_played
from src.cards import Card, Color, CardType
from src.utils import build_hand_keyboard, build_color_keyboard


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

    # Find game by looking through all chats where user is playing
    # Data format: action:chat_id:payload
    parts = data.split(":")
    if len(parts) < 2:
        return

    action = parts[0]
    chat_id = int(parts[1])
    game = get_game(chat_id)

    if not game or game.status != "playing":
        await query.edit_message_text("❌ Game sudah berakhir! / Game is over!")
        return

    current = game.current_player
    if not current or current.user_id != user.id:
        await query.answer("❌ Bukan giliran kamu! / Not your turn!", show_alert=True)
        return

    if action == "play":
        card_index = int(parts[2])
        if card_index >= len(current.hand):
            await query.answer("❌ Kartu tidak valid!", show_alert=True)
            return

        card = current.hand[card_index]

        # Check if must respond to pending draw
        if game.pending_draw > 0:
            if card.card_type not in (CardType.DRAW_TWO, CardType.WILD_DRAW_FOUR):
                await query.answer(
                    f"⚠️ Kamu harus stack +{game.pending_draw} atau ambil kartu! / Stack or draw!",
                    show_alert=True
                )
                return

        if not card.can_play_on(game.top_card, game.current_color):
            await query.answer("❌ Kartu tidak bisa dimainkan! / Card can't be played!", show_alert=True)
            return

        # Play card
        current.hand.pop(card_index)
        game.discard_pile.append(card)
        current.uno_called = False

        # Handle card effects
        if card.card_type in (CardType.WILD, CardType.WILD_DRAW_FOUR):
            # Ask for color
            if card.card_type == CardType.WILD_DRAW_FOUR:
                game.pending_draw += 4
            save_game(game)
            keyboard = build_color_keyboard(chat_id, card_index)
            await query.edit_message_text(
                f"🌈 Kamu main {card}!\nPilih warna / Choose color:",
                reply_markup=keyboard
            )
            return

        # Apply color
        game.current_color = card.color

        msg = f"🃏 @{current.username} main / played: *{card}*\n"

        if card.card_type == CardType.SKIP:
            game.next_turn()
            skipped = game.current_player
            msg += f"⏭ @{skipped.username} di-skip!\n"

        elif card.card_type == CardType.REVERSE:
            game.direction *= -1
            if len(game.players) == 2:
                game.next_turn()
                skipped = game.current_player
                msg += f"🔄 Arah dibalik! @{skipped.username} skip!\n"
            else:
                msg += "🔄 Arah dibalik! / Direction reversed!\n"

        elif card.card_type == CardType.DRAW_TWO:
            game.pending_draw += 2

        # Check win
        if len(current.hand) == 0:
            await query.edit_message_text(f"🎉 Kamu menang! / You won! 🏆")
            add_win(current.user_id, current.username)
            await ctx.bot.send_message(
                chat_id,
                f"🎉🏆 *@{current.username} MENANG! / WINS!* 🏆🎉\n\n"
                f"Kartu habis! / Cards are empty!\n"
                f"Ketik /new untuk main lagi! / Type /new to play again!",
                parse_mode=ParseMode.MARKDOWN
            )
            delete_game(chat_id)
            return

        # Check UNO
        if len(current.hand) == 1:
            current.uno_called = True
            msg += f"🔔 *UNO! @{current.username} tinggal 1 kartu!*\n"

        game.next_turn()

        # Handle pending draw for next player
        if game.pending_draw > 0 and card.card_type not in (CardType.DRAW_TWO, CardType.WILD_DRAW_FOUR):
            next_player = game.current_player
            for _ in range(game.pending_draw):
                drawn = draw_card(game)
                if drawn:
                    next_player.hand.append(drawn)
            msg += f"💔 @{next_player.username} ambil +{game.pending_draw} kartu!\n"
            game.pending_draw = 0
            game.next_turn()

        save_game(game)
        await query.edit_message_text(f"✅ Kartu dimainkan! / Card played!")

        next_p = game.current_player
        msg += f"\n▶️ Giliran / Turn: *@{next_p.username}*"

        await ctx.bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
        await send_turn_pm(ctx, game)

    elif action == "draw":
        if game.pending_draw > 0:
            # Must draw pending
            for _ in range(game.pending_draw):
                card = draw_card(game)
                if card:
                    current.hand.append(card)
            drawn_count = game.pending_draw
            game.pending_draw = 0
            game.next_turn()
            save_game(game)

            await query.edit_message_text(f"💔 Kamu ambil +{drawn_count} kartu! / You drew +{drawn_count} cards!")
            next_p = game.current_player
            await ctx.bot.send_message(
                chat_id,
                f"💔 @{current.username} ambil +{drawn_count} kartu!\n"
                f"▶️ Giliran / Turn: *@{next_p.username}*",
                parse_mode=ParseMode.MARKDOWN
            )
            await send_turn_pm(ctx, game)
        else:
            card = draw_card(game)
            if not card:
                await query.answer("❌ Deck kosong! / Deck is empty!", show_alert=True)
                return

            current.hand.append(card)

            # Can play the drawn card?
            if card.can_play_on(game.top_card, game.current_color):
                save_game(game)
                keyboard = build_draw_play_keyboard(chat_id, len(current.hand) - 1)
                await query.edit_message_text(
                    f"🎴 Kamu ambil: *{card}*\n\nMau dimainkan? / Play it?",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            else:
                game.next_turn()
                save_game(game)
                await query.edit_message_text(f"🎴 Kamu ambil: {card}\nTidak bisa dimainkan, giliran berikutnya.")
                next_p = game.current_player
                await ctx.bot.send_message(
                    chat_id,
                    f"🎴 @{current.username} ambil kartu!\n"
                    f"▶️ Giliran / Turn: *@{next_p.username}*",
                    parse_mode=ParseMode.MARKDOWN
                )
                await send_turn_pm(ctx, game)

    elif action == "color":
        color_name = parts[2]
        chosen_color = Color[color_name]
        game.current_color = chosen_color

        msg = f"🌈 @{current.username} pilih warna / chose color: *{chosen_color.value}*\n"

        # Check win
        if len(current.hand) == 0:
            await query.edit_message_text("🎉 Kamu menang! / You won!")
            add_win(current.user_id, current.username)
            await ctx.bot.send_message(
                chat_id,
                f"🎉🏆 *@{current.username} MENANG! / WINS!* 🏆🎉",
                parse_mode=ParseMode.MARKDOWN
            )
            delete_game(chat_id)
            return

        if len(current.hand) == 1:
            current.uno_called = True
            msg += f"🔔 *UNO! @{current.username} tinggal 1 kartu!*\n"

        game.next_turn()

        # Handle Wild Draw 4 pending
        if game.pending_draw > 0:
            top_card = game.top_card
            if top_card and top_card.card_type == CardType.WILD_DRAW_FOUR:
                pass  # Will be handled when next player draws

        save_game(game)
        await query.edit_message_text(f"✅ Warna dipilih: {chosen_color.value}")

        next_p = game.current_player
        msg += f"▶️ Giliran / Turn: *@{next_p.username}*"
        await ctx.bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
        await send_turn_pm(ctx, game)

    elif action == "skip_draw":
        # Pass drawn card without playing
        game.next_turn()
        save_game(game)
        await query.edit_message_text("⏩ Kartu disimpan, giliran selesai. / Card kept, turn passed.")
        next_p = game.current_player
        await ctx.bot.send_message(
            chat_id,
            f"⏩ @{current.username} menyimpan kartu.\n▶️ Giliran / Turn: *@{next_p.username}*",
            parse_mode=ParseMode.MARKDOWN
        )
        await send_turn_pm(ctx, game)


def build_draw_play_keyboard(chat_id: int, card_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Main / Play", callback_data=f"play:{chat_id}:{card_index}"),
            InlineKeyboardButton("⏩ Simpan / Keep", callback_data=f"skip_draw:{chat_id}:0"),
        ]
    ])


async def send_turn_pm(ctx, game):
    from src.utils import build_hand_keyboard
    current = game.current_player
    top = game.top_card

    try:
        keyboard = build_hand_keyboard(current.hand, top, game.current_color, game.pending_draw, game.chat_id)
        pm_text = (
            f"🃏 *Giliran kamu! / Your turn!*\n\n"
            f"Top: {top} | Color: {game.current_color.value if game.current_color else '?'}\n"
            + (f"⚠️ Pending draw: *+{game.pending_draw}*\n" if game.pending_draw > 0 else "")
            + f"Kartu kamu ({len(current.hand)}):\n\nPilih kartu / Choose a card:"
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
            f"Kirim /start ke bot dulu! / Send /start to the bot first!"
        )
