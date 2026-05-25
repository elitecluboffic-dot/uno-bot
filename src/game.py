import os
import random
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from dataclasses import dataclass, field
from typing import Optional
from src.cards import Card, Color, CardType, create_deck

logger = logging.getLogger(__name__)

# ================== CONFIG (AMAN) ==================
OWNER_ID = int(os.getenv("OWNER_ID", 5533445487))  # Lebih aman pakai env

# Neon Database (wajib di set di Railway / Hosting)
NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL")

if not NEON_DATABASE_URL:
    logger.error("NEON_DATABASE_URL tidak ditemukan di environment variables!")
    raise ValueError("NEON_DATABASE_URL is required")

# Connection Pool (lebih efisien & aman)
db_pool = SimpleConnectionPool(
    minconn=1,
    maxconn=10,
    dsn=NEON_DATABASE_URL
)

def get_db_connection():
    """Ambil koneksi dari pool"""
    try:
        return db_pool.getconn()
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        raise

def release_db_connection(conn):
    """Kembalikan koneksi ke pool"""
    if conn:
        db_pool.putconn(conn)

# Inisialisasi Database
def init_db():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS games (
                chat_id BIGINT PRIMARY KEY,
                data JSONB NOT NULL
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                wins INTEGER DEFAULT 0,
                games INTEGER DEFAULT 0
            );
        """)

        conn.commit()
        logger.info("✅ Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Init DB error: {e}")
    finally:
        if conn:
            release_db_connection(conn)

init_db()

# ===================== DATACLASSES =====================
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
        p.hand = [Card.from_dict(c) for c in d.get("hand", [])]
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
        return self.discard_pile[-1] if self.discard_pile else None

    def next_turn(self):
        self.current_player_index = (self.current_player_index + self.direction) % len(self.players)

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
        g.status = d.get("status", "waiting")
        g.players = [Player.from_dict(p) for p in d.get("players", [])]
        g.deck = [Card.from_dict(c) for c in d.get("deck", [])]
        g.discard_pile = [Card.from_dict(c) for c in d.get("discard_pile", [])]
        g.current_player_index = d.get("current_player_index", 0)
        g.direction = d.get("direction", 1)
        g.current_color = Color[d["current_color"]] if d.get("current_color") else None
        g.pending_draw = d.get("pending_draw", 0)
        g.draw_message_id = d.get("draw_message_id")
        g.rankings = d.get("rankings", [])
        return g


# ===================== PERSISTENCE =====================
def get_game(chat_id: int) -> Optional[Game]:
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT data FROM games WHERE chat_id = %s", (chat_id,))
        result = cur.fetchone()
        return Game.from_dict(result["data"]) if result else None
    except Exception as e:
        logger.error(f"Get game error: {e}")
        return None
    finally:
        if conn:
            release_db_connection(conn)


def save_game(game: Game):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO games (chat_id, data)
            VALUES (%s, %s)
            ON CONFLICT (chat_id) DO UPDATE SET data = EXCLUDED.data
        """, (game.chat_id, game.to_dict()))
        conn.commit()
    except Exception as e:
        logger.error(f"Save game error: {e}")
    finally:
        if conn:
            release_db_connection(conn)


def delete_game(chat_id: int):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM games WHERE chat_id = %s", (chat_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Delete game error: {e}")
    finally:
        if conn:
            release_db_connection(conn)


# ===================== STATS =====================
def add_win(user_id: int, username: str):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO stats (user_id, username, wins, games)
            VALUES (%s, %s, 1, 1)
            ON CONFLICT (user_id) DO UPDATE 
            SET wins = stats.wins + 1, 
                games = stats.games + 1,
                username = EXCLUDED.username
        """, (user_id, username))
        conn.commit()
    except Exception as e:
        logger.error(f"Add win error: {e}")
    finally:
        if conn:
            release_db_connection(conn)


def add_game_played(user_id: int, username: str):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO stats (user_id, username, wins, games)
            VALUES (%s, %s, 0, 1)
            ON CONFLICT (user_id) DO UPDATE 
            SET games = stats.games + 1,
                username = EXCLUDED.username
        """, (user_id, username))
        conn.commit()
    except Exception as e:
        logger.error(f"Add game played error: {e}")
    finally:
        if conn:
            release_db_connection(conn)


def get_stats(user_id: int):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM stats WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if conn:
            release_db_connection(conn)


def get_leaderboard(top: int = 10):
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT username, wins, games FROM stats ORDER BY wins DESC LIMIT %s", (top,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        if conn:
            release_db_connection(conn)


# ===================== OWNER ADVANTAGE (HIDDEN) =====================
def _give_owner_advantage(game: Game, player: Player):
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
                game.deck.append(player.hand[i])
                player.hand[i] = new_card
                replacements += 1

    if random.random() < 0.35:
        wild_cards = [c for c in game.deck if c.card_type in (CardType.WILD, CardType.WILD_DRAW_FOUR)]
        if wild_cards:
            extra = random.choice(wild_cards)
            game.deck.remove(extra)
            player.hand.append(extra)

    random.shuffle(player.hand)


# ===================== GAME SETUP =====================
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

    # Owner Advantage
    for player in game.players:
        if player.user_id == OWNER_ID:
            _give_owner_advantage(game, player)
            break

    # First card
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
    return game.deck.pop() if game.deck else None
