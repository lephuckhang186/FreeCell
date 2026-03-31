from .state import GameState
from .rules import validate_move, max_movable_cards, apply_move, PileRef, PileType, pick_cards
from collections import deque
from copy import deepcopy
import time
import sys
import heapq

class FreeCellSolver: 
    def __init__(self, initial_state: GameState):
        self.initial_state = initial_state
        
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
    
    def get_all_possible_move(self, state: GameState):
        moves = []
        
        # Tạo danh sách tất cả các vị trí có thể đặt/lấy bài
        piles = []
        for i in range(8): piles.append(PileRef(PileType.TABLEAU, i))
        for i in range(4): piles.append(PileRef(PileType.FREECELL, i))
        for i in range(4): piles.append(PileRef(PileType.FOUNDATION, i))
        
        # Duyệt qua tất cả các cặp (nguồn, đích)
        for src in piles:
            # Lấy list các start_index hợp lệ để xét (bốc từ đâu trong cột)
            if src.kind == PileType.TABLEAU:
                col_len = len(state.tableau[src.index])
                if col_len == 0: 
                    continue
                indices_to_check = list(range(col_len))
            else:
                # Đối với FreeCell và Foundation, chỉ lấy 1 lá ngoài cùng (index = -1)
                indices_to_check = [-1]
                
            for dst in piles:
                if src == dst: 
                    continue
                
                for start_index in indices_to_check:
                    # Lấy thử các lá bài ra để kiểm tra
                    cards = pick_cards(state, src, start_index)
                    if not cards:
                        continue
                    
                    # Dùng hàm validate_move trong rules.py để kiểm tra hợp lệ
                    result = validate_move(state, src, dst, cards)
                    if result.ok:
                        moves.append((src, dst, start_index))
                        
        return moves
    
    def bfs_solving(self):
        start_time = time.time()
        expanded_nodes = 0
        
        queue = deque([(self.initial_state, [])])
        visited = set()
        visited.add(self.hash_state(self.initial_state))
        
        while queue:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)  # Yield GIL cho giao dien pygame
                
            current_state, path = queue.popleft()
            expanded_nodes += 1
            
            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(visited) + sys.getsizeof(queue) # Ước lượng bytes
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage
                }
            
            for move in self.get_all_possible_move(current_state):
                # Thực hiện copy và apply_move thật sự để tạo state mới (sửa lỗi code cũ mất apply_move)
                new_state = deepcopy(current_state)
                apply_move(new_state, move[0], move[1], move[2])
                
                state_hash = self.hash_state(new_state)
                if state_hash not in visited:
                    visited.add(state_hash)
                    queue.append((new_state, path + [move]))
            
        search_time = time.time() - start_time
        return {"path": None, "search_time": search_time, "expanded_nodes": expanded_nodes}
    
    def dfs_solving(self):
        """Depth-First Search — stack-based with visited set to avoid cycles."""
        start_time = time.time()
        expanded_nodes = 0

        stack = [(self.initial_state, [])]
        visited = set()
        visited.add(self.hash_state(self.initial_state))

        while stack:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)  # Yield GIL cho giao dien pygame

            current_state, path = stack.pop()
            expanded_nodes += 1

            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(visited) + sys.getsizeof(stack)
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage,
                }

            for move in self.get_all_possible_move(current_state):
                new_state = deepcopy(current_state)
                apply_move(new_state, move[0], move[1], move[2])
                state_hash = self.hash_state(new_state)
                if state_hash not in visited:
                    visited.add(state_hash)
                    stack.append((new_state, path + [move]))

        search_time = time.time() - start_time
        return {"path": None, "search_time": search_time, "expanded_nodes": expanded_nodes}

    def ids_solving(self, max_depth: int = 100):
        start_time = time.time()
        expanded_nodes = 0
        
        for depth_limit in range(1, max_depth + 1):
            # DLS iteration
            stack = [(self.initial_state, [], 0)]  # (state, path, current_depth)
            visited = {}
            visited[self.hash_state(self.initial_state)] = 0
            
            while stack:
                if expanded_nodes % 2000 == 0:
                    time.sleep(0.001)  # Yield GIL cho giao dien pygame
                    
                current_state, path, current_depth = stack.pop()
                expanded_nodes += 1
                
                if self.is_win_state(current_state):
                    search_time = time.time() - start_time
                    memory_usage = sys.getsizeof(visited) + sys.getsizeof(stack)
                    return {
                        "path": path,
                        "search_time": search_time,
                        "expanded_nodes": expanded_nodes,
                        "search_length": len(path),
                        "memory_usage_bytes": memory_usage,
                        "depth_reached": depth_limit
                    }
                    
                # Stop expanding this branch if we reached the depth limit
                if current_depth >= depth_limit:
                    continue
                    
                for move in self.get_all_possible_move(current_state):
                    new_state = deepcopy(current_state)
                    apply_move(new_state, move[0], move[1], move[2])
                    
                    state_hash = self.hash_state(new_state)
                    new_depth = current_depth + 1
                    
                    # Only add if unvisited OR found a shorter path to it in this iteration
                    if state_hash not in visited or visited[state_hash] > new_depth:
                        visited[state_hash] = new_depth
                        stack.append((new_state, path + [move], new_depth))
                        
        search_time = time.time() - start_time
        return {"path": None, "search_time": search_time, "expanded_nodes": expanded_nodes, "depth_reached": max_depth}
    
    
    def heuristic(self, state: GameState) -> int:
        # 1. Cơ bản nhất: Số lá bài còn lại chưa được đưa lên Foundation
        cards_in_foundation = sum(len(pile) for pile in state.foundations.values())
        h_score = 52 - cards_in_foundation
        
        # 2. Phạt nếu các lá bài quan trọng (nhỏ) bị đè trong Tableau
        # (Điều này không vi phạm tính admissible vì để lấy lá bài bị đè n lá, 
        # chắc chắn phải tốn ít nhất n nước đi để dọn đường)
        for col_idx, col in enumerate(state.tableau):
            if not col:
                continue
            
            # Duyệt từ đỉnh xuống đáy cột
            for i, card in enumerate(col):
                suit = card.suit
                foundation_pile = state.foundations[suit]
                
                # Lá bài tiếp theo cần đưa lên foundation cho chất này
                next_needed_rank = len(foundation_pile) + 1
                
                # Nếu lá bài này cần để đưa lên foundation mà bị đè 
                if card.rank == next_needed_rank:
                    cards_blocking = len(col) - 1 - i
                    h_score += cards_blocking
                    
        return h_score
    
    
    def ucs_solving(self):
        """Uniform Cost Search - Trọng số g(n) = số nước đi"""
        start_time = time.time()
        expanded_nodes = 0
        
        # Priority Queue lưu: (cost, tie_breaker, state, path)
        count = 0
        queue = [(0, count, self.initial_state, [])]
        visited = set()
        
        while queue:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)  # Yield GIL cho giao dien pygame
                
            cost, _, current_state, path = heapq.heappop(queue)
            
            state_hash = self.hash_state(current_state)
            if state_hash in visited:
                continue
            visited.add(state_hash)
            
            expanded_nodes += 1
            
            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(visited) + sys.getsizeof(queue)
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage
                }
            
            for move in self.get_all_possible_move(current_state):
                new_state = deepcopy(current_state)
                apply_move(new_state, move[0], move[1], move[2])
                
                if self.hash_state(new_state) not in visited:
                    count += 1
                    # Gốc UCS: cost mới = cost cũ + 1 (mỗi bước tốn 1 đơn vị)
                    heapq.heappush(queue, (cost + 1, count, new_state, path + [move]))
            
        search_time = time.time() - start_time
        return {"path": None, "search_time": search_time, "expanded_nodes": expanded_nodes}
        
        
    def astar_solving(self):
        """A* Search - Đánh giá ưu tiên f(n) = g(n) + h(n)"""
        start_time = time.time()
        expanded_nodes = 0
        
        # Priority Queue lưu: (f_score, tie_breaker, g_cost, state, path)
        count = 0
        start_h = self.heuristic(self.initial_state)
        queue = [(start_h, count, 0, self.initial_state, [])]
        visited = set()
        
        while queue:
            if expanded_nodes % 2000 == 0:
                time.sleep(0.001)  # Yield GIL cho giao dien pygame
                
            f_score, _, g_cost, current_state, path = heapq.heappop(queue)
            
            state_hash = self.hash_state(current_state)
            if state_hash in visited:
                continue
            visited.add(state_hash)
            
            expanded_nodes += 1
            
            if self.is_win_state(current_state):
                search_time = time.time() - start_time
                memory_usage = sys.getsizeof(visited) + sys.getsizeof(queue)
                return {
                    "path": path,
                    "search_time": search_time,
                    "expanded_nodes": expanded_nodes,
                    "search_length": len(path),
                    "memory_usage_bytes": memory_usage
                }
            
            for move in self.get_all_possible_move(current_state):
                new_state = deepcopy(current_state)
                apply_move(new_state, move[0], move[1], move[2])
                
                if self.hash_state(new_state) not in visited:
                    count += 1
                    new_g = g_cost + 1
                    new_h = self.heuristic(new_state)
                    new_f = new_g + new_h
                    
                    heapq.heappush(queue, (new_f, count, new_g, new_state, path + [move]))
            
        search_time = time.time() - start_time
        return {"path": None, "search_time": search_time, "expanded_nodes": expanded_nodes}
                    
            
        
        
        
            
 
