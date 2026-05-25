"""
get_stickers.py — Ambil semua file_id dari sticker pack classic_colorblind
Jalankan sekali: python get_stickers.py
Hasilnya disimpan ke data/sticker_ids.json
"""

import asyncio
import json
import os
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

STICKER_PACK = "classic_colorblind"

# Urutan kartu di pack classic_colorblind (54 stiker):
# Wild, Wild+4, lalu per warna: 0-9, Skip, Reverse, +2
# Urutan warna: Red, Green, Blue, Yellow
CARD_ORDER = [
    "WILD_WILD",
    "WILD_WILD_DRAW_FOUR",
    # RED
    "RED_0", "RED_1", "RED_2", "RED_3", "RED_4",
    "RED_5", "RED_6", "RED_7", "RED_8", "RED_9",
    "RED_DRAW_TWO", "RED_REVERSE", "RED_SKIP",
    # GREEN
    "GREEN_0", "GREEN_1", "GREEN_2", "GREEN_3", "GREEN_4",
    "GREEN_5", "GREEN_6", "GREEN_7", "GREEN_8", "GREEN_9",
    "GREEN_DRAW_TWO", "GREEN_REVERSE", "GREEN_SKIP",
    # BLUE
    "BLUE_0", "BLUE_1", "BLUE_2", "BLUE_3", "BLUE_4",
    "BLUE_5", "BLUE_6", "BLUE_7", "BLUE_8", "BLUE_9",
    "BLUE_DRAW_TWO", "BLUE_REVERSE", "BLUE_SKIP",
    # YELLOW
    "YELLOW_0", "YELLOW_1", "YELLOW_2", "YELLOW_3", "YELLOW_4",
    "YELLOW_5", "YELLOW_6", "YELLOW_7", "YELLOW_8", "YELLOW_9",
    "YELLOW_DRAW_TWO", "YELLOW_REVERSE", "YELLOW_SKIP",
]


async def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN tidak ditemukan!")

    bot = Bot(token=token)

    print(f"Fetching sticker pack: {STICKER_PACK}...")
    sticker_set = await bot.get_sticker_set(STICKER_PACK)
    stickers = sticker_set.stickers

    print(f"Total stickers found: {len(stickers)}")
    print(f"Expected: {len(CARD_ORDER)}")

    if len(stickers) != len(CARD_ORDER):
        print(f"\n⚠️  Jumlah stiker tidak cocok!")
        print(f"Pack punya {len(stickers)} stiker, tapi mapping punya {len(CARD_ORDER)}")
        print("\nDumping semua stiker untuk inspeksi...")
        for i, s in enumerate(stickers):
            print(f"  [{i:02d}] file_id: {s.file_id} | emoji: {s.emoji}")
        print("\nSesuaikan CARD_ORDER di script ini dengan urutan yang benar.")
        return

    result = {}
    for i, (card_key, sticker) in enumerate(zip(CARD_ORDER, stickers)):
        result[card_key] = sticker.file_id
        print(f"  [{i:02d}] {card_key} → {sticker.file_id[:30]}...")

    os.makedirs("data", exist_ok=True)
    with open("data/sticker_ids.json", "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n✅ Berhasil! Disimpan ke data/sticker_ids.json")
    print(f"Total: {len(result)} kartu")

    await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
