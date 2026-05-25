from PIL import Image, ImageDraw, ImageFont
import io
import os

# Try to load font from multiple locations
_FONT_PATHS = [
    os.path.join(os.path.dirname(__file__), "Poppins-Bold.ttf"),
    os.path.join(os.path.dirname(__file__), "fonts", "Poppins-Bold.ttf"),
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

FONT_BOLD = None
for path in _FONT_PATHS:
    if os.path.exists(path):
        FONT_BOLD = path
        break

# Card dimensions (portrait, like real UNO card ratio)
CARD_W, CARD_H = 240, 360
HAND_COLS = 4

# Colors matching real UNO cards
COLOR_PALETTE = {
    "RED":    ("#C1272D", "#E8333A"),   # dark bg, light oval
    "GREEN":  ("#008751", "#00A85E"),
    "BLUE":   ("#0057A8", "#006FD6"),
    "YELLOW": ("#F5A800", "#FFCC00"),
    "WILD":   ("#1a1a1a", "#2c2c2c"),
}

# Color initials for corner (like @unobot)
COLOR_INITIAL = {
    "RED": "R",
    "GREEN": "G",
    "BLUE": "B",
    "YELLOW": "Y",
    "WILD": "W",
}


def _font(size):
    if FONT_BOLD:
        try:
            return ImageFont.truetype(FONT_BOLD, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _draw_centered_text(draw, text, font, cx, cy, fill="white", shadow_fill=(0, 0, 0, 100)):
    """Draw text centered at (cx, cy) with drop shadow."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw // 2 - bbox[0]
    ty = cy - th // 2 - bbox[1]
    # Shadow
    draw.text((tx + 3, ty + 3), text, font=font, fill=shadow_fill)
    # Main text
    draw.text((tx, ty), text, font=font, fill=fill)


def _draw_single_card(color_name: str, center_label: str, corner_label: str) -> Image.Image:
    """Draw a single UNO card mimicking the @unobot sticker style."""
    dark, light = COLOR_PALETTE.get(color_name, COLOR_PALETTE["WILD"])

    img = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # --- Card background with rounded corners ---
    radius = 28
    d.rounded_rectangle([0, 0, CARD_W - 1, CARD_H - 1], radius=radius, fill=dark)

    # --- White border ---
    border = 6
    d.rounded_rectangle(
        [border, border, CARD_W - border - 1, CARD_H - border - 1],
        radius=radius - 3,
        outline="white",
        width=5
    )

    cx = CARD_W // 2
    cy = CARD_H // 2

    if color_name == "WILD":
        # --- 4-color oval for WILD ---
        ox1, oy1 = 22, 50
        ox2, oy2 = CARD_W - 22, CARD_H - 50
        ocx = (ox1 + ox2) // 2
        ocy = (oy1 + oy2) // 2

        # Build 4-quadrant oval
        mask = Image.new("L", (CARD_W, CARD_H), 0)
        ImageDraw.Draw(mask).ellipse([ox1, oy1, ox2, oy2], fill=255)

        quad = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        qd = ImageDraw.Draw(quad)
        qd.ellipse([ox1, oy1, ox2, oy2], fill="#C1272D")
        qd.rectangle([ocx, oy1, ox2, ocy], fill="#0057A8")
        qd.rectangle([ocx, ocy, ox2, oy2], fill="#FFCC00")
        qd.rectangle([ox1, ocy, ocx, oy2], fill="#008751")

        out = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        out.paste(quad, mask=mask)
        img.paste(out, mask=out.split()[3])

        d = ImageDraw.Draw(img)
        d.ellipse([ox1 + 3, oy1 + 3, ox2 - 3, oy2 - 3], outline="white", width=4)

        # Center text on wild card
        if center_label not in ("WILD", "+4"):
            fnt = _font(32)
            _draw_centered_text(d, center_label, fnt, cx, cy)

    else:
        # --- White outer oval ---
        ox1, oy1 = 18, 45
        ox2, oy2 = CARD_W - 18, CARD_H - 45

        # Draw tilted oval effect: white oval, then colored inner oval slightly offset
        # White oval background
        d.ellipse([ox1, oy1, ox2, oy2], fill="white")

        # Colored inner oval (slightly tilted = offset)
        tilt = 12
        d.ellipse([ox1 + tilt, oy1 + tilt, ox2 - tilt, oy2 - tilt], fill=dark)

        # --- Center number/symbol ---
        if len(center_label) == 1:
            fnt_size = 130
        elif len(center_label) == 2:
            fnt_size = 95
        else:
            fnt_size = 65

        fnt = _font(fnt_size)
        _draw_centered_text(d, center_label, fnt, cx, cy)

    # --- Corner labels (top-left and bottom-right, rotated 180 for bottom) ---
    # Use color initial + card value like @unobot: "R4", "G+2", etc.
    initial = COLOR_INITIAL.get(color_name, "")
    top_label = f"{initial}\n{corner_label}" if color_name != "WILD" else corner_label

    fnt_corner = _font(28)
    margin_x = 12
    margin_y = 10

    # Top-left
    _draw_multiline_corner(d, top_label, fnt_corner, margin_x, margin_y, "white")

    # Bottom-right (rotated 180°) — draw on temp image then rotate
    corner_img = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(corner_img)
    _draw_multiline_corner(cd, top_label, fnt_corner, margin_x, margin_y, "white")
    corner_img = corner_img.rotate(180)
    img = Image.alpha_composite(img, corner_img)

    return img


def _draw_multiline_corner(draw, text, font, x, y, fill):
    """Draw multiline corner label (e.g. 'R' on line 1, '4' on line 2)."""
    lines = text.split("\n")
    cur_y = y
    for line in lines:
        if not line:
            continue
        draw.text((x, cur_y), line, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), line, font=font)
        line_h = bbox[3] - bbox[1]
        cur_y += line_h + 2


def _card_labels(card_dict: dict) -> tuple[str, str]:
    """Return (center_label, corner_label) for a card dict."""
    ct = card_dict["card_type"]
    num = card_dict.get("number")
    if ct == "NUMBER":
        return str(num), str(num)
    elif ct == "SKIP":
        return "⊘", "⊘"
    elif ct == "REVERSE":
        return "↺", "↺"
    elif ct == "DRAW_TWO":
        return "+2", "+2"
    elif ct == "WILD":
        return "WILD", "W"
    elif ct == "WILD_DRAW_FOUR":
        return "+4", "+4"
    return "?", "?"


def render_top_card(card_dict: dict) -> bytes:
    """Render a single card as PNG bytes (2x size for top card display)."""
    center, corner = _card_labels(card_dict)
    color = card_dict["color"]
    img = _draw_single_card(color, center, corner)
    img = img.resize((CARD_W * 2, CARD_H * 2), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_card_sticker(card_dict: dict) -> bytes:
    """Render a single card as WebP sticker bytes."""
    center, corner = _card_labels(card_dict)
    color = card_dict["color"]
    img = _draw_single_card(color, center, corner)
    # Stickers must be 512x512
    img = img.resize((512, 512), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


def render_hand(cards: list[dict], playable_indices: list[int], chat_id: int) -> bytes:
    """Render all cards in hand as a grid PNG image."""
    n = len(cards)

    if n == 0:
        img = Image.new("RGBA", (CARD_W, CARD_H), (30, 30, 30, 255))
        d = ImageDraw.Draw(img)
        fnt = _font(28)
        _draw_centered_text(d, "No cards", fnt, CARD_W // 2, CARD_H // 2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    cols = min(HAND_COLS, n)
    rows = (n + cols - 1) // cols
    pad = 12
    bg_color = (20, 20, 20, 255)

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
            overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 160))
            card_img = Image.alpha_composite(card_img, overlay)

        # Gold badge with card number
        d_overlay = ImageDraw.Draw(card_img)
        num_label = str(i + 1)
        num_fnt = _font(22)
        badge_size = 30
        bx = CARD_W - badge_size - 6
        by = 6
        # Badge background
        d_overlay.ellipse([bx, by, bx + badge_size, by + badge_size], fill="#FFD700")
        # Badge border
        d_overlay.ellipse([bx, by, bx + badge_size, by + badge_size], outline="#B8860B", width=2)
        # Badge number
        bbox = d_overlay.textbbox((0, 0), num_label, font=num_fnt)
        nw = bbox[2] - bbox[0]
        nh = bbox[3] - bbox[1]
        d_overlay.text(
            (bx + (badge_size - nw) // 2 - bbox[0], by + (badge_size - nh) // 2 - bbox[1]),
            num_label, font=num_fnt, fill="#1a1a1a"
        )

        img.paste(card_img, (x, y), card_img)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_card_with_overlay(card_dict: dict, playable: bool) -> bytes:
    """
    Render kartu dengan overlay visual untuk inline query:
    - playable=True  → border hijau tebal + centang putih pojok kanan atas
    - playable=False → gelap + silang merah di tengah
    Ukuran output sama dengan render_top_card (2x card size).
    """
    center, corner = _card_labels(card_dict)
    color = card_dict["color"]

    # Render base card lalu scale 2x supaya konsisten dengan top card
    img = _draw_single_card(color, center, corner)
    img = img.resize((CARD_W * 2, CARD_H * 2), Image.LANCZOS)
    w, h = img.size  # 480 x 720

    if not playable:
        # --- Overlay gelap semi-transparan ---
        dark_overlay = Image.new("RGBA", (w, h), (0, 0, 0, 150))
        img = Image.alpha_composite(img, dark_overlay)

        # --- Silang merah ---
        d = ImageDraw.Draw(img)
        margin = 36
        lw = max(w // 10, 10)
        d.line([(margin, margin), (w - margin, h - margin)], fill=(220, 30, 30, 255), width=lw)
        d.line([(w - margin, margin), (margin, h - margin)], fill=(220, 30, 30, 255), width=lw)

    else:
        # --- Border hijau tebal di luar kartu ---
        d = ImageDraw.Draw(img)
        bw = max(w // 14, 8)
        radius = 52  # 28 * 2 (scaled)
        d.rounded_rectangle(
            [0, 0, w - 1, h - 1],
            radius=radius,
            outline=(50, 220, 50, 255),
            width=bw,
        )

        # --- Centang putih di pojok kanan atas ---
        # Bentuk: garis L terbalik (checkmark)
        cx = w - 42
        cy = 36
        s = 22  # ukuran centang
        lw_check = 6
        # Titik: kiri bawah → tengah → kanan atas
        pts = [
            (cx - s, cy),           # kiri
            (cx - s // 3, cy + s),  # bawah tengah
            (cx + s, cy - s // 2),  # kanan atas
        ]
        d.line(pts, fill=(255, 255, 255, 255), width=lw_check)

    # Simpan sebagai JPEG (lebih kecil, cocok untuk upload cache Telegram)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue()
