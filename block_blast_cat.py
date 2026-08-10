import pygame
import random
import sys
import json
import os
import argparse
import math
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from client_audio import play_match_music, stop_match_audio

# Khởi tạo Pygame
pygame.init()
try:
    pygame.mixer.init()
except pygame.error:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= CÁC HẰNG SỐ & GIAO DIỆN PASTEL =================
WIDTH, HEIGHT = 850, 650
FPS = 60

# Bảng màu Pastel
PASTEL_BG = (255, 250, 240)
PASTEL_GRID_EMPTY = (240, 230, 220)
PASTEL_TEXT = (100, 80, 70)
PASTEL_ACCENT_DARK = (110, 85, 75)
PASTEL_GLOW = (255, 200, 220, 150)
PASTEL_PREVIEW = (150, 150, 150)
INPUT_BOX_COLOR = (255, 255, 255)
INPUT_BOX_ACTIVE = (255, 182, 193)

BLOCK_COLORS = [
    (173, 216, 230), (255, 182, 193), (176, 224, 230),
    (255, 218, 185), (221, 160, 221), (152, 251, 152),
]

GRID_SIZE = 8
CELL_SIZE = 55
PADDING = 5
GRID_OFFSET_X = 50
GRID_OFFSET_Y = 90

PANEL_X = 580
PANEL_WIDTH = 250
DRAG_SCALE_FACTOR = 1.2

SHAPES = [
    [[1]], [[1, 1]], [[1], [1]], [[1, 1, 1]], [[1], [1], [1]],
    [[1, 1, 1, 1]], [[1], [1], [1], [1]], [[1, 1], [1, 1]],
    [[1, 1], [1, 0]], [[1, 1, 1], [1, 0, 0]], [[1, 1, 1], [0, 1, 0]],
    [[1, 1, 0], [0, 1, 1]], [[0, 1, 1], [1, 1, 0]], [[1, 1, 1], [0, 0, 1]],
]

# Các trạng thái của Game
STATE_LOGIN = "LOGIN"
STATE_PLAY = "PLAY"
STATE_LEADERBOARD = "LEADERBOARD"

# ================= TẠO FONT HỖ TRỢ TIẾNG VIỆT =================
try:
    FONT_PATH = pygame.font.match_font('comicsansms')
    if not FONT_PATH: FONT_PATH = pygame.font.match_font('arial')
    font_large = pygame.font.Font(FONT_PATH, 48)
    font_medium = pygame.font.Font(FONT_PATH, 28)
    font_small = pygame.font.Font(FONT_PATH, 20)

    font_path_vn = pygame.font.match_font('segoeui')
    if not font_path_vn: font_path_vn = pygame.font.match_font('arial')
    font_vn_large = pygame.font.Font(font_path_vn, 48)
    font_vn_medium = pygame.font.Font(font_path_vn, 32)
    font_vn_small = pygame.font.Font(font_path_vn, 22)
except:
    font_large = pygame.font.SysFont('arial', 48, bold=True)
    font_medium = pygame.font.SysFont('arial', 28, bold=True)
    font_small = pygame.font.SysFont('arial', 20)
    font_vn_large = pygame.font.SysFont('arial', 48, bold=True)
    font_vn_medium = pygame.font.SysFont('arial', 32, bold=True)
    font_vn_small = pygame.font.SysFont('arial', 22)


def load_vietnamese_font(size):
    for font_path in (
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf",
    ):
        if os.path.exists(font_path):
            return pygame.font.Font(font_path, size)

    return pygame.font.SysFont("Arial", size, bold=True)


font_login_vn_medium = load_vietnamese_font(32)
font_login_vn_small = load_vietnamese_font(22)
font_online_label = load_vietnamese_font(12)
font_online_value = load_vietnamese_font(14)
font_online_overlay_title = load_vietnamese_font(32)
font_online_overlay_text = load_vietnamese_font(20)
font_neko_title = load_vietnamese_font(18)
font_neko_text = load_vietnamese_font(14)
font_neko_tiny = load_vietnamese_font(12)
font_neko_button = load_vietnamese_font(13)

NEKO_AI_STATE_DIR = os.path.join(
    os.getenv("APPDATA") or os.path.expanduser("~"),
    "NekoBlockBlast",
)
NEKO_AI_STATE_PATH = os.path.join(NEKO_AI_STATE_DIR, "neko_ai_state.json")
NEKO_AI_MAX_QUESTION_LENGTH = 360

NEKO_QUICK_QUESTIONS = [
    "Hướng dẫn cách chơi",
    "Mẹo cho người mới",
    "Làm sao để được nhiều điểm?",
    "Phân tích bàn chơi hiện tại",
    "Tôi nên đặt khối ở đâu?",
]

NEKO_TUTORIAL_STEPS = [
    (
        "Chọn và đặt khối",
        "Chọn một khối mèo ở bảng bên phải, kéo vào vùng ô trống trên bàn chơi.",
    ),
    (
        "Hoàn thành hàng hoặc cột",
        "Khi một hàng hoặc cột được lấp đầy, các ô đó sẽ biến mất để mở thêm chỗ.",
    ),
    (
        "Điểm và combo",
        "Mỗi ô đặt xuống có điểm. Xóa nhiều hàng/cột cùng lúc sẽ được thưởng thêm.",
    ),
    (
        "Khi trò chơi kết thúc",
        "Nếu tất cả khối hiện có đều không còn vị trí đặt hợp lệ, ván chơi kết thúc.",
    ),
    (
        "Mẹo cho người mới",
        "Giữ trung tâm bàn thoáng, đặt khối lớn trước và đừng tạo quá nhiều lỗ nhỏ.",
    ),
]


# ================= LỚP HIỆU ỨNG VÀ MÈO (Giữ nguyên) =================
class Particle:
    def __init__(self, x, y, color):
        self.x, self.y = x, y
        self.vx = random.uniform(-4, 4)
        self.vy = random.uniform(-6, 2)
        self.life = random.randint(20, 40)
        self.max_life = self.life
        self.color = color
        self.size = random.randint(4, 8)

    def update(self):
        self.x += self.vx;
        self.y += self.vy
        self.vy += 0.25;
        self.life -= 1

    def draw(self, surface):
        if self.life > 0:
            current_size = max(1, int(self.size * (self.life / self.max_life)))
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), current_size)


class HappyCatPopup:
    def __init__(self):
        self.active = False
        self.y_pos = HEIGHT
        self.alpha = 255
        self.surf = pygame.Surface((150, 150), pygame.SRCALPHA)
        self._draw_happy_cat(self.surf, 150)

    def _draw_happy_cat(self, surf, s):
        cat_color = (255, 220, 150);
        ear_color = (255, 150, 180);
        eye_color = (50, 30, 20)
        scale = s / 55
        pygame.draw.polygon(surf, cat_color,
                            [(10 * scale, 25 * scale), (5 * scale, 5 * scale), (25 * scale, 15 * scale)])
        pygame.draw.polygon(surf, cat_color,
                            [(45 * scale, 25 * scale), (50 * scale, 5 * scale), (30 * scale, 15 * scale)])
        pygame.draw.polygon(surf, ear_color,
                            [(10 * scale, 20 * scale), (8 * scale, 8 * scale), (20 * scale, 15 * scale)])
        pygame.draw.polygon(surf, ear_color,
                            [(45 * scale, 20 * scale), (47 * scale, 8 * scale), (35 * scale, 15 * scale)])
        rect = pygame.Rect(5 * scale, 15 * scale, 45 * scale, 35 * scale)
        pygame.draw.rect(surf, cat_color, rect, border_radius=int(12 * scale))
        pygame.draw.arc(surf, eye_color, pygame.Rect(14 * scale, 28 * scale, 8 * scale, 6 * scale), 0, 3.14159,
                        int(2 * scale))
        pygame.draw.arc(surf, eye_color, pygame.Rect(33 * scale, 28 * scale, 8 * scale, 6 * scale), 0, 3.14159,
                        int(2 * scale))
        pygame.draw.circle(surf, (255, 120, 140), (12 * scale, 35 * scale), 5 * scale)
        pygame.draw.circle(surf, (255, 120, 140), (43 * scale, 35 * scale), 5 * scale)
        pygame.draw.polygon(surf, ear_color,
                            [(24 * scale, 36 * scale), (30 * scale, 36 * scale), (27 * scale, 40 * scale)])
        pygame.draw.arc(surf, eye_color, pygame.Rect(20 * scale, 38 * scale, 7 * scale, 5 * scale), 3.14159, 0,
                        int(2 * scale))
        pygame.draw.arc(surf, eye_color, pygame.Rect(27 * scale, 38 * scale, 7 * scale, 5 * scale), 3.14159, 0,
                        int(2 * scale))

    def trigger(self):
        self.active = True;
        self.y_pos = HEIGHT;
        self.alpha = 255

    def update(self):
        if self.active:
            self.y_pos -= 4;
            self.alpha -= 3
            if self.alpha <= 0: self.active = False; self.alpha = 0

    def draw(self, surface):
        if self.active:
            temp_surf = self.surf.copy()
            temp_surf.set_alpha(self.alpha)
            surface.blit(temp_surf, (20, self.y_pos))
            text = font_vn_medium.render("Tuyệt Vời!", True, (255, 150, 50))
            text.set_alpha(self.alpha)
            surface.blit(text, (20, self.y_pos - 35))


class SurpriseCat:
    def __init__(self, max_size=420):
        self.max_size = max_size
        self.surface_base = pygame.Surface((max_size, max_size), pygame.SRCALPHA)
        self._draw_crying_cat(self.surface_base, max_size)
        self.active = False;
        self.triggered = False;
        self.state = 'idle'
        self.current_size = 0;
        self.zoom_speed = 6.5;
        self.hold_frames = 0
        self.max_hold = 90;
        self.alpha = 255;
        self.fade_speed = 5

    def _draw_crying_cat(self, surf, s):
        cat_color = (255, 180, 100);
        ear_color = (240, 100, 120)
        eye_color = (50, 30, 20);
        tear_color = (60, 150, 255);
        scale = s / 55
        pygame.draw.polygon(surf, cat_color,
                            [(10 * scale, 25 * scale), (5 * scale, 5 * scale), (25 * scale, 15 * scale)])
        pygame.draw.polygon(surf, cat_color,
                            [(45 * scale, 25 * scale), (50 * scale, 5 * scale), (30 * scale, 15 * scale)])
        pygame.draw.polygon(surf, ear_color,
                            [(10 * scale, 20 * scale), (8 * scale, 8 * scale), (20 * scale, 15 * scale)])
        pygame.draw.polygon(surf, ear_color,
                            [(45 * scale, 20 * scale), (47 * scale, 8 * scale), (35 * scale, 15 * scale)])
        rect = pygame.Rect(5 * scale, 15 * scale, 45 * scale, 35 * scale)
        pygame.draw.rect(surf, cat_color, rect, border_radius=int(12 * scale))
        eye_radius = 6 * scale
        pygame.draw.circle(surf, eye_color, (18 * scale, 30 * scale), eye_radius)
        pygame.draw.circle(surf, eye_color, (37 * scale, 30 * scale), eye_radius)
        tear_size = int(8 * scale)
        pygame.draw.ellipse(surf, tear_color,
                            (18 * scale - tear_size // 2, 30 * scale + 2 * scale, tear_size, tear_size * 1.5))
        pygame.draw.ellipse(surf, tear_color,
                            (37 * scale - tear_size // 2, 30 * scale + 2 * scale, tear_size, tear_size * 1.5))
        pygame.draw.circle(surf, (255, 255, 255), (16 * scale, 28 * scale), 2 * scale)
        pygame.draw.circle(surf, (255, 255, 255), (35 * scale, 28 * scale), 2 * scale)
        pygame.draw.circle(surf, (255, 120, 140), (12 * scale, 38 * scale), 6 * scale)
        pygame.draw.circle(surf, (255, 120, 140), (43 * scale, 38 * scale), 6 * scale)
        pygame.draw.polygon(surf, ear_color,
                            [(24 * scale, 36 * scale), (30 * scale, 36 * scale), (27 * scale, 40 * scale)])
        mouth_rect = pygame.Rect(20 * scale, 38 * scale, 14 * scale, 10 * scale)
        pygame.draw.arc(surf, eye_color, mouth_rect, 0, 3.14159 / 2, int(2 * scale))

    def trigger(self):
        if not self.triggered:
            self.active = True;
            self.triggered = True;
            self.state = 'zooming'
            self.current_size = 10;
            self.alpha = 255;
            self.hold_frames = 0

    def update(self):
        if not self.active: return
        if self.state == 'zooming':
            self.current_size += self.zoom_speed
            if self.current_size >= self.max_size:
                self.current_size = self.max_size;
                self.state = 'holding'
        elif self.state == 'holding':
            self.hold_frames += 1
            if self.hold_frames >= self.max_hold: self.state = 'fading'
        elif self.state == 'fading':
            self.alpha -= self.fade_speed
            if self.alpha <= 0:
                self.alpha = 0;
                self.active = False;
                self.state = 'idle'

    def draw(self, surface):
        if self.active and self.current_size > 0:
            scaled_surf = pygame.transform.smoothscale(self.surface_base,
                                                       (int(self.current_size), int(self.current_size)))
            if self.alpha < 255:
                temp_surf = scaled_surf.copy()
                temp_surf.set_alpha(self.alpha)
                scaled_surf = temp_surf
            grid_center_x = GRID_OFFSET_X + (GRID_SIZE * (CELL_SIZE + PADDING)) // 2
            grid_center_y = GRID_OFFSET_Y + (GRID_SIZE * (CELL_SIZE + PADDING)) // 2
            draw_x = grid_center_x - self.current_size // 2
            draw_y = grid_center_y - self.current_size // 2
            surface.blit(scaled_surf, (draw_x, draw_y))


class Block:
    _cat_base_surface = None

    def __init__(self, shape, color, slot_index):
        self.shape = shape;
        self.base_color = color;
        self.slot_index = slot_index
        self.rows = len(shape);
        self.cols = len(shape[0])
        if Block._cat_base_surface is None: Block._init_image()
        self.surface = self._create_block_surface()
        self.is_dragging = False;
        self.is_hovered = False
        self.reset_pos()

    @staticmethod
    def _init_image():
        surf = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        cat_color = (255, 228, 196);
        ear_color = (255, 182, 193);
        eye_color = (100, 80, 70)
        pygame.draw.polygon(surf, cat_color, [(10, 25), (5, 5), (25, 15)])
        pygame.draw.polygon(surf, cat_color, [(45, 25), (50, 5), (30, 15)])
        pygame.draw.polygon(surf, ear_color, [(10, 20), (8, 8), (20, 15)])
        pygame.draw.polygon(surf, ear_color, [(45, 20), (47, 8), (35, 15)])
        rect = pygame.Rect(5, 15, 45, 35)
        pygame.draw.rect(surf, cat_color, rect, border_radius=12)
        pygame.draw.circle(surf, eye_color, (18, 30), 4)
        pygame.draw.circle(surf, eye_color, (37, 30), 4)
        pygame.draw.circle(surf, ear_color, (12, 35), 3)
        pygame.draw.circle(surf, ear_color, (43, 35), 3)
        pygame.draw.line(surf, eye_color, (24, 35), (27, 39), 2)
        pygame.draw.line(surf, eye_color, (27, 39), (30, 35), 2)
        Block._cat_base_surface = surf

    def _create_block_surface(self, alpha=255):
        w = self.cols * (CELL_SIZE + PADDING) - PADDING
        h = self.rows * (CELL_SIZE + PADDING) - PADDING
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for r in range(self.rows):
            for c in range(self.cols):
                if self.shape[r][c]:
                    x = c * (CELL_SIZE + PADDING);
                    y = r * (CELL_SIZE + PADDING)
                    surf.blit(Block._cat_base_surface, (x, y))
        if alpha < 255: surf.set_alpha(alpha)
        return surf

    @property
    def width(self):
        return self.surface.get_width()

    @property
    def height(self):
        return self.surface.get_height()

    def reset_pos(self):
        slot_center_x = PANEL_X + PANEL_WIDTH // 2
        slot_y_base = 120
        slot_height = (HEIGHT - slot_y_base - 20) // 3
        slot_center_y = slot_y_base + self.slot_index * slot_height + slot_height // 2
        self.x = slot_center_x - self.width // 2
        self.y = slot_center_y - self.height // 2

    def draw(self, surface, alpha=255, is_preview=False, pos=None):
        draw_x, draw_y = (self.x, self.y) if pos is None else pos
        target_surf = self.surface

        if self.is_dragging:
            new_w = int(self.width * DRAG_SCALE_FACTOR)
            new_h = int(self.height * DRAG_SCALE_FACTOR)
            target_surf = pygame.transform.smoothscale(self.surface, (new_w, new_h))
            draw_x -= (new_w - self.width) // 2;
            draw_y -= (new_h - self.height) // 2

        if is_preview:
            preview_surf = target_surf.copy()
            preview_surf.fill((*PASTEL_PREVIEW, 180), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(preview_surf, (draw_x, draw_y))
        elif alpha < 255:
            temp_surf = target_surf.copy()
            temp_surf.set_alpha(alpha)
            surface.blit(temp_surf, (draw_x, draw_y))
        else:
            if self.is_hovered and not self.is_dragging and pos is None:
                glow_size = 15
                glow_rect = pygame.Rect(self.x - glow_size // 2, self.y - glow_size // 2,
                                        self.width + glow_size, self.height + glow_size)
                glow_surf = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                pygame.draw.ellipse(glow_surf, PASTEL_GLOW, glow_surf.get_rect())
                surface.blit(glow_surf, glow_rect.topleft)
            surface.blit(target_surf, (draw_x, draw_y))

    def get_rect(self):
        return pygame.Rect(self.x, self.y, self.width, self.height)


# ================= LỚP GAME CHÍNH =================
def render_fit(text, color, max_width, start_size=13, min_size=10):
    for size in range(start_size, min_size - 1, -1):
        font = load_vietnamese_font(size)
        surface = font.render(text, True, color)
        if surface.get_width() <= max_width or size == min_size:
            return surface
    return font_neko_button.render(text, True, color)


def wrap_text(text, font, max_width):
    lines = []
    for raw_line in str(text).splitlines() or [""]:
        words = raw_line.split(" ")
        line = ""
        for word in words:
            candidate = word if not line else f"{line} {word}"
            if font.size(candidate)[0] <= max_width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = word
            else:
                clipped = word
                while font.size(clipped)[0] > max_width and len(clipped) > 4:
                    clipped = clipped[:-1]
                lines.append(f"{clipped}..." if clipped != word else word)
                line = ""
        if line:
            lines.append(line)
    return lines


class NekoButton:
    def __init__(self, button_id, label, rect, accessibility_label=None):
        self.button_id = button_id
        self.label = label
        self.rect = pygame.Rect(rect)
        self.accessibility_label = accessibility_label or label

    def draw(self, surface, mouse_pos, enabled=True):
        hovered = enabled and self.rect.collidepoint(mouse_pos)
        fill = (255, 255, 255) if hovered else (255, 245, 238)
        border = PASTEL_ACCENT_DARK if hovered else (255, 182, 193)
        text_color = PASTEL_TEXT if enabled else (170, 155, 145)
        if not enabled:
            fill = (242, 234, 228)
            border = (220, 205, 195)

        pygame.draw.rect(surface, fill, self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, 2, border_radius=8)
        label = render_fit(self.label, text_color, self.rect.width - 12)
        surface.blit(label, label.get_rect(center=self.rect.center))

    def clicked(self, event, enabled=True):
        return (
            enabled
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


class NekoAIGuide:
    def __init__(self, game):
        self.game = game
        self.visible = False
        self.tutorial_active = False
        self.tutorial_step = 0
        self.input_text = ""
        self.input_active = False
        self.is_loading = False
        self.error_message = ""
        self.request_future = None
        self.pending_question = ""
        self.messages = []
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.auto_prompted = False
        self.cat_accessibility_label = "Mở Neko AI, trợ lý trong game"
        self.state_data = self.load_state()
        self.tutorial_seen = bool(self.state_data.get("tutorial_seen"))

        self.cat_rect = pygame.Rect(0, 0, 64, 64)
        self.panel_rect = pygame.Rect(0, 0, 310, 390)
        self.close_button = None
        self.send_button = None
        self.input_rect = pygame.Rect(0, 0, 1, 1)
        self.quick_buttons = []
        self.tutorial_buttons = []

    def load_state(self):
        try:
            with open(NEKO_AI_STATE_PATH, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save_state(self):
        try:
            os.makedirs(NEKO_AI_STATE_DIR, exist_ok=True)
            with open(NEKO_AI_STATE_PATH, "w", encoding="utf-8") as file:
                json.dump(self.state_data, file, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def mark_tutorial_seen(self):
        self.tutorial_seen = True
        self.state_data["tutorial_seen"] = True
        self.save_state()

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)

    def ensure_intro(self):
        if self.auto_prompted or self.game.state != STATE_PLAY:
            return
        self.auto_prompted = True
        if not self.tutorial_seen:
            self.visible = True
            self.tutorial_active = True
            self.add_message(
                "assistant",
                "Meo meo! Mình là Neko AI. Mình sẽ chỉ nhanh cách chơi nhé.",
            )

    def add_message(self, role, content):
        clean_content = str(content).strip()
        if not clean_content:
            return
        self.messages.append({"role": role, "content": clean_content[:1200]})
        self.messages = self.messages[-12:]

    def calculate_layout(self):
        cat_size = 64
        right_rect = pygame.Rect(WIDTH - cat_size - 16, HEIGHT - cat_size - 14, cat_size, cat_size)
        important_panel = pygame.Rect(PANEL_X - 8, 118, PANEL_WIDTH + 10, HEIGHT - 120)
        if right_rect.colliderect(important_panel):
            self.cat_rect = pygame.Rect(18, HEIGHT - cat_size - 14, cat_size, cat_size)
        else:
            self.cat_rect = right_rect

        panel_width = min(310, WIDTH - 32)
        panel_height = min(450, HEIGHT - 96)
        board_right = GRID_OFFSET_X + GRID_SIZE * (CELL_SIZE + PADDING) - PADDING
        panel_x = max(board_right + 2, WIDTH - panel_width - 16)
        panel_y = max(90, HEIGHT - panel_height - 64)
        self.panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
        self.close_button = NekoButton(
            "close",
            "X",
            pygame.Rect(self.panel_rect.right - 36, self.panel_rect.y + 10, 26, 26),
            "Thu nhỏ bảng trò chuyện Neko AI",
        )

    def draw_cat_icon(self, surface):
        self.calculate_layout()
        rect = self.cat_rect
        ticks = pygame.time.get_ticks()
        bob = int(math.sin(ticks / 280) * 3)
        blink = ticks % 2600 > 2440
        cx = rect.centerx
        cy = rect.centery + bob

        if self.visible:
            glow = pygame.Surface((rect.width + 18, rect.height + 18), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (255, 200, 220, 110), glow.get_rect())
            surface.blit(glow, (rect.x - 9, rect.y - 9 + bob))

        tail_points = [
            (cx + 22, cy + 12),
            (cx + 34, cy + 4),
            (cx + 31, cy - 7),
            (cx + 22, cy - 2),
        ]
        pygame.draw.lines(surface, (245, 178, 185), False, tail_points, 8)
        pygame.draw.circle(surface, (255, 222, 205), (cx, cy + 8), 25)
        pygame.draw.polygon(surface, (255, 222, 205), [(cx - 23, cy - 10), (cx - 15, cy - 32), (cx - 4, cy - 13)])
        pygame.draw.polygon(surface, (255, 222, 205), [(cx + 23, cy - 10), (cx + 15, cy - 32), (cx + 4, cy - 13)])
        pygame.draw.polygon(surface, (245, 178, 185), [(cx - 18, cy - 13), (cx - 14, cy - 25), (cx - 7, cy - 13)])
        pygame.draw.polygon(surface, (245, 178, 185), [(cx + 18, cy - 13), (cx + 14, cy - 25), (cx + 7, cy - 13)])
        pygame.draw.circle(surface, (255, 182, 193), (cx - 14, cy + 10), 4)
        pygame.draw.circle(surface, (255, 182, 193), (cx + 14, cy + 10), 4)
        if blink:
            pygame.draw.line(surface, PASTEL_TEXT, (cx - 14, cy - 1), (cx - 6, cy - 1), 2)
            pygame.draw.line(surface, PASTEL_TEXT, (cx + 6, cy - 1), (cx + 14, cy - 1), 2)
        else:
            pygame.draw.circle(surface, PASTEL_TEXT, (cx - 10, cy - 2), 3)
            pygame.draw.circle(surface, PASTEL_TEXT, (cx + 10, cy - 2), 3)
        pygame.draw.line(surface, PASTEL_TEXT, (cx - 3, cy + 6), (cx, cy + 9), 2)
        pygame.draw.line(surface, PASTEL_TEXT, (cx + 3, cy + 6), (cx, cy + 9), 2)
        paw_y = cy + 20 + int(math.sin(ticks / 180) * 2)
        pygame.draw.circle(surface, (255, 222, 205), (cx + 20, paw_y), 7)
        pygame.draw.arc(surface, PASTEL_ACCENT_DARK, pygame.Rect(cx - 20, cy + 5, 40, 20), 0, math.pi, 2)

    def draw_panel(self, surface):
        if not self.visible:
            return

        mouse_pos = pygame.mouse.get_pos()
        rect = self.panel_rect
        shadow = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        shadow.fill((140, 100, 90, 38))
        surface.blit(shadow, (rect.x + 4, rect.y + 5))
        pygame.draw.rect(surface, (255, 250, 245), rect, border_radius=8)
        pygame.draw.rect(surface, (235, 180, 170), rect, 2, border_radius=8)

        title = font_neko_title.render("Neko AI – Trợ lý của bạn", True, PASTEL_TEXT)
        surface.blit(title, (rect.x + 14, rect.y + 13))
        self.close_button.draw(surface, mouse_pos)

        if self.tutorial_active:
            self.draw_tutorial(surface)
        else:
            self.draw_chat(surface)

    def draw_tutorial(self, surface):
        rect = self.panel_rect
        content_rect = pygame.Rect(rect.x + 16, rect.y + 54, rect.width - 32, rect.height - 112)
        pygame.draw.rect(surface, (255, 255, 255), content_rect, border_radius=8)
        pygame.draw.rect(surface, (242, 215, 205), content_rect, 2, border_radius=8)

        step_title, step_body = NEKO_TUTORIAL_STEPS[self.tutorial_step]
        step_text = font_neko_tiny.render(
            f"Bước {self.tutorial_step + 1}/{len(NEKO_TUTORIAL_STEPS)}",
            True,
            PASTEL_ACCENT_DARK,
        )
        surface.blit(step_text, (content_rect.x + 12, content_rect.y + 12))
        title = font_neko_title.render(step_title, True, PASTEL_TEXT)
        surface.blit(title, (content_rect.x + 12, content_rect.y + 34))

        y = content_rect.y + 66
        for line in wrap_text(step_body, font_neko_text, content_rect.width - 24):
            text = font_neko_text.render(line, True, PASTEL_TEXT)
            surface.blit(text, (content_rect.x + 12, y))
            y += 22

        hint = "Meo meo, bạn vẫn chơi bình thường sau khi thu nhỏ bảng này."
        y = content_rect.bottom - 54
        for line in wrap_text(hint, font_neko_tiny, content_rect.width - 24):
            text = font_neko_tiny.render(line, True, (135, 110, 100))
            surface.blit(text, (content_rect.x + 12, y))
            y += 18

        button_y = rect.bottom - 48
        button_w = 66
        gap = 6
        labels = [
            ("back", "Quay lại", "Quay lại bước hướng dẫn trước"),
            ("skip", "Bỏ qua", "Bỏ qua hướng dẫn Neko AI"),
            (
                "finish" if self.tutorial_step == len(NEKO_TUTORIAL_STEPS) - 1 else "next",
                "Hoàn tất" if self.tutorial_step == len(NEKO_TUTORIAL_STEPS) - 1 else "Tiếp theo",
                "Hoàn tất hướng dẫn" if self.tutorial_step == len(NEKO_TUTORIAL_STEPS) - 1 else "Xem bước hướng dẫn tiếp theo",
            ),
        ]
        start_x = rect.right - (button_w * 3 + gap * 2) - 14
        self.tutorial_buttons = []
        for index, (button_id, label, accessibility_label) in enumerate(labels):
            button = NekoButton(
                button_id,
                label,
                pygame.Rect(start_x + index * (button_w + gap), button_y, button_w, 30),
                accessibility_label,
            )
            enabled = button_id != "back" or self.tutorial_step > 0
            button.draw(surface, pygame.mouse.get_pos(), enabled=enabled)
            self.tutorial_buttons.append((button, enabled))

    def build_message_items(self, area_width):
        items = []
        for message in self.messages[-8:]:
            role = "Bạn" if message["role"] == "user" else "Neko"
            lines = wrap_text(f"{role}: {message['content']}", font_neko_tiny, area_width - 18)
            height = 12 + len(lines) * 17
            items.append((message["role"], lines, height))
        return items

    def draw_chat_messages(self, surface, area):
        pygame.draw.rect(surface, (255, 255, 255), area, border_radius=8)
        pygame.draw.rect(surface, (242, 215, 205), area, 2, border_radius=8)
        items = self.build_message_items(area.width)
        visible_items = []
        total_height = 0
        for item in reversed(items):
            next_height = total_height + item[2] + 6
            if visible_items and next_height > area.height - 10:
                break
            visible_items.append(item)
            total_height = next_height
        visible_items.reverse()

        y = area.bottom - total_height - 4
        for role, lines, height in visible_items:
            bubble_rect = pygame.Rect(area.x + 6, y, area.width - 12, height)
            fill = (245, 252, 255) if role == "user" else (255, 246, 250)
            pygame.draw.rect(surface, fill, bubble_rect, border_radius=8)
            text_y = bubble_rect.y + 6
            for line in lines:
                text = font_neko_tiny.render(line, True, PASTEL_TEXT)
                surface.blit(text, (bubble_rect.x + 8, text_y))
                text_y += 17
            y += height + 6

    def draw_quick_questions(self, surface, top_y):
        rect = self.panel_rect
        self.quick_buttons = []
        button_w = rect.width - 28
        button_h = 21
        gap = 4
        for index, question in enumerate(NEKO_QUICK_QUESTIONS):
            button_rect = pygame.Rect(
                rect.x + 14,
                top_y + index * (button_h + gap),
                button_w,
                button_h,
            )
            button = NekoButton(
                f"quick_{index}",
                question,
                button_rect,
                f"Câu hỏi nhanh: {question}",
            )
            button.draw(surface, pygame.mouse.get_pos(), enabled=not self.is_loading)
            self.quick_buttons.append((button, question))

    def draw_chat(self, surface):
        rect = self.panel_rect
        message_area = pygame.Rect(rect.x + 14, rect.y + 54, rect.width - 28, rect.height - 232)
        self.draw_chat_messages(surface, message_area)

        status_y = message_area.bottom + 8
        if self.is_loading:
            status = font_neko_tiny.render("Neko đang nghĩ...", True, PASTEL_ACCENT_DARK)
            surface.blit(status, (rect.x + 16, status_y))
        elif self.error_message:
            for line in wrap_text(self.error_message, font_neko_tiny, rect.width - 32)[:2]:
                status = font_neko_tiny.render(line, True, (180, 85, 85))
                surface.blit(status, (rect.x + 16, status_y))
                status_y += 16

        quick_top = rect.bottom - 162
        self.draw_quick_questions(surface, quick_top)

        self.input_rect = pygame.Rect(rect.x + 14, rect.bottom - 40, rect.width - 86, 30)
        input_fill = (255, 255, 255) if self.input_active else (255, 247, 242)
        input_border = PASTEL_ACCENT_DARK if self.input_active else (230, 200, 190)
        pygame.draw.rect(surface, input_fill, self.input_rect, border_radius=8)
        pygame.draw.rect(surface, input_border, self.input_rect, 2, border_radius=8)
        shown = self.input_text
        if self.input_active and pygame.time.get_ticks() % 1000 < 500:
            shown += "|"
        if not shown:
            shown = "Hỏi Neko..."
        input_text = render_fit(shown, (145, 120, 110), self.input_rect.width - 16, start_size=13, min_size=10)
        surface.blit(input_text, (self.input_rect.x + 9, self.input_rect.y + 7))

        self.send_button = NekoButton(
            "send",
            "Gửi",
            pygame.Rect(rect.right - 62, rect.bottom - 40, 48, 30),
            "Gửi câu hỏi cho Neko AI",
        )
        self.send_button.draw(
            surface,
            pygame.mouse.get_pos(),
            enabled=bool(self.input_text.strip()) and not self.is_loading,
        )

    def draw(self, surface):
        self.draw_cat_icon(surface)
        self.draw_panel(surface)

    def handle_event(self, event):
        self.calculate_layout()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.cat_rect.collidepoint(event.pos):
                self.visible = not self.visible
                self.input_active = False
                if self.visible and not self.tutorial_seen and not self.messages:
                    self.start_tutorial()
                return True

            if not self.visible:
                return False

            if self.close_button and self.close_button.clicked(event):
                self.visible = False
                self.input_active = False
                return True

            if self.tutorial_active:
                for button, enabled in self.tutorial_buttons:
                    if button.clicked(event, enabled=enabled):
                        self.handle_tutorial_action(button.button_id)
                        return True
                return self.panel_rect.collidepoint(event.pos)

            self.input_active = self.input_rect.collidepoint(event.pos)
            if self.send_button and self.send_button.clicked(
                event,
                enabled=bool(self.input_text.strip()) and not self.is_loading,
            ):
                self.send_question(self.input_text)
                return True
            for button, question in self.quick_buttons:
                if button.clicked(event, enabled=not self.is_loading):
                    if question == "Hướng dẫn cách chơi":
                        self.start_tutorial()
                    else:
                        self.send_question(question)
                    return True

            return self.panel_rect.collidepoint(event.pos)

        if self.visible and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.visible = False
                self.input_active = False
                return True
            if not self.tutorial_active and self.input_active:
                if event.key == pygame.K_RETURN:
                    self.send_question(self.input_text)
                elif event.key == pygame.K_BACKSPACE:
                    self.input_text = self.input_text[:-1]
                else:
                    char = getattr(event, "unicode", "")
                    if char and char.isprintable() and len(self.input_text) < NEKO_AI_MAX_QUESTION_LENGTH:
                        self.input_text += char
                return True
        return False

    def handle_tutorial_action(self, action):
        if action == "back":
            self.tutorial_step = max(0, self.tutorial_step - 1)
        elif action == "next":
            self.tutorial_step = min(len(NEKO_TUTORIAL_STEPS) - 1, self.tutorial_step + 1)
        elif action in {"skip", "finish"}:
            self.tutorial_active = False
            self.mark_tutorial_seen()
            self.add_message(
                "assistant",
                "Xong rồi nhé. Khi cần xem lại, bấm câu hỏi nhanh Hướng dẫn cách chơi.",
            )

    def start_tutorial(self):
        self.visible = True
        self.tutorial_active = True
        self.tutorial_step = 0
        self.error_message = ""

    def update(self):
        self.ensure_intro()
        if self.request_future is None or not self.request_future.done():
            return
        try:
            data = self.request_future.result()
            reply = str(data.get("reply") or "").strip()
            if not reply:
                raise ValueError("empty AI reply")
            self.add_message("assistant", reply)
            self.error_message = ""
        except Exception:
            self.add_message("assistant", self.build_client_fallback(self.pending_question))
            self.error_message = "Chưa kết nối được backend AI; Neko đang dùng gợi ý cơ bản."
        finally:
            self.request_future = None
            self.pending_question = ""
            self.is_loading = False

    def send_question(self, question):
        clean_question = question.strip()
        if not clean_question:
            self.error_message = "Bạn nhập câu hỏi cho Neko trước nhé."
            return
        if len(clean_question) > NEKO_AI_MAX_QUESTION_LENGTH:
            self.error_message = "Câu hỏi hơi dài, hãy rút ngắn để Neko trả lời nhanh hơn."
            return
        if self.is_loading:
            return

        self.tutorial_active = False
        self.add_message("user", clean_question)
        self.input_text = ""
        self.error_message = ""
        self.is_loading = True
        self.pending_question = clean_question
        game_state = self.build_game_state(clean_question)
        self.request_future = self.executor.submit(
            self.post_ai_request,
            clean_question,
            game_state,
        )

    def include_game_state(self, question):
        normalized_question = question.casefold()
        keywords = ("bàn", "khối", "đặt", "điểm", "combo", "nước")
        return any(keyword in normalized_question for keyword in keywords)

    def build_game_state(self, question):
        if not self.include_game_state(question):
            return {"score": int(self.game.score)}
        board = [
            [1 if cell is not None else 0 for cell in row[:GRID_SIZE]]
            for row in self.game.grid[:GRID_SIZE]
        ]
        blocks = [
            [[1 if cell else 0 for cell in row] for row in block.shape]
            for block in self.game.available_blocks[:3]
        ]
        return {
            "score": int(self.game.score),
            "board": board,
            "current_blocks": blocks,
            "combo": 0,
        }

    def post_ai_request(self, question, game_state):
        payload = json.dumps(
            {
                "question": question,
                "game_state": game_state,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.game.access_token:
            headers["Authorization"] = f"Bearer {self.game.access_token}"
        request = urllib.request.Request(
            f"{self.game.api_base_url}/api/ai-guide/chat",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=14) as response:
            return json.loads(response.read().decode("utf-8"))

    def build_client_fallback(self, question):
        normalized_question = (question or "").casefold()
        if "hướng dẫn" in normalized_question or "cách chơi" in normalized_question:
            return (
                "Phản hồi hướng dẫn cơ bản: kéo khối vào ô trống, lấp đầy hàng/cột "
                "để xóa và ghi điểm. Không còn chỗ đặt khối thì ván kết thúc."
            )
        if "đặt" in normalized_question or "phân tích" in normalized_question:
            return (
                "Phản hồi hướng dẫn cơ bản: đây chỉ là gợi ý, hãy ưu tiên đặt khối "
                "lớn trước và giữ nhiều ô trống liền nhau ở giữa bàn."
            )
        return (
            "Phản hồi hướng dẫn cơ bản: meo meo, hãy giữ bàn thoáng và chuẩn bị "
            "xóa nhiều hàng/cột cùng lúc để được nhiều điểm hơn."
        )


class Game:
    def __init__(
        self,
        player_name=None,
        online_match=False,
        match_id=None,
        api_base_url="http://127.0.0.1:8000",
        access_token=None,
        start_in_play=None,
        embedded=False,
    ):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Cute Cat Block Blast (Multiplayer Edition)")
        self.clock = pygame.time.Clock()
        self.embedded = bool(embedded)
        self.running = True

        # Biến trạng thái
        player_name = (player_name or "").strip()[:20]
        has_player_name = bool(player_name)
        self.skip_login = (
            has_player_name
            if start_in_play is None
            else bool(start_in_play and has_player_name)
        )
        self.state = STATE_PLAY if self.skip_login else STATE_LOGIN
        self.player_name = player_name
        self.input_active = not self.skip_login
        self.leaderboard_data = self.load_leaderboard()
        self.online_mode = bool(online_match)
        self.match_id = match_id
        self.api_base_url = api_base_url.rstrip("/")
        self.access_token = access_token or os.environ.get("NEKO_ACCESS_TOKEN", "")
        self.online_match_state = None
        self.online_remaining_seconds = 0
        self.online_server_score = 0
        self.online_opponent_score = 0
        self.online_result = None
        self.online_finished = False
        self.online_connection_lost = False
        self.online_reconnecting = False
        self.online_connection_error = "Mất kết nối server"
        self.connection_fail_count = 0
        self.online_user_id = None
        self.online_poll_interval = 2500
        self.last_online_poll = -self.online_poll_interval
        self.online_poll_executor = (
            ThreadPoolExecutor(max_workers=1) if self.online_mode else None
        )
        self.online_poll_future = None
        self.last_submitted_score = None
        if self.online_mode:
            self.skip_login = True
            self.state = STATE_PLAY
            self.input_active = False

        self.cat_surprise = SurpriseCat(max_size=420)
        self.happy_popup = HappyCatPopup()
        self.load_sounds()
        self.reset_game()
        self.neko_ai = NekoAIGuide(self)

    # --- CÁC HÀM XỬ LÝ LEADERBOARD ---
    def load_leaderboard(self):
        """Tải dữ liệu bảng xếp hạng từ file JSON"""
        leaderboard_path = os.path.join(BASE_DIR, "leaderboard.json")
        if not os.path.exists(leaderboard_path):
            return []

        try:
            with open(leaderboard_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            return []

        if not isinstance(data, list):
            return []

        merged = {}
        for item in data:
            if not isinstance(item, dict):
                continue

            name = str(item.get("name", "")).strip()
            if not name:
                continue

            try:
                score = int(item.get("score", 0))
            except (TypeError, ValueError):
                continue

            key = name.casefold()
            if key not in merged or score > merged[key]["score"]:
                merged[key] = {"name": name, "score": score}

        return sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:100]

    def save_leaderboard(self):
        """Lưu điểm người chơi hiện tại vào file JSON"""
        if self.score > 0 and self.player_name.strip() != "":
            self.leaderboard_data = self.load_leaderboard()
            player_name = self.player_name.strip()
            player_key = player_name.casefold()
            found_player = False

            for entry in self.leaderboard_data:
                entry_name = str(entry.get("name", "")).strip()
                if entry_name.casefold() == player_key:
                    found_player = True
                    if self.score > int(entry.get("score", 0)):
                        entry["name"] = player_name
                        entry["score"] = self.score
                    break

            if not found_player:
                self.leaderboard_data.append({
                    "name": player_name,
                    "score": self.score
                })

            # Sắp xếp lại từ cao xuống thấp
            self.leaderboard_data = sorted(self.leaderboard_data, key=lambda x: x["score"], reverse=True)
            # Chỉ giữ lại top 100 để file không bị quá nặng
            self.leaderboard_data = self.leaderboard_data[:100]

            leaderboard_path = os.path.join(BASE_DIR, "leaderboard.json")
            with open(leaderboard_path, "w", encoding="utf-8") as f:
                json.dump(self.leaderboard_data, f, ensure_ascii=False, indent=4)

    # --- TẢI ÂM THANH & HÌNH ẢNH ---
    def load_sounds(self):
        def get_sound(file_name):
            try:
                return pygame.mixer.Sound(os.path.join(BASE_DIR, file_name))
            except Exception as e:
                return None

        self.snd_drop = get_sound("drop.mp3")
        self.snd_clear = get_sound("clear.mp3")
        self.snd_happy = get_sound("happy.mp3")
        self.snd_gameover = get_sound("gameover.mp3")
        self.snd_jumpscare = get_sound("kinhdi.mp3")
        self.match_music_path = os.path.join(BASE_DIR, "bgm.mp3")

        self.is_jumpscare = False
        self.jumpscare_done = False
        try:
            raw_img = pygame.image.load(os.path.join(BASE_DIR, "kinhdi.jpg")).convert()
            self.jumpscare_img = pygame.transform.scale(raw_img, (WIDTH, HEIGHT))
        except:
            self.jumpscare_img = None

        self.start_match_audio()

    def start_match_audio(self):
        play_match_music(self.match_music_path)

    def stop_match_audio(self):
        stop_match_audio()

    # --- KHỞI TẠO LẠI BÀN CHƠI ---
    def reset_game(self):
        self.grid = [[None for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.score = 0
        self.milestones = [100, 300, 500, 1000, 1500, 2000, 3000, 5000, 10000]
        self.available_blocks = []
        self.dragging_block = None
        self.game_over = False
        self.particles = []
        self.spawn_blocks()

        if hasattr(self, 'cat_surprise'):
            self.cat_surprise.triggered = False
            self.cat_surprise.active = False
            self.cat_surprise.state = 'idle'

            if not self.is_jumpscare:
                self.start_match_audio()

    # --- LOGIC GAME CHÍNH ---
    def spawn_blocks(self):
        self.available_blocks = []
        for i in range(3):
            shape = random.choice(SHAPES)
            color = random.choice(BLOCK_COLORS)
            self.available_blocks.append(Block(shape, color, i))

    def can_place(self, block, grid_r, grid_c):
        if grid_r < 0 or grid_c < 0 or grid_r + block.rows > GRID_SIZE or grid_c + block.cols > GRID_SIZE: return False
        for r in range(block.rows):
            for c in range(block.cols):
                if block.shape[r][c] == 1 and self.grid[grid_r + r][grid_c + c] is not None: return False
        return True

    def place_block(self, block, grid_r, grid_c):
        cells_count = 0
        for r in range(block.rows):
            for c in range(block.cols):
                if block.shape[r][c] == 1:
                    self.grid[grid_r + r][grid_c + c] = 'CAT'
                    cells_count += 1
        self.score += cells_count * 10

        if self.snd_drop: self.snd_drop.play()

        self.available_blocks.remove(block)
        if len(self.available_blocks) == 0: self.spawn_blocks()
        self.check_lines()

        if self.milestones and self.score >= self.milestones[0]:
            self.happy_popup.trigger()
            if self.snd_happy: self.snd_happy.play()
            while self.milestones and self.score >= self.milestones[0]:
                self.milestones.pop(0)

        # BẪY TROLL 10K ĐIỂM
        if self.score >= 10000 and not self.jumpscare_done:
            self.is_jumpscare = True
            self.jumpscare_done = True
            self.stop_match_audio()
            if self.snd_jumpscare: self.snd_jumpscare.play()

        self.check_game_over()

    def check_lines(self):
        rows_to_clear = [r for r in range(GRID_SIZE) if all(self.grid[r][c] is not None for c in range(GRID_SIZE))]
        cols_to_clear = [c for c in range(GRID_SIZE) if all(self.grid[r][c] is not None for r in range(GRID_SIZE))]
        if not rows_to_clear and not cols_to_clear: return

        lines_cleared = len(rows_to_clear) + len(cols_to_clear)
        self.score += lines_cleared * 100 + (lines_cleared - 1) * 50

        if self.snd_clear: self.snd_clear.play()

        cells_to_anim = set()
        for r in rows_to_clear:
            for c in range(GRID_SIZE): cells_to_anim.add((r, c))
        for c in cols_to_clear:
            for r in range(GRID_SIZE): cells_to_anim.add((r, c))

        for r, c in cells_to_anim:
            if self.grid[r][c] is not None:
                center_x = GRID_OFFSET_X + c * (CELL_SIZE + PADDING) + CELL_SIZE // 2
                center_y = GRID_OFFSET_Y + r * (CELL_SIZE + PADDING) + CELL_SIZE // 2
                for _ in range(12):
                    self.particles.append(Particle(center_x, center_y, random.choice(BLOCK_COLORS)))
                self.grid[r][c] = None

    def check_game_over(self):
        if not self.available_blocks: return
        for block in self.available_blocks:
            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    if self.can_place(block, r, c): return

        self.game_over = True
        self.stop_match_audio()
        if self.online_mode:
            return
        self.save_leaderboard()  # CHẾT LÀ LƯU ĐIỂM NGAY!

        if hasattr(self, 'cat_surprise'):
            self.cat_surprise.trigger()
            if self.snd_gameover: self.snd_gameover.play()

    def request_exit(self):
        self.stop_match_audio()
        if hasattr(self, "neko_ai"):
            self.neko_ai.shutdown()
        if self.online_poll_executor:
            self.online_poll_executor.shutdown(wait=False, cancel_futures=True)
            self.online_poll_executor = None
        if self.embedded:
            self.running = False
            return
        pygame.quit()
        sys.exit()

    # --- XỬ LÝ SỰ KIỆN CHUỘT / PHÍM ---
    def handle_events(self):
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.request_exit()
                return

            if self.online_mode and event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.request_exit()
                return

            # NẾU ĐANG Ở MÀN HÌNH ĐĂNG NHẬP
            if self.state == STATE_LOGIN:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    # Bấm vào input box
                    input_rect = pygame.Rect(WIDTH // 2 - 150, HEIGHT // 2 - 25, 300, 50)
                    if input_rect.collidepoint(event.pos):
                        self.input_active = True
                    else:
                        self.input_active = False

                if event.type == pygame.KEYDOWN and self.input_active:
                    if event.key == pygame.K_RETURN:
                        if self.player_name.strip() != "":
                            self.state = STATE_PLAY  # Vào game
                    elif event.key == pygame.K_BACKSPACE:
                        self.player_name = self.player_name[:-1]
                    else:
                        # Giới hạn độ dài tên
                        if len(self.player_name) < 20:
                            self.player_name += event.unicode
                continue

            # NẾU ĐANG Ở BẢNG XẾP HẠNG
            if self.state == STATE_LEADERBOARD:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        self.state = STATE_PLAY
                        self.reset_game()
                    elif event.key == pygame.K_ESCAPE:
                        self.request_exit()
                        return
                continue

            # NẾU ĐANG TRONG TRẬN GAME (VÀ ĐÃ GAME OVER)
            if self.state == STATE_PLAY and self.neko_ai.handle_event(event):
                continue

            if self.state == STATE_PLAY and self.game_over:
                if not self.online_mode and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        self.stop_match_audio()
                        self.state = STATE_LEADERBOARD
                    elif event.key == pygame.K_ESCAPE:
                        self.request_exit()
                        return
                continue

            # NẾU ĐANG TRONG TRẬN GAME (BÌNH THƯỜNG)
            if (
                self.state == STATE_PLAY
                and not self.dragging_block
                and not self.online_finished
            ):
                for block in self.available_blocks:
                    block.is_hovered = block.get_rect().collidepoint(mouse_pos)

            if (
                self.state == STATE_PLAY
                and not self.online_finished
                and not self.game_over
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
            ):
                for block in reversed(self.available_blocks):
                    if block.get_rect().collidepoint(mouse_pos):
                        block.is_dragging = True;
                        block.is_hovered = False
                        self.dragging_block = block
                        break
            elif self.state == STATE_PLAY and event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if self.dragging_block:
                    center_x = self.dragging_block.x + self.dragging_block.width // 2
                    center_y = self.dragging_block.y + self.dragging_block.height // 2
                    tl_x = center_x - self.dragging_block.cols * CELL_SIZE // 2
                    tl_y = center_y - self.dragging_block.rows * CELL_SIZE // 2
                    grid_c = round((tl_x - GRID_OFFSET_X) / (CELL_SIZE + PADDING))
                    grid_r = round((tl_y - GRID_OFFSET_Y) / (CELL_SIZE + PADDING))
                    if self.can_place(self.dragging_block, grid_r, grid_c):
                        self.place_block(self.dragging_block, grid_r, grid_c)
                    else:
                        self.dragging_block.reset_pos()
                    self.dragging_block.is_dragging = False;
                    self.dragging_block = None
            elif self.state == STATE_PLAY and event.type == pygame.MOUSEMOTION:
                if self.dragging_block:
                    self.dragging_block.x = mouse_pos[0] - self.dragging_block.width // 2
                    self.dragging_block.y = mouse_pos[1] - self.dragging_block.height // 2

    # --- CÁC HÀM VẼ GIAO DIỆN ---
    def draw_login_screen(self):
        self.screen.fill(PASTEL_BG)

        # Tiêu đề
        title = font_vn_large.render("NEKO BLOCK BLAST", True, PASTEL_TEXT)
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, HEIGHT // 2 - 150))

        subtitle = font_login_vn_medium.render("Nhập họ tên hoặc nickname", True, PASTEL_TEXT)
        self.screen.blit(subtitle, (WIDTH // 2 - subtitle.get_width() // 2, HEIGHT // 2 - 70))

        # Khung nhập tên
        input_rect = pygame.Rect(WIDTH // 2 - 150, HEIGHT // 2 - 25, 300, 50)
        color = INPUT_BOX_ACTIVE if self.input_active else INPUT_BOX_COLOR
        pygame.draw.rect(self.screen, color, input_rect, border_radius=10)
        pygame.draw.rect(self.screen, PASTEL_TEXT, input_rect, 3, border_radius=10)

        # Render chữ đang nhập (hiệu ứng nhấp nháy con trỏ)
        display_text = self.player_name
        if self.input_active and pygame.time.get_ticks() % 1000 < 500:
            display_text += "|"

        txt_surface = font_login_vn_medium.render(display_text, True, PASTEL_TEXT)
        self.screen.blit(txt_surface, (input_rect.x + 10, input_rect.y + 5))

        # Nút hướng dẫn
        if self.player_name.strip() != "":
            hint = font_login_vn_small.render("Nhấn ENTER để bắt đầu!", True, (100, 200, 100))
            self.screen.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT // 2 + 50))

    def draw_leaderboard_screen(self):
        self.screen.fill(PASTEL_BG)

        title = font_vn_large.render("🏆 BẢNG XẾP HẠNG 🏆", True, (255, 150, 50))
        self.screen.blit(title, (WIDTH // 2 - title.get_width() // 2, 50))

        # Khung nền xếp hạng
        board_rect = pygame.Rect(WIDTH // 2 - 250, 130, 500, 400)
        pygame.draw.rect(self.screen, PASTEL_GRID_EMPTY, board_rect, border_radius=20)

        if not self.leaderboard_data:
            empty_txt = font_vn_medium.render("Chưa có ai chơi! Hãy là người đầu tiên!", True, PASTEL_TEXT)
            self.screen.blit(empty_txt, (WIDTH // 2 - empty_txt.get_width() // 2, HEIGHT // 2))
        else:
            # Hiển thị Top 7 người cao nhất
            for i, data in enumerate(self.leaderboard_data[:7]):
                rank_text = f"#{i + 1}"
                name_text = data['name'][:15]
                score_text = f"{data['score']} pt"

                # Highlight người chơi hiện tại vừa mới chơi xong
                is_current_player = (data['name'] == self.player_name and data['score'] == self.score)
                text_color = (255, 100, 100) if is_current_player else PASTEL_TEXT

                rank_surf = font_vn_medium.render(rank_text, True, text_color)
                name_surf = font_vn_medium.render(name_text, True, text_color)
                score_surf = font_vn_medium.render(score_text, True, text_color)

                y_pos = 150 + i * 50
                self.screen.blit(rank_surf, (WIDTH // 2 - 220, y_pos))
                self.screen.blit(name_surf, (WIDTH // 2 - 120, y_pos))
                self.screen.blit(score_surf, (WIDTH // 2 + 100, y_pos))

        replay_hint = font_login_vn_small.render(
            "Nhấn ENTER để chơi lại", True, PASTEL_TEXT
        )
        exit_hint = font_login_vn_small.render(
            "Nhấn ESC để quay lại menu", True, PASTEL_TEXT
        )
        self.screen.blit(
            replay_hint,
            replay_hint.get_rect(center=(WIDTH // 2, HEIGHT - 72)),
        )
        self.screen.blit(
            exit_hint,
            exit_hint.get_rect(center=(WIDTH // 2, HEIGHT - 40)),
        )

    def draw_grid(self):
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                rect_x = GRID_OFFSET_X + c * (CELL_SIZE + PADDING);
                rect_y = GRID_OFFSET_Y + r * (CELL_SIZE + PADDING)
                rect = pygame.Rect(rect_x, rect_y, CELL_SIZE, CELL_SIZE)
                pygame.draw.rect(self.screen, PASTEL_GRID_EMPTY, rect, border_radius=8)
                if self.grid[r][c] == 'CAT': self.screen.blit(Block._cat_base_surface, rect.topleft)

    def draw_animations(self):
        for p in self.particles[:]:
            p.update()
            if p.life <= 0:
                self.particles.remove(p)
            else:
                p.draw(self.screen)

    def draw_preview(self):
        if self.dragging_block:
            center_x = self.dragging_block.x + self.dragging_block.width // 2
            center_y = self.dragging_block.y + self.dragging_block.height // 2
            tl_x = center_x - self.dragging_block.cols * CELL_SIZE // 2
            tl_y = center_y - self.dragging_block.rows * CELL_SIZE // 2
            grid_c = round((tl_x - GRID_OFFSET_X) / (CELL_SIZE + PADDING))
            grid_r = round((tl_y - GRID_OFFSET_Y) / (CELL_SIZE + PADDING))
            if self.can_place(self.dragging_block, grid_r, grid_c):
                preview_x = GRID_OFFSET_X + grid_c * (CELL_SIZE + PADDING)
                preview_y = GRID_OFFSET_Y + grid_r * (CELL_SIZE + PADDING)
                self.dragging_block.draw(self.screen, is_preview=True, pos=(preview_x, preview_y))

    def draw_ui(self):
        title_text = font_medium.render("Neko Block Blast", True, PASTEL_TEXT)
        self.screen.blit(title_text, (GRID_OFFSET_X, 30))

        if self.online_mode:
            score_bg_rect = pygame.Rect(PANEL_X, 8, PANEL_WIDTH - 20, 112)
            pygame.draw.rect(
                self.screen, PASTEL_GRID_EMPTY, score_bg_rect, border_radius=15
            )

            opponent_name = "Đang chờ"
            for player in (self.online_match_state or {}).get("players", []):
                if player.get("user_id") != self.online_user_id:
                    opponent_name = player.get("display_name", opponent_name)
                    break

            def shorten_name(name, limit=13):
                clean_name = str(name).strip()
                if len(clean_name) <= limit:
                    return clean_name
                return f"{clean_name[:limit - 3].rstrip()}..."

            rows = [
                ("Người chơi:", shorten_name(self.player_name)),
                ("Thời gian:", f"{self.online_remaining_seconds}s"),
                ("Điểm của bạn:", str(self.score)),
                (
                    "Đối thủ:",
                    f"{shorten_name(opponent_name)} - "
                    f"{self.online_opponent_score} điểm",
                ),
            ]
            row_height = 27
            for index, (label_text, value_text) in enumerate(rows):
                row_y = score_bg_rect.y + 4 + index * row_height
                label = font_online_label.render(label_text, True, PASTEL_TEXT)
                value = font_online_value.render(value_text, True, PASTEL_TEXT)
                self.screen.blit(label, (score_bg_rect.x + 12, row_y))
                self.screen.blit(value, (score_bg_rect.x + 12, row_y + 12))
        else:
            # Giữ nguyên panel của chế độ chơi đơn.
            score_bg_rect = pygame.Rect(PANEL_X, 30, PANEL_WIDTH - 20, 100)
            pygame.draw.rect(
                self.screen, PASTEL_GRID_EMPTY, score_bg_rect, border_radius=15
            )
            name_text = font_vn_small.render(
                f"Người chơi: {self.player_name}", True, PASTEL_TEXT
            )
            self.screen.blit(name_text, (PANEL_X + 20, 40))
            score_val = font_large.render(str(self.score), True, PASTEL_TEXT)
            self.screen.blit(score_val, (PANEL_X + 20, 65))

        hint_text = font_vn_small.render("Kéo Mèo Vào Lưới!", True, PASTEL_TEXT)
        hint_rect = hint_text.get_rect(center=(PANEL_X + PANEL_WIDTH // 2, HEIGHT - 30))
        self.screen.blit(hint_text, hint_rect)

        if self.online_mode and self.online_reconnecting:
            reconnect_text = font_online_value.render(
                "Đang kết nối lại server...", True, PASTEL_ACCENT_DARK
            )
            self.screen.blit(reconnect_text, (GRID_OFFSET_X, 67))

    def draw_game_over(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 170))
        self.screen.blit(overlay, (0, 0))

        go_title = font_login_vn_medium.render(
            "Mèo hết chỗ nằm!", True, (255, 80, 80)
        )
        self.cat_surprise.draw(self.screen)

        grid_center_x = GRID_OFFSET_X + (GRID_SIZE * (CELL_SIZE + PADDING)) // 2
        grid_center_y = GRID_OFFSET_Y + (GRID_SIZE * (CELL_SIZE + PADDING)) // 2
        draw_y = grid_center_y - self.cat_surprise.current_size // 2

        self.screen.blit(go_title, (grid_center_x - go_title.get_width() // 2, draw_y + 10))
        comfort_text = font_login_vn_small.render(
            "Đừng buồn, thử lại nhé!", True, (255, 220, 220)
        )
        self.screen.blit(
            comfort_text,
            comfort_text.get_rect(center=(grid_center_x, draw_y + 52)),
        )

        score_desc = font_login_vn_small.render(
            f"Điểm của {self.player_name}: {self.score}",
            True,
            (255, 255, 255),
        )
        score_desc_rect = score_desc.get_rect(
            center=(grid_center_x, draw_y + self.cat_surprise.current_size + 16)
        )
        self.screen.blit(score_desc, score_desc_rect)

        leaderboard_hint = font_login_vn_small.render(
            "Nhấn ENTER để xem bảng xếp hạng", True, (220, 220, 220)
        )
        exit_hint = font_login_vn_small.render(
            "Nhấn ESC để quay lại menu", True, (220, 220, 220)
        )
        hint_y = draw_y + self.cat_surprise.current_size + 45
        self.screen.blit(
            leaderboard_hint,
            leaderboard_hint.get_rect(center=(grid_center_x, hint_y)),
        )
        self.screen.blit(
            exit_hint,
            exit_hint.get_rect(center=(grid_center_x, hint_y + 28)),
        )

    def online_request(self, path, method="GET", payload=None):
        headers = {"Authorization": f"Bearer {self.access_token}"}
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.api_base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def update_online_state(self, match_state):
        self.online_match_state = match_state
        self.online_remaining_seconds = match_state.get("remaining_seconds", 0)
        players = match_state.get("players", [])

        my_player = next(
            (
                player
                for player in players
                if player.get("user_id") == self.online_user_id
            ),
            None,
        )
        opponent = next(
            (
                player
                for player in players
                if player.get("user_id") != self.online_user_id
            ),
            None,
        )
        if opponent:
            self.online_opponent_score = opponent.get("score", 0)
        if my_player:
            self.online_server_score = my_player.get("score", 0)
        if match_state.get("status") in {"finished", "cancelled", "abandoned"}:
            self.online_finished = True
            self.online_result = (
                "cancelled"
                if match_state.get("status") != "finished"
                else my_player.get("result") if my_player else "draw"
            )
            self.stop_match_audio()
            if self.dragging_block:
                self.dragging_block.reset_pos()
                self.dragging_block.is_dragging = False
                self.dragging_block = None

    def fetch_online_update(self, score, should_submit_score):
        if should_submit_score:
            try:
                self.online_request(
                    f"/matches/{self.match_id}/score",
                    method="POST",
                    payload={"score": score},
                )
            except urllib.error.HTTPError as error:
                if error.code != 409:
                    raise
        match_state = self.online_request(f"/matches/{self.match_id}")
        user_id = self.online_user_id
        if user_id is None:
            me = self.online_request("/auth/me")
            user_id = me.get("id")
        return match_state, user_id, score if should_submit_score else None

    def handle_online_poll_error(self, error):
        if isinstance(error, urllib.error.HTTPError):
            if error.code == 401:
                self.online_connection_error = "Phiên đăng nhập hết hạn"
                self.online_connection_lost = True
                self.online_reconnecting = False
                self.stop_match_audio()
                return
            if error.code == 404:
                self.online_connection_error = "Không tìm thấy trận đấu"
                self.online_connection_lost = True
                self.online_reconnecting = False
                self.stop_match_audio()
                return
        self.register_online_connection_failure()

    def poll_online_match(self):
        if not self.online_mode or self.online_finished or self.online_connection_lost:
            return

        if self.online_poll_future is not None:
            if not self.online_poll_future.done():
                return
            try:
                match_state, user_id, submitted_score = (
                    self.online_poll_future.result()
                )
            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                OSError,
                ValueError,
            ) as error:
                self.handle_online_poll_error(error)
            except Exception as error:
                self.handle_online_poll_error(error)
            else:
                self.online_user_id = user_id
                if submitted_score is not None:
                    self.last_submitted_score = submitted_score
                self.online_connection_lost = False
                self.online_reconnecting = False
                self.connection_fail_count = 0
                self.update_online_state(match_state)
            finally:
                self.online_poll_future = None
            return

        now = pygame.time.get_ticks()
        if now - self.last_online_poll < self.online_poll_interval:
            return
        self.last_online_poll = now
        should_submit_score = self.score != self.last_submitted_score
        self.online_poll_future = self.online_poll_executor.submit(
            self.fetch_online_update,
            self.score,
            should_submit_score,
        )

    def register_online_connection_failure(self):
        self.connection_fail_count += 1
        self.online_reconnecting = True
        if self.connection_fail_count >= 8:
            self.online_connection_error = "Mất kết nối server"
            self.online_connection_lost = True
            self.online_reconnecting = False
            self.stop_match_audio()
            if self.dragging_block:
                self.dragging_block.reset_pos()
                self.dragging_block.is_dragging = False
                self.dragging_block = None

    def draw_online_overlay(self):
        if not self.online_finished and not self.online_connection_lost:
            return
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 175))
        self.screen.blit(overlay, (0, 0))

        if self.online_connection_lost:
            title_text = self.online_connection_error
            detail_text = "Nhấn ESC để thoát"
        else:
            result_labels = {
                "win": "Thắng",
                "lose": "Thua",
                "draw": "Hòa",
                "cancelled": "Trận đã hủy",
            }
            title_text = result_labels.get(self.online_result, "Hòa")
            detail_text = (
                f"Điểm của bạn: {self.online_server_score}    "
                f"Điểm đối thủ: {self.online_opponent_score}"
            )
        title = font_online_overlay_title.render(title_text, True, (255, 255, 255))
        detail = font_online_overlay_text.render(detail_text, True, (255, 255, 255))
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 280)))
        self.screen.blit(detail, detail.get_rect(center=(WIDTH // 2, 335)))
        if not self.online_connection_lost:
            exit_hint = font_online_overlay_text.render(
                "Nhấn ESC để thoát", True, (220, 220, 220)
            )
            self.screen.blit(
                exit_hint, exit_hint.get_rect(center=(WIDTH // 2, 380))
            )

    # --- VÒNG LẶP CHÍNH ---
    def run(self):
        try:
            self._run_loop()
        finally:
            self.stop_match_audio()

    def _run_loop(self):
        while self.running:
            self.poll_online_match()
            # ================= BẪY JUMPSCARE CHẶN ĐỨNG TRÒ CHƠI =================
            if hasattr(self, 'is_jumpscare') and self.is_jumpscare:
                if self.jumpscare_img:
                    self.screen.blit(self.jumpscare_img, (0, 0))
                else:
                    self.screen.fill((0, 0, 0))
                pygame.display.flip()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.request_exit()
                        break
                self.clock.tick(FPS)
                continue
            # ====================================================================

            self.handle_events()
            if not self.running:
                break

            if self.state == STATE_LOGIN:
                self.draw_login_screen()

            elif self.state == STATE_LEADERBOARD:
                self.draw_leaderboard_screen()

            elif self.state == STATE_PLAY:
                self.cat_surprise.update()
                self.happy_popup.update()
                self.neko_ai.update()

                self.screen.fill(PASTEL_BG)
                self.draw_grid()
                self.draw_animations()
                self.draw_preview()
                self.draw_ui()

                for block in self.available_blocks:
                    if block != self.dragging_block: block.draw(self.screen)
                if self.dragging_block: self.dragging_block.draw(self.screen)

                if self.game_over and not self.online_mode:
                    self.draw_game_over()
                else:
                    self.cat_surprise.draw(self.screen)
                    self.happy_popup.draw(self.screen)
                if self.online_mode:
                    self.draw_online_overlay()
                self.neko_ai.draw(self.screen)

            pygame.display.flip()
            self.clock.tick(FPS)


def run_game(
    player_name=None,
    online_match=False,
    match_id=None,
    api_base_url="http://127.0.0.1:8000",
    access_token=None,
    start_in_play=None,
    embedded=False,
):
    normalized_player_name = (player_name or "").strip()[:20]
    if start_in_play is None:
        start_in_play = bool(normalized_player_name)
    try:
        game = Game(
            player_name=normalized_player_name,
            online_match=online_match,
            match_id=match_id,
            api_base_url=api_base_url,
            access_token=access_token,
            start_in_play=start_in_play,
            embedded=embedded,
        )
        game.run()
    finally:
        stop_match_audio()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--player-name", default="")
    parser.add_argument("--online-match", action="store_true")
    parser.add_argument("--match-id", type=int)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    run_game(
        player_name=args.player_name,
        online_match=args.online_match,
        match_id=args.match_id,
        api_base_url=args.api_base_url,
    )
