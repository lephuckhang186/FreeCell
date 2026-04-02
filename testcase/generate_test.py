import random
import os

# ==========================================
# CÀI ĐẶT ĐỘ KHÓ (DIFFICULTY)
# 1-10: 1 là dễ nhất (nhiều bài ở Foundation), 10 là khó nhất (toàn bộ bài ở Tableau, xáo mạnh)
# ==========================================
DIFFICULTY = 4


def suit(x):
    return x // 13


def rank(x):
    return x % 13


def card_str(x):
    ranks = "A23456789TJQK"
    suits = "CDHS"
    return ranks[rank(x)] + suits[suit(x)]


# Giữ nguyên logic can_put từ file gốc để đảm bảo tương thích với solver
def can_put(a, b):
    if b is None:
        return True
    if (suit(a) % 2) == (suit(b) % 2):
        return False
    return rank(a) + 1 == rank(b)


# --- KHỞI TẠO TRẠNG THÁI "THẮNG" ---
foundation_stacks = [list(range(i * 13, (i + 1) * 13)) for i in range(4)]
tableau = [[] for _ in range(8)]
freecell = [None] * 4

# --- RÚT BÀI RA KHỎI FOUNDATION (ĐẢM BẢO GIẢI ĐƯỢC 100%) ---
# Rút toàn bộ 52 quân bài để Foundation và FreeCell luôn empty
cards_to_pull = 52

pulled_cards = []
for _ in range(cards_to_pull):
    valid_f = [f for f in foundation_stacks if f]
    if not valid_f:
        break
    f_pile = random.choice(valid_f)
    pulled_cards.append(f_pile.pop())

# Trộn toàn bộ lá bài đã rút một cách ngẫu nhiên trước khi xếp vào Tableau
# Điều này giúp xóa sạch mọi pattern có sẵn (như A-2-3...)
random.shuffle(pulled_cards)
for i, card in enumerate(pulled_cards):
    tableau[i % 8].append(card)

# --- XÁO TRỘN BẰNG BƯỚC ĐI HỢP LỆ (SHUFFLE) ---
# Độ khó càng cao, thực hiện càng nhiều moves để tạo ra các thế bài phức tạp
MOVES = DIFFICULTY * 2000
for _ in range(MOVES):
    c1 = random.randint(0, 7)
    c2 = random.randint(0, 7)
    if not tableau[c1] or c1 == c2:
        continue

    a = tableau[c1][-1]
    b = tableau[c2][-1] if tableau[c2] else None

    if can_put(a, b):
        tableau[c1].pop()
        tableau[c2].append(a)

# --- CHUẨN BỊ NỘI DUNG OUTPUT ---
output = []
output.append("[FOUNDATION]")
suits_name = ["C", "D", "H", "S"]
for i, stack in enumerate(foundation_stacks):
    name = suits_name[i]
    if not stack:
        output.append(f"{name}: empty")
    else:
        output.append(f"{name}: {card_str(stack[-1])}")

output.append("\n[FREECELL]")
for i, card in enumerate(freecell):
    output.append(f"{i}: {'empty' if card is None else card_str(card)}")

output.append("\n[TABLEAU]")
for col in tableau:
    output.append(" ".join(card_str(x) for x in col))

final_content = "\n".join(output)

# --- TÍNH TOÁN FILENAME VÀ LƯU FILE ---
testcase_dir = os.path.dirname(os.path.abspath(__file__))
existing_files = os.listdir(testcase_dir) if os.path.exists(testcase_dir) else []
nums = [
    int(f[8:-4])
    for f in existing_files
    if f.startswith("testcase") and f.endswith(".txt") and f[8:-4].isdigit()
]
next_num = max(nums) + 1 if nums else 1
new_filename = os.path.join(testcase_dir, f"testcase{next_num}.txt")

with open(new_filename, "w", encoding="utf-8") as f:
    f.write(final_content)

print(f"Đã tạo file test mới: {new_filename}")
print(f"Tham số: DIFFICULTY={DIFFICULTY}, MOVES={MOVES}, CARDS_IN_PLAY={cards_to_pull}")
print("-" * 20)
print(final_content)
