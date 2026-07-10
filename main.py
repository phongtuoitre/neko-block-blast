import pygame
import random
import sys

# Khởi tạo Pygame
pygame.init()

# ================= CÁC HẰNG SỐ =================
WIDTH, HEIGHT = 800, 600
FPS = 60

# Kích thước Grid
GRID_SIZE = 8
CELL_SIZE = 50
PADDING = 4
GRID_OFFSET_X = 50
GRID_OFFSET_Y = 80

# Kích thước Panel (bên phải)
PANEL_X = 520
PANEL_WIDTH = 250

# Màu sắc
BG_COLOR = (30, 30, 46)  # Màu nền tối
GRID_EMPTY_COLOR = (49, 50, 68)  # Màu ô trống
TEXT_COLOR = (205, 214, 244)  # Màu chữ
PREVIEW_ALPHA = 100  # Độ mờ của bóng preview
ANIMATION_COLOR = (255, 255, 255)  # Màu hiệu ứng nháy sáng

# Các màu của Block
BLOCK_COLORS = [
    (137, 180, 250),  # Xanh dương
    (166, 227, 161),  # Xanh lá
    (249, 226, 175),  # Vàng
    (250, 179, 135),  # Cam
    (243, 139, 168),  # Đỏ
    (203, 166, 247),  # Tím
]

# Định nghĩa các hình dạng Block (1: có block, 0: trống)
SHAPES = [
    [[1]],  # 1x1
    [[1, 1]],  # 1x2
    [[1], [1]],  # 2x1
    [[1, 1, 1]],  # 1x3
    [[1], [1], [1]],  # 3x1
    [[1, 1, 1, 1]],  # 1x4
    [[1], [1], [1], [1]],  # 4x1
    [[1, 1], [1, 1]],  # 2x2 vuông
    [[1, 1, 1], [1, 1, 1], [1, 1, 1]],  # 3x3 vuông
    [[1, 1], [1, 0]],  # L nhỏ
    [[1, 1, 1], [1, 0, 0], [1, 0, 0]],  # L lớn
    [[1, 1, 1], [0, 0, 1], [0, 0, 1]],  # J lớn
    [[1, 1, 1], [0, 1, 0]],  # T ngang
    [[1, 0], [1, 1], [1, 0]],  # T dọc
    [[1, 1, 0], [0, 1, 1]],  # Z
]


# ================= LỚP BLOCK =================
class Block:
    def __init__(self, shape, color, slot_index):
        self.shape = shape
        self.color = color
        self.slot_index = slot_index
        self.rows = len(shape)
        self.cols = len(shape[0])

        # Kích thước thực tế của block khi vẽ
        self.width = self.cols * CELL_SIZE + (self.cols - 1) * PADDING
        self.height = self.rows * CELL_SIZE + (self.rows - 1) * PADDING

        self.is_dragging = False
        self.reset_pos()

    def reset_pos(self):
        """Đưa block về lại vị trí bên phải màn hình dựa theo slot_index"""
        slot_center_x = PANEL_X + PANEL_WIDTH // 2
        slot_center_y = 150 + self.slot_index * 140
        self.x = slot_center_x - self.width // 2
        self.y = slot_center_y - self.height // 2

    def draw(self, surface, alpha=255, offset_x=0, offset_y=0):
        """Vẽ block lên màn hình. Hỗ trợ vẽ bóng mờ (alpha < 255)"""
        for r in range(self.rows):
            for c in range(self.cols):
                if self.shape[r][c]:
                    rect_x = self.x + offset_x + c * (CELL_SIZE + PADDING)
                    rect_y = self.y + offset_y + r * (CELL_SIZE + PADDING)
                    rect = pygame.Rect(rect_x, rect_y, CELL_SIZE, CELL_SIZE)

                    if alpha < 255:
                        # Vẽ mờ (preview)
                        s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                        s.fill((*self.color, alpha))
                        surface.blit(s, rect.topleft)
                    else:
                        # Vẽ bình thường
                        pygame.draw.rect(surface, self.color, rect, border_radius=6)

    def get_rect(self):
        """Lấy bounding box để check click chuột"""
        return pygame.Rect(self.x, self.y, self.width, self.height)


# ================= LỚP GAME CHÍNH =================
class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Python Block Blast")
        self.clock = pygame.time.Clock()

        # Font chữ (sử dụng font hệ thống hỗ trợ unicode cơ bản)
        self.font_large = pygame.font.SysFont('arial', 48, bold=True)
        self.font_medium = pygame.font.SysFont('arial', 32, bold=True)
        self.font_small = pygame.font.SysFont('arial', 20)

        self.reset_game()

    def reset_game(self):
        # Grid lưu trữ màu của block, None nếu trống
        self.grid = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.score = 0
        self.available_blocks = []
        self.dragging_block = None
        self.game_over = False

        # Lưu các ô đang có hiệu ứng biến mất
        self.clearing_animations = []

        self.spawn_blocks()

    def spawn_blocks(self):
        """Sinh ra 3 block mới ngẫu nhiên"""
        self.available_blocks = []
        for i in range(3):
            shape = random.choice(SHAPES)
            color = random.choice(BLOCK_COLORS)
            self.available_blocks.append(Block(shape, color, i))

    def can_place(self, block, grid_r, grid_c):
        """Kiểm tra xem block có thể đặt vào tọa độ (grid_r, grid_c) không"""
        # Kiểm tra tràn viền
        if grid_r < 0 or grid_c < 0:
            return False
        if grid_r + block.rows > GRID_SIZE or grid_c + block.cols > GRID_SIZE:
            return False

        # Kiểm tra đè lên block khác
        for r in range(block.rows):
            for c in range(block.cols):
                if block.shape[r][c] == 1:
                    if self.grid[grid_r + r][grid_c + c] is not None:
                        return False
        return True

    def place_block(self, block, grid_r, grid_c):
        """Đặt block vào grid và cập nhật điểm"""
        blocks_placed_count = 0
        for r in range(block.rows):
            for c in range(block.cols):
                if block.shape[r][c] == 1:
                    self.grid[grid_r + r][grid_c + c] = block.color
                    blocks_placed_count += 1

        self.score += blocks_placed_count * 10  # 10 điểm cho mỗi ô vuông của block

        self.available_blocks.remove(block)
        if len(self.available_blocks) == 0:
            self.spawn_blocks()

        self.check_lines()
        self.check_game_over()

    def check_lines(self):
        """Kiểm tra và xóa các hàng/cột đã đầy"""
        rows_to_clear = []
        cols_to_clear = []

        # Kiểm tra hàng
        for r in range(GRID_SIZE):
            if all(self.grid[r][c] is not None for c in range(GRID_SIZE)):
                rows_to_clear.append(r)

        # Kiểm tra cột
        for c in range(GRID_SIZE):
            if all(self.grid[r][c] is not None for r in range(GRID_SIZE)):
                cols_to_clear.append(c)

        if not rows_to_clear and not cols_to_clear:
            return

        # Tính điểm combo
        lines_cleared = len(rows_to_clear) + len(cols_to_clear)
        self.score += lines_cleared * 100 + (lines_cleared - 1) * 50

        # Lưu lại animation và xóa
        for r in rows_to_clear:
            for c in range(GRID_SIZE):
                if self.grid[r][c] is not None:
                    self.clearing_animations.append({'r': r, 'c': c, 'life': 15})
                self.grid[r][c] = None

        for c in cols_to_clear:
            for r in range(GRID_SIZE):
                if self.grid[r][c] is not None:
                    self.clearing_animations.append({'r': r, 'c': c, 'life': 15})
                self.grid[r][c] = None

    def check_game_over(self):
        """Kiểm tra xem còn block nào có thể đặt được không"""
        if not self.available_blocks:
            return

        can_move = False
        for block in self.available_blocks:
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    if self.can_place(block, r, c):
                        can_move = True
                        break
                if can_move: break
            if can_move: break

        if not can_move:
            self.game_over = True

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if self.game_over:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    self.reset_game()
                continue

            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Chuột trái
                    mouse_pos = event.pos
                    # Duyệt ngược để ưu tiên block hiển thị trên cùng
                    for block in reversed(self.available_blocks):
                        if block.get_rect().collidepoint(mouse_pos):
                            block.is_dragging = True
                            self.dragging_block = block
                            # Tâm của block di chuyển đến con trỏ chuột
                            block.x = mouse_pos[0] - block.width // 2
                            block.y = mouse_pos[1] - block.height // 2
                            break

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1 and self.dragging_block:
                    # Tính toán tọa độ grid gần nhất
                    grid_r = round((self.dragging_block.y - GRID_OFFSET_Y) / (CELL_SIZE + PADDING))
                    grid_c = round((self.dragging_block.x - GRID_OFFSET_X) / (CELL_SIZE + PADDING))

                    if self.can_place(self.dragging_block, grid_r, grid_c):
                        self.place_block(self.dragging_block, grid_r, grid_c)
                    else:
                        self.dragging_block.reset_pos()

                    self.dragging_block.is_dragging = False
                    self.dragging_block = None

            elif event.type == pygame.MOUSEMOTION:
                if self.dragging_block:
                    mouse_pos = event.pos
                    # Kéo mượt, luôn giữ block ở giữa con trỏ chuột
                    self.dragging_block.x = mouse_pos[0] - self.dragging_block.width // 2
                    self.dragging_block.y = mouse_pos[1] - self.dragging_block.height // 2

    def draw_grid(self):
        """Vẽ bàn cờ chính"""
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                rect_x = GRID_OFFSET_X + c * (CELL_SIZE + PADDING)
                rect_y = GRID_OFFSET_Y + r * (CELL_SIZE + PADDING)
                rect = pygame.Rect(rect_x, rect_y, CELL_SIZE, CELL_SIZE)

                # Vẽ ô nền
                color = self.grid[r][c] if self.grid[r][c] else GRID_EMPTY_COLOR
                pygame.draw.rect(self.screen, color, rect, border_radius=6)

    def draw_animations(self):
        """Vẽ hiệu ứng xóa hàng (nháy trắng)"""
        for anim in self.clearing_animations[:]:
            rect_x = GRID_OFFSET_X + anim['c'] * (CELL_SIZE + PADDING)
            rect_y = GRID_OFFSET_Y + anim['r'] * (CELL_SIZE + PADDING)
            rect = pygame.Rect(rect_x, rect_y, CELL_SIZE, CELL_SIZE)

            # Giảm thời gian sống
            anim['life'] -= 1
            if anim['life'] <= 0:
                self.clearing_animations.remove(anim)
            else:
                pygame.draw.rect(self.screen, ANIMATION_COLOR, rect, border_radius=6)

    def draw_ui(self):
        """Vẽ giao diện: Điểm số, chữ, v.v."""
        # Score
        score_text = self.font_small.render("SCORE", True, TEXT_COLOR)
        score_val = self.font_large.render(str(self.score), True, TEXT_COLOR)
        self.screen.blit(score_text, (PANEL_X, 30))
        self.screen.blit(score_val, (PANEL_X, 50))

        # Đường kẻ phân cách panel
        pygame.draw.line(self.screen, GRID_EMPTY_COLOR, (PANEL_X - 20, 20), (PANEL_X - 20, HEIGHT - 20), 2)

    def draw_preview(self):
        """Vẽ bóng mờ (preview) khi đang kéo block lên grid hợp lệ"""
        if self.dragging_block:
            grid_r = round((self.dragging_block.y - GRID_OFFSET_Y) / (CELL_SIZE + PADDING))
            grid_c = round((self.dragging_block.x - GRID_OFFSET_X) / (CELL_SIZE + PADDING))

            if self.can_place(self.dragging_block, grid_r, grid_c):
                preview_x = GRID_OFFSET_X + grid_c * (CELL_SIZE + PADDING)
                preview_y = GRID_OFFSET_Y + grid_r * (CELL_SIZE + PADDING)

                off_x = preview_x - self.dragging_block.x
                off_y = preview_y - self.dragging_block.y

                self.dragging_block.draw(self.screen, alpha=PREVIEW_ALPHA, offset_x=off_x, offset_y=off_y)

    def draw_game_over(self):
        """Hiển thị màn hình kết thúc"""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))  # Làm tối màn hình
        self.screen.blit(overlay, (0, 0))

        go_text = self.font_large.render("GAME OVER", True, (243, 139, 168))
        desc_text = self.font_small.render("Nhấp chuột để chơi lại!", True, TEXT_COLOR)

        self.screen.blit(go_text, (WIDTH // 2 - go_text.get_width() // 2, HEIGHT // 2 - 50))
        self.screen.blit(desc_text, (WIDTH // 2 - desc_text.get_width() // 2, HEIGHT // 2 + 20))

    def run(self):
        while True:
            self.handle_events()

            # Render
            self.screen.fill(BG_COLOR)

            self.draw_grid()
            self.draw_animations()
            self.draw_preview()
            self.draw_ui()

            # Vẽ các block có sẵn
            for block in self.available_blocks:
                if block != self.dragging_block:
                    block.draw(self.screen)

            # Block đang kéo được vẽ sau cùng để nằm trên (z-index cao nhất)
            if self.dragging_block:
                self.dragging_block.draw(self.screen)

            if self.game_over:
                self.draw_game_over()

            pygame.display.flip()
            self.clock.tick(FPS)


# ================= CHẠY GAME =================
if __name__ == "__main__":
    game = Game()
    game.run()