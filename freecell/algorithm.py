from .models import is_red
from .state import GameState
from .rules import validate_move, max_movable_cards, apply_move, PileRef, PileType, pick_cards
from collections import deque
import time
import sys
import heapq

DEBUG_STATS = True
REPORT_INTERVAL = 1000

# ===== BFS DEBUG CONFIG =====
# BFS_DEBUG_LEVEL:
#   0 = Tắt hoàn toàn
#   1 = Chỉ in thống kê tổng (mỗi BFS_DEBUG_INTERVAL node)
#   2 = In chi tiết mỗi node được expand (state + số moves sinh)
#   3 = In CỰC chi tiết: từng move được xét, skip hay thêm vào queue
BFS_DEBUG_LEVEL = 1
BFS_DEBUG_INTERVAL = 500   # In thống kê mỗi bao nhiêu node (level 1)
BFS_NODE_LIMIT   = 50      # Chỉ in chi tiết node/move cho N node đầu (level 2,3)


class MoveCostConfig:
    """Cấu hình cho move_cost function."""
    def __init__(self, algorithm='ucs'):
        self.algorithm = algorithm  # 'ucs' hoặc 'astar'
        
        if algorithm == 'ucs':
            # ===== UCS: Cost phản ánh CHIẾN LƯỢC, KHÔNG phải số bước =====
            self.BASE_COST = 10.0      # Base lớn để có độ phân giải
            self.EPSILON = 0.001
            self.MIN_COST = 0.1
            
            # Penalty/Reward weights - TẠO KHÁC BIỆT RÕ
            self.FC_PENALTY_BASE = 8.0      # Phạt nặng khi dùng freecell
            self.FC_PENALTY_PER_EMPTY = 3.0  # Càng nhiều freecell trống càng phạt
            self.FOUNDATION_REWARD = 15.0    # Đảm bảo Foundation luôn là rẻ nhất (sẽ bị kẹp về MIN_COST = 0.1)
            self.EMPTY_COLUMN_REWARD = 1.0   # Giảm reward cột trống để không rẻ hơn Foundation
            self.FREECELL_RELEASE_REWARD = 3.0  # Thưởng giải phóng freecell
            self.NATURAL_MOVE_REWARD = 2.0   # Thưởng nước đi tự nhiên
            self.FOUNDATION_SRC_PENALTY = 15.0  # Phạt rất nặng khi lấy bài từ foundation
            
        else:  # astar
            # ===== A*: Cost ≈ SỐ BƯỚC, chỉ điều chỉnh nhẹ để định hướng =====
            self.BASE_COST = 1.0
            self.EPSILON = 0.001
            self.MIN_COST = 0.001
            
            # Penalty/Reward weights - CHỈ ĐIỀU CHỈNH NHẸ
            self.FC_PENALTY_BASE = 0.02
            self.FC_PENALTY_PER_EMPTY = 0.01
            self.FOUNDATION_REWARD = 0.05
            self.EMPTY_COLUMN_REWARD = 0.03
            self.FREECELL_RELEASE_REWARD = 0.02
            self.NATURAL_MOVE_REWARD = 0.01
            self.FOUNDATION_SRC_PENALTY = 0.1
    
    def get_epsilon(self):
        return self.EPSILON
     
    def get_min_cost(self):
        return self.MIN_COST


class FreeCellSolver: 
    def __init__(self, initial_state: GameState):
        self.initial_state = initial_state

    def _report_stats(
        self,
        phase: str,
        start_time: float,
        expanded_nodes: int,
        frontier_size: int,
        depth: int,
    ) -> None:
        if not DEBUG_STATS:
            return
        if expanded_nodes > 0 and expanded_nodes % REPORT_INTERVAL:
            return
        elapsed = time.time() - start_time
        print(
            f"[DEBUG][{phase}] expanded={expanded_nodes}, frontier={frontier_size}, depth={depth}, elapsed={elapsed:.2f}s"
        )
        
    def hash_state(self, state: GameState) -> bytes:
        # Tối ưu hóa: Biểu diễn trạng thái bằng dãy bytes siêu nhỏ gọn (chỉ ~60 bytes/state)
        # Giảm cực kì nhiều RAM (từ tuple objects sang bytes) và chống sinh node trùng lặp
        suit_idx = {"C": 0, "D": 1, "H": 2, "S": 3}
        
        # 1. Foundation: Chỉ cần lưu rank lớn nhất của 4 chất (4 bytes)
        f_bytes = []
        for s in ("C", "D", "H", "S"):
            pile = state.foundations.get(s, [])
            f_bytes.append(pile[-1].rank if pile else 0)
            
        # 2. FreeCells: 4 bytes. Sắp xếp lại để triệt tiêu bài toán hoán vị (Symmetry Breaking)
        fc_bytes = []
        for c in state.free_cells:
            if c is None:
                fc_bytes.append(0)
            else:
                fc_bytes.append(suit_idx[c.suit.value] * 13 + c.rank)
        fc_bytes.sort() # [12, 0, 4, 0] -> [0, 0, 4, 12] (Logical equivalent state)
        
        # 3. Tableau: Sắp xếp các cột để giảm số lượng hoán vị cột thừa thãi
        tab_cols = []
        for col in state.tableau:
            col_b = bytearray()
            for c in col:
                col_b.append(suit_idx[c.suit.value] * 13 + c.rank)
            tab_cols.append(bytes(col_b))
        tab_cols.sort() # Cột giống nhau đứng tính là một state duy nhất
        
        tab_bytes = bytearray()
        for b in tab_cols:
            tab_bytes.extend(b)
            tab_bytes.append(255) # Byte ngăn cách các cột
            
        return bytes(f_bytes + fc_bytes) + bytes(tab_bytes)
    
    def is_win_state(self, state: GameState) -> bool:
        return sum(len(pile) for pile in state.foundations.values()) == 52
    
    def _tableau_sequences(self, column: list) -> list[tuple[int, int]]:
        sequences: list[tuple[int, int]] = []
        if not column:
            return sequences
        seq_len = 1
        sequences.append((len(column) - 1, seq_len))
        prev_card = column[-1]
        for idx in range(len(column) - 2, -1, -1):
            candidate = column[idx]
            if (
                is_red(candidate.suit) == is_red(prev_card.suit)
                or candidate.rank != prev_card.rank + 1
            ):
                break
            seq_len += 1
            sequences.append((idx, seq_len))
            prev_card = candidate
        return sequences

    # ===== DEBUG HELPER =====
    def _fmt_card(self, card) -> str:
        """Hiển thị card dạng '5H', 'KC', 'A♠' v.v."""
        if card is None:
            return '__'
        rank_map = {1: 'A', 11: 'J', 12: 'Q', 13: 'K'}
        r = rank_map.get(card.rank, str(card.rank))
        s = card.suit.value[0].upper()  # C, D, H, S
        return f"{r}{s}"

    def _fmt_pile(self, pile_ref: PileRef) -> str:
        """Hiển thị tên pile dạng 'TAB[3]', 'FC[1]', 'FND[2]'."""
        short = {PileType.TABLEAU: 'TAB', PileType.FREECELL: 'FC', PileType.FOUNDATION: 'FND'}
        return f"{short[pile_ref.kind]}[{pile_ref.index}]"

    def _fmt_move(self, state: GameState, move: tuple) -> str:
        """Hiển thị nước đi dạng '5H,4S TAB[2]->TAB[5]'."""
        src, dst, start_idx = move
        cards = pick_cards(state, src, start_idx)
        cards_str = ','.join(self._fmt_card(c) for c in cards) if cards else '?'
        return f"{cards_str} {self._fmt_pile(src)}->{self._fmt_pile(dst)}"

    def _fmt_state_brief(self, state: GameState) -> str:
        """Tóm tắt state: foundation ranks + số ô FC trống + số cột trống."""
        fnd = []
        for s in ('C', 'D', 'H', 'S'):
            pile = state.foundations.get(s, [])
            fnd.append(f"{s}:{pile[-1].rank if pile else 0}")
        fc_empty = sum(1 for c in state.free_cells if c is None)
        tab_empty = sum(1 for col in state.tableau if not col)
        fc_cards = [self._fmt_card(c) for c in state.free_cells]
        return (f"FND=[{','.join(fnd)}] "
                f"FC=[{','.join(fc_cards)}]({fc_empty} trống) "
                f"TAB_empty={tab_empty}")
    # ===== END DEBUG HELPER =====

    # ===== OPTIMIZATION 2: AUTO-FOUNDATION (Forced Moves) =====
    def _is_safe_to_foundation(self, state: GameState, card) -> bool:
        """
        Stovely's Rule: Đưa lá bài lên Foundation là AN TOÀN nếu:
        - Là Ace (rank 1) → LUÔN an toàn
        - Là 2 → an toàn nếu Ace cùng chất đã lên Foundation
        - Là rank r (đỏ) → an toàn nếu cả 2 chất đen đã có >= r-1 trên Foundation
        - Là rank r (đen) → an toàn nếu cả 2 chất đỏ đã có >= r-1 trên Foundation
        Nghĩa là: lá bài này sẽ không bao giờ cần lấy xuống lại.
        """
        from .models import Suit
        if card.rank <= 2:
            return True
        needed_below = card.rank - 2  # Lá đối màu cần có trên Foundation
        if is_red(card.suit):
            # Cần cả 2 chất đen (Clubs, Spades) có rank >= needed_below
            black_suits = [Suit.CLUBS, Suit.SPADES]
            return all(
                len(state.foundations.get(s, [])) >= needed_below
                for s in black_suits
            )
        else:
            # Cần cả 2 chất đỏ (Diamonds, Hearts) có rank >= needed_below
            red_suits = [Suit.DIAMONDS, Suit.HEARTS]
            return all(
                len(state.foundations.get(s, [])) >= needed_below
                for s in red_suits
            )

    def _apply_forced_foundations(self, state: GameState) -> tuple[bool, list]:
        """
        Áp dụng tất cả nước Foundation bắt buộc/an toàn liên tục.
        Trả về (any_applied, moves_applied) — LIST MOVES được thêm vào path
        để game replay có thể thực hiện chính xác (không bị thiếu bước Foundation).
        """
        any_applied = False
        moves_applied = []   # <-- Mới: ghi lại từng move được áp dụng
        changed = True
        while changed:
            changed = False
            # Kiểm tra từng freecell
            for fc_idx, card in enumerate(state.free_cells):
                if card is None:
                    continue
                src = PileRef(PileType.FREECELL, fc_idx)
                for f_idx in range(4):
                    dst = PileRef(PileType.FOUNDATION, f_idx)
                    if validate_move(state, src, dst, [card]).ok and self._is_safe_to_foundation(state, card):
                        apply_move(state, src, dst, -1)
                        moves_applied.append((src, dst, -1))  # Ghi lại move
                        changed = True
                        any_applied = True
                        break
            # Kiểm tra top card của từng cột tableau
            for col_idx, col in enumerate(state.tableau):
                if not col:
                    continue
                card = col[-1]
                src = PileRef(PileType.TABLEAU, col_idx)
                for f_idx in range(4):
                    dst = PileRef(PileType.FOUNDATION, f_idx)
                    if validate_move(state, src, dst, [card]).ok and self._is_safe_to_foundation(state, card):
                        apply_move(state, src, dst, -1)
                        moves_applied.append((src, dst, -1))  # Ghi lại move
                        changed = True
                        any_applied = True
                        break
        return any_applied, moves_applied
    # ===== END AUTO-FOUNDATION =====

    def get_all_possible_move(self, state: GameState, _debug: bool = False):
        moves = []

        tableau_sources = [
            PileRef(PileType.TABLEAU, idx)
            for idx, column in enumerate(state.tableau)
            if column
        ]
        freecell_sources = [
            PileRef(PileType.FREECELL, idx)
            for idx, card in enumerate(state.free_cells)
            if card
        ]
        src_piles = tableau_sources + freecell_sources

        dst_tableau = [PileRef(PileType.TABLEAU, i) for i in range(8)]
        
        # Symmetry breaking: Chỉ thêm ONE empty freecell duy nhất làm dst
        empty_fc_idx = -1
        for idx in range(4):
            if state.free_cells[idx] is None:
                empty_fc_idx = idx
                break

        dst_freecells = []
        for idx, card in enumerate(state.free_cells):
            if card is None:
                if idx == empty_fc_idx:
                    dst_freecells.append(PileRef(PileType.FREECELL, idx))
            else:
                pass # Already handled freecells occupancy in sources

        dst_foundations = [PileRef(PileType.FOUNDATION, i) for i in range(4)]
        dst_piles = dst_tableau + dst_freecells + dst_foundations

        # ── OPTIMIZATION 3: Pre-compute thông tin để prune ──
        empty_tab_count = sum(1 for col in state.tableau if not col)

        rejected = []  # chỉ dùng khi _debug=True ở level 3
        for src in src_piles:
            if src.kind == PileType.TABLEAU:
                sequences = self._tableau_sequences(state.tableau[src.index])
            else:
                sequences = [(-1, 1)]
            if not sequences:
                continue

            for dst in dst_piles:
                if src == dst:
                    continue
                allow_multi = dst.kind == PileType.TABLEAU
                max_cards = max_movable_cards(state, dst.index) if allow_multi else 1

                for start_index, seq_len in sequences:
                    if not allow_multi and seq_len != 1:
                        continue
                    if allow_multi and seq_len > max_cards:
                        continue

                    # ── OPTIMIZATION 3a: Bỏ qua move cột-đơn vào cột-trống khi >=2 cột trống ──
                    # Di chuyển 1 lá đơn sang cột trống sẽ tạo thêm 1 cột trống khác:
                    # nếu đã có >=2 cột trống → việc này chỉ hoán đổi vị trí, vô ích.
                    if (dst.kind == PileType.TABLEAU
                            and not state.tableau[dst.index]   # dst là cột trống
                            and src.kind == PileType.TABLEAU
                            and start_index == len(state.tableau[src.index]) - 1  # chỉ 1 lá trên đầu
                            and empty_tab_count >= 2):
                        if _debug and BFS_DEBUG_LEVEL >= 3:
                            cards = pick_cards(state, src, start_index)
                            cards_str = ','.join(self._fmt_card(c) for c in cards)
                            rejected.append(f"      [PRUNE-3a] {cards_str} {self._fmt_pile(src)}->{self._fmt_pile(dst)}: cột trống dư thừa")
                        continue

                    # ── OPTIMIZATION 3b: Bỏ qua move toàn cột vào cột trống khi src chỉ có 1 lá ──
                    # Cột 1 lá duy nhất di sang cột trống = chỉ đổi index, k thay đổi gì
                    if (dst.kind == PileType.TABLEAU
                            and not state.tableau[dst.index]
                            and src.kind == PileType.TABLEAU
                            and len(state.tableau[src.index]) == 1):
                        if _debug and BFS_DEBUG_LEVEL >= 3:
                            cards = pick_cards(state, src, start_index)
                            cards_str = ','.join(self._fmt_card(c) for c in cards)
                            rejected.append(f"      [PRUNE-3b] {cards_str} {self._fmt_pile(src)}->{self._fmt_pile(dst)}: cột 1 lá vào trống")
                        continue

                    cards = pick_cards(state, src, start_index)
                    if not cards:
                        continue

                    result = validate_move(state, src, dst, cards)
                    if result.ok:
                        moves.append((src, dst, start_index))
                    elif _debug and BFS_DEBUG_LEVEL >= 3:
                        cards_str = ','.join(self._fmt_card(c) for c in cards)
                        rejected.append(f"      [REJECT] {cards_str} {self._fmt_pile(src)}->{self._fmt_pile(dst)}: {result.reason}")

        if _debug and BFS_DEBUG_LEVEL >= 3 and rejected:
            print(f"    [BFS][MOVES] Bị loại/Prune ({len(rejected)} move):")
            for r in rejected[:10]:  # Chỉ in tối đa 10 để tránh spam
                print(r)
            if len(rejected) > 10:
                print(f"      ... và {len(rejected) - 10} move bị loại khác")

        # Kỹ thuật: Move Sorting - Ép các nước đi lên Foundation xếp lên hàng ưu tiên số 1
        # Trọng số:
        #  -1: Ưu tiên tuyệt đối (Đưa bài lên Foundation)
        #   0: Ưu tiên nhì (Đảo bài trên Tableau)
        #   1: Ưu tiên bét (Vứt bài vào Freecell rỗng)
        def _score_move(m: tuple[PileRef, PileRef, int]) -> int:
            dst_pile = m[1]
            if dst_pile.kind == PileType.FOUNDATION:
                return -1
            if dst_pile.kind == PileType.TABLEAU:
                return 0
            if dst_pile.kind == PileType.FREECELL:
                return 1
            return 2

        moves.sort(key=_score_move)
        return moves
    
    def bfs_solving(self):
        """
        BFS tối ưu với 3 kỹ thuật:
        1. Parent Tracking: Không lưu path trong queue → tiết kiệm bộ nhớ O(N×depth) → O(N)
        2. Auto-Foundation: Áp dụng ngay forced moves (Stovely's rule) sau mỗi clone
        3. Dead-Move Pruning: Lọc bỏ moves vô ích trước khi thêm vào queue
        """
        start_time = time.time()
        expanded_nodes = 0

        # ── Áp dụng forced foundations cho state ban đầu và ghi lại moves ──
        initial_state_norm = self.initial_state.clone()
        _, initial_forced_moves = self._apply_forced_foundations(initial_state_norm)
        initial_hash = self.hash_state(initial_state_norm)

        # ── BFS DEBUG: Khởi động ──
        if BFS_DEBUG_LEVEL >= 1:
            print("\n" + "=" * 60)
            print("[BFS] BẮT ĐẦU TÌM KIẾM (đã tối ưu: Parent Tracking + Auto-Foundation + Pruning)")
            print(f"[BFS] State ban đầu (sau forced): {self._fmt_state_brief(initial_state_norm)}")
            print("=" * 60)

        # ── OPTIMIZATION 1: Parent Tracking ──
        # parent dict: hash → (parent_hash, moves_segment)
        # moves_segment = [explicit_move] + forced_moves (tất cả moves cần để game replay)
        # None tại initial_hash = root (không có parent)
        parent: dict[bytes, tuple | None] = {initial_hash: None}
        queue: deque[tuple[GameState, bytes, int]] = deque(
            [(initial_state_norm, initial_hash, 0)]
        )

        if BFS_DEBUG_LEVEL >= 2:
            print(f"[BFS] Hash state ban đầu: {initial_hash.hex()[:20]}...")
            print(f"[BFS] Queue khởi tạo: {len(queue)} node")

        while queue:
            # FIX: Chỉ yield GIL khi đã expand ít nhất 1 node (tránh sleep trước khi bắt đầu)
            if expanded_nodes > 0 and expanded_nodes % 2000 == 0:
                time.sleep(0.001)  # Yield GIL cho giao dien pygame

            # FIX: Lấy hash được lưu sẵn trong queue thay vì tính lại O(N)
            current_state, current_hash, depth = queue.popleft()
            expanded_nodes += 1

            # ── BFS DEBUG level 1: Thống kê theo interval ──
            if BFS_DEBUG_LEVEL >= 1 and expanded_nodes % BFS_DEBUG_INTERVAL == 0:
                elapsed = time.time() - start_time
                print(f"[BFS][STAT] node={expanded_nodes:,}  queue={len(queue):,}  "
                      f"visited={len(parent):,}  depth={depth}  "
                      f"elapsed={elapsed:.2f}s")

            # ── BFS DEBUG level 2: Chi tiết từng node ──
            if BFS_DEBUG_LEVEL >= 2 and expanded_nodes <= BFS_NODE_LIMIT:
                par_entry = parent.get(current_hash)
                last_move_str = "(gốc)"
                if par_entry is not None:
                    last_move_str = self._fmt_move(current_state, par_entry[1])
                print(f"\n[BFS][NODE #{expanded_nodes}] depth={depth}  queue_size={len(queue)}")
                print(f"  State: {self._fmt_state_brief(current_state)}")
                print(f"  Nước vừa đi: {last_move_str}")

            self._report_stats("BFS", start_time, expanded_nodes, len(queue), depth)

            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(parent) + sys.getsizeof(queue)

                # ── Reconstruct path từ parent dict (bao gồm cả forced moves) ──
                path = []
                h = current_hash
                while parent[h] is not None:
                    par_hash, moves_segment = parent[h]  # moves_segment là list moves
                    path.extend(reversed(moves_segment))  # Thêm ngược (sẽ reverse sau)
                    h = par_hash
                path.reverse()  # Từ gốc → goal
                # Thêm forced moves của initial state (nếu có) vào đầu path
                path = initial_forced_moves + path

                # ── BFS DEBUG: Kết quả thắng ──
                if BFS_DEBUG_LEVEL >= 1:
                    print("\n" + "=" * 60)
                    print(f"[BFS] ✅ TÌM THẤY LỜI GIẢI!")
                    print(f"[BFS]   Số bước: {len(path)}")
                    print(f"[BFS]   Số node đã expand: {expanded_nodes:,}")
                    print(f"[BFS]   Kích thước queue cuối: {len(queue):,}")
                    print(f"[BFS]   Số state đã thăm: {len(parent):,}")
                    print(f"[BFS]   Thời gian: {search_time:.4f}s")
                    print(f"[BFS]   Bộ nhớ (ước lượng): {memory_usage:,} bytes")
                    print("=" * 60)
                if BFS_DEBUG_LEVEL >= 2:
                    print("[BFS] Chuỗi nước đi (path):")
                    trace_state = self.initial_state.clone()
                    for i, mv in enumerate(path):
                        print(f"  Bước {i+1:3d}: {self._fmt_move(trace_state, mv)}")
                        apply_move(trace_state, mv[0], mv[1], mv[2])

                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage
                }

            # ── Sinh moves và mở rộng node ──
            use_detail = BFS_DEBUG_LEVEL >= 3 and expanded_nodes <= BFS_NODE_LIMIT
            possible_moves = self.get_all_possible_move(current_state, _debug=use_detail)

            if BFS_DEBUG_LEVEL >= 2 and expanded_nodes <= BFS_NODE_LIMIT:
                print(f"  Sinh được {len(possible_moves)} move hợp lệ")

            added_count = 0
            skipped_count = 0
            for move in possible_moves:
                new_state = current_state.clone()
                apply_move(new_state, move[0], move[1], move[2])

                # ── OPTIMIZATION 2: Áp dụng forced foundations và ghi lại moves ──
                _, forced_moves = self._apply_forced_foundations(new_state)

                state_hash = self.hash_state(new_state)
                if state_hash not in parent:
                    # Lưu moves_segment = [explicit_move] + forced_moves
                    # để path reconstruction bao gồm TẤT CẢ moves cho game replay
                    moves_segment = [move] + forced_moves
                    parent[state_hash] = (current_hash, moves_segment)
                    queue.append((new_state, state_hash, depth + 1))
                    added_count += 1

                    if BFS_DEBUG_LEVEL >= 3 and expanded_nodes <= BFS_NODE_LIMIT:
                        print(f"    [ADD ] {self._fmt_move(current_state, move)}  "
                              f"hash={state_hash.hex()[:12]}...")
                else:
                    skipped_count += 1
                    if BFS_DEBUG_LEVEL >= 3 and expanded_nodes <= BFS_NODE_LIMIT:
                        print(f"    [SKIP] {self._fmt_move(current_state, move)}  (đã thăm)")

            if BFS_DEBUG_LEVEL >= 2 and expanded_nodes <= BFS_NODE_LIMIT:
                print(f"  > Thêm vào queue: {added_count}  |  Skip (đã thăm): {skipped_count}")

        search_time = time.time() - start_time

        # ── BFS DEBUG: Không tìm được lời giải ──
        if BFS_DEBUG_LEVEL >= 1:
            print("\n" + "=" * 60)
            print(f"[BFS] ❌ KHÔNG TÌM THẤY LỜI GIẢI")
            print(f"[BFS]   Số node đã expand: {expanded_nodes:,}")
            print(f"[BFS]   Số state đã thăm: {len(parent):,}")
            print(f"[BFS]   Thời gian: {search_time:.4f}s")
            print("=" * 60)

        return {"path": None, "search_time": search_time, "expanded_nodes": expanded_nodes}
    

    def ids_solving(self, max_depth: int = 100):
        start_time = time.time()
        expanded_nodes = 0

        # global_visited: hash -> max_depth_remaining_when_reached
        global_visited = {}

        def dls(state, depth_limit, current_depth, last_move, path, path_set):
            nonlocal expanded_nodes
            expanded_nodes += 1

            if expanded_nodes % 100_000 == 0:
                self._report_stats(
                    "IDS", start_time, expanded_nodes, len(path), current_depth
                )

            if self.is_win_state(state):
                return list(path)

            if current_depth >= depth_limit:
                return None

            remaining = depth_limit - current_depth

            # Pure IDS: Lấy tất cả nước đi hợp lệ
            for move in self.get_all_possible_move(state):
                if last_move and move[0] == last_move[1] and move[1] == last_move[0]:
                    continue

                _, moved = apply_move(state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation_v2(state)

                s_hash = self.hash_state(state)
                # Pruning dựa trên không gian trạng thái đã duyệt và Cycle Detection
                if (
                    s_hash in global_visited and global_visited[s_hash] >= remaining - 1
                ) or (s_hash in path_set):
                    from .rules import undo_move
                    for i in range(len(auto_moves) - 1, -1, -1):
                        undo_move(
                            state, auto_moves[i][0], auto_moves[i][1], auto_cards[i]
                        )
                    undo_move(state, move[0], move[1], moved)
                    continue

                global_visited[s_hash] = remaining - 1
                path_set.add(s_hash)
                path.append(move)
                path.extend(auto_moves)

                result = dls(
                    state, depth_limit, current_depth + 1, move, path, path_set
                )
                if result is not None:
                    return result

                # Backtrack
                for _ in range(len(auto_moves) + 1):
                    path.pop()
                path_set.remove(s_hash)

                from .rules import undo_move
                for i in range(len(auto_moves) - 1, -1, -1):
                    undo_move(state, auto_moves[i][0], auto_moves[i][1], auto_cards[i])
                undo_move(state, move[0], move[1], moved)

            return None

        # Main IDS loop
        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation_v2(initial_state)
        init_hash = self.hash_state(initial_state)

        if self.is_win_state(initial_state):
            return {
                "path": init_auto,
                "search_time": time.time() - start_time,
                "expanded_nodes": expanded_nodes,
            }

        for d_limit in range(1, max_depth + 1):
            path_set = {init_hash}
            res = dls(initial_state, d_limit, 0, None, list(init_auto), path_set)

            if res is not None:
                memory_usage = (
                    sys.getsizeof(global_visited)
                    + len(global_visited) * (sys.getsizeof(init_hash) + 28)
                    + sys.getsizeof(path_set)
                )
                return {
                    "path": res,
                    "search_time": time.time() - start_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(res),
                    "depth_reached": d_limit,
                    "memory_usage_bytes": memory_usage,
                }

        search_time = time.time() - start_time
        return {
            "path": None,
            "search_time": search_time,
            "expanded_nodes": expanded_nodes,
            "memory_usage_bytes": sys.getsizeof(global_visited)
            + len(global_visited) * (sys.getsizeof(init_hash) + 28),
        }

    def _auto_move_to_foundation_v2(self, state: GameState):
        """Tự động đẩy bài an toàn lên foundation (không tốn depth)."""
        from .models import Suit
        _SUITS = list(Suit)
        _SUIT_TO_IDX = {s: i for i, s in enumerate(_SUITS)}

        auto_moves = []
        auto_cards = []
        changed = True
        while changed:
            changed = False
            for i, card in enumerate(state.free_cells):
                if card and self._is_safe_to_foundation_v2(card, state):
                    src, dst = (
                        PileRef(PileType.FREECELL, i),
                        PileRef(PileType.FOUNDATION, _SUIT_TO_IDX[card.suit]),
                    )
                    _, moved = apply_move(state, src, dst, -1)
                    auto_moves.append((src, dst, -1))
                    auto_cards.append(moved)
                    changed = True
                    break
            if changed:
                continue
            for i, col in enumerate(state.tableau):
                if col and self._is_safe_to_foundation_v2(col[-1], state):
                    card = col[-1]
                    src, dst = (
                        PileRef(PileType.TABLEAU, i),
                        PileRef(PileType.FOUNDATION, _SUIT_TO_IDX[card.suit]),
                    )
                    si = len(col) - 1
                    _, moved = apply_move(state, src, dst, si)
                    auto_moves.append((src, dst, si))
                    auto_cards.append(moved)
                    changed = True
                    break
        return auto_moves, auto_cards

    def _is_safe_to_foundation_v2(self, card, state) -> bool:
        from .models import Suit
        suit = card.suit
        rank = card.rank

        foundation_top = len(state.foundations.get(suit, []))
        if rank != foundation_top + 1:
            return False

        opposite_suits = {
            Suit.SPADES: [Suit.HEARTS, Suit.DIAMONDS],
            Suit.CLUBS: [Suit.HEARTS, Suit.DIAMONDS],
            Suit.HEARTS: [Suit.SPADES, Suit.CLUBS],
            Suit.DIAMONDS: [Suit.SPADES, Suit.CLUBS],
        }

        if rank <= 2:
            return True

        for opp in opposite_suits[suit]:
            if len(state.foundations.get(opp, [])) < rank - 1:
                return False
        return True
    
    
    def get_move_cost(self, current_state: GameState, move: tuple[PileRef, PileRef, int], config: MoveCostConfig = MoveCostConfig('ucs')) -> float:
        """
        Tính cost cho nước đi với cấu hình linh hoạt.
        Dùng được cho cả UCS và A*.
        """
        src, dst, start_index = move
        cost = config.BASE_COST
        
        # Thống kê tài nguyên hiện tại
        empty_freecell = sum(1 for fc in current_state.free_cells if fc is None)
        empty_tableau = sum(1 for col in current_state.tableau if not col)
        total_freecell = len(current_state.free_cells)
        
        # === 1. Nước đi lên Foundation ===
        if dst.kind == PileType.FOUNDATION:
            cost -= config.FOUNDATION_REWARD
        
        # === 2. Nước đi vào Freecell ===
        elif dst.kind == PileType.FREECELL:
            # Càng nhiều freecell trống, càng nên hạn chế dùng
            penalty = (config.FC_PENALTY_BASE + 
                      (empty_freecell * config.FC_PENALTY_PER_EMPTY))
            cost += penalty
        
        # === 3. Nước đi vào Tableau ===
        elif dst.kind == PileType.TABLEAU:
            # 3a. Di chuyển toàn bộ cột (tạo cột trống)
            if src.kind == PileType.TABLEAU and start_index == 0:
                # Càng ít cột trống, reward càng lớn
                reward = config.EMPTY_COLUMN_REWARD * (1 + empty_tableau * 0.5)
                cost -= reward
            
            # 3b. Giải phóng Freecell
            elif src.kind == PileType.FREECELL:
                # Càng ít freecell trống, càng quý
                occupied_freecell = total_freecell - empty_freecell
                reward = config.FREECELL_RELEASE_REWARD * (1 + occupied_freecell * 0.5)
                cost -= reward
            
            # 3c. Nước đi tự nhiên (xếp đúng màu, giảm dần)
            if self._is_natural_tableau_move(current_state, src, dst, start_index):
                cost -= config.NATURAL_MOVE_REWARD
        
        # === 4. Phạt nước đi từ Foundation ra ===
        if src.kind == PileType.FOUNDATION:
            cost += config.FOUNDATION_SRC_PENALTY
        
        # === 5. Đặc biệt cho UCS: phạt nhẹ nước đi vô ích ===
        if config.algorithm == 'ucs' and self._is_useless_move(current_state, src, dst, start_index):
            cost += config.EPSILON * 0.5
        
        # Đảm bảo cost > 0 và không quá lớn
        min_cost = config.get_epsilon()
        return max(cost, min_cost)
    
    def _is_natural_tableau_move(self, state: GameState, src: PileRef, dst: PileRef, start_index: int) -> bool:
        """Kiểm tra nước đi có tự nhiên (xếp đúng quy tắc) không."""
        src_pile = pick_cards(state, src, start_index)
        dst_pile = state.tableau[dst.index] if dst.kind == PileType.TABLEAU else []
        if not dst_pile or not src_pile:
            return False
        
        top_dst = dst_pile[-1]
        moved_card = src_pile[0]
        
        return (is_red(top_dst.suit) != is_red(moved_card.suit) and 
                top_dst.rank == moved_card.rank + 1)
    
    def _is_useless_move(self, state: GameState, src: PileRef, dst: PileRef, start_index: int) -> bool:
        """
        Phát hiện nước đi vô ích (chỉ làm tăng độ phức tạp).
        Dùng chủ yếu cho UCS để tránh lãng phí.
        """
        # Di chuyển qua lại giữa các freecell
        if (src.kind == PileType.FREECELL and 
            dst.kind == PileType.FREECELL):
            return True
        
        # Di chuyển bài từ tableau này sang tableau khác 
        # mà không tạo sequence có ích
        src_pile_len = len(state.tableau[src.index]) if src.kind == PileType.TABLEAU else 1
        if (src.kind == PileType.TABLEAU and 
            dst.kind == PileType.TABLEAU and 
            src_pile_len - start_index == 1 and start_index == 0):
            # Di chuyển lá bài đơn độc vô ích
            return True
        
        return False

    def ucs_solving(self):
        """Uniform Cost Search - Trọng số g(n) = tổng cost của từng nước đi (get_move_cost)"""
        from .rules import undo_move
        start_time = time.time()
        expanded_nodes = 0

        count = 0
        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation_v2(initial_state)

        queue = [(0.0, count, initial_state, init_auto)]
        best_cost = {self.hash_state(initial_state): 0.0}
        config = MoveCostConfig("ucs")

        while queue:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)

            cost, _, current_state, path = heapq.heappop(queue)
            state_hash = self.hash_state(current_state)

            if state_hash in best_cost and best_cost[state_hash] < cost - 0.001:
                continue

            expanded_nodes += 1
            self._report_stats("UCS", start_time, expanded_nodes, len(queue), len(path))

            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(best_cost) + sys.getsizeof(queue)
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "total_cost": cost,
                    "memory_usage_bytes": memory_usage,
                }

            for move in self.get_all_possible_move(current_state):
                move_cost = self.get_move_cost(current_state, move, config)
                new_cost = cost + move_cost

                _, moved = apply_move(current_state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation_v2(current_state)

                new_hash = self.hash_state(current_state)
                if new_hash not in best_cost or new_cost < best_cost[new_hash] - 0.001:
                    best_cost[new_hash] = new_cost
                    count += 1
                    new_state = current_state.clone()
                    heapq.heappush(
                        queue, (new_cost, count, new_state, path + [move] + auto_moves)
                    )

                for i in range(len(auto_moves) - 1, -1, -1):
                    undo_move(
                        current_state, auto_moves[i][0], auto_moves[i][1], auto_cards[i]
                    )
                undo_move(current_state, move[0], move[1], moved)

        return {
            "path": None,
            "search_time": time.time() - start_time,
            "expanded_nodes": expanded_nodes,
        }
            
    
    def heuristic(self, state: GameState) -> int:
        # 1. Cơ bản nhất: Số lá bài còn lại chưa được đưa lên Foundation
        cards_in_foundation = sum(len(pile) for pile in state.foundations.values())
        h_score = (52 - cards_in_foundation) * 5  # Nhân hệ số 5 để ưu tiên việc đẩy bài lên Foundation
        
        # 2. Phạt cấu trúc Tableau xấu và lá bài bị đè
        for col_idx, col in enumerate(state.tableau):
            if not col:
                continue
            
            for i in range(len(col)):
                card = col[i]
                
                # Phạt đứt gãy sequence (lá dưới không nối tiếp đúng lá trên)
                if i < len(col) - 1:
                    next_card = col[i+1]
                    if is_red(card.suit) == is_red(next_card.suit) or next_card.rank != card.rank - 1:
                        h_score += 2
                
                # Phạt nếu đè lên lá đang cần đưa lên Foundation ngay lập tức
                foundation_pile = state.foundations.get(card.suit, [])
                next_needed_rank = len(foundation_pile) + 1
                if card.rank == next_needed_rank:
                    cards_blocking = len(col) - 1 - i
                    h_score += cards_blocking * 10
                    
        # 3. Phạt Freecell bị chiếm dụng (mất đi không gian trung chuyển)
        occupied_fc = sum(1 for c in state.free_cells if c is not None)
        h_score += occupied_fc * 2
        
        return h_score
    
    def astar_solving(self):
        """A* Search - Đánh giá ưu tiên f(n) = g(n) + h(n)"""
        from .rules import undo_move
        start_time = time.time()
        expanded_nodes = 0

        count = 0
        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation_v2(initial_state)

        start_h = self.heuristic(initial_state)
        queue = [(start_h, count, 0.0, initial_state, init_auto)]
        visited = set()
        config = MoveCostConfig("astar")

        while queue:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)

            _, _, g_cost, current_state, path = heapq.heappop(queue)

            state_hash = self.hash_state(current_state)
            if state_hash in visited:
                continue
            visited.add(state_hash)

            expanded_nodes += 1
            self._report_stats("A*", start_time, expanded_nodes, len(queue), len(path))

            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(visited) + sys.getsizeof(queue)
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage,
                }

            for move in self.get_all_possible_move(current_state):
                move_cost = self.get_move_cost(current_state, move, config)
                new_g = g_cost + move_cost

                _, moved = apply_move(current_state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation_v2(current_state)

                if self.hash_state(current_state) not in visited:
                    count += 1
                    new_h = self.heuristic(current_state)
                    new_f = new_g + new_h
                    new_state = current_state.clone()
                    heapq.heappush(
                        queue,
                        (new_f, count, new_g, new_state, path + [move] + auto_moves),
                    )

                for i in range(len(auto_moves) - 1, -1, -1):
                    undo_move(
                        current_state, auto_moves[i][0], auto_moves[i][1], auto_cards[i]
                    )
                undo_move(current_state, move[0], move[1], moved)

        search_time = time.time() - start_time
        return {
            "path": None,
            "search_time": search_time,
            "expanded_nodes": expanded_nodes,
        }
                    
            
        
        
        
            
 
