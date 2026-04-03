import random
import os
import re

# =========================
# CONFIG
# =========================
LEVEL_CONFIG = {
    # Difficulty tuning for Easy/Medium/Hard tiers:
    # - MOVES: Shuffle count.
    # - NOISE: Probability of introducing non-rule-abiding card movements.
    # - MIN_SEQ: Target tableau sequence quality ratio.
    1: (140, 2, 0.65, 0.03),
    2: (340, 3, 0.55, 0.08),
    3: (700, 4, 0.45, 0.14),
    4: (850, 4, 0.42, 0.12),
    5: (1100, 5, 0.33, 0.18),
    6: (1700, 6, 0.27, 0.22),
    7: (2500, 7, 0.22, 0.26),
    8: (7500, 9, 0.18, 0.4),
    9: (12000, 12, 0.1, 0.5),
    10: (15000, 15, 0.0, 0.7),
}

LEVEL = 5  # Default
MOVES, BLOCK_DEPTH, MIN_SEQ, NOISE = LEVEL_CONFIG[LEVEL]

# =========================
# CARD UTILS
# =========================

def suit(x):
    return x // 13


def rank(x):
    return x % 13


def is_red(s):
    return s in [1, 2]


def can_put(card_to_move, target_card):
    if target_card is None:
        return True
    if is_red(suit(card_to_move)) == is_red(suit(target_card)):
        return False
    return rank(card_to_move) + 1 == rank(target_card)


def card_str(x):
    ranks = "A23456789TJQK"
    suits = "CDHS"
    return ranks[rank(x)] + suits[suit(x)]


# =========================
# INIT
# =========================
def init_tableau():
    # Begin with a solvable "perfect" state to ensure validity after shuffling.
    sequences = []
    # Low levels (1-3) favor alternating suits for clarity.
    # Higher levels introduce more variety in the initial cascade.
    if LEVEL <= 3:
        suits_cycle = [3, 2, 0, 1]  # S(b), H(r), C(b), D(r)
    else:
        suits_cycle = [3, 2, 1, 0]  # S(b), H(r), D(r), C(b)
    for i in range(4):
        seq = []
        for r in range(12, -1, -1):
            s = suits_cycle[(i + (12 - r)) % 4]
            seq.append(s * 13 + r)
        sequences.append(seq)

    tableau = [[] for _ in range(8)]
    for i in range(4):
        tableau[i * 2].extend(sequences[i][:7])
        tableau[i * 2 + 1].extend(sequences[i][7:])
    return tableau


# =========================
# SCORE CONTROLLERS
# =========================
def seq_score(tableau):
    good, total = 0, 0
    for col in tableau:
        for i in range(len(col) - 1):
            total += 1
            # Score based on how many cards follow the descending alternating rule.
            if can_put(col[i + 1], col[i]):
                good += 1
    return good / total if total > 0 else 0


def block_ok(tableau):
    for col in tableau:
        for i, card in enumerate(col):
            if rank(card) <= 2:  # A, 2, 3
                if len(col) - i - 1 > BLOCK_DEPTH:
                    return False
    return True


def balance_ok(tableau):
    """
    Keep the tableau distribution reasonable.
    Without this, some generated boards can have one empty column and another column
    significantly longer than the rest (still solvable, but feels "uneven").
    """
    lens = [len(col) for col in tableau]
    if not lens:
        return False

    min_len = min(lens)
    max_len = max(lens)

    # Allow a bit more spread for harder levels.
    if LEVEL <= 3:
        spread_limit = 4
        max_allowed = 9
    elif LEVEL <= 7:
        spread_limit = 5
        max_allowed = 10
    else:
        spread_limit = 6
        max_allowed = 10

    if min_len < 1:
        return False
    if max_len > max_allowed:
        return False
    if max_len - min_len > spread_limit:
        return False
    return True


# =========================
# GENERATE
# =========================
def generate():
    attempts = 0
    while True:
        attempts += 1
        tableau = init_tableau()

        for _ in range(MOVES):
            c1 = random.randint(0, 7)
            c2 = random.randint(0, 7)
            if c1 == c2 or not tableau[c1]:
                continue

            a = tableau[c1][-1]
            b = tableau[c2][-1] if tableau[c2] else None

            # Use noise threshold to allow occasional illegal shuffles.
            # This ensures the resulting board feels varied and mimics natural distribution.
            if random.random() < NOISE:
                tableau[c1].pop()
                tableau[c2].append(a)
            else:
                if can_put(a, b):
                    tableau[c1].pop()
                    tableau[c2].append(a)

        if seq_score(tableau) >= MIN_SEQ and block_ok(tableau) and balance_ok(tableau):
            return tableau, attempts


# =========================
# FILE HANDLER
# =========================
def get_next_filename():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if LEVEL <= 3:
        folder = "easy"
    elif LEVEL <= 7:
        folder = "medium"
    else:
        folder = "hard"

    testcase_dir = os.path.join(base_dir, folder)
    if not os.path.exists(testcase_dir):
        os.makedirs(testcase_dir)

    nums = []
    for f in os.listdir(testcase_dir):
        if f.endswith(".txt"):
            m = re.search(r"\d+", f)
            if m:
                nums.append(int(m.group()))

    next_num = max(nums) + 1 if nums else 1
    return os.path.join(testcase_dir, f"testcase{next_num}.txt")


def write_file(tableau, filename):
    with open(filename, "w", encoding="utf-8") as f:
        f.write("[FOUNDATION]\n")
        f.write("C: empty\nS: empty\nD: empty\nH: empty\n\n")

        f.write("[FREECELL]\n")
        for i in range(4):
            f.write(f"{i}: empty\n")

        f.write("\n[TABLEAU]\n")
        for col in tableau:
            f.write(" ".join(card_str(x) for x in col) + "\n")


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    while True:
        try:
            val = input("Input difficulty (1-10): ").strip()
            level_input = int(val)
            if 1 <= level_input <= 10:
                LEVEL = level_input
                MOVES, BLOCK_DEPTH, MIN_SEQ, NOISE = LEVEL_CONFIG[LEVEL]
                break
            else:
                print("Error: Please enter a number between 1 and 10.")
        except ValueError:
            print("Error: Invalid number format.")

    print(f"Generating LEVEL {LEVEL}...")
    board, attempts = generate()
    filename = get_next_filename()
    write_file(board, filename)
    print(f"✅ Generated: {filename} (after {attempts} attempts)")
    print(
        f"   MOVES: {MOVES} | NOISE: {NOISE} | TARGET SEQ: {MIN_SEQ} | BLOCK LIMIT: {BLOCK_DEPTH}"
    )
