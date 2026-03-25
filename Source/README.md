# FreeCell

A fully playable **FreeCell** solitaire card game written in Python using [pygame](https://www.pygame.org/).

---

## Prerequisites

* Python 3.10 or higher
* pip

---

## Installation

1. **Clone the repository** (or download the `Source/` folder):

   ```bash
   git clone https://github.com/lephuckhang186/FreeCell.git
   cd FreeCell/Source
   ```

2. **Install the required libraries**:

   ```bash
   pip install -r requirements.txt
   ```

---

## Running the game

```bash
python main.py
```

A window (1024 × 768) will open showing a freshly shuffled FreeCell board.

---

## How to play

| Area | Description |
|------|-------------|
| **Free Cells** (top-left, 4 slots) | Each slot holds at most one card temporarily. |
| **Foundations** (top-right, 4 piles) | Build each suit from Ace up to King. |
| **Tableau** (8 columns) | Main playing area. Build sequences in alternating colours and descending rank. |

### Move rules

* You may move only the **top card** of any tableau column or a free cell.
* A card can be placed on a tableau column if it is **one rank lower and the opposite colour** of the column's current top card (or the column is empty).
* A card can be placed in a **free cell** if the free cell is empty.
* A card is placed on a **foundation** automatically when it is the correct next card for its suit (Ace first, then 2, 3 … King).

### Controls

| Key / Action | Effect |
|--------------|--------|
| **Left-click** a card | Select the card (highlighted in yellow) |
| **Left-click** a destination | Move the selected card there |
| **Left-click** the selected card again | Deselect |
| **N** | Start a **new game** |
| **Z** | **Undo** the last move |
| **Escape** | Quit the game |

### Winning

Move all 52 cards onto the four foundations to win. A congratulation screen will appear; press **N** to play again.

---

## Project structure

```
Source/
├── main.py           # Game source code
├── README.md         # This file
└── requirements.txt  # Python dependencies
```

---

## Notes

* Card suit symbols (♠ ♥ ♦ ♣) are rendered using Unicode.  The game automatically selects a suitable font (`Segoe UI` on Windows, `DejaVu Sans` or `Noto Sans` on Linux/macOS).  If none of these fonts are available, pygame falls back to its built-in default font which may not display the symbols correctly.  Install a Unicode-capable font such as **DejaVu Sans** (`sudo apt install fonts-dejavu` on Debian/Ubuntu) if symbols appear as boxes.

---

## Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| pygame  | 2.5.2   | Window, rendering, and event handling |

Install all dependencies at once:

```bash
pip install -r requirements.txt
```
