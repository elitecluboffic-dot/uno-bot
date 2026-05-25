import random
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class Color(Enum):
    RED = "🔴"
    GREEN = "🟢"
    BLUE = "🔵"
    YELLOW = "🟡"
    WILD = "⬛"


class CardType(Enum):
    NUMBER = "number"
    SKIP = "skip"
    REVERSE = "reverse"
    DRAW_TWO = "draw_two"
    WILD = "wild"
    WILD_DRAW_FOUR = "wild_draw_four"


@dataclass
class Card:
    color: Color
    card_type: CardType
    number: Optional[int] = None

    def __str__(self):
        if self.card_type == CardType.NUMBER:
            return f"{self.color.value}{self.number}"
        elif self.card_type == CardType.SKIP:
            return f"{self.color.value}⏭"
        elif self.card_type == CardType.REVERSE:
            return f"{self.color.value}🔄"
        elif self.card_type == CardType.DRAW_TWO:
            return f"{self.color.value}+2"
        elif self.card_type == CardType.WILD:
            return "⬛🌈"
        elif self.card_type == CardType.WILD_DRAW_FOUR:
            return "⬛+4"
        return "?"

    def short_name(self):
        if self.card_type == CardType.NUMBER:
            return f"{self.color.name[:1]}{self.number}"
        elif self.card_type == CardType.SKIP:
            return f"{self.color.name[:1]}SK"
        elif self.card_type == CardType.REVERSE:
            return f"{self.color.name[:1]}RV"
        elif self.card_type == CardType.DRAW_TWO:
            return f"{self.color.name[:1]}D2"
        elif self.card_type == CardType.WILD:
            return "WC"
        elif self.card_type == CardType.WILD_DRAW_FOUR:
            return "WD4"

    def can_play_on(self, top_card: "Card", current_color: Color) -> bool:
        if self.card_type in (CardType.WILD, CardType.WILD_DRAW_FOUR):
            return True
        if self.color == current_color:
            return True
        if self.card_type == top_card.card_type:
            if self.card_type == CardType.NUMBER and self.number == top_card.number:
                return True
            if self.card_type != CardType.NUMBER:
                return True
        return False

    def to_dict(self):
        return {
            "color": self.color.name,
            "card_type": self.card_type.name,
            "number": self.number
        }

    @staticmethod
    def from_dict(d):
        return Card(
            color=Color[d["color"]],
            card_type=CardType[d["card_type"]],
            number=d.get("number")
        )


def create_deck() -> list[Card]:
    deck = []
    colors = [Color.RED, Color.GREEN, Color.BLUE, Color.YELLOW]

    for color in colors:
        deck.append(Card(color, CardType.NUMBER, 0))
        for n in range(1, 10):
            deck.append(Card(color, CardType.NUMBER, n))
            deck.append(Card(color, CardType.NUMBER, n))
        for _ in range(2):
            deck.append(Card(color, CardType.SKIP))
            deck.append(Card(color, CardType.REVERSE))
            deck.append(Card(color, CardType.DRAW_TWO))

    for _ in range(4):
        deck.append(Card(Color.WILD, CardType.WILD))
        deck.append(Card(Color.WILD, CardType.WILD_DRAW_FOUR))

    random.shuffle(deck)
    return deck
