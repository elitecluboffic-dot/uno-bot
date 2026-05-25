from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from src.cards import Card, Color, CardType
from typing import Optional
import io


def get_playable_indices(
    hand: list[Card],
    top_card: Optional[Card],
    current_color: Optional[Color],
    pending_draw: int = 0
) -> list[int]:
    playable = []
    for i, card in enumerate(hand):
        if pending_draw > 0:
            if card.card_type in (CardType.DRAW_TWO, CardType.WILD_DRAW_FOUR):
                playable.append(i)
        else:
            if top_card and card.can_play_on(top_card, current_color):
                playable.append(i)
    return playable


def build_play_keyboard(
    hand: list[Card],
    playable_indices: list[int],
    chat_id: int,
    pending_draw: int = 0
) -> InlineKeyboardMarkup:
    buttons = []
    row = []

    for i, card in enumerate(hand):
        is_playable = i in playable_indices
        emoji = "✅" if is_playable else "❌"
        label = f"{emoji} {i+1}. {card}"
        btn = InlineKeyboardButton(label, callback_data=f"play:{chat_id}:{i}")
        row.append(btn)
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Draw button
    if pending_draw > 0:
        draw_label = f"💔 Ambil +{pending_draw} kartu (wajib)"
    else:
        draw_label = "🎴 Ambil kartu / Draw card"
    buttons.append([InlineKeyboardButton(draw_label, callback_data=f"draw:{chat_id}:0")])

    return InlineKeyboardMarkup(buttons)


def build_color_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔴 Merah / Red", callback_data=f"color:{chat_id}:RED"),
            InlineKeyboardButton("🟢 Hijau / Green", callback_data=f"color:{chat_id}:GREEN"),
        ],
        [
            InlineKeyboardButton("🔵 Biru / Blue", callback_data=f"color:{chat_id}:BLUE"),
            InlineKeyboardButton("🟡 Kuning / Yellow", callback_data=f"color:{chat_id}:YELLOW"),
        ],
    ])


def mention(user) -> str:
    if user.username:
        return f"[@{user.username}](https://t.me/{user.username})"
    return user.first_name or "User"


def game_status_text(status: str) -> str:
    mapping = {
        "waiting": "⏳ Menunggu / Waiting",
        "open": "🔓 Terbuka / Open",
        "closed": "🔒 Tertutup / Closed",
        "playing": "🎮 Berlangsung / Playing",
    }
    return mapping.get(status, status)
