"""
inline.py — Handle inline queries untuk sistem kartu UNO kayak @unobot.

Alur:
1. Pemain ngetik @botKamu di chat grup
2. handle_inline_query dipanggil → tampilkan kartu yang bisa dimainkan
3. Pemain tap kartu → handle_chosen_inline_result dipanggil → proses logika game
"""

import json
import os
import logging
from telegram import (
    Update,
    InlineQueryResultCachedSticker,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from src.game import get_game, save_game, delete_game, draw_card, add_win
from src.cards import Card, Color, CardType
from src.utils import (
    get_playable_indices,
    build_color_keyboard,
    mention,
)

logger = logging.getLogger(__name__)

STICKER_FILE = "data/sticker_ids.json"
_sticker_ids: dict = {}


def _load_stickers():
    """Load sticker file_ids dari JSON, sekali saja."""
    global _sticker_ids
    if not _sticker_ids and os.path.exists(STICKER_FILE):
        with open(STICKER_FILE) as f:
            _sticker_ids = json.load(f)


def _card_key(card_dict: dict) -> str:
    """
    Key harus sama persis dengan CARD_ORDER di get_stickers.py.
    NUMBER  → "RED_1", "BLUE_0", dst
    Lainnya → "RED_SKIP", "WILD_WILD", "WILD_WILD_DRAW_FOUR", dst
    """
    ct = card_dict["card_type"]
    color = card_dict["color"]
    num = card_dict.get("number", "")
    if ct == "NUMBER":
        return f"{color}_{num}"
    return f"{color}_{ct}"


async def handle_inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Called when user types @botKamu in any chat.
    Shows only playable cards in the player's hand.
    """
    _load_stickers()

    query = update.inline_query
    user = query.from_user
    user_id = user.id

    query_text = query.query.strip()
    game = None

    if query_text.isdigit():
        game = get_game(int(query_text))
    else:
        from src.game import _load_all, Game
        all_games = _load_all()
        for cid_str, gdata in all_games.items():
            if gdata.get("status") != "playing":
                continue
            g = Game.from_dict(gdata)
            cp = g.current_player
            if cp and cp.user_id == user_id:
                game = g
                break

    if not game or game.status != "playing":
        await query.answer(
            results=[_make_no_game_result()],
            cache_time=5,
            is_personal=True,
        )
        return

    current = game.current_player
    if not current or current.user_id != user_id:
        await query.answer(
            results=[_make_not_your_turn_result()],
            cache_time=5,
            is_personal=True,
        )
        return

    top = game.top_card
    playable = get_playable_indices(current.hand, top, game.current_color, game.pending_draw)

    results = []

    # Draw card option (always shown first)
    draw_label = f"💔 Ambil +{game.pending_draw} kartu (wajib)" if game.pending_draw > 0 else "🎴 Ambil kartu / Draw card"
    results.append(InlineQueryResultArticle(
        id=f"draw:{game.chat_id}",
        title=draw_label,
        description="Tap untuk ambil kartu",
        input_message_content=InputTextMessageContent(
            message_text=f"__draw__{game.chat_id}",
        ),
        thumbnail_url="https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/UNO_Logo.svg/200px-UNO_Logo.svg.png"
    ))

    # Hanya tampilkan kartu yang bisa dimainkan
    for i, card in enumerate(current.hand):
        if i not in playable:
            continue

        card_dict = card.to_dict()
        label = _card_display_name(card)
        result_id = f"card:{game.chat_id}:{i}:1"

        sticker_fid = _sticker_ids.get(_card_key(card_dict))

        if sticker_fid:
            results.append(InlineQueryResultCachedSticker(
                id=result_id,
                sticker_file_id=sticker_fid,
            ))
        else:
            results.append(InlineQueryResultArticle(
                id=result_id,
                title=f"✅ {label}",
                description="Tap untuk mainkan kartu ini",
                input_message_content=InputTextMessageContent(
                    message_text=f"__card__{game.chat_id}__{i}",
                ),
            ))

    await query.answer(
        results=results,
        cache_time=0,
        is_personal=True,
    )


async def handle_chosen_inline_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Called when user picks a card from inline results.
    Processes the game logic and sends message to group.
    """
    result = update.chosen_inline_result
    result_id = result.result_id
    user = result.from_user

    parts = result_id.split(":")
    action = parts[0]

    if action == "draw":
        chat_id = int(parts[1])
        await _process_draw(ctx, user, chat_id)

    elif action == "card":
        chat_id = int(parts[1])
        card_index = int(parts[2])
        await _process_play_card(ctx, user, chat_id, card_index)


async def _process_draw(ctx, user, chat_id: int):
    """Process draw card action."""
    game = get_game(chat_id)
    if not game or game.status != "playing":
        return

    current = game.current_player
    if not current or current.user_id != user.id:
        return

    if game.pending_draw > 0:
        for _ in range(game.pending_draw):
            c = draw_card(game)
            if c:
                current.hand.append(c)
        drawn_count = game.pending_draw
        game.pending_draw = 0
        game.next_turn()
        save_game(game)

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
            await ctx.bot.send_message(chat_id, "❌ Deck kosong!")
            return
        current.hand.append(c)

        if c.can_play_on(game.top_card, game.current_color):
            save_game(game)
            from src.utils import build_play_keyboard

            playable = get_playable_indices(current.hand, game.top_card, game.current_color, 0)
            keyboard = build_play_keyboard(current.hand, playable, chat_id, 0)
            await ctx.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🎴 *@{current.username}* ambil: *{c}*\n"
                    f"Kartu bisa dimainkan! Tap 'Make your choice!' atau ketik @{ctx.bot.username}"
                ),
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            game.next_turn()
            save_game(game)
            next_p = game.current_player
            await ctx.bot.send_message(
                chat_id,
                f"🎴 *@{current.username}* ambil kartu — tidak bisa dimainkan.\n"
                f"▶️ Giliran / Turn: *@{next_p.username}*",
                parse_mode=ParseMode.MARKDOWN
            )
            await send_turn_to_group(ctx, game)


async def _process_play_card(ctx, user, chat_id: int, card_index: int):
    """Process playing a card."""
    game = get_game(chat_id)
    if not game or game.status != "playing":
        return

    current = game.current_player
    if not current or current.user_id != user.id:
        await ctx.bot.send_message(
            chat_id,
            f"❌ @{user.username} bukan giliran kamu!"
        )
        return

    if card_index >= len(current.hand):
        return

    card = current.hand[card_index]

    # Validate stacking
    if game.pending_draw > 0:
        if card.card_type not in (CardType.DRAW_TWO, CardType.WILD_DRAW_FOUR):
            await ctx.bot.send_message(
                chat_id,
                f"⚠️ @{current.username} harus stack +{game.pending_draw} atau ambil kartu!"
            )
            return

    if not card.can_play_on(game.top_card, game.current_color):
        await ctx.bot.send_message(
            chat_id,
            f"❌ @{current.username} kartu *{card}* tidak bisa dimainkan!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Play the card
    current.hand.pop(card_index)
    game.discard_pile.append(card)
    current.uno_called = False

    # Notify group (text only)
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=f"🃏 *@{current.username}* main: *{card}*",
        parse_mode=ParseMode.MARKDOWN
    )

    # Handle wild cards — need color picker
    if card.card_type in (CardType.WILD, CardType.WILD_DRAW_FOUR):
        if card.card_type == CardType.WILD_DRAW_FOUR:
            game.pending_draw += 4
        save_game(game)
        keyboard = build_color_keyboard(chat_id)
        await ctx.bot.send_message(
            chat_id,
            f"🌈 *@{current.username}* pilih warna / choose color:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # Apply card effects
    game.current_color = card.color
    effect_msg = ""

    if card.card_type == CardType.SKIP:
        game.next_turn()
        skipped = game.current_player
        effect_msg = f"⏭ @{skipped.username} di-skip!\n"
        game.next_turn()

    elif card.card_type == CardType.REVERSE:
        game.direction *= -1
        if len(game.players) == 2:
            game.next_turn()
            effect_msg = f"🔄 Reverse! @{game.current_player.username} skip!\n"
            game.next_turn()
        else:
            effect_msg = "🔄 Arah dibalik! / Direction reversed!\n"
            game.next_turn()

    elif card.card_type == CardType.DRAW_TWO:
        game.pending_draw += 2
        game.next_turn()

    else:
        game.next_turn()

    # Check win
    if len(current.hand) == 0:
        add_win(current.user_id, current.username)
        await ctx.bot.send_message(
            chat_id,
            f"🎉🏆 *@{current.username} MENANG! / WINS!* 🏆🎉\n\n"
            f"Ketik /new untuk main lagi!",
            parse_mode=ParseMode.MARKDOWN
        )
        delete_game(chat_id)
        return

    # UNO call
    uno_msg = ""
    if len(current.hand) == 1:
        current.uno_called = True
        uno_msg = f"🔔 *UNO! @{current.username} tinggal 1 kartu!*\n"

    if effect_msg or uno_msg:
        await ctx.bot.send_message(
            chat_id,
            effect_msg + uno_msg,
            parse_mode=ParseMode.MARKDOWN
        )

    save_game(game)
    await send_turn_to_group(ctx, game)


async def send_turn_to_group(ctx, game):
    """
    Notify group whose turn it is — teks saja, tanpa gambar.
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    current = game.current_player
    top = game.top_card

    if "active_chat_ids" not in ctx.bot_data:
        ctx.bot_data["active_chat_ids"] = set()
    ctx.bot_data["active_chat_ids"].add(game.chat_id)

    # Hanya nama pemain, tanpa sisa kartu
    player_list = "\n".join([
        f"  {'▶️' if p.user_id == current.user_id else '  '} @{p.username}"
        + (" 🔔 *UNO!*" if len(p.hand) == 1 else "")
        for p in game.players
    ])

    pending_msg = f"⚠️ Wajib stack/ambil: *+{game.pending_draw}*\n" if game.pending_draw > 0 else ""

    text = (
        f"▶️ Giliran / Turn: *@{current.username}*\n"
        f"🃏 Top: *{top}* | 🎨 {game.current_color.value if game.current_color else '?'}\n"
        f"{pending_msg}"
        f"\n👥 Pemain:\n{player_list}"
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🃏 Make your choice!",
            switch_inline_query_current_chat=""
        )
    ]])

    await ctx.bot.send_message(
        chat_id=game.chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


def _card_display_name(card: Card) -> str:
    color_names = {"RED": "Merah", "GREEN": "Hijau", "BLUE": "Biru", "YELLOW": "Kuning", "WILD": "Wild"}
    color = color_names.get(card.color.name, card.color.name)
    if card.card_type == CardType.NUMBER:
        return f"{color} {card.number}"
    elif card.card_type == CardType.SKIP:
        return f"{color} Skip"
    elif card.card_type == CardType.REVERSE:
        return f"{color} Reverse"
    elif card.card_type == CardType.DRAW_TWO:
        return f"{color} +2"
    elif card.card_type == CardType.WILD:
        return "Wild (ganti warna)"
    elif card.card_type == CardType.WILD_DRAW_FOUR:
        return "Wild +4"
    return "?"


def _make_no_game_result():
    return InlineQueryResultArticle(
        id="no_game",
        title="❌ Tidak ada game aktif",
        description="Kamu belum join game UNO",
        input_message_content=InputTextMessageContent("Saya belum join game UNO."),
    )


def _make_not_your_turn_result():
    return InlineQueryResultArticle(
        id="not_turn",
        title="⏳ Bukan giliran kamu",
        description="Tunggu giliran kamu!",
        input_message_content=InputTextMessageContent("Bukan giliran saya."),
    )
