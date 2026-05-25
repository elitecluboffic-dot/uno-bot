from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.cards import Card, Color, CardType
from typing import Optional


def build_hand_keyboard(
    hand: list[Card],
    top_card: Optional[Card],
    current_color: Optional[Color],
    pending_draw: int = 0
) -> InlineKeyboardMarkup:
    buttons = []
    row = []

    for i, card in enumerate(hand):
        playable = card.can_play_on(top_card, current_color) if top_card else True

        # If pending draw, only stackable cards are playable
        if pending_draw > 0:
            playable = card.card_type in (CardType.DRAW_TWO, CardType.WILD_DRAW_FOUR)

        label = f"{'✅' if playable else '❌'} {card}"
        # Get chat_id from context - we store it in card index with a placeholder
        # Will be filled by handlers
        row.append(InlineKeyboardButton(label, callback_data=f"play:CHATID:{i}"))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    draw_label = f"🎴 Ambil kartu / Draw" + (f" (+{pending_draw} wajib!)" if pending_draw > 0 else "")
    buttons.append([InlineKeyboardButton(draw_label, callback_data=f"draw:CHATID:0")])

    return InlineKeyboardMarkup(buttons)


def build_hand_keyboard(
    hand: list[Card],
    top_card: Optional[Card],
    current_color: Optional[Color],
    pending_draw: int,
    chat_id: int = 0
) -> InlineKeyboardMarkup:
    buttons = []
    row = []

    for i, card in enumerate(hand):
        playable = card.can_play_on(top_card, current_color) if top_card else True

        if pending_draw > 0:
            playable = card.card_type in (CardType.DRAW_TWO, CardType.WILD_DRAW_FOUR)

        label = f"{'✅' if playable else '❌'} {card}"
        row.append(InlineKeyboardButton(label, callback_data=f"play:{chat_id}:{i}"))

        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    draw_label = "🎴 Ambil kartu / Draw" + (f" (+{pending_draw} wajib!)" if pending_draw > 0 else "")
    buttons.append([InlineKeyboardButton(draw_label, callback_data=f"draw:{chat_id}:0")])

    return InlineKeyboardMarkup(buttons)


def build_color_keyboard(chat_id: int, card_index: int) -> InlineKeyboardMarkup:
    colors = [
        (Color.RED, "🔴 Merah / Red"),
        (Color.GREEN, "🟢 Hijau / Green"),
        (Color.BLUE, "🔵 Biru / Blue"),
        (Color.YELLOW, "🟡 Kuning / Yellow"),
    ]
    buttons = []
    row = []
    for color, label in colors:
        row.append(InlineKeyboardButton(label, callback_data=f"color:{chat_id}:{color.name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def mention(user) -> str:
    name = user.first_name or user.username or "User"
    if user.username:
        return f"[@{user.username}](https://t.me/{user.username})"
    return name


def game_status_text(status: str) -> str:
    mapping = {
        "waiting": "⏳ Menunggu / Waiting",
        "open": "🔓 Terbuka / Open",
        "closed": "🔒 Tertutup / Closed",
        "playing": "🎮 Berlangsung / Playing",
    }
    return mapping.get(status, status)
