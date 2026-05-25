"""
inline.py — Handle inline queries untuk sistem kartu UNO kayak @unobot.

Alur:
1. Pemain ngetik @botKamu di chat grup
2. handle_inline_query dipanggil → tampilkan kartu yang bisa dimainkan
3. Pemain tap kartu → handle_chosen_inline_result dipanggil → proses logika game
"""

import io
import logging
from telegram import (
    Update,
    InlineQueryResultCachedPhoto,
    InlineQueryResultPhoto,
    InputMediaPhoto,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from src.game import get_game, save_game, delete_game, draw_card, add_win
from src.cards import Card, Color, CardType
from src.utils import (
    get_playable_indices,
    build_color_keyboard,
    mention,
)
from src.card_renderer import render_card_sticker, render_top_card

logger = logging.getLogger(__name__)

# Cache: {card_key: file_id} — supaya tidak re-upload tiap kali
_card_file_id_cache: dict[str, str] = {}


def _card_key(card_dict: dict) -> str:
    """Unique key for a card, used for caching file_id."""
    ct = card_dict["card_type"]
    color = card_dict["color"]
    num = card_dict.get("number", "")
    return f"{color}_{ct}_{num}"


async def _get_or_upload_card(bot, card_dict: dict) -> str:
    """
    Return cached file_id for a card, or upload it and cache the result.
    Returns file_id string.
    """
    key = _card_key(card_dict)
    if key in _card_file_id_cache:
        return _card_file_id_cache[key]

    # Render card as PNG
    img_bytes = render_top_card(card_dict)

    # Upload to Telegram via a dummy send to get file_id
    # We send to the bot's own file storage using send_photo with chat_id workaround
    # Actually we'll return raw bytes and let InlineQueryResultPhoto handle it via upload
    # Store after first real use
    _card_file_id_cache[key] = None  # placeholder
    return None


async def handle_inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Called when user types @botKamu in any chat.
    Shows the player's hand as inline results.
    """
    query = update.inline_query
    user = query.from_user
    user_id = user.id

    # Find which game this user is in
    # We need to find the game where this user is the current player
    # Pass chat_id via query text: user types "@bot <chat_id>" or we detect from context
    # Best approach: user types @bot (empty query) → we find their active game

    # Parse optional chat_id from query string (for multi-group support)
    query_text = query.query.strip()

    game = None
    chat_id_hint = None

    if query_text.isdigit():
        chat_id_hint = int(query_text)
        game = get_game(chat_id_hint)
    else:
        # Baca semua game aktif langsung dari file — tidak bergantung bot_data
        from src.game import _load_all
        all_games = _load_all()
        for cid_str, gdata in all_games.items():
            if gdata.get("status") != "playing":
                continue
            from src.game import Game
            g = Game.from_dict(gdata)
            cp = g.current_player
            if cp and cp.user_id == user_id:
                game = g
                break

    # Not in any game or not current player
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

    # Each card in hand
    for i, card in enumerate(current.hand):
        card_dict = card.to_dict()
        is_playable = i in playable

        # Render card image
        img_bytes = render_top_card(card_dict)

        label = _card_display_name(card)
        desc = "✅ Bisa dimainkan" if is_playable else "❌ Tidak bisa dimainkan"

        # Encode card index + chat_id into result id
        result_id = f"card:{game.chat_id}:{i}:{'1' if is_playable else '0'}"

        # Use InlineQueryResultPhoto with raw bytes via InputFile
        # We upload via bot.send_photo to get file_id, then cache
        cached_fid = _card_file_id_cache.get(_card_key(card_dict))

        if cached_fid:
            results.append(InlineQueryResultCachedPhoto(
                id=result_id,
                photo_file_id=cached_fid,
                title=label,
                description=desc,
                caption=f"{'✅' if is_playable else '❌'} {label}",
            ))
        else:
            # Fallback: article with card info (will upgrade to photo after first upload)
            results.append(InlineQueryResultArticle(
                id=result_id,
                title=f"{'✅' if is_playable else '❌'} {label}",
                description=desc,
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
    Processes the game logic and sends card image to group.
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
        # Must draw stacked cards
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
            # Can play the drawn card — ask via color keyboard or just notify
            save_game(game)
            from src.utils import build_play_keyboard
            from src.card_renderer import render_hand
            import io as _io

            playable = get_playable_indices(current.hand, game.top_card, game.current_color, 0)
            hand_dicts = [card.to_dict() for card in current.hand]
            img_bytes = render_hand(hand_dicts, playable, chat_id)

            keyboard = build_play_keyboard(current.hand, playable, chat_id, 0)
            await ctx.bot.send_photo(
                chat_id=chat_id,
                photo=_io.BytesIO(img_bytes),
                caption=(
                    f"🎴 *@{current.username}* ambil: *{c}*\n"
                    f"Kartu bisa dimainkan! Pilih kartu atau ketik @{ctx.bot.username}"
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

    # Send card image to group
    card_dict = card.to_dict()
    img_bytes = render_top_card(card_dict)
    sent = await ctx.bot.send_photo(
        chat_id=chat_id,
        photo=io.BytesIO(img_bytes),
        caption=f"🃏 *@{current.username}* main: *{card}*",
        parse_mode=ParseMode.MARKDOWN
    )

    # Cache file_id for future use
    fid = sent.photo[-1].file_id
    _card_file_id_cache[_card_key(card_dict)] = fid

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
    Notify group whose turn it is.
    - Kirim top card + tombol 'Make your choice!' ke GRUP
    - Kirim hand image ke DM pemain (private, biar lawan tidak lihat)
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from src.card_renderer import render_hand
    from src.utils import get_playable_indices

    current = game.current_player
    top = game.top_card

    # Register this chat as active
    if "active_chat_ids" not in ctx.bot_data:
        ctx.bot_data["active_chat_ids"] = set()
    ctx.bot_data["active_chat_ids"].add(game.chat_id)

    card_counts = "\n".join([
        f"  {'▶️' if p.user_id == current.user_id else '  '} @{p.username}: {len(p.hand)} kartu"
        + (" 🔔 *UNO!*" if len(p.hand) == 1 else "")
        for p in game.players
    ])

    pending_msg = f"⚠️ Wajib stack/ambil: *+{game.pending_draw}*\n" if game.pending_draw > 0 else ""

    caption = (
        f"▶️ Giliran / Turn: *@{current.username}*\n"
        f"🃏 Top: *{top}* | 🎨 {game.current_color.value if game.current_color else '?'}\n"
        f"{pending_msg}"
        f"\n👥 Kartu pemain:\n{card_counts}"
    )

    # Tombol "Make your choice!" di grup — tap langsung buka inline query
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🃏 Make your choice!",
            switch_inline_query_current_chat=""
        )
    ]])

    # Kirim top card + tombol ke GRUP
    top_img = render_top_card(top.to_dict())
    await ctx.bot.send_photo(
        chat_id=game.chat_id,
        photo=io.BytesIO(top_img),
        caption=caption,
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )

    # Kirim hand image ke DM pemain (biar lawan tidak bisa lihat)
    playable = get_playable_indices(current.hand, top, game.current_color, game.pending_draw)
    hand_dicts = [c.to_dict() for c in current.hand]
    hand_img = render_hand(hand_dicts, playable, game.chat_id)

    try:
        await ctx.bot.send_photo(
            chat_id=current.user_id,
            photo=io.BytesIO(hand_img),
            caption=(
                f"🃏 Kartu kamu — giliran sekarang!\n"
                f"Top: *{top}* | 🎨 {game.current_color.value if game.current_color else '?'}\n"
                f"{pending_msg}"
                f"_(terang = bisa dimainkan, tap 'Make your choice!' di grup)_"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        # DM gagal — pemain belum pernah /start bot di DM
        # Kirim notif ke grup
        await ctx.bot.send_message(
            game.chat_id,
            f"⚠️ *@{current.username}*, start dulu bot ini di DM agar kartu dikirim private!\n"
            f"Tap: @{(await ctx.bot.get_me()).username}",
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
