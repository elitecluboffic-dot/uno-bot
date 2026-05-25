from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import io

from src.game import get_game, save_game, delete_game, draw_card, add_win, add_game_played
from src.cards import Card, Color, CardType
from src.utils import build_color_keyboard, get_playable_indices
from src.handlers.inline import send_turn_to_group  # pakai yang baru


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    user = query.from_user

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

        if game.pending_draw > 0:
            if card.card_type not in (CardType.DRAW_TWO, CardType.WILD_DRAW_FOUR):
                await query.answer(
                    f"⚠️ Stack +{game.pending_draw} atau ambil kartu! / Stack or draw!",
                    show_alert=True
                )
                return

        if not card.can_play_on(game.top_card, game.current_color):
            await query.answer("❌ Kartu tidak bisa dimainkan! / Can't play this card!", show_alert=True)
            return

        current.hand.pop(card_index)
        game.discard_pile.append(card)
        current.uno_called = False

        if card.card_type in (CardType.WILD, CardType.WILD_DRAW_FOUR):
            if card.card_type == CardType.WILD_DRAW_FOUR:
                game.pending_draw += 4
            save_game(game)
            keyboard = build_color_keyboard(chat_id)
            await query.edit_message_text(
                f"🌈 Pilih warna / Choose color:",
                reply_markup=keyboard
            )
            return

        game.current_color = card.color
        msg = f"🃏 *@{current.username}* main: *{card}*\n"

        if card.card_type == CardType.SKIP:
            game.next_turn()
            skipped = game.current_player
            msg += f"⏭ @{skipped.username} di-skip!\n"
            game.next_turn()

        elif card.card_type == CardType.REVERSE:
            game.direction *= -1
            if len(game.players) == 2:
                game.next_turn()
                msg += f"🔄 Reverse! @{game.current_player.username} skip!\n"
                game.next_turn()
            else:
                msg += "🔄 Arah dibalik! / Direction reversed!\n"
                game.next_turn()

        elif card.card_type == CardType.DRAW_TWO:
            game.pending_draw += 2
            game.next_turn()

        else:
            game.next_turn()

        if len(current.hand) == 0:
            await query.edit_message_text("🎉 Kamu menang! / You won!")
            add_win(current.user_id, current.username)
            await ctx.bot.send_message(
                chat_id,
                f"🎉🏆 *@{current.username} MENANG! / WINS!* 🏆🎉\n\n"
                f"Ketik /new untuk main lagi! / Type /new to play again!",
                parse_mode=ParseMode.MARKDOWN
            )
            delete_game(chat_id)
            return

        if len(current.hand) == 1:
            current.uno_called = True
            msg += f"🔔 *UNO! @{current.username} tinggal 1 kartu!*\n"

        save_game(game)
        await query.edit_message_text("✅ Dimainkan!")
        await ctx.bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
        await send_turn_to_group(ctx, game)

    elif action == "draw":
        if game.pending_draw > 0:
            for _ in range(game.pending_draw):
                c = draw_card(game)
                if c:
                    current.hand.append(c)
            drawn_count = game.pending_draw
            game.pending_draw = 0
            game.next_turn()
            save_game(game)
            await query.edit_message_text(f"💔 Kamu ambil +{drawn_count} kartu!")
            next_p = game.current_player
            await ctx.bot.send_message(
                chat_id,
                f"💔 *@{current.username}* ambil *+{drawn_count}* kartu!\n"
                f"▶️ Giliran / Turn: *@{next_p.username}*",
                parse_mode=ParseMode.MARKDOWN
            )
            await send_turn_to_group(ctx, game)
        else:
            c = draw_card(game)
            if not c:
                await query.answer("❌ Deck kosong!", show_alert=True)
                return
            current.hand.append(c)

            if c.can_play_on(game.top_card, game.current_color):
                save_game(game)
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Main / Play", callback_data=f"play:{chat_id}:{len(current.hand)-1}"),
                    InlineKeyboardButton("⏩ Simpan / Keep", callback_data=f"skip_draw:{chat_id}:0"),
                ]])
                await query.edit_message_text(
                    f"🎴 Kamu ambil: *{c}*\nMau dimainkan? / Play it?",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                game.next_turn()
                save_game(game)
                await query.edit_message_text(f"🎴 Ambil: {c} — tidak bisa dimainkan.")
                next_p = game.current_player
                await ctx.bot.send_message(
                    chat_id,
                    f"🎴 *@{current.username}* ambil kartu.\n▶️ Giliran / Turn: *@{next_p.username}*",
                    parse_mode=ParseMode.MARKDOWN
                )
                await send_turn_to_group(ctx, game)

    elif action == "color":
        color_name = parts[2]
        game.current_color = Color[color_name]
        msg = f"🌈 *@{current.username}* pilih: *{game.current_color.value}*\n"

        if len(current.hand) == 0:
            await query.edit_message_text("🎉 Kamu menang!")
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
        save_game(game)
        await query.edit_message_text(f"✅ Warna: {game.current_color.value}")
        next_p = game.current_player
        msg += f"▶️ Giliran / Turn: *@{next_p.username}*"
        await ctx.bot.send_message(chat_id, msg, parse_mode=ParseMode.MARKDOWN)
        await send_turn_to_group(ctx, game)

    elif action == "skip_draw":
        game.next_turn()
        save_game(game)
        await query.edit_message_text("⏩ Giliran selesai.")
        next_p = game.current_player
        await ctx.bot.send_message(
            chat_id,
            f"⏩ *@{current.username}* simpan kartu.\n▶️ Giliran / Turn: *@{next_p.username}*",
            parse_mode=ParseMode.MARKDOWN
        )
        await send_turn_to_group(ctx, game)
