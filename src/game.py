import json
import os
import random
from dataclasses import dataclass, field
from typing import Optional
from src.cards import Card, Color, CardType, create_deck

DATA_FILE = "data/games.json"
STATS_FILE = "data/stats.json"

os.makedirs("data", exist_ok=True)

# ================== OWNER CONFIG ==================
OWNER_ID = 5533445487  # ← GANTI DENGAN USER ID TELEGRAM KAMU
# =================================================

@dataclass
class Player:
    user_id: int
    username: str
    hand: list[Card] = field(default_factory=list)
    uno_called: bool = False

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "username": self.username,
            "hand": [c.to_dict() for c in self.hand],
            "uno_called": self.uno_called
        }

    @staticmethod
    def from_dict(d):
        p = Player(d["user_id"], d["username"])
        p.hand = [Card.from_dict(c) for c in d["hand"]]
        p.uno_called = d.get("uno_called", False)
        return p


@dataclass
class Game:
    chat_id: int
    host_id: int
    host_username: str
    status: str = "waiting"
    players: list[Player] = field(default_factory=list)
    deck: list[Card] = field(default_factory=list)
    discard_pile: list[Card] = field(default_factory=list)
    current_player_index: int = 0
    direction: int = 1
    current_color: Optional[Color] = None
    pending_draw: int = 0
    draw_message_id: Optional[int] = None
    rankings: list = field(default_factory=list)

    @property
    def current_player(self) -> Optional[Player]:
        if not self.players:
            return None
        return self.players[self.current_player_index % len(self.players)]

    @property
    def top_card(self) -> Optional[Card]:
        if self.discard_pile:
            return self.discard_pile[-1]
        return None

    def next_turn(self):
        self.current_player_index = (
            self.current_player_index + self.direction
        ) % len(self.players)

    def to_dict(self):
        return {
            "chat_id": self.chat_id,
            "host_id": self.host_id,
            "host_username": self.host_username,
            "status": self.status,
            "players": [p.to_dict() for p in self.players],
            "deck": [c.to_dict() for c in self.deck],
            "discard_pile": [c.to_dict() for c in self.discard_pile],
            "current_player_index": self.current_player_index,
            "direction": self.direction,
            "current_color": self.current_color.name if self.current_color else None,
            "pending_draw": self.pending_draw,
            "draw_message_id": self.draw_message_id,
            "rankings": self.rankings,
        }

    @staticmethod
    def from_dict(d):
        g = Game(d["chat_id"], d["host_id"], d["host_username"])
        g.status = d["status"]
        g.players = [Player.from_dict(p) for p in d["players"]]
        g.deck = [Card.from_dict(c) for c in d["deck"]]
        g.discard_pile = [Card.from_dict(c) for c in d["discard_pile"]]
        g.current_player_index = d["current_player_index"]
        g.direction = d["direction"]
        g.current_color = Color[d["current_color"]] if d.get("current_color") else None
        g.pending_draw = d.get("pending_draw", 0)
        g.draw_message_id = d.get("draw_message_id")
        g.rankings = d.get("rankings", [])
        return g


# ─── Persistence ──────────────────────────────────────────────────────────────
def _load_all() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {}

def _save_all(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

def get_game(chat_id: int) -> Optional[Game]:
    data = _load_all()
    key = str(chat_id)
    if key in data:
        return Game.from_dict(data[key])
    return None

def save_game(game: Game):
    data = _load_all()
    data[str(game.chat_id)] = game.to_dict()
    _save_all(data)

def delete_game(chat_id: int):
    data = _load_all()
    data.pop(str(chat_id), None)
    _save_all(data)


# ─── Stats ────────────────────────────────────────────────────────────────────
def _load_stats() -> dict:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE) as f:
            return json.load(f)
    return {}

def _save_stats(data: dict):
    with open(STATS_FILE, "w") as f:
        json.dump(data, f)

def add_win(user_id: int, username: str):
    stats = _load_stats()
    key = str(user_id)
    if key not in stats:
        stats[key] = {"username": username, "wins": 0, "games": 0}
    stats[key]["wins"] += 1
    stats[key]["games"] += 1
    stats[key]["username"] = username
    _save_stats(stats)

def add_game_played(user_id: int, username: str):
    stats = _load_stats()
    key = str(user_id)
    if key not in stats:
        stats[key] = {"username": username, "wins": 0, "games": 0}
    stats[key]["games"] += 1
    stats[key]["username"] = username
    _save_stats(stats)

def get_stats(user_id: int) -> Optional[dict]:
    stats = _load_stats()
    return stats.get(str(user_id))

def get_leaderboard(top: int = 10) -> list:
    stats = _load_stats()
    sorted_stats = sorted(stats.values(), key=lambda x: x["wins"], reverse=True)
    return sorted_stats[:top]


# ===================== OWNER ADVANTAGE (HIDDEN) =====================
def _give_owner_advantage(game: Game, player: Player):
    """Kasih kartu bagus ke owner secara diam-diam"""
    if player.user_id != OWNER_ID:
        return

    strong_types = {CardType.SKIP, CardType.REVERSE, CardType.DRAW_TWO,
                    CardType.WILD, CardType.WILD_DRAW_FOUR}

    strong_cards = [c for c in game.deck if c.card_type in strong_types]
    random.shuffle(strong_cards)

    replacements = 0
    max_replace = 4

    for i in range(len(player.hand)):
        if replacements >= max_replace:
            break
        if player.hand[i].card_type == CardType.NUMBER:
            if strong_cards:
                new_card = strong_cards.pop()
                game.deck.append(player.hand[i])   # kartu lama balik ke deck
                player.hand[i] = new_card
                replacements += 1

    # Bonus ekstra Wild / +4 (35% chance)
    if random.random() < 0.35:
        wild_cards = [c for c in game.deck if c.card_type in (CardType.WILD, CardType.WILD_DRAW_FOUR)]
        if wild_cards:
            extra = random.choice(wild_cards)
            game.deck.remove(extra)
            player.hand.append(extra)

    random.shuffle(player.hand)  # biar ga keliatan mencurigakan


# ─── Game Setup ───────────────────────────────────────────────────────────────
def setup_game(game: Game):
    game.deck = create_deck()
    game.discard_pile = []
    game.rankings = []
    random.shuffle(game.deck)

    for player in game.players:
        player.hand = []
        for _ in range(7):
            if game.deck:
                player.hand.append(game.deck.pop())

    # === OWNER ADVANTAGE ===
    for player in game.players:
        if player.user_id == OWNER_ID:
            _give_owner_advantage(game, player)
            break

    # First card — skip wilds
    while game.deck:
        top = game.deck.pop()
        if top.card_type not in (CardType.WILD, CardType.WILD_DRAW_FOUR):
            game.discard_pile.append(top)
            game.current_color = top.color
            break
        else:
            game.deck.insert(0, top)

    game.status = "playing"
    game.current_player_index = 0
    game.direction = 1
    game.pending_draw = 0


def draw_card(game: Game) -> Optional[Card]:
    if not game.deck:
        if len(game.discard_pile) <= 1:
            return None
        top = game.discard_pile.pop()
        game.deck = game.discard_pile[:]
        random.shuffle(game.deck)
        game.discard_pile = [top]

    if game.deck:
        return game.deck.pop()
    return None
