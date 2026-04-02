from .models import is_red, Suit
from .state import GameState
from .rules import (
    validate_move,
    max_movable_cards,
    apply_move,
    undo_move,
    PileRef,
    PileType,
    pick_cards,
)
from collections import deque
import time
import sys
import heapq

DEBUG_STATS = True
REPORT_INTERVAL = 1000


class MoveCostConfig:
    """Cấu hình cho move_cost function."""

    def __init__(self, algorithm="ucs"):
        self.algorithm = algorithm  # 'ucs' hoặc 'astar'

        if algorithm == "ucs":
            # ===== UCS: Cost phản ánh CHIẾN LƯỢC, KHÔNG phải số bước =====
            self.BASE_COST = 10.0  # Base lớn để có độ phân giải
            self.EPSILON = 0.001
            self.MIN_COST = 0.1

            # Penalty/Reward weights - TẠO KHÁC BIỆT RÕ
            self.FC_PENALTY_BASE = 8.0  # Phạt nặng khi dùng freecell
            self.FC_PENALTY_PER_EMPTY = 3.0  # Càng nhiều freecell trống càng phạt
            self.FOUNDATION_REWARD = (
                15.0  # Đảm bảo Foundation luôn là rẻ nhất (sẽ bị kẹp về MIN_COST = 0.1)
            )
            self.EMPTY_COLUMN_REWARD = (
                1.0  # Giảm reward cột trống để không rẻ hơn Foundation
            )
            self.FREECELL_RELEASE_REWARD = 3.0  # Thưởng giải phóng freecell
            self.NATURAL_MOVE_REWARD = 2.0  # Thưởng nước đi tự nhiên
            self.FOUNDATION_SRC_PENALTY = (
                15.0  # Phạt rất nặng khi lấy bài từ foundation
            )

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

    def hash_state(self, state: GameState) -> tuple:
        # Tối ưu hóa: Băm bằng Tuple (Sử dụng hệ thống C-backend của Python cho tốc độ cực cao)
        # 1. Foundation
        f_tup = (
            len(state.foundations.get("C", [])),
            len(state.foundations.get("D", [])),
            len(state.foundations.get("H", [])),
            len(state.foundations.get("S", [])),
        )

        # 2. FreeCells
        fc_tup = tuple(
            sorted((c.suit.value, c.rank) for c in state.free_cells if c is not None)
        )

        # 3. Tableau
        tab_tup = tuple(
            sorted(tuple((c.suit.value, c.rank) for c in col) for col in state.tableau)
        )

        return (f_tup, fc_tup, tab_tup)

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

    def get_all_possible_move(self, state: GameState):
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
                pass  # Already handled freecells occupancy in sources

        dst_foundations = [PileRef(PileType.FOUNDATION, i) for i in range(4)]
        dst_piles = dst_tableau + dst_freecells + dst_foundations

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

                # CẮT TỈA NODE RÁC: Không bao giờ di chuyển giữa các Freecell trống
                if src.kind == PileType.FREECELL and dst.kind == PileType.FREECELL:
                    continue

                allow_multi = dst.kind == PileType.TABLEAU
                max_cards = max_movable_cards(state, dst.index) if allow_multi else 1

                for start_index, seq_len in sequences:
                    # CẮT TỈA NODE RÁC: Không di chuyển toàn bộ một cột sang một cột trống khác
                    if src.kind == PileType.TABLEAU and dst.kind == PileType.TABLEAU:
                        if not state.tableau[dst.index] and start_index == 0:
                            continue

                    if not allow_multi and seq_len != 1:
                        continue
                    if allow_multi and seq_len > max_cards:
                        continue

                    cards = pick_cards(state, src, start_index)
                    if not cards:
                        continue

                    result = validate_move(state, src, dst, cards)
                    if result.ok:
                        moves.append((src, dst, start_index))

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

    def _auto_move_to_foundation(self, state: GameState):
        """Tự động đẩy bài an toàn lên foundation (không tốn depth)."""
        _SUITS = list(Suit)
        _SUIT_TO_IDX = {s: i for i, s in enumerate(_SUITS)}

        auto_moves = []
        auto_cards = []
        changed = True
        while changed:
            changed = False
            for i, card in enumerate(state.free_cells):
                if card and self._is_safe_to_foundation(card, state):
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
                if col and self._is_safe_to_foundation(col[-1], state):
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

    def bfs_solving(self):
        start_time = time.time()
        expanded_nodes = 0

        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation(initial_state)

        queue = deque([(initial_state, init_auto)])
        visited = set()
        visited.add(self.hash_state(self.initial_state))

        while queue:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)  # Yield GIL cho giao dien pygame

            current_state, path = queue.popleft()
            expanded_nodes += 1
            self._report_stats("BFS", start_time, expanded_nodes, len(queue), len(path))

            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(visited) + sys.getsizeof(
                    queue
                )  # Ước lượng bytes
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage,
                }

            for move in self.get_all_possible_move(current_state):
                _, moved = apply_move(current_state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation(current_state)

                state_hash = self.hash_state(current_state)
                if state_hash not in visited:
                    visited.add(state_hash)
                    new_state = current_state.clone()
                    queue.append((new_state, path + [move] + auto_moves))

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
                # Đã loại bỏ time.sleep() để CPU bung 100% công suất

            if self.is_win_state(state):
                return list(path)

            if current_depth >= depth_limit:
                return None

            remaining = depth_limit - current_depth

            # Pure IDS: Lấy tất cả nước đi hợp lệ (không dùng Heuristic)
            for move in self.get_all_possible_move(state):
                if last_move and move[0] == last_move[1] and move[1] == last_move[0]:
                    continue

                _, moved = apply_move(state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation(state)

                s_hash = self.hash_state(state)
                # Pruning dựa trên không gian trạng thái đã duyệt và Cycle Detection
                if (
                    s_hash in global_visited and global_visited[s_hash] >= remaining - 1
                ) or (s_hash in path_set):
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

                for i in range(len(auto_moves) - 1, -1, -1):
                    undo_move(state, auto_moves[i][0], auto_moves[i][1], auto_cards[i])
                undo_move(state, move[0], move[1], moved)

            return None

        # Main IDS loop: Duyệt từng tầng một cách thuần túy
        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation(initial_state)
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
                # Tính toán bộ nhớ: Global visited là nguồn tốn RAM chính
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

    def _is_safe_to_foundation(self, card, state) -> bool:
        """
        Lá bài an toàn để tự động lên foundation khi:
        tất cả lá rank thấp hơn của màu đối đã lên foundation.
        Tránh đưa lá lên quá sớm khiến bị kẹt.
        """
        suit = card.suit
        rank = card.rank  # Ace=1, 2..King=13

        # Phải đúng thứ tự trên foundation
        foundation_top = len(state.foundations.get(suit, []))
        if rank != foundation_top + 1:
            return False

        # Màu đối của suit
        opposite_suits = {
            Suit.SPADES: [Suit.HEARTS, Suit.DIAMONDS],
            Suit.CLUBS: [Suit.HEARTS, Suit.DIAMONDS],
            Suit.HEARTS: [Suit.SPADES, Suit.CLUBS],
            Suit.DIAMONDS: [Suit.SPADES, Suit.CLUBS],
        }

        # An toàn nếu rank ≤ 2 (Ace/2 luôn safe)
        if rank <= 2:
            return True

        # An toàn nếu cả 2 màu đối đã có rank-1 trên foundation
        for opp in opposite_suits[suit]:
            if len(state.foundations.get(opp, [])) < rank - 1:
                return False
        return True

    def get_move_cost(
        self,
        current_state: GameState,
        move: tuple[PileRef, PileRef, int],
        config: MoveCostConfig = MoveCostConfig("ucs"),
    ) -> float:
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
            penalty = config.FC_PENALTY_BASE + (
                empty_freecell * config.FC_PENALTY_PER_EMPTY
            )
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
        if config.algorithm == "ucs" and self._is_useless_move(
            current_state, src, dst, start_index
        ):
            cost += config.EPSILON * 0.5

        # Đảm bảo cost > 0 và không quá lớn
        min_cost = config.get_epsilon()
        return max(cost, min_cost)

    def _is_natural_tableau_move(
        self, state: GameState, src: PileRef, dst: PileRef, start_index: int
    ) -> bool:
        """Kiểm tra nước đi có tự nhiên (xếp đúng quy tắc) không."""
        src_pile = pick_cards(state, src, start_index)
        dst_pile = state.tableau[dst.index] if dst.kind == PileType.TABLEAU else []
        if not dst_pile or not src_pile:
            return False

        top_dst = dst_pile[-1]
        moved_card = src_pile[0]

        return (
            is_red(top_dst.suit) != is_red(moved_card.suit)
            and top_dst.rank == moved_card.rank + 1
        )

    def _is_useless_move(
        self, state: GameState, src: PileRef, dst: PileRef, start_index: int
    ) -> bool:
        """
        Phát hiện nước đi vô ích (chỉ làm tăng độ phức tạp).
        Dùng chủ yếu cho UCS để tránh lãng phí.
        """
        # Di chuyển qua lại giữa các freecell
        if src.kind == PileType.FREECELL and dst.kind == PileType.FREECELL:
            return True

        # Di chuyển bài từ tableau này sang tableau khác
        # mà không tạo sequence có ích
        src_pile_len = (
            len(state.tableau[src.index]) if src.kind == PileType.TABLEAU else 1
        )
        if (
            src.kind == PileType.TABLEAU
            and dst.kind == PileType.TABLEAU
            and src_pile_len - start_index == 1
            and start_index == 0
        ):
            # Di chuyển lá bài đơn độc vô ích
            return True

        return False

    def ucs_solving(self):
        """Uniform Cost Search - Trọng số g(n) = tổng cost của từng nước đi (get_move_cost)"""
        start_time = time.time()
        expanded_nodes = 0

        # Priority Queue lưu: (cost, tie_breaker, state, path)
        count = 0
        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation(initial_state)

        queue = [(0.0, count, initial_state, init_auto)]
        best_cost = {
            self.hash_state(initial_state): 0.0
        }  # Lưu chi phí tốt nhất đến mỗi state

        # Dùng một config duy nhất để tính điểm
        config = MoveCostConfig("ucs")

        while queue:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)

            cost, _, current_state, path = heapq.heappop(queue)
            state_hash = self.hash_state(current_state)

            # Bỏ qua nếu đã có đường đi tốt hơn
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
                # Tính cost cho nước đi (phải tính trước khi apply move)
                move_cost = self.get_move_cost(current_state, move, config)
                new_cost = cost + move_cost

                _, moved = apply_move(current_state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation(current_state)

                new_hash = self.hash_state(current_state)

                # Chỉ thêm nếu tìm được đường đi tốt hơn
                if new_hash not in best_cost or new_cost < best_cost[new_hash] - 0.001:
                    best_cost[new_hash] = new_cost
                    count += 1
                    new_state = (
                        current_state.clone()
                    )  # Chỉ clone khi chắc chắn thêm vào queue
                    heapq.heappush(
                        queue, (new_cost, count, new_state, path + [move] + auto_moves)
                    )

                # Backtrack trả lại trạng thái cho current_state
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
        h_score = (
            52 - cards_in_foundation
        ) * 5  # Nhân hệ số 5 để ưu tiên việc đẩy bài lên Foundation

        # 2. Phạt cấu trúc Tableau xấu và lá bài bị đè
        for col_idx, col in enumerate(state.tableau):
            if not col:
                continue

            for i in range(len(col)):
                card = col[i]

                # Phạt đứt gãy sequence (lá dưới không nối tiếp đúng lá trên)
                if i < len(col) - 1:
                    next_card = col[i + 1]
                    if (
                        is_red(card.suit) == is_red(next_card.suit)
                        or next_card.rank != card.rank - 1
                    ):
                        h_score += 2

                # Phạt nếu đè lên lá đang cần đưa lên Foundation ngay lập tức
                foundation_pile = state.foundations.get(card.suit, [])
                next_needed_rank = len(foundation_pile) + 1
                if card.rank == next_needed_rank:
                    cards_blocking = len(col) - 1 - i
                    h_score += (
                        cards_blocking * 10
                    )  # Phạt cực nặng vì cản trở tiến độ quan trọng

        # 3. Phạt Freecell bị chiếm dụng (mất đi không gian trung chuyển)
        occupied_fc = sum(1 for c in state.free_cells if c is not None)
        h_score += occupied_fc * 2

        return h_score

    def astar_solving(self):
        """A* Search - Đánh giá ưu tiên f(n) = g(n) + h(n)"""
        start_time = time.time()
        expanded_nodes = 0

        # Priority Queue lưu: (f_score, tie_breaker, g_cost, state, path)
        count = 0
        initial_state = self.initial_state.clone()
        init_auto, _ = self._auto_move_to_foundation(initial_state)

        start_h = self.heuristic(initial_state)
        queue = [(start_h, count, 0.0, initial_state, init_auto)]
        visited = set()
        config = MoveCostConfig("astar")

        while queue:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)  # Yield GIL cho giao dien pygame

            f_score, _, g_cost, current_state, path = heapq.heappop(queue)

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
                # Tính cost cho nước đi trước khi mutate state
                move_cost = self.get_move_cost(current_state, move, config)
                new_g = g_cost + move_cost

                _, moved = apply_move(current_state, move[0], move[1], move[2])
                auto_moves, auto_cards = self._auto_move_to_foundation(current_state)

                if self.hash_state(current_state) not in visited:
                    count += 1
                    new_h = self.heuristic(current_state)
                    new_f = new_g + new_h
                    new_state = (
                        current_state.clone()
                    )  # Tránh clone những nhánh đã visited

                    heapq.heappush(
                        queue,
                        (new_f, count, new_g, new_state, path + [move] + auto_moves),
                    )

                # Backtrack
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
