import json
import logging
import math
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pygame

from client_audio import stop_match_audio
from client_api import (
    API_BASE_URL,
    ApiError,
    create_room,
    forgot_password,
    get_active_match,
    get_current_user,
    get_room,
    join_room,
    leave_room,
    login,
    register,
    reset_password,
    start_room,
    toggle_ready,
)


pygame.init()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_LOG_PATH = os.path.join(os.getcwd(), "neko_client.log")
LOGGER = logging.getLogger("neko_client")
if not LOGGER.handlers:
    handler = logging.FileHandler(CLIENT_LOG_PATH, encoding="utf-8", delay=True)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)

WIDTH, HEIGHT = 850, 650
FPS = 60

PASTEL_BG = (255, 250, 240)
PASTEL_GRID_EMPTY = (240, 230, 220)
PASTEL_TEXT = (100, 80, 70)
PASTEL_ACCENT = (255, 182, 193)
PASTEL_ACCENT_DARK = (230, 135, 155)
PASTEL_BUTTON = (255, 245, 235)
PASTEL_SHADOW = (220, 205, 190)
WHITE = (255, 255, 255)

STATE_MENU = "MENU"
STATE_NAME_INPUT = "NAME_INPUT"
STATE_ONLINE = "ONLINE"
STATE_LOGIN = "LOGIN"
STATE_REGISTER = "REGISTER"
STATE_FORGOT_PASSWORD = "FORGOT_PASSWORD"
STATE_RESET_PASSWORD = "RESET_PASSWORD"
STATE_ONLINE_LOBBY = "ONLINE_LOBBY"
STATE_ROOM_MODE = "ROOM_MODE"
STATE_ROOM_JOIN = "ROOM_JOIN"
STATE_ROOM_WAITING = "ROOM_WAITING"
STATE_LEADERBOARD = "LEADERBOARD"


def get_font(size, bold=False):
    font_path = pygame.font.match_font("comicsansms")
    if not font_path:
        font_path = pygame.font.match_font("segoeui")
    if not font_path:
        font_path = pygame.font.match_font("arial")

    if font_path:
        font = pygame.font.Font(font_path, size)
        font.set_bold(bold)
        return font

    return pygame.font.SysFont("arial", size, bold=bold)


def get_vietnamese_font(size):
    for font_path in (
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
    ):
        if os.path.exists(font_path):
            return pygame.font.Font(font_path, size)

    return pygame.font.SysFont("Arial", size, bold=True)


FONT_TITLE = get_font(52, True)
FONT_VIETNAMESE_TITLE = get_vietnamese_font(52)
FONT_BUTTON = get_vietnamese_font(30)
FONT_MEDIUM = get_vietnamese_font(28)
FONT_SMALL = get_vietnamese_font(22)
FONT_VIETNAMESE_TINY = get_vietnamese_font(18)
FONT_NEKO_LOBBY_TITLE = get_vietnamese_font(16)
FONT_NEKO_LOBBY_TEXT = get_vietnamese_font(13)
FONT_NEKO_LOBBY_TINY = get_vietnamese_font(11)
FONT_NEKO_LOBBY_BUTTON = get_vietnamese_font(12)

LOBBY_NEKO_MAX_QUESTION_LENGTH = 320
LOBBY_NEKO_QUICK_QUESTIONS = [
    "Hướng dẫn cách chơi",
    "Chơi đơn là gì?",
    "Cách vào phòng 1v1",
    "Bảng xếp hạng hoạt động thế nào?",
    "Tôi nên bắt đầu từ đâu?",
]


class Button:
    def __init__(self, text, center, size):
        self.text = text
        self.rect = pygame.Rect(0, 0, size[0], size[1])
        self.rect.center = center

    def draw(self, surface, mouse_pos):
        hovered = self.rect.collidepoint(mouse_pos)
        fill = WHITE if hovered else PASTEL_BUTTON
        border = PASTEL_ACCENT_DARK if hovered else PASTEL_ACCENT
        shadow = self.rect.move(0, 5)

        pygame.draw.rect(surface, PASTEL_SHADOW, shadow, border_radius=14)
        pygame.draw.rect(surface, fill, self.rect, border_radius=14)
        pygame.draw.rect(surface, border, self.rect, 3, border_radius=14)

        text_surf = FONT_BUTTON.render(self.text, True, PASTEL_TEXT)
        surface.blit(text_surf, text_surf.get_rect(center=self.rect.center))

    def is_clicked(self, event):
        return (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


class InputField:
    def __init__(
        self,
        label,
        rect,
        password=False,
        username=False,
        room_code=False,
        digits_only=False,
        max_length=64,
    ):
        self.label = label
        self.rect = pygame.Rect(rect)
        self.password = password
        self.password_visible = False
        self.username = username
        self.room_code = room_code
        self.digits_only = digits_only
        self.max_length = max_length
        self.value = ""
        self.active = False

    def draw(self, surface):
        label = FONT_VIETNAMESE_TINY.render(self.label, True, PASTEL_TEXT)
        surface.blit(label, (self.rect.x, self.rect.y - 24))
        fill = WHITE if self.active else PASTEL_BUTTON
        border = PASTEL_ACCENT_DARK if self.active else PASTEL_ACCENT
        pygame.draw.rect(surface, fill, self.rect, border_radius=10)
        pygame.draw.rect(surface, border, self.rect, 3, border_radius=10)

        shown = (
            "*" * len(self.value)
            if self.password and not self.password_visible
            else self.value
        )
        if self.active and pygame.time.get_ticks() % 1000 < 500:
            shown += "|"
        text = FONT_SMALL.render(shown, True, PASTEL_TEXT)
        surface.blit(text, (self.rect.x + 12, self.rect.y + 9))

    def handle_key(self, event):
        if event.key == pygame.K_BACKSPACE:
            self.value = self.value[:-1]
        elif event.key != pygame.K_RETURN and event.unicode and event.unicode.isprintable():
            if len(self.value) >= self.max_length:
                return
            if self.room_code:
                if not (event.unicode.isascii() and event.unicode.isalnum()):
                    return
                self.value += event.unicode.upper()
                return
            if self.digits_only and not (
                event.unicode.isascii() and event.unicode.isdigit()
            ):
                return
            if self.username and not (
                event.unicode.isascii()
                and (event.unicode.isalnum() or event.unicode == "_")
            ):
                return
            self.value += event.unicode


def is_valid_nickname_char(char):
    return char.isascii() and (char.isalnum() or char in (" ", "_"))


def safe_log_text(value, limit=1200):
    text = "" if value is None else str(value)
    text = re.sub(
        r"(?i)(authorization|access_token|api_key|connection|string|password|secret|sig|token)(['\"]?\s*[:=]\s*)[^,}\s]+",
        r"\1\2[redacted]",
        text,
    )
    if len(text) > limit:
        return f"{text[:limit]}...[truncated]"
    return text


def render_neko_fit(text, color, max_width, start_size=12, min_size=9):
    for size in range(start_size, min_size - 1, -1):
        font = get_vietnamese_font(size)
        surface = font.render(text, True, color)
        if surface.get_width() <= max_width or size == min_size:
            return surface
    return FONT_NEKO_LOBBY_BUTTON.render(text, True, color)


def wrap_neko_text(text, font, max_width):
    lines = []
    for raw_line in str(text).splitlines() or [""]:
        line = ""
        for word in raw_line.split(" "):
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


class CompactNekoButton:
    def __init__(self, button_id, label, rect):
        self.button_id = button_id
        self.label = label
        self.rect = pygame.Rect(rect)

    def draw(self, surface, mouse_pos, enabled=True):
        hovered = enabled and self.rect.collidepoint(mouse_pos)
        fill = WHITE if hovered else PASTEL_BUTTON
        border = PASTEL_ACCENT_DARK if hovered else PASTEL_ACCENT
        text_color = PASTEL_TEXT if enabled else (170, 155, 145)
        if not enabled:
            fill = (242, 234, 228)
            border = (220, 205, 195)

        pygame.draw.rect(surface, fill, self.rect, border_radius=8)
        pygame.draw.rect(surface, border, self.rect, 2, border_radius=8)
        label = render_neko_fit(self.label, text_color, self.rect.width - 10)
        surface.blit(label, label.get_rect(center=self.rect.center))

    def clicked(self, event, enabled=True):
        return (
            enabled
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        )


class LobbyNekoAI:
    def __init__(self, api_base_url):
        self.api_base_url = api_base_url.rstrip("/")
        self.visible = False
        self.input_text = ""
        self.input_active = False
        self.is_loading = False
        self.error_message = ""
        self.pending_question = ""
        self.messages = [
            {
                "role": "assistant",
                "content": "Meo meo! Mình có thể giúp bạn chọn chế độ chơi ở sảnh.",
            }
        ]
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.request_future = None
        self.last_response_source = None
        self.last_used_fallback = None
        self.last_error = None

        self.cat_rect = pygame.Rect(WIDTH - 78, HEIGHT - 76, 62, 62)
        self.panel_rect = pygame.Rect(16, 178, 222, 420)
        self.close_button = None
        self.send_button = None
        self.input_rect = pygame.Rect(0, 0, 1, 1)
        self.quick_buttons = []

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)

    def add_message(self, role, content):
        clean_content = str(content).strip()
        if not clean_content:
            return
        self.messages.append({"role": role, "content": clean_content[:1000]})
        self.messages = self.messages[-10:]

    def calculate_layout(self):
        self.cat_rect = pygame.Rect(WIDTH - 78, HEIGHT - 76, 62, 62)
        self.panel_rect = pygame.Rect(16, 178, 222, 420)
        self.close_button = CompactNekoButton(
            "close",
            "X",
            pygame.Rect(self.panel_rect.right - 34, self.panel_rect.y + 10, 24, 24),
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
            glow = pygame.Surface((rect.width + 16, rect.height + 16), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (255, 200, 220, 105), glow.get_rect())
            surface.blit(glow, (rect.x - 8, rect.y - 8 + bob))

        pygame.draw.lines(
            surface,
            (245, 178, 185),
            False,
            [(cx + 21, cy + 11), (cx + 33, cy + 3), (cx + 30, cy - 7)],
            7,
        )
        pygame.draw.circle(surface, (255, 222, 205), (cx, cy + 8), 24)
        pygame.draw.polygon(
            surface,
            (255, 222, 205),
            [(cx - 22, cy - 10), (cx - 14, cy - 30), (cx - 4, cy - 13)],
        )
        pygame.draw.polygon(
            surface,
            (255, 222, 205),
            [(cx + 22, cy - 10), (cx + 14, cy - 30), (cx + 4, cy - 13)],
        )
        pygame.draw.polygon(
            surface,
            (245, 178, 185),
            [(cx - 17, cy - 13), (cx - 13, cy - 24), (cx - 7, cy - 13)],
        )
        pygame.draw.polygon(
            surface,
            (245, 178, 185),
            [(cx + 17, cy - 13), (cx + 13, cy - 24), (cx + 7, cy - 13)],
        )
        pygame.draw.circle(surface, (255, 182, 193), (cx - 13, cy + 10), 4)
        pygame.draw.circle(surface, (255, 182, 193), (cx + 13, cy + 10), 4)
        if blink:
            pygame.draw.line(surface, PASTEL_TEXT, (cx - 13, cy - 1), (cx - 6, cy - 1), 2)
            pygame.draw.line(surface, PASTEL_TEXT, (cx + 6, cy - 1), (cx + 13, cy - 1), 2)
        else:
            pygame.draw.circle(surface, PASTEL_TEXT, (cx - 10, cy - 2), 3)
            pygame.draw.circle(surface, PASTEL_TEXT, (cx + 10, cy - 2), 3)
        pygame.draw.line(surface, PASTEL_TEXT, (cx - 3, cy + 6), (cx, cy + 9), 2)
        pygame.draw.line(surface, PASTEL_TEXT, (cx + 3, cy + 6), (cx, cy + 9), 2)
        paw_y = cy + 19 + int(math.sin(ticks / 180) * 2)
        pygame.draw.circle(surface, (255, 222, 205), (cx + 19, paw_y), 6)

    def draw_messages(self, surface, area):
        pygame.draw.rect(surface, WHITE, area, border_radius=8)
        pygame.draw.rect(surface, (242, 215, 205), area, 2, border_radius=8)
        items = []
        for message in self.messages[-7:]:
            role = "Bạn" if message["role"] == "user" else "Neko"
            lines = wrap_neko_text(
                f"{role}: {message['content']}",
                FONT_NEKO_LOBBY_TINY,
                area.width - 18,
            )
            if len(lines) > 8:
                lines = lines[:7] + ["..."]
            items.append((message["role"], lines, 12 + len(lines) * 16))

        visible_items = []
        total_height = 0
        for item in reversed(items):
            next_height = total_height + item[2] + 5
            if visible_items and next_height > area.height - 8:
                break
            visible_items.append(item)
            total_height = next_height
        visible_items.reverse()

        y = area.bottom - total_height - 4
        for role, lines, height in visible_items:
            bubble_rect = pygame.Rect(area.x + 6, y, area.width - 12, height)
            fill = (245, 252, 255) if role == "user" else (255, 246, 250)
            pygame.draw.rect(surface, fill, bubble_rect, border_radius=8)
            text_y = bubble_rect.y + 5
            for line in lines:
                text = FONT_NEKO_LOBBY_TINY.render(line, True, PASTEL_TEXT)
                surface.blit(text, (bubble_rect.x + 7, text_y))
                text_y += 16
            y += height + 5

    def draw_quick_questions(self, surface, top_y):
        self.quick_buttons = []
        button_h = 21
        gap = 4
        for index, question in enumerate(LOBBY_NEKO_QUICK_QUESTIONS):
            button = CompactNekoButton(
                f"quick_{index}",
                question,
                pygame.Rect(
                    self.panel_rect.x + 12,
                    top_y + index * (button_h + gap),
                    self.panel_rect.width - 24,
                    button_h,
                ),
            )
            button.draw(surface, pygame.mouse.get_pos(), enabled=not self.is_loading)
            self.quick_buttons.append((button, question))

    def draw_panel(self, surface):
        if not self.visible:
            return

        rect = self.panel_rect
        shadow = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        shadow.fill((140, 100, 90, 34))
        surface.blit(shadow, (rect.x + 4, rect.y + 5))
        pygame.draw.rect(surface, (255, 250, 245), rect, border_radius=8)
        pygame.draw.rect(surface, (235, 180, 170), rect, 2, border_radius=8)

        title = render_neko_fit(
            "Neko AI – Trợ lý sảnh chờ",
            PASTEL_TEXT,
            rect.width - 56,
            start_size=15,
            min_size=10,
        )
        surface.blit(title, (rect.x + 12, rect.y + 14))
        self.close_button.draw(surface, pygame.mouse.get_pos())

        quick_top = rect.bottom - 162
        message_area = pygame.Rect(
            rect.x + 12,
            rect.y + 52,
            rect.width - 24,
            quick_top - rect.y - 62,
        )
        self.draw_messages(surface, message_area)

        status_y = message_area.bottom + 6
        if self.is_loading:
            status = FONT_NEKO_LOBBY_TINY.render(
                "Neko đang nghĩ...", True, PASTEL_ACCENT_DARK
            )
            surface.blit(status, (rect.x + 14, status_y))
        elif self.error_message:
            for line in wrap_neko_text(self.error_message, FONT_NEKO_LOBBY_TINY, rect.width - 28)[:2]:
                status = FONT_NEKO_LOBBY_TINY.render(line, True, (180, 85, 85))
                surface.blit(status, (rect.x + 14, status_y))
                status_y += 15

        self.draw_quick_questions(surface, quick_top)

        self.input_rect = pygame.Rect(rect.x + 12, rect.bottom - 38, rect.width - 78, 28)
        input_fill = WHITE if self.input_active else (255, 247, 242)
        input_border = PASTEL_ACCENT_DARK if self.input_active else (230, 200, 190)
        pygame.draw.rect(surface, input_fill, self.input_rect, border_radius=8)
        pygame.draw.rect(surface, input_border, self.input_rect, 2, border_radius=8)
        shown = self.input_text
        if self.input_active and pygame.time.get_ticks() % 1000 < 500:
            shown += "|"
        if not shown:
            shown = "Hỏi Neko..."
        input_text = render_neko_fit(
            shown,
            (145, 120, 110),
            self.input_rect.width - 14,
            start_size=12,
            min_size=9,
        )
        surface.blit(input_text, (self.input_rect.x + 8, self.input_rect.y + 7))

        self.send_button = CompactNekoButton(
            "send",
            "Gửi",
            pygame.Rect(rect.right - 58, rect.bottom - 38, 46, 28),
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
                return True
            if not self.visible:
                return False
            if self.close_button and self.close_button.clicked(event):
                self.visible = False
                self.input_active = False
                return True
            self.input_active = self.input_rect.collidepoint(event.pos)
            if self.send_button and self.send_button.clicked(
                event,
                enabled=bool(self.input_text.strip()) and not self.is_loading,
            ):
                self.send_question(self.input_text)
                return True
            for button, question in self.quick_buttons:
                if button.clicked(event, enabled=not self.is_loading):
                    self.send_question(question)
                    return True
            return self.panel_rect.collidepoint(event.pos)

        if self.visible and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.visible = False
                self.input_active = False
                return True
            if self.input_active:
                if event.key == pygame.K_RETURN:
                    self.send_question(self.input_text)
                elif event.key == pygame.K_BACKSPACE:
                    self.input_text = self.input_text[:-1]
                else:
                    char = getattr(event, "unicode", "")
                    if (
                        char
                        and char.isprintable()
                        and len(self.input_text) < LOBBY_NEKO_MAX_QUESTION_LENGTH
                    ):
                        self.input_text += char
                return True
        return False

    def build_lobby_question(self, question):
        return (
            "Ngữ cảnh: người chơi đang ở sảnh/menu chính của Neko Block Blast, "
            "chưa vào ván chơi và không có trạng thái bàn chơi. Hãy trả lời theo "
            "ngữ cảnh menu, không phân tích bàn chơi hiện tại. Câu hỏi: "
            f"{question}"
        )

    def send_question(self, question):
        clean_question = question.strip()
        if not clean_question:
            self.error_message = "Bạn nhập câu hỏi cho Neko trước nhé."
            return
        if len(clean_question) > LOBBY_NEKO_MAX_QUESTION_LENGTH:
            self.error_message = "Câu hỏi hơi dài, hãy rút ngắn để Neko trả lời nhanh hơn."
            return
        if self.is_loading:
            return

        self.add_message("user", clean_question)
        self.input_text = ""
        self.error_message = ""
        self.is_loading = True
        self.pending_question = clean_question
        self.request_future = self.executor.submit(
            self.post_ai_request,
            self.build_lobby_question(clean_question),
        )

    def post_ai_request(self, question):
        payload = json.dumps({"question": question}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.api_base_url}/api/ai-guide/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=18) as response:
            return json.loads(response.read().decode("utf-8"))

    def update(self):
        if self.request_future is None or not self.request_future.done():
            return
        try:
            data = self.request_future.result()
            self.last_response_source = data.get("source")
            self.last_used_fallback = data.get("used_fallback")
            self.last_error = data.get("error")
            reply = str(data.get("reply") or "").strip()
            if not reply:
                raise ValueError("empty AI reply")
            self.add_message("assistant", reply)
            self.error_message = ""
        except Exception as exc:
            LOGGER.warning("lobby_neko_ai_failed detail=%s", safe_log_text(exc))
            self.last_response_source = "client_fallback"
            self.last_used_fallback = True
            self.last_error = safe_log_text(exc)
            self.add_message("assistant", self.build_client_fallback(self.pending_question))
            self.error_message = "Neko đang dùng hướng dẫn sảnh cơ bản."
        finally:
            self.request_future = None
            self.pending_question = ""
            self.is_loading = False

    def build_client_fallback(self, question):
        normalized_question = (question or "").casefold()
        if "1v1" in normalized_question or "phòng" in normalized_question:
            return (
                "Phản hồi hướng dẫn cơ bản: vào ĐẤU 1V1 ONLINE, đăng nhập, "
                "rồi tạo phòng hoặc tham gia bằng mã phòng."
            )
        if "chơi đơn" in normalized_question:
            return (
                "Phản hồi hướng dẫn cơ bản: CHƠI ĐƠN là chế độ luyện tập một mình, "
                "kéo khối vào bàn và cố ghi điểm cao nhất."
            )
        if "bảng xếp hạng" in normalized_question:
            return (
                "Phản hồi hướng dẫn cơ bản: bảng xếp hạng lưu điểm tốt nhất để "
                "bạn so sánh thành tích sau mỗi ván."
            )
        return (
            "Phản hồi hướng dẫn cơ bản: nếu mới chơi, hãy bắt đầu với CHƠI ĐƠN, "
            "sau đó đăng nhập để thử phòng 1v1."
        )


class Launcher:
    def __init__(self):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Neko Block Blast - Menu")
        self.clock = pygame.time.Clock()
        self.state = STATE_ONLINE
        self.player_name = ""
        self.name_input_active = True
        self.name_error = ""
        self.buttons = self.create_menu_buttons()
        self.confirm_button = Button("XÁC NHẬN", (WIDTH // 2, HEIGHT // 2 + 90), (240, 58))
        self.back_button = Button("QUAY LẠI", (WIDTH // 2, HEIGHT - 80), (240, 58))

        self.online_buttons = [
            Button("ĐĂNG NHẬP", (WIDTH // 2, 285), (300, 58)),
            Button("ĐĂNG KÝ", (WIDTH // 2, 365), (300, 58)),
            Button("THOÁT", (WIDTH // 2, 445), (300, 58)),
        ]
        self.login_fields = [
            InputField("Tên đăng nhập", (240, 220, 370, 48), username=True),
            InputField("Mật khẩu", (240, 305, 370, 48), password=True),
        ]
        self.register_fields = [
            InputField("Tên đăng nhập", (240, 135, 370, 44), username=True),
            InputField("Tên hiển thị", (240, 215, 370, 44)),
            InputField("Email", (240, 295, 370, 44)),
            InputField("Mật khẩu", (240, 375, 370, 44), password=True),
        ]
        self.login_button = Button("ĐĂNG NHẬP", (WIDTH // 2 - 135, 475), (240, 56))
        self.register_button = Button("ĐĂNG KÝ", (WIDTH // 2 - 135, 490), (240, 56))
        self.form_back_button = Button("QUAY LẠI", (WIDTH // 2 + 135, 475), (240, 56))
        self.forgot_password_button = Button(
            "QUÊN MẬT KHẨU", (WIDTH // 2, 535), (310, 50)
        )
        self.login_password_toggle = Button("HIỆN", (675, 329), (100, 42))
        self.register_password_toggle = Button("HIỆN", (675, 397), (100, 42))
        self.reset_password_toggle = Button("HIỆN", (675, 374), (100, 42))
        self.login_password_visible = False
        self.register_password_visible = False
        self.reset_password_visible = False

        self.forgot_email_field = InputField(
            "Địa chỉ Gmail", (240, 235, 370, 50)
        )
        self.forgot_send_button = Button(
            "GỬI MÃ", (WIDTH // 2 - 135, 365), (240, 56)
        )
        self.forgot_back_button = Button(
            "QUAY LẠI", (WIDTH // 2 + 135, 365), (240, 56)
        )
        self.reset_fields = [
            InputField("Địa chỉ Gmail", (240, 165, 370, 46)),
            InputField(
                "Mã xác thực 6 số",
                (240, 250, 370, 46),
                digits_only=True,
                max_length=6,
            ),
            InputField("Mật khẩu mới", (240, 350, 370, 48), password=True),
        ]
        self.reset_submit_button = Button(
            "ĐỔI MẬT KHẨU", (WIDTH // 2 - 135, 475), (240, 56)
        )
        self.reset_back_button = Button(
            "QUAY LẠI", (WIDTH // 2 + 135, 475), (240, 56)
        )
        self.lobby_buttons = [
            Button("TẠO PHÒNG", (WIDTH // 2, 300), (340, 56)),
            Button("THAM GIA PHÒNG", (WIDTH // 2, 372), (340, 56)),
            Button("QUAY LẠI MENU", (WIDTH // 2, 444), (340, 56)),
        ]
        self.room_mode_buttons = [
            Button("1v1", (WIDTH // 2, 275), (280, 58)),
            Button("2v2 - ĐANG PHÁT TRIỂN", (WIDTH // 2, 355), (480, 58)),
            Button("QUAY LẠI", (WIDTH // 2, 435), (280, 58)),
        ]
        self.room_code_field = InputField(
            "Mã phòng",
            (WIDTH // 2 - 185, 245, 370, 52),
            room_code=True,
            max_length=6,
        )
        self.join_room_button = Button("THAM GIA", (WIDTH // 2 - 135, 370), (240, 56))
        self.join_back_button = Button("QUAY LẠI", (WIDTH // 2 + 135, 370), (240, 56))
        self.room_waiting_buttons = [
            Button("SẴN SÀNG", (255, 485), (280, 54)),
            Button("LÀM MỚI", (595, 485), (280, 54)),
            Button("RỜI PHÒNG", (255, 555), (280, 54)),
            Button("BẮT ĐẦU", (595, 555), (280, 54)),
        ]
        self.access_token = None
        self.online_user = None
        self.current_user = None
        self.current_room = None
        self.room_poll_executor = ThreadPoolExecutor(max_workers=1)
        self.room_poll_future = None
        self.last_room_poll = 0
        self.launching_match = False
        self.current_match_started = None
        self.leave_room_in_progress = False
        self.online_message = ""
        self.online_error = ""
        self.lobby_neko_ai = LobbyNekoAI(API_BASE_URL)

    def create_menu_buttons(self):
        labels = [
            "CHƠI ĐƠN",
            "ĐẤU 1V1 ONLINE",
            "BẢNG XẾP HẠNG",
            "ĐĂNG XUẤT",
            "THOÁT",
        ]
        start_y = 275
        gap = 72
        return [
            Button(label, (WIDTH // 2, start_y + index * gap), (360, 58))
            for index, label in enumerate(labels)
        ]

    def draw_cat_header(self):
        cx, cy = WIDTH // 2, 95
        cat_color = (255, 228, 196)
        ear_color = (255, 182, 193)
        eye_color = PASTEL_TEXT

        pygame.draw.polygon(self.screen, cat_color, [(cx - 62, cy - 5), (cx - 78, cy - 48), (cx - 28, cy - 30)])
        pygame.draw.polygon(self.screen, cat_color, [(cx + 62, cy - 5), (cx + 78, cy - 48), (cx + 28, cy - 30)])
        pygame.draw.polygon(self.screen, ear_color, [(cx - 58, cy - 13), (cx - 70, cy - 38), (cx - 34, cy - 27)])
        pygame.draw.polygon(self.screen, ear_color, [(cx + 58, cy - 13), (cx + 70, cy - 38), (cx + 34, cy - 27)])
        pygame.draw.rect(self.screen, cat_color, pygame.Rect(cx - 70, cy - 20, 140, 90), border_radius=28)
        pygame.draw.circle(self.screen, eye_color, (cx - 32, cy + 18), 7)
        pygame.draw.circle(self.screen, eye_color, (cx + 32, cy + 18), 7)
        pygame.draw.circle(self.screen, ear_color, (cx - 48, cy + 35), 8)
        pygame.draw.circle(self.screen, ear_color, (cx + 48, cy + 35), 8)
        pygame.draw.line(self.screen, eye_color, (cx - 7, cy + 32), (cx, cy + 40), 3)
        pygame.draw.line(self.screen, eye_color, (cx, cy + 40), (cx + 7, cy + 32), 3)

    def draw_title(self):
        title = FONT_TITLE.render("NEKO BLOCK BLAST", True, PASTEL_TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 165)))

    def confirm_player_name(self):
        name = self.player_name.strip()
        if not name:
            self.name_error = "Vui lòng nhập nickname"
            return
        self.player_name = name[:20]
        self.name_error = ""
        self.state = STATE_MENU

    def draw_name_input(self):
        self.screen.fill(PASTEL_BG)
        self.draw_cat_header()
        self.draw_title()
        label = FONT_MEDIUM.render("Nhập họ tên hoặc nickname", True, PASTEL_TEXT)
        self.screen.blit(label, label.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 80)))

        input_rect = pygame.Rect(WIDTH // 2 - 185, HEIGHT // 2 - 35, 370, 58)
        input_color = WHITE if self.name_input_active else PASTEL_BUTTON
        pygame.draw.rect(self.screen, input_color, input_rect, border_radius=14)
        pygame.draw.rect(self.screen, PASTEL_ACCENT_DARK, input_rect, 3, border_radius=14)
        display_text = self.player_name
        if self.name_input_active and pygame.time.get_ticks() % 1000 < 500:
            display_text += "|"
        name_surf = FONT_MEDIUM.render(display_text, True, PASTEL_TEXT)
        self.screen.blit(name_surf, (input_rect.x + 14, input_rect.y + 10))

        hint = FONT_VIETNAMESE_TINY.render("Tối đa 20 ký tự", True, PASTEL_TEXT)
        hint_rect = hint.get_rect(centerx=WIDTH // 2, top=input_rect.bottom + 14)
        self.screen.blit(hint, hint_rect)
        rule = FONT_VIETNAMESE_TINY.render(
            "Chỉ dùng chữ không dấu, số và khoảng trắng", True, PASTEL_TEXT
        )
        rule_rect = rule.get_rect(centerx=WIDTH // 2, top=hint_rect.bottom + 10)
        self.screen.blit(rule, rule_rect)
        self.confirm_button.rect.centerx = WIDTH // 2
        self.confirm_button.rect.top = rule_rect.bottom + 24
        if self.name_error:
            error = FONT_VIETNAMESE_TINY.render(self.name_error, True, PASTEL_ACCENT_DARK)
            self.screen.blit(
                error,
                error.get_rect(centerx=WIDTH // 2, top=self.confirm_button.rect.bottom + 12),
            )
        self.confirm_button.draw(self.screen, pygame.mouse.get_pos())

    def draw_menu(self):
        self.screen.fill(PASTEL_BG)
        self.draw_cat_header()
        self.draw_title()
        greeting = FONT_SMALL.render(f"Xin chào, {self.player_name}", True, PASTEL_TEXT)
        self.screen.blit(greeting, greeting.get_rect(center=(WIDTH // 2, 35)))
        for button in self.buttons:
            button.draw(self.screen, pygame.mouse.get_pos())
        self.lobby_neko_ai.draw(self.screen)

    def draw_online(self):
        self.screen.fill(PASTEL_BG)
        self.draw_cat_header()
        title = FONT_VIETNAMESE_TITLE.render("TÀI KHOẢN", True, PASTEL_TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 190)))
        for button in self.online_buttons:
            button.draw(self.screen, pygame.mouse.get_pos())
        self.draw_online_status(520)

    def draw_form(self, title_text, fields, submit_button, message_y=555):
        self.screen.fill(PASTEL_BG)
        title = FONT_VIETNAMESE_TITLE.render(title_text, True, PASTEL_TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 68)))
        for field in fields:
            field.draw(self.screen)
        submit_button.draw(self.screen, pygame.mouse.get_pos())
        self.form_back_button.draw(self.screen, pygame.mouse.get_pos())
        message = self.online_error or self.online_message
        if message:
            color = PASTEL_ACCENT_DARK if self.online_error else PASTEL_TEXT
            text = FONT_VIETNAMESE_TINY.render(message, True, color)
            self.screen.blit(text, text.get_rect(center=(WIDTH // 2, message_y)))

    def draw_login(self):
        self.form_back_button.rect.centery = self.login_button.rect.centery
        self.login_fields[1].password_visible = self.login_password_visible
        self.draw_form(
            "ĐĂNG NHẬP",
            self.login_fields,
            self.login_button,
            message_y=610,
        )
        self.login_password_toggle.text = (
            "ẨN" if self.login_password_visible else "HIỆN"
        )
        self.login_password_toggle.draw(self.screen, pygame.mouse.get_pos())
        self.forgot_password_button.draw(self.screen, pygame.mouse.get_pos())

    def draw_register(self):
        self.form_back_button.rect.centery = self.register_button.rect.centery
        self.register_fields[3].password_visible = self.register_password_visible
        self.draw_form("ĐĂNG KÝ", self.register_fields, self.register_button)
        self.register_password_toggle.text = (
            "ẨN" if self.register_password_visible else "HIỆN"
        )
        self.register_password_toggle.draw(self.screen, pygame.mouse.get_pos())
        hint = FONT_VIETNAMESE_TINY.render("Mật khẩu tối thiểu 8 ký tự", True, PASTEL_TEXT)
        self.screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 445)))

    def draw_forgot_password(self):
        self.screen.fill(PASTEL_BG)
        title = FONT_VIETNAMESE_TITLE.render("QUÊN MẬT KHẨU", True, PASTEL_TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 120)))
        self.forgot_email_field.draw(self.screen)
        self.forgot_send_button.draw(self.screen, pygame.mouse.get_pos())
        self.forgot_back_button.draw(self.screen, pygame.mouse.get_pos())
        self.draw_online_status(445)

    def draw_reset_password(self):
        self.screen.fill(PASTEL_BG)
        title = FONT_VIETNAMESE_TITLE.render("ĐẶT LẠI MẬT KHẨU", True, PASTEL_TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 80)))
        self.reset_fields[2].password_visible = self.reset_password_visible
        for field in self.reset_fields:
            field.draw(self.screen)
        self.reset_password_toggle.text = (
            "ẨN" if self.reset_password_visible else "HIỆN"
        )
        self.reset_password_toggle.draw(self.screen, pygame.mouse.get_pos())
        self.reset_submit_button.draw(self.screen, pygame.mouse.get_pos())
        self.reset_back_button.draw(self.screen, pygame.mouse.get_pos())
        self.draw_online_status(555)

    def draw_online_lobby(self):
        self.screen.fill(PASTEL_BG)
        display_name = self.online_user.get("display_name", "") if self.online_user else ""
        greeting = FONT_MEDIUM.render(f"Xin chào, {display_name}", True, PASTEL_TEXT)
        status = FONT_SMALL.render("Đăng nhập thành công", True, PASTEL_ACCENT_DARK)
        self.screen.blit(greeting, greeting.get_rect(center=(WIDTH // 2, 150)))
        self.screen.blit(status, status.get_rect(center=(WIDTH // 2, 195)))
        for button in self.lobby_buttons:
            button.draw(self.screen, pygame.mouse.get_pos())
        if self.online_message:
            message = FONT_VIETNAMESE_TINY.render(
                self.online_message, True, PASTEL_TEXT
            )
            self.screen.blit(message, message.get_rect(center=(WIDTH // 2, 585)))

    def draw_room_mode(self):
        self.screen.fill(PASTEL_BG)
        title = FONT_VIETNAMESE_TITLE.render("CHỌN CHẾ ĐỘ", True, PASTEL_TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 155)))
        for button in self.room_mode_buttons:
            button.draw(self.screen, pygame.mouse.get_pos())
        self.draw_online_status(520)

    def draw_room_join(self):
        self.screen.fill(PASTEL_BG)
        title = FONT_VIETNAMESE_TITLE.render("THAM GIA PHÒNG", True, PASTEL_TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 145)))
        self.room_code_field.draw(self.screen)
        self.join_room_button.draw(self.screen, pygame.mouse.get_pos())
        self.join_back_button.draw(self.screen, pygame.mouse.get_pos())
        self.draw_online_status(440)

    def draw_online_status(self, y, fallback=""):
        message = self.online_error or self.online_message or fallback
        if message:
            color = PASTEL_ACCENT_DARK if self.online_error else PASTEL_TEXT
            text = FONT_VIETNAMESE_TINY.render(message, True, color)
            self.screen.blit(text, text.get_rect(center=(WIDTH // 2, y)))

    def draw_team(self, team, rect):
        pygame.draw.rect(self.screen, PASTEL_GRID_EMPTY, rect, border_radius=14)
        heading = FONT_MEDIUM.render(f"TEAM {team}", True, PASTEL_TEXT)
        self.screen.blit(heading, heading.get_rect(center=(rect.centerx, rect.y + 32)))
        players = [
            player
            for player in (self.current_room or {}).get("players", [])
            if player.get("team") == team
        ]
        if not players:
            empty = FONT_VIETNAMESE_TINY.render("Đang chờ người chơi", True, PASTEL_TEXT)
            self.screen.blit(empty, empty.get_rect(center=(rect.centerx, rect.y + 105)))
            return
        for index, player in enumerate(players):
            y = rect.y + 82 + index * 76
            host = " (Chủ phòng)" if player.get("is_host") else ""
            display_name = player.get("display_name", "")[:16]
            name = FONT_SMALL.render(
                f"{display_name}{host}", True, PASTEL_TEXT
            )
            ready_text = "Sẵn sàng" if player.get("is_ready") else "Chưa sẵn sàng"
            ready_color = PASTEL_ACCENT_DARK if player.get("is_ready") else PASTEL_TEXT
            ready = FONT_VIETNAMESE_TINY.render(ready_text, True, ready_color)
            self.screen.blit(name, name.get_rect(center=(rect.centerx, y)))
            self.screen.blit(ready, ready.get_rect(center=(rect.centerx, y + 28)))

    def draw_room_waiting(self):
        self.screen.fill(PASTEL_BG)
        room = self.current_room or {}
        title = FONT_MEDIUM.render(
            f"PHÒNG {room.get('room_code', '')}", True, PASTEL_TEXT
        )
        mode = FONT_SMALL.render(
            f"Chế độ: {room.get('mode', '')}", True, PASTEL_ACCENT_DARK
        )
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 45)))
        self.screen.blit(mode, mode.get_rect(center=(WIDTH // 2, 82)))
        self.draw_team(1, pygame.Rect(55, 115, 350, 315))
        self.draw_team(2, pygame.Rect(445, 115, 350, 315))

        leave_button = self.room_waiting_buttons[2]
        original_leave_text = leave_button.text
        if self.leave_room_in_progress:
            leave_button.text = "ĐANG RỜI..."
        for button in self.room_waiting_buttons[:3]:
            button.draw(self.screen, pygame.mouse.get_pos())
        leave_button.text = original_leave_text
        if (
            room.get("status") == "waiting"
            and self.is_current_user_host()
        ):
            self.room_waiting_buttons[3].text = "BẮT ĐẦU"
            self.room_waiting_buttons[3].draw(self.screen, pygame.mouse.get_pos())
        fallback = ""
        if self.launching_match or room.get("status") == "playing":
            fallback = "Trận đấu đang bắt đầu..."
        elif room.get("status") == "waiting":
            fallback = "Đang chờ chủ phòng bắt đầu..."
        self.draw_online_status(620, fallback)

    def load_leaderboard(self):
        leaderboard_path = os.path.join(BASE_DIR, "leaderboard.json")
        if not os.path.exists(leaderboard_path):
            return []
        try:
            with open(leaderboard_path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []

        merged = {}
        for item in data:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                score = item.get("score", 0)
                if name:
                    try:
                        score = int(score)
                    except (TypeError, ValueError):
                        continue
                    key = name.casefold()
                    if key not in merged or score > merged[key]["score"]:
                        merged[key] = {"name": name, "score": score}
        return sorted(merged.values(), key=lambda entry: entry["score"], reverse=True)

    def draw_leaderboard(self):
        self.screen.fill(PASTEL_BG)
        title = FONT_VIETNAMESE_TITLE.render("BẢNG XẾP HẠNG", True, PASTEL_TEXT)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 80)))
        board_rect = pygame.Rect(WIDTH // 2 - 285, 135, 570, 380)
        pygame.draw.rect(self.screen, PASTEL_GRID_EMPTY, board_rect, border_radius=18)
        entries = self.load_leaderboard()
        if not entries:
            empty = FONT_MEDIUM.render("Chưa có điểm nào", True, PASTEL_TEXT)
            self.screen.blit(empty, empty.get_rect(center=board_rect.center))
        else:
            for index, entry in enumerate(entries[:8]):
                y = 165 + index * 40
                rank = FONT_SMALL.render(f"#{index + 1}", True, PASTEL_ACCENT_DARK)
                name = FONT_SMALL.render(entry["name"][:18], True, PASTEL_TEXT)
                score = FONT_SMALL.render(f'{entry["score"]} pt', True, PASTEL_TEXT)
                self.screen.blit(rank, (board_rect.x + 35, y))
                self.screen.blit(name, (board_rect.x + 125, y))
                self.screen.blit(score, (board_rect.right - score.get_width() - 40, y))
        self.back_button.draw(self.screen, pygame.mouse.get_pos())

    def launch_single_player(self):
        player_name = self.player_name.strip()[:20]
        if getattr(sys, "frozen", False):
            self.run_frozen_game(
                player_name=player_name,
                start_in_play=True,
            )
            return
        pygame.display.iconify()
        subprocess.run(
            [
                sys.executable,
                os.path.join(BASE_DIR, "block_blast_cat.py"),
                "--player-name",
                player_name,
            ],
            cwd=BASE_DIR,
        )
        pygame.display.set_caption("Neko Block Blast - Menu")

    def restore_launcher_display(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Neko Block Blast - Menu")
        self.clock = pygame.time.Clock()

    def run_frozen_game(self, **game_options):
        from block_blast_cat import run_game

        try:
            run_game(embedded=True, **game_options)
        except SystemExit:
            pass
        finally:
            stop_match_audio()
            self.restore_launcher_display()

    def quit_launcher(self):
        self.lobby_neko_ai.shutdown()
        self.room_poll_executor.shutdown(wait=False, cancel_futures=True)
        stop_match_audio()
        pygame.quit()
        sys.exit()

    def activate_first_field(self, fields):
        for index, field in enumerate(fields):
            field.active = index == 0

    def open_login(self, message=""):
        self.state = STATE_LOGIN
        self.online_error = ""
        self.online_message = message
        self.activate_first_field(self.login_fields)

    def complete_authentication(self, token, user):
        self.access_token = token
        self.online_user = user
        self.current_user = user
        self.player_name = (
            user.get("display_name") or user.get("username") or ""
        ).strip()[:20]
        self.online_error = ""
        self.online_message = ""
        self.login_fields[1].value = ""
        self.state = STATE_MENU

    def logout(self, message=""):
        self.stop_room_polling()
        stop_match_audio()
        self.access_token = None
        self.online_user = None
        self.current_user = None
        self.current_room = None
        self.player_name = ""
        self.launching_match = False
        self.current_match_started = None
        self.leave_room_in_progress = False
        self.login_fields[1].value = ""
        self.online_error = message
        self.online_message = ""
        self.state = STATE_ONLINE

    def handle_expired_session(self, error):
        if getattr(error, "status_code", None) == 401:
            self.logout("Phiên đăng nhập hết hạn")
            return True
        return False

    @staticmethod
    def is_gmail(email):
        return email.strip().casefold().endswith("@gmail.com")

    def submit_forgot_password(self):
        email = self.forgot_email_field.value.strip().casefold()
        if not self.is_gmail(email):
            self.online_error = "Vui lòng sử dụng địa chỉ Gmail."
            return
        try:
            forgot_password(email)
        except ApiError as exc:
            self.online_error = (
                "Không kết nối được server"
                if exc.kind == "connection"
                else exc.detail or "Không thể gửi mã xác thực"
            )
            return

        self.reset_fields[0].value = email
        self.reset_fields[1].value = ""
        self.reset_fields[2].value = ""
        self.online_error = ""
        self.online_message = "Mã xác thực đã được gửi. Vui lòng kiểm tra Gmail."
        self.activate_first_field(self.reset_fields)
        self.state = STATE_RESET_PASSWORD

    def submit_reset_password(self):
        email = self.reset_fields[0].value.strip().casefold()
        code = self.reset_fields[1].value.strip()
        new_password = self.reset_fields[2].value
        if not self.is_gmail(email):
            self.online_error = "Vui lòng sử dụng địa chỉ Gmail."
            return
        if len(code) != 6 or not code.isdigit():
            self.online_error = "Mã xác thực phải gồm 6 chữ số"
            return
        if len(new_password) < 8:
            self.online_error = "Mật khẩu mới phải có ít nhất 8 ký tự"
            return
        try:
            reset_password(email, code, new_password)
        except ApiError as exc:
            self.online_error = (
                "Không kết nối được server"
                if exc.kind == "connection"
                else exc.detail or "Không thể đổi mật khẩu"
            )
            return

        self.reset_fields[1].value = ""
        self.reset_fields[2].value = ""
        self.login_fields[1].value = ""
        self.open_login("Đổi mật khẩu thành công. Vui lòng đăng nhập lại.")

    def submit_login(self):
        username = self.login_fields[0].value.strip()
        password = self.login_fields[1].value
        if not username or not password:
            self.online_error = "Vui lòng nhập đầy đủ tài khoản và mật khẩu"
            return
        try:
            token_data = login(username, password)
            token = token_data["access_token"]
            user = get_current_user(token)
        except ApiError as exc:
            self.online_error = (
                "Không kết nối được server"
                if exc.kind == "connection"
                else "Sai tài khoản hoặc mật khẩu"
            )
            return
        except (KeyError, TypeError):
            self.online_error = "Phản hồi từ server không hợp lệ"
            return

        self.complete_authentication(token, user)

    def submit_register(self):
        username = self.register_fields[0].value.strip()
        display_name = self.register_fields[1].value.strip()
        email = self.register_fields[2].value.strip()
        password = self.register_fields[3].value
        if not all((username, display_name, email, password)):
            self.online_error = "Vui lòng nhập đầy đủ thông tin"
            return
        if not 3 <= len(username) <= 20:
            self.online_error = "Username phải dài từ 3 đến 20 ký tự"
            return
        if len(password) < 8:
            self.online_error = "Mật khẩu phải có ít nhất 8 ký tự"
            return
        if not self.is_gmail(email):
            self.online_error = "Vui lòng sử dụng địa chỉ Gmail."
            return
        try:
            register(username, display_name, email, password)
        except ApiError as exc:
            if exc.kind == "connection":
                self.online_error = "Không kết nối được server"
            elif "email" in exc.detail.casefold():
                self.online_error = "Email đã được sử dụng"
            elif "username" in exc.detail.casefold():
                self.online_error = "Tên đăng nhập đã tồn tại"
            else:
                self.online_error = "Thông tin đăng ký không hợp lệ"
            return

        try:
            token_data = login(username, password)
            token = token_data["access_token"]
            user = get_current_user(token)
        except ApiError as exc:
            if exc.kind == "connection":
                self.online_error = "Không kết nối được server"
            else:
                self.online_error = "Đăng ký thành công, hãy đăng nhập"
            self.login_fields[0].value = username
            self.login_fields[1].value = ""
            self.state = STATE_LOGIN
            return
        except (KeyError, TypeError):
            self.online_error = "Phản hồi từ server không hợp lệ"
            return

        for field in self.register_fields:
            field.value = ""
        self.login_fields[0].value = username
        self.complete_authentication(token, user)

    def set_room_error(self, error):
        if self.handle_expired_session(error):
            return
        if error.kind == "connection":
            self.online_error = "Không kết nối được server"
        elif "not found" in error.detail.casefold():
            self.online_error = "Không tìm thấy phòng"
        elif "full" in error.detail.casefold():
            self.online_error = "Phòng đã đầy"
        elif "not waiting" in error.detail.casefold():
            self.online_error = "Phòng không còn ở trạng thái chờ"
        else:
            self.online_error = "Không thể thực hiện yêu cầu"

    def enter_room(self, room):
        self.current_room = room
        self.stop_room_polling()
        self.last_room_poll = 0
        self.launching_match = False
        self.current_match_started = None
        self.online_error = ""
        self.online_message = ""
        self.state = STATE_ROOM_WAITING

    def stop_room_polling(self):
        if self.room_poll_future and not self.room_poll_future.done():
            self.room_poll_future.cancel()
        self.room_poll_future = None

    @staticmethod
    def is_already_left_room_error(error):
        detail = getattr(error, "detail", "").casefold()
        return (
            getattr(error, "status_code", None) in {403, 404}
            and (
                "room not found" in detail
                or "not in room" in detail
                or "player is not in room" in detail
                or "user is not in room" in detail
            )
        )

    @staticmethod
    def format_leave_room_error(error):
        if getattr(error, "kind", "") == "connection":
            return "Không kết nối được server khi rời phòng"
        status_code = getattr(error, "status_code", None)
        detail = safe_log_text(getattr(error, "detail", "")) or "không rõ lỗi"
        if status_code:
            return f"Không thể rời phòng (HTTP {status_code}: {detail})"
        return f"Không thể rời phòng ({detail})"

    def clear_room_state_after_leave(self):
        self.current_room = None
        self.stop_room_polling()
        stop_match_audio()
        self.launching_match = False
        self.current_match_started = None
        self.leave_room_in_progress = False
        self.online_error = ""
        self.online_message = ""
        self.state = STATE_ONLINE_LOBBY

    @staticmethod
    def poll_room_request(token, room_code):
        try:
            room = get_room(token, room_code)
            match = None
            if room.get("status") == "playing":
                try:
                    match = get_active_match(token, room_code)
                except ApiError as exc:
                    if "no active match" not in exc.detail.casefold():
                        raise
            return room_code, room, match, None
        except ApiError as exc:
            return room_code, None, None, exc

    def update_room_polling(self):
        if self.state != STATE_ROOM_WAITING or not self.current_room:
            return

        if self.room_poll_future is not None:
            if not self.room_poll_future.done():
                return
            try:
                room_code, room, match, error = self.room_poll_future.result()
            except Exception:
                room_code, room, match, error = (
                    self.current_room.get("room_code"),
                    None,
                    None,
                    ApiError("connection"),
                )
            self.room_poll_future = None

            if (
                self.state != STATE_ROOM_WAITING
                or not self.current_room
                or room_code != self.current_room.get("room_code")
            ):
                return
            if error:
                if self.handle_expired_session(error):
                    return
                if self.is_already_left_room_error(error):
                    self.clear_room_state_after_leave()
                    return
                if error.kind == "connection":
                    self.online_error = "Tạm thời không kết nối được server"
                return

            self.current_room = room
            self.online_error = ""
            if room.get("status") == "playing":
                self.online_message = "Trận đấu đang bắt đầu..."
            if (
                match
                and not self.launching_match
                and match.get("match_id") != self.current_match_started
            ):
                self.online_message = "Trận đấu đang bắt đầu..."
                self.launch_online_match(match)
            return

        if self.launching_match:
            return
        now = pygame.time.get_ticks()
        if now - self.last_room_poll < 1000:
            return
        self.last_room_poll = now
        self.room_poll_future = self.room_poll_executor.submit(
            self.poll_room_request,
            self.access_token,
            self.current_room["room_code"],
        )

    def submit_create_room(self, mode):
        try:
            room = create_room(self.access_token, mode)
        except ApiError as exc:
            self.set_room_error(exc)
            return
        self.enter_room(room)

    def submit_join_room(self):
        room_code = self.room_code_field.value.strip().upper()
        if len(room_code) != 6:
            self.online_error = "Mã phòng phải gồm 6 ký tự"
            return
        try:
            room = join_room(self.access_token, room_code)
        except ApiError as exc:
            self.set_room_error(exc)
            return
        self.enter_room(room)

    def refresh_room(self):
        if not self.current_room:
            return
        try:
            self.current_room = get_room(
                self.access_token, self.current_room["room_code"]
            )
            self.online_error = ""
            self.online_message = "Đã cập nhật danh sách người chơi"
        except ApiError as exc:
            self.set_room_error(exc)

    def start_current_room(self):
        if not self.current_room:
            return
        try:
            match = start_room(
                self.access_token, self.current_room["room_code"]
            )
        except ApiError as exc:
            detail = exc.detail.casefold()
            if "exactly 2" in detail:
                self.online_error = "Phòng cần đủ 2 người chơi"
            elif "ready" in detail:
                self.online_error = "Người chơi còn lại chưa sẵn sàng"
            elif "only the host" in detail:
                self.online_error = "Chỉ chủ phòng được bắt đầu"
            else:
                self.set_room_error(exc)
            return
        self.current_room["status"] = "playing"
        self.online_message = "Trận đấu đang bắt đầu..."
        self.launch_online_match(match)

    def enter_active_match(self):
        if not self.current_room:
            return
        try:
            match = get_active_match(
                self.access_token, self.current_room["room_code"]
            )
        except ApiError as exc:
            if self.handle_expired_session(exc):
                return
            if "no active match" in exc.detail.casefold():
                self.online_error = "Chưa có trận đấu đang diễn ra"
            else:
                self.set_room_error(exc)
            return
        self.launch_online_match(match)

    def launch_online_match(self, match):
        match_id = match.get("match_id")
        if self.launching_match or match_id == self.current_match_started:
            return
        self.launching_match = True
        self.current_match_started = match_id
        env = os.environ.copy()
        env["NEKO_ACCESS_TOKEN"] = self.access_token
        display_name = self.online_user.get("display_name", self.player_name)
        pygame.display.iconify()
        try:
            if getattr(sys, "frozen", False):
                self.run_frozen_game(
                    player_name=display_name,
                    online_match=True,
                    match_id=match_id,
                    api_base_url=API_BASE_URL,
                    access_token=self.access_token,
                )
            else:
                subprocess.run(
                    [
                        sys.executable,
                        os.path.join(BASE_DIR, "block_blast_cat.py"),
                        "--online-match",
                        "--player-name",
                        display_name,
                        "--match-id",
                        str(match_id),
                        "--api-base-url",
                        API_BASE_URL,
                    ],
                    cwd=BASE_DIR,
                    env=env,
                )
        finally:
            self.launching_match = False
            pygame.display.set_caption("Neko Block Blast - Menu")
        try:
            self.current_room = get_room(
                self.access_token, self.current_room["room_code"]
            )
        except ApiError as exc:
            if self.handle_expired_session(exc):
                return
            if self.is_already_left_room_error(exc):
                self.clear_room_state_after_leave()
                return
            self.current_room = None
            self.state = STATE_ONLINE_LOBBY

    def toggle_room_ready(self):
        if not self.current_room:
            return
        try:
            self.current_room = toggle_ready(
                self.access_token, self.current_room["room_code"]
            )
            self.online_error = ""
            self.online_message = ""
        except ApiError as exc:
            self.set_room_error(exc)

    def leave_current_room(self):
        if self.leave_room_in_progress:
            return
        if not self.current_room:
            self.clear_room_state_after_leave()
            return
        self.leave_room_in_progress = True
        self.online_error = ""
        self.online_message = "Đang rời phòng..."
        room_code = self.current_room["room_code"]
        self.stop_room_polling()
        try:
            leave_room(self.access_token, room_code)
        except ApiError as exc:
            LOGGER.warning(
                "leave_room_failed status_code=%s detail=%s response_body=%s exception_type=%s",
                getattr(exc, "status_code", None),
                safe_log_text(getattr(exc, "detail", "")),
                safe_log_text(getattr(exc, "response_body", "")),
                type(exc).__name__,
            )
            if self.handle_expired_session(exc):
                return
            if self.is_already_left_room_error(exc):
                self.clear_room_state_after_leave()
                return
            self.leave_room_in_progress = False
            self.online_error = self.format_leave_room_error(exc)
            return
        self.clear_room_state_after_leave()

    def is_current_user_host(self):
        if not self.current_room or not self.online_user:
            return False
        return self.current_room.get("host_user_id") == self.online_user.get("id")

    def handle_menu_click(self, button_text):
        if button_text == "CHƠI ĐƠN":
            self.launch_single_player()
        elif button_text == "ĐẤU 1V1 ONLINE":
            self.state = STATE_ONLINE_LOBBY
            self.online_error = ""
            self.online_message = ""
        elif button_text == "BẢNG XẾP HẠNG":
            self.state = STATE_LEADERBOARD
        elif button_text == "ĐĂNG XUẤT":
            self.logout()
        elif button_text == "THOÁT":
            self.quit_launcher()

    def handle_form_event(
        self,
        event,
        fields,
        submit_button,
        submit_action,
        back_button=None,
        back_state=STATE_ONLINE,
    ):
        back_button = back_button or self.form_back_button
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for field in fields:
                field.active = field.rect.collidepoint(event.pos)
            if submit_button.is_clicked(event):
                submit_action()
            elif back_button.is_clicked(event):
                self.state = back_state
                self.online_error = ""
                self.online_message = ""
        elif event.type == pygame.KEYDOWN:
            active_index = next(
                (index for index, field in enumerate(fields) if field.active), None
            )
            if active_index is None:
                return
            if event.key == pygame.K_TAB:
                fields[active_index].active = False
                fields[(active_index + 1) % len(fields)].active = True
            elif event.key == pygame.K_RETURN:
                if active_index < len(fields) - 1:
                    fields[active_index].active = False
                    fields[active_index + 1].active = True
                else:
                    submit_action()
            else:
                fields[active_index].handle_key(event)
                self.online_error = ""

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit_launcher()

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.state in (STATE_MENU, STATE_NAME_INPUT, STATE_ONLINE):
                    self.quit_launcher()
                if self.state in (STATE_LOGIN, STATE_REGISTER):
                    self.state = STATE_ONLINE
                elif self.state in (STATE_FORGOT_PASSWORD, STATE_RESET_PASSWORD):
                    self.state = STATE_LOGIN
                elif self.state == STATE_ONLINE_LOBBY:
                    self.state = STATE_MENU
                elif self.state in (STATE_ROOM_MODE, STATE_ROOM_JOIN):
                    self.state = STATE_ONLINE_LOBBY
                elif self.state == STATE_ROOM_WAITING:
                    self.online_message = "Hãy dùng nút RỜI PHÒNG để quay lại sảnh"
                else:
                    self.state = STATE_MENU
                continue

            if self.state == STATE_NAME_INPUT:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    input_rect = pygame.Rect(WIDTH // 2 - 185, HEIGHT // 2 - 35, 370, 58)
                    self.name_input_active = input_rect.collidepoint(event.pos)
                    if self.confirm_button.is_clicked(event):
                        self.confirm_player_name()
                if event.type == pygame.KEYDOWN and self.name_input_active:
                    if event.key == pygame.K_RETURN:
                        self.confirm_player_name()
                    elif event.key == pygame.K_BACKSPACE:
                        self.player_name = self.player_name[:-1]
                        self.name_error = ""
                    elif (
                        len(self.player_name) < 20
                        and event.unicode
                        and event.unicode.isprintable()
                        and is_valid_nickname_char(event.unicode)
                    ):
                        self.player_name += event.unicode
                        self.name_error = ""
            elif self.state == STATE_MENU:
                if self.lobby_neko_ai.handle_event(event):
                    continue
                for button in self.buttons:
                    if button.is_clicked(event):
                        self.handle_menu_click(button.text)
            elif self.state == STATE_ONLINE:
                if self.online_buttons[0].is_clicked(event):
                    self.open_login()
                elif self.online_buttons[1].is_clicked(event):
                    self.state = STATE_REGISTER
                    self.online_error = ""
                    self.online_message = ""
                    self.activate_first_field(self.register_fields)
                elif self.online_buttons[2].is_clicked(event):
                    self.quit_launcher()
            elif self.state == STATE_LOGIN:
                if self.login_password_toggle.is_clicked(event):
                    self.login_password_visible = not self.login_password_visible
                elif self.forgot_password_button.is_clicked(event):
                    self.state = STATE_FORGOT_PASSWORD
                    self.online_error = ""
                    self.online_message = ""
                    self.forgot_email_field.active = True
                else:
                    self.handle_form_event(
                        event, self.login_fields, self.login_button, self.submit_login
                    )
            elif self.state == STATE_REGISTER:
                if self.register_password_toggle.is_clicked(event):
                    self.register_password_visible = (
                        not self.register_password_visible
                    )
                else:
                    self.handle_form_event(
                        event,
                        self.register_fields,
                        self.register_button,
                        self.submit_register,
                    )
            elif self.state == STATE_FORGOT_PASSWORD:
                self.handle_form_event(
                    event,
                    [self.forgot_email_field],
                    self.forgot_send_button,
                    self.submit_forgot_password,
                    back_button=self.forgot_back_button,
                    back_state=STATE_LOGIN,
                )
            elif self.state == STATE_RESET_PASSWORD:
                if self.reset_password_toggle.is_clicked(event):
                    self.reset_password_visible = not self.reset_password_visible
                else:
                    self.handle_form_event(
                        event,
                        self.reset_fields,
                        self.reset_submit_button,
                        self.submit_reset_password,
                        back_button=self.reset_back_button,
                        back_state=STATE_LOGIN,
                    )
            elif self.state == STATE_ONLINE_LOBBY:
                if self.lobby_buttons[0].is_clicked(event):
                    self.state = STATE_ROOM_MODE
                    self.online_error = ""
                    self.online_message = ""
                elif self.lobby_buttons[1].is_clicked(event):
                    self.state = STATE_ROOM_JOIN
                    self.online_error = ""
                    self.online_message = ""
                    self.room_code_field.value = ""
                    self.room_code_field.active = True
                elif self.lobby_buttons[2].is_clicked(event):
                    self.state = STATE_MENU
            elif self.state == STATE_ROOM_MODE:
                if self.room_mode_buttons[0].is_clicked(event):
                    self.submit_create_room("1v1")
                elif self.room_mode_buttons[1].is_clicked(event):
                    self.online_error = ""
                    self.online_message = (
                        "Chế độ 2v2 sẽ được phát triển ở phiên bản sau"
                    )
                elif self.room_mode_buttons[2].is_clicked(event):
                    self.state = STATE_ONLINE_LOBBY
            elif self.state == STATE_ROOM_JOIN:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.room_code_field.active = self.room_code_field.rect.collidepoint(
                        event.pos
                    )
                    if self.join_room_button.is_clicked(event):
                        self.submit_join_room()
                    elif self.join_back_button.is_clicked(event):
                        self.state = STATE_ONLINE_LOBBY
                elif event.type == pygame.KEYDOWN and self.room_code_field.active:
                    if event.key == pygame.K_RETURN:
                        self.submit_join_room()
                    else:
                        self.room_code_field.handle_key(event)
                        self.online_error = ""
            elif self.state == STATE_ROOM_WAITING:
                if self.room_waiting_buttons[0].is_clicked(event):
                    self.toggle_room_ready()
                elif self.room_waiting_buttons[1].is_clicked(event):
                    self.refresh_room()
                elif self.room_waiting_buttons[2].is_clicked(event):
                    self.leave_current_room()
                elif (
                    self.current_room.get("status") == "waiting"
                    and self.is_current_user_host()
                    and self.room_waiting_buttons[3].is_clicked(event)
                ):
                    if self.current_room.get("mode") == "2v2":
                        self.online_error = ""
                        self.online_message = (
                            "Chế độ 2v2 sẽ được phát triển ở phiên bản sau"
                        )
                    else:
                        self.start_current_room()
            elif self.state == STATE_LEADERBOARD and self.back_button.is_clicked(event):
                self.state = STATE_MENU

    def draw(self):
        if self.state == STATE_NAME_INPUT:
            self.draw_name_input()
        elif self.state == STATE_MENU:
            self.draw_menu()
        elif self.state == STATE_ONLINE:
            self.draw_online()
        elif self.state == STATE_LOGIN:
            self.draw_login()
        elif self.state == STATE_REGISTER:
            self.draw_register()
        elif self.state == STATE_FORGOT_PASSWORD:
            self.draw_forgot_password()
        elif self.state == STATE_RESET_PASSWORD:
            self.draw_reset_password()
        elif self.state == STATE_ONLINE_LOBBY:
            self.draw_online_lobby()
        elif self.state == STATE_ROOM_MODE:
            self.draw_room_mode()
        elif self.state == STATE_ROOM_JOIN:
            self.draw_room_join()
        elif self.state == STATE_ROOM_WAITING:
            self.draw_room_waiting()
        elif self.state == STATE_LEADERBOARD:
            self.draw_leaderboard()

    def run(self):
        while True:
            self.update_room_polling()
            if self.state == STATE_MENU:
                self.lobby_neko_ai.update()
            self.handle_events()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)


if __name__ == "__main__":
    Launcher().run()
