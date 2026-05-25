from PIL import Image, ImageDraw, ImageFont
import io
import os

FONT_BOLD = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"

CARD_W, CARD_H = 200, 300
HAND_COLS = 4  # cards per row in hand image

COLOR_PALETTE = {
    "RED":    ("#C0392B", "#E74C3C"),
    "GREEN":  ("#1E8449", "#27AE60"),
    "BLUE":   ("#1A5276", "#2980B9"),
    "YELLOW": ("#D4AC0D", "#F1C40F"),
    "WILD":   ("#1a1a1a", "#2c2c2c"),
}

def _font(size):
    try:
        return ImageFont.truetype(FONT_BOLD, size)
    except:
        return ImageFont.load_default()


def _draw_single_card(color_name: str, center_label: str, corner_label: str) -> Image.Image:
    dark, light = COLOR_PALETTE.get(color_name, COLOR_PALETTE["WILD"])

    img = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background
    r = 22
    d.rounded_rectangle([0, 0, CARD_W, CARD_H], radius=r, fill=dark)
    # White border
    d.rounded_rectangle([5, 5, CARD_W-5, CARD_H-5], radius=r-3, outline="white", width=4)

    if color_name == "WILD":
        # 4-color oval
        ox1, oy1, ox2, oy2 = 20, 42, CARD_W-20, CARD_H-42
        cx = (ox1+ox2)//2
        cy = (oy1+oy2)//2

        mask = Image.new("L", (CARD_W, CARD_H), 0)
        ImageDraw.Draw(mask).ellipse([ox1, oy1, ox2, oy2], fill=255)

        quad = Image.new("RGBA", (CARD_W, CARD_H), (0,0,0,0))
        qd = ImageDraw.Draw(quad)
        # TL red, TR blue, BR yellow, BL green
        qd.ellipse([ox1, oy1, ox2, oy2], fill="#C0392B")
        qd.rectangle([cx, oy1, ox2, cy], fill="#2980B9")
        qd.rectangle([cx, cy, ox2, oy2], fill="#F1C40F")
        qd.rectangle([ox1, cy, cx, oy2], fill="#27AE60")

        out = Image.new("RGBA", (CARD_W, CARD_H), (0,0,0,0))
        out.paste(quad, mask=mask)
        img.paste(out, mask=out.split()[3])

        d = ImageDraw.Draw(img)
        d.ellipse([ox1+2, oy1+2, ox2-2, oy2-2], outline="white", width=3)

        # Center text
        txt = center_label
        fnt = _font(36 if len(txt) <= 4 else 28)
        bbox = d.textbbox((0,0), txt, font=fnt)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        tx = (CARD_W-tw)//2 - bbox[0]
        ty = (CARD_H-th)//2 - bbox[1]
        d.text((tx+2, ty+2), txt, font=fnt, fill=(0,0,0,100))
        d.text((tx, ty), txt, font=fnt, fill="white")

    else:
        # Outer oval (light)
        ox1, oy1, ox2, oy2 = 16, 38, CARD_W-16, CARD_H-38
        d.ellipse([ox1, oy1, ox2, oy2], fill=light)
        # Inner oval (dark) — slightly tilted effect
        pad = 14
        d.ellipse([ox1+pad, oy1+pad, ox2-pad, oy2-pad], fill=dark)

        # Center label
        fnt_size = 80 if len(center_label) == 1 else (56 if len(center_label) == 2 else 40)
        fnt = _font(fnt_size)
        bbox = d.textbbox((0,0), center_label, font=fnt)
        tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
        tx = (CARD_W-tw)//2 - bbox[0]
        ty = (CARD_H-th)//2 - bbox[1]
        d.text((tx+3, ty+3), center_label, font=fnt, fill=(0,0,0,80))
        d.text((tx, ty), center_label, font=fnt, fill="white")

    # Corner labels
    fnt_c = _font(26)
    d.text((10, 6), corner_label, font=fnt_c, fill="white")
    bbox2 = d.textbbox((0,0), corner_label, font=fnt_c)
    cw = bbox2[2]-bbox2[0]
    ch = bbox2[3]-bbox2[1]
    d.text((CARD_W-10-cw, CARD_H-8-ch), corner_label, font=fnt_c, fill="white")

    return img


def _card_labels(card_dict: dict) -> tuple[str, str]:
    ct = card_dict["card_type"]
    num = card_dict.get("number")
    if ct == "NUMBER":
        return str(num), str(num)
    elif ct == "SKIP":
        return "Skip", "⊘"
    elif ct == "REVERSE":
        return "Rev", "↺"
    elif ct == "DRAW_TWO":
        return "+2", "+2"
    elif ct == "WILD":
        return "WILD", "W"
    elif ct == "WILD_DRAW_FOUR":
        return "+4", "+4"
    return "?", "?"


def render_top_card(card_dict: dict) -> bytes:
    """Render a single card as PNG bytes."""
    center, corner = _card_labels(card_dict)
    color = card_dict["color"]
    img = _draw_single_card(color, center, corner)
    # Scale up a bit for top card
    img = img.resize((CARD_W*2, CARD_H*2), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_hand(cards: list[dict], playable_indices: list[int], chat_id: int) -> bytes:
    """Render all cards in hand as a grid image."""
    n = len(cards)
    if n == 0:
        img = Image.new("RGBA", (CARD_W, CARD_H), (30, 30, 30, 255))
        d = ImageDraw.Draw(img)
        d.text((20, CARD_H//2), "No cards", font=_font(28), fill="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    cols = min(HAND_COLS, n)
    rows = (n + cols - 1) // cols
    pad = 10
    bg_color = (25, 25, 25, 255)

    total_w = cols * CARD_W + (cols + 1) * pad
    total_h = rows * CARD_H + (rows + 1) * pad

    img = Image.new("RGBA", (total_w, total_h), bg_color)

    for i, card in enumerate(cards):
        row = i // cols
        col = i % cols
        x = pad + col * (CARD_W + pad)
        y = pad + row * (CARD_H + pad)

        center, corner = _card_labels(card)
        color = card["color"]
        card_img = _draw_single_card(color, center, corner)

        # Dim unplayable cards
        if i not in playable_indices:
            dark_overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 140))
            card_img = Image.alpha_composite(card_img, dark_overlay)

        # Add index number overlay
        d_overlay = ImageDraw.Draw(card_img)
        num_fnt = _font(20)
        num_label = str(i + 1)
        # Badge circle
        bx, by = CARD_W - 30, 6
        d_overlay.ellipse([bx, by, bx+24, by+24], fill="#FFD700")
        bbox = d_overlay.textbbox((0,0), num_label, font=num_fnt)
        nw = bbox[2]-bbox[0]
        nh = bbox[3]-bbox[1]
        d_overlay.text((bx + (24-nw)//2, by + (24-nh)//2 - bbox[1]), num_label, font=num_fnt, fill="#1a1a1a")

        img.paste(card_img, (x, y), card_img)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
