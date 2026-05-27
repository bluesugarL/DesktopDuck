import ctypes
import ctypes.wintypes
import glob
import os
import random
import shutil
import sys
import pygame.mixer
from PyQt5.QtWidgets import (
    QApplication, QLabel, QMainWindow, QMenu, QAction, QActionGroup,
    QSystemTrayIcon, QFileDialog, QMessageBox, QGraphicsOpacityEffect,
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QPoint, QTimer, QRect, QEasingCurve
from PyQt5.QtGui import QPixmap, QIcon, QFont, QTransform

DEFAULT_PET_HEIGHT = 200
SIZE_OPTIONS = {"小": 140, "中": 200, "大": 260}
VERSION = "0.2.0"

# schedule rules: (day_of_week, hour, minute, bubble_text) — day_of_week=None means every day
# 0=Mon 1=Tue 2=Wed 3=Thu 4=Fri 5=Sat 6=Sun
SCHEDULE_RULES = [
    (None, 12, 0, "该吃午饭了"),
    (1, 19, 0, "佳人们，开播了"),
    (2, 22, 0, "gjjc要结算啦！"),
    (6, 22, 0, "jjc要结算啦！"),
]

# PyInstaller support
if getattr(sys, "frozen", False):
    _BASE_DIR = sys._MEIPASS
    _EXE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _EXE_DIR = _BASE_DIR

AUDIO_DIR = os.path.join(_EXE_DIR, "Audio")
FOOD_DIR = os.path.join(_BASE_DIR, "food")
MOOD_DIR = os.path.join(_BASE_DIR, "mood")

FOOD_REACTIONS = {
    "过期罐头": {
        "speech": "我chovy，你tm拿食物给我拿好了鸭，我吃柠檬",
        "mood": "Mood_angry",
        "mood_duration": 6000,
        "good": False,
        "delta": -1,
    },
    "安康鱼肝脏": {
        "speech": "好吃喵~谢谢喵~谢谢投喂喵~",
        "good": True,
        "delta": 1,
    },
    "油炸豆腐": {
        "speech": "好吃喵~谢谢喵~谢谢投喂喵~",
        "good": True,
        "delta": 1,
    },
    "火腿肠": {
        "speech": "好吃喵~谢谢喵~谢谢投喂喵~",
        "good": True,
        "delta": 1,
    },
    "精炼粉末": {
        "speech": "好吃喵~谢谢喵~谢谢投喂喵~",
        "good": True,
        "delta": 3,
    },
    "礼包": {
        "speech": "分析礼包中……",
        "good": True,
        "delta": 3,
        "no_repeat_warning": True,
        "is_gift": True,
    },
    "沙拉": {
        "speech": "好吃喵~谢谢喵~谢谢投喂喵~",
        "good": True,
        "delta": 1,
    },
    "KFC炸鸡": {
        "speech": "好吃喵~谢谢喵~谢谢投喂喵~",
        "good": True,
        "delta": 2,
        "no_repeat_warning": True,
    },
}

# ── helpers ───────────────────────────────────────────────────────────

def _load_sprites(height: int) -> tuple[list[QPixmap], list[str]]:
    """Return (scaled pixmaps, filenames)."""
    pic_dirs = [
        os.path.join(_BASE_DIR, "Pic"),
        _BASE_DIR,
    ]
    pixmaps = []
    names = []
    for d in pic_dirs:
        for p in sorted(glob.glob(os.path.join(d, "*.png"))):
            pix = QPixmap(p)
            if not pix.isNull():
                pixmaps.append(pix.scaledToHeight(height, Qt.SmoothTransformation))
                names.append(os.path.splitext(os.path.basename(p))[0].lower())
        if pixmaps:
            break
    if not pixmaps:
        pixmaps = [QPixmap()]
        names = [""]
    # ensure duck is the default sprite
    try:
        idx = names.index("duck")
        if idx != 0:
            pixmaps.insert(0, pixmaps.pop(idx))
            names.insert(0, names.pop(idx))
    except ValueError:
        pass
    return pixmaps, names

def _load_audio_files() -> list[str]:
    os.makedirs(AUDIO_DIR, exist_ok=True)
    seen = set()
    files = []
    # bundled defaults first, then user-added external
    for base in (_BASE_DIR, _EXE_DIR):
        for ext in ("*.mp3", "*.wav", "*.ogg"):
            for p in sorted(glob.glob(os.path.join(base, "Audio", ext))):
                name = os.path.basename(p)
                if name not in seen:
                    seen.add(name)
                    files.append(p)
    # copy bundled audio to external dir so users can see/remove them
    bundled_audio = os.path.join(_BASE_DIR, "Audio")
    if os.path.isdir(bundled_audio) and os.path.isdir(AUDIO_DIR):
        for f in os.listdir(bundled_audio):
            src = os.path.join(bundled_audio, f)
            dst = os.path.join(AUDIO_DIR, f)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
    return files

def _get_active_window_rect() -> QRect | None:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    if hwnd == 0:
        return None
    rect = ctypes.wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    if not ctypes.windll.user32.IsWindowVisible(hwnd):
        return None
    return QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

def _load_food(height: int = 55) -> list[tuple[str, QPixmap]]:
    foods = []
    for p in sorted(glob.glob(os.path.join(FOOD_DIR, "*.png"))):
        pix = QPixmap(p)
        if not pix.isNull():
            name = os.path.splitext(os.path.basename(p))[0]
            foods.append((name, pix.scaledToHeight(height, Qt.SmoothTransformation)))
    return foods


def _load_moods(pet_height: int) -> dict[str, QPixmap]:
    moods = {}
    for p in sorted(glob.glob(os.path.join(MOOD_DIR, "*.png"))):
        pix = QPixmap(p)
        if not pix.isNull():
            name = os.path.splitext(os.path.basename(p))[0]
            moods[name] = pix.scaledToHeight(pet_height, Qt.SmoothTransformation)
    return moods


def _startup_dir() -> str:
    return os.path.join(os.environ["APPDATA"],
                        "Microsoft", "Windows", "Start Menu", "Programs", "Startup")

def _startup_shortcut_path() -> str:
    return os.path.join(_startup_dir(), "DesktopDuck.lnk")

# ── popups ────────────────────────────────────────────────────────────

SPEECH_LINES = [
    "好无聊啊...", "闹麻了", "很对很对很对很对很对很对",
    "不对不对不对不对不对不对", "饿了...", "那么问题来了，大家觉得……",
    "ZZZzzz", "B站咕咕鸭，点个关注吧~", "分析礼包ing", "浚c又犯病了",
]

class FoodDropLabel(QLabel):
    """Falling food animation with fade-out."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self._pos_anim = QPropertyAnimation(self, b"pos")
        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity")
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)

        self._pos_anim.finished.connect(self._on_landed)
        self._hold_timer.timeout.connect(self._start_fade)
        self._fade_anim.finished.connect(self._on_fade_done)
        self._on_landed_cb = None

    def drop(self, pixmap: QPixmap, start_pos: QPoint, end_pos: QPoint,
             on_landed_cb):
        self._on_landed_cb = on_landed_cb
        self._opacity.setOpacity(1.0)
        self.setPixmap(pixmap)
        self.resize(pixmap.size())
        self.move(start_pos)
        self.show()
        self._pos_anim.setDuration(500)
        self._pos_anim.setStartValue(start_pos)
        self._pos_anim.setEndValue(end_pos)
        self._pos_anim.setEasingCurve(QEasingCurve.InQuad)
        self._pos_anim.start()

    def _on_landed(self):
        self._hold_timer.start(200)

    def _start_fade(self):
        self._fade_anim.setDuration(250)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.start()

    def _on_fade_done(self):
        self.hide()
        if self._on_landed_cb:
            self._on_landed_cb()


class BubblePopup(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(
            "background: #fff; border: 2px solid #999; border-radius: 12px; "
            "padding: 8px 14px; font-size: 14px; color: #111;"
        )
        self.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_text(self, text: str, anchor_pos: QPoint, duration_ms: int = 3000):
        self.setText(text)
        self.adjustSize()
        x = anchor_pos.x() + 20
        y = anchor_pos.y() - self.height() - 10
        self.move(max(0, x), max(0, y))
        self.show()
        self._hide_timer.start(duration_ms)


class BadgePopup(QLabel):
    """Image badge that floats above the pet briefly (like a Bilibili fan badge)."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_badge(self, pixmap: QPixmap, anchor_pos: QPoint, duration_ms: int = 2500):
        self.setPixmap(pixmap)
        self.resize(pixmap.size())
        x = anchor_pos.x() - self.width() // 2
        y = anchor_pos.y() - self.height() - 5
        self.move(max(0, x), max(0, y))
        self.show()
        self._hide_timer.start(duration_ms)


# ── main pet window ───────────────────────────────────────────────────

class DesktopPet(QMainWindow):
    def __init__(self, sprites: list[QPixmap], sprite_names: list[str], pet_height: int):
        super().__init__()

        self._sprites = sprites
        self._sprite_names = sprite_names
        self._sprite_idx = 0
        self._pet_height = pet_height
        self._audio_files = _load_audio_files()
        self._badge_pixmaps = self._load_badges()
        self._food_items = _load_food()
        self._mood_pixmaps = _load_moods(pet_height)
        self._poof_pixmap = self._load_poof()

        # --- feeding state ---
        self._feeding = False
        self._last_food = None
        self._last_food_count = 0
        self._food_label = FoodDropLabel()
        self._poof_label = QLabel(None)
        self._poof_label.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self._poof_label.setAttribute(Qt.WA_TranslucentBackground)
        self._poof_label.setStyleSheet("background: transparent;")

        # --- mood state ---
        self._pre_mood_sprite_idx = None
        self._mood_timer = QTimer(self)
        self._mood_timer.setSingleShot(True)
        self._mood_timer.timeout.connect(self._clear_mood)

        # --- favorability ---
        self._favorability = 0

        # --- gift pack tracking ---
        self._gift_count = 0

        # --- marry scene ---
        self._marrying = False

        # --- award scene ---
        self._award_anim_timer = QTimer(self)
        self._award_anim_timer.timeout.connect(self._do_award_step)
        self._award_anim_index = 0
        self._award_base_pixmap = None
        self._award_angles = []
        self._award_end_timer = QTimer(self)
        self._award_end_timer.setSingleShot(True)
        self._award_end_timer.timeout.connect(self._end_award_scene)
        self._pre_award_sprite_idx = None
        self._pre_award_pos = None

        # --- celebration ---
        self._celebrating = False
        self._oh_left_label = QLabel(None)
        self._oh_left_label.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self._oh_left_label.setAttribute(Qt.WA_TranslucentBackground)
        self._oh_left_label.setStyleSheet("background: transparent;")
        self._oh_right_label = QLabel(None)
        self._oh_right_label.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self._oh_right_label.setAttribute(Qt.WA_TranslucentBackground)
        self._oh_right_label.setStyleSheet("background: transparent;")
        self._oh_left_pix = self._load_oh("oh_1.png")
        self._oh_right_pix = self._load_oh("oh_2.png")

        special_name = "哦齁哦齁哦齁.mp3"
        self._special_audio = None
        for base in (_BASE_DIR, _EXE_DIR):
            path = os.path.join(base, "Audio", "special", special_name)
            if os.path.exists(path):
                self._special_audio = path
                break

        # default voice for triple-click
        self._default_voice = None
        for base in (_BASE_DIR, _EXE_DIR):
            path = os.path.join(base, "Audio", "那么问题来了，大家觉得.mp3")
            if os.path.exists(path):
                self._default_voice = path
                break

        # chovy audio for expired can
        self._chovy_audio = None
        for base in (_BASE_DIR, _EXE_DIR):
            path = os.path.join(base, "Audio", "special", "chovy.mp3")
            if os.path.exists(path):
                self._chovy_audio = path
                break

        # award scene audio
        self._busy_audio = None
        for base in (_BASE_DIR, _EXE_DIR):
            path = os.path.join(base, "Audio", "special", "很忙.mp3")
            if os.path.exists(path):
                self._busy_audio = path
                break

        # marry scene audio
        self._lover_audio = None
        for base in (_BASE_DIR, _EXE_DIR):
            path = os.path.join(base, "Audio", "special", "Lover.flac")
            if os.path.exists(path):
                self._lover_audio = path
                break

        self._celebrate_timer = QTimer(self)
        self._celebrate_timer.setSingleShot(True)
        self._celebrate_timer.timeout.connect(self._end_celebration)

        # --- window setup ---
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        self.label = QLabel(self)
        self._show_sprite(0)
        self.resize(self.label.size())

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 50,
                  screen.bottom() - self.height() - 80)

        self.drag_pos = None
        self._was_dragged = False
        self._rest_pos = None

        # --- audio ---
        pygame.mixer.init()
        self._volume = 0.5
        self._play_mode = "random"
        self._seq_index = 0
        self._click_count = 0
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._reset_clicks)

        # --- animations ---
        self._anim = QPropertyAnimation(self, b"pos")
        self._anim.finished.connect(self._on_anim_done)

        # --- idle timer ---
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._do_idle)

        # --- popups ---
        self._bubble = BubblePopup(None)
        self._badge_popup = BadgePopup(None)

        # --- tray ---
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._make_tray_icon())
        self._tray.setToolTip("Desktop Duck")
        self._tray.activated.connect(self._on_tray_activated)
        self._build_tray_menu()
        self._tray.show()

        # --- app icon for message boxes ---
        self._app_icon = QIcon()
        ico_path = os.path.join(_BASE_DIR, "downPic", "duck.ico")
        if os.path.exists(ico_path):
            self._app_icon = QIcon(ico_path)

        # --- scheduled bubbles ---
        self._schedule_timer = QTimer(self)
        self._schedule_timer.timeout.connect(self._check_schedule)
        self._schedule_timer.start(30000)  # check every 30 seconds
        self._scheduled_fired = set()  # tracks "YYYY-MM-DD HH:MM" slots already fired

        self.show()
        self._start_idle()

    # ── badge loading ─────────────────────────────────────────────────

    def _load_badges(self) -> list[QPixmap]:
        badge_dir = os.path.join(_BASE_DIR, "downPic")
        badges = []
        for p in sorted(glob.glob(os.path.join(badge_dir, "badge*.png"))):
            pix = QPixmap(p)
            if not pix.isNull():
                w = int(self._pet_height * 0.8)
                badges.append(pix.scaledToWidth(w, Qt.SmoothTransformation))
        return badges

    def _load_poof(self) -> QPixmap | None:
        poof_path = os.path.join(FOOD_DIR, "poof.png")
        if os.path.exists(poof_path):
            pix = QPixmap(poof_path)
            if not pix.isNull():
                return pix.scaledToHeight(60, Qt.SmoothTransformation)
        return None

    def _load_oh(self, filename: str) -> QPixmap | None:
        path = os.path.join(_BASE_DIR, "downPic", filename)
        if os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                return pix.scaledToHeight(int(self._pet_height * 0.8),
                                          Qt.SmoothTransformation)
        return None

    # ── sprite ───────────────────────────────────────────────────────

    def _show_sprite(self, idx: int):
        self._sprite_idx = idx % len(self._sprites)
        pix = self._sprites[self._sprite_idx]
        self.label.setPixmap(pix)
        self.label.resize(pix.size())

    def _random_sprite(self):
        if len(self._sprites) > 1:
            others = [i for i in range(len(self._sprites)) if i != self._sprite_idx]
            self._show_sprite(random.choice(others))

    def _pick_sprite_for(self, action: str):
        """Prefer sprites whose filename contains the action keyword."""
        if len(self._sprites) <= 1:
            return
        keywords = {"hop": ["hop", "jump"], "walk": ["walk"], "shuffle": ["shuffle"]}
        candidates = []
        for kw in keywords.get(action, []):
            for i, name in enumerate(self._sprite_names):
                if i != self._sprite_idx and kw in name:
                    candidates.append(i)
        if candidates:
            self._show_sprite(random.choice(candidates))
        else:
            self._random_sprite()

    # ── tray icon ────────────────────────────────────────────────────

    def _make_tray_icon(self) -> QIcon:
        icon_path = os.path.join(_BASE_DIR, "downPic", "duck.png")
        pix = QPixmap(icon_path)
        if not pix.isNull():
            pix = pix.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            pix = self._sprites[0].scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return QIcon(pix)

    def _build_tray_menu(self):
        m = QMenu()
        show_act = m.addAction("显示/隐藏")
        show_act.triggered.connect(self._toggle_visible)
        switch_act = m.addAction("换装")
        switch_act.triggered.connect(self._random_sprite)
        m.addSeparator()
        exit_act = m.addAction("退出")
        exit_act.triggered.connect(QApplication.quit)
        self._tray.setContextMenu(m)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_visible()

    def _toggle_visible(self):
        self.setVisible(not self.isVisible())
        self._bubble.hide()
        self._badge_popup.hide()

    # ── right-click menu ─────────────────────────────────────────────

    def _show_menu(self, pos):
        menu = QMenu(self)

        switch_act = menu.addAction("换装")
        switch_act.triggered.connect(self._random_sprite)

        # size submenu
        size_menu = menu.addMenu("大小")
        size_group = QActionGroup(size_menu)
        size_group.setExclusive(True)
        current_label = {v: k for k, v in SIZE_OPTIONS.items()}.get(self._pet_height, "中")
        for label in SIZE_OPTIONS:
            act = size_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(label == current_label)
            act.triggered.connect(lambda checked, lb=label: self._set_pet_size(lb))
            size_group.addAction(act)

        # audio submenu
        if self._audio_files:
            audio_menu = menu.addMenu("发声")
            for f in self._audio_files:
                name = os.path.basename(f)
                act = audio_menu.addAction(name)
                act.triggered.connect(lambda checked, path=f: self._play_audio(path))

        upload_act = menu.addAction("上传音频")
        upload_act.triggered.connect(self._upload_audio)

        # play mode
        mode_menu = menu.addMenu("播放模式")
        mode_group = QActionGroup(mode_menu)
        mode_group.setExclusive(True)
        for label in ("随机播放", "顺序播放"):
            act = mode_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(
                (label == "随机播放" and self._play_mode == "random")
                or (label == "顺序播放" and self._play_mode == "sequential")
            )
            act.triggered.connect(lambda checked, lb=label: self._set_play_mode(lb))
            mode_group.addAction(act)

        # volume submenu
        vol_menu = menu.addMenu("音量")
        vol_group = QActionGroup(vol_menu)
        vol_group.setExclusive(True)
        for label, val in [("10%", 0.1), ("30%", 0.3), ("50%", 0.5),
                           ("70%", 0.7), ("100%", 1.0)]:
            act = vol_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(abs(self._volume - val) < 0.01)
            act.triggered.connect(lambda checked, v=val: self._set_volume(v))
            vol_group.addAction(act)

        feed_menu = menu.addMenu("投喂")
        if self._food_items:
            for name, pix in self._food_items:
                act = feed_menu.addAction(name)
                act.triggered.connect(lambda checked, n=name, p=pix: self._feed_pet(n, p))
        else:
            no_food = feed_menu.addAction("(没有食物)")
            no_food.setEnabled(False)

        bubble_menu = menu.addMenu("气泡")
        for line in SPEECH_LINES[:6]:
            act = bubble_menu.addAction(line)
            act.triggered.connect(lambda checked, text=line: self._say(text))

        menu.addSeparator()

        fav_view = menu.addAction("查看好感度")
        fav_view.triggered.connect(self._show_favorability)

        fav_clear = menu.addAction("好感度清零")
        fav_clear.triggered.connect(self._clear_favorability)

        menu.addSeparator()

        auto_act = menu.addAction("开机自启" if not self._has_startup() else "取消自启")
        auto_act.triggered.connect(self._toggle_autostart)

        menu.addSeparator()

        about_act = menu.addAction("关于")
        about_act.triggered.connect(self._show_about)

        exit_act = menu.addAction("退出")
        exit_act.triggered.connect(QApplication.quit)

        menu.exec_(self.mapToGlobal(pos))

    # ── size ──────────────────────────────────────────────────────────

    def _set_pet_size(self, label: str):
        new_h = SIZE_OPTIONS[label]
        if new_h == self._pet_height:
            return
        self._pet_height = new_h
        self._sprites, self._sprite_names = _load_sprites(new_h)
        self._badge_pixmaps = self._load_badges()
        self._mood_pixmaps = _load_moods(new_h)
        self._poof_pixmap = self._load_poof()
        self._oh_left_pix = self._load_oh("oh_1.png")
        self._oh_right_pix = self._load_oh("oh_2.png")
        self._show_sprite(min(self._sprite_idx, len(self._sprites) - 1))
        self.resize(self.label.size())
        self._tray.setIcon(self._make_tray_icon())

    # ── drag & click ─────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self._was_dragged = False
            self._anim.stop()
            self._idle_timer.stop()
            self._bubble.hide()
            self._badge_popup.hide()
            if self._rest_pos is not None:
                self.move(self._rest_pos)
                self._rest_pos = None

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
            delta = event.globalPos() - self.drag_pos
            if (delta - self.pos()).manhattanLength() > 3:
                self._was_dragged = True
            self.move(delta)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._was_dragged:
            self._bounce()
            self._click_count += 1
            if self._click_count >= 3:
                self._reset_clicks()
                if self._default_voice:
                    self._play_audio(self._default_voice)
                elif self._audio_files:
                    self._play_next()
            else:
                self._click_timer.start(500)
        self.drag_pos = None
        self._start_idle()

    def _reset_clicks(self):
        self._click_count = 0

    # ── audio ────────────────────────────────────────────────────────

    def _pick_audio(self) -> str | None:
        if not self._audio_files:
            return None
        if self._play_mode == "sequential":
            idx = self._seq_index % len(self._audio_files)
            self._seq_index = (self._seq_index + 1) % len(self._audio_files)
            return self._audio_files[idx]
        else:
            return random.choice(self._audio_files)

    def _play_next(self):
        path = self._pick_audio()
        if path:
            self._play_audio(path)

    def _play_audio(self, path: str):
        try:
            pygame.mixer.music.set_volume(self._volume)
            pygame.mixer.music.load(path)
            pygame.mixer.music.play()
        except pygame.error:
            pass

    def _set_volume(self, vol: float):
        self._volume = vol

    def _set_play_mode(self, label: str):
        self._play_mode = "random" if label == "随机播放" else "sequential"

    def _upload_audio(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择音频文件", "",
            "Audio Files (*.mp3 *.wav *.ogg);;All Files (*)"
        )
        if paths:
            os.makedirs(AUDIO_DIR, exist_ok=True)
            for src in paths:
                dst = os.path.join(AUDIO_DIR, os.path.basename(src))
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
            self._audio_files = _load_audio_files()

    # ── popups ───────────────────────────────────────────────────────

    def _say(self, text: str):
        top_center = QPoint(self.pos().x(), self.pos().y())
        self._bubble.show_text(text, top_center)

    def _show_badge(self):
        if not self._badge_pixmaps:
            return
        pix = random.choice(self._badge_pixmaps)
        top_center = QPoint(self.pos().x() + self.width() // 2, self.pos().y())
        self._badge_popup.show_badge(pix, top_center)

    # ── feeding ──────────────────────────────────────────────────────

    def _feed_pet(self, food_name: str, food_pix: QPixmap):
        if self._feeding or self._celebrating or self._marrying:
            return
        self._feeding = True

        pet_cx = self.pos().x() + self.width() // 2
        start = QPoint(pet_cx - food_pix.width() // 2,
                       self.pos().y() - food_pix.height() - 10)
        end = QPoint(start.x(),
                     self.pos().y() + self.height() - food_pix.height() - 15)

        self._food_label.drop(food_pix, start, end,
                              lambda: self._on_food_landed(food_name))

    def _on_food_landed(self, food_name: str):
        reaction = FOOD_REACTIONS.get(food_name, {})

        # adjust favorability
        prev_fav = self._favorability
        delta = reaction.get("delta", 1)
        self._favorability = max(-5, min(10, self._favorability + delta))

        # bad-end check before normal reaction
        if self._favorability <= -5:
            QTimer.singleShot(300, self._trigger_bad_end)
            self._feeding = False
            return

        # play chovy audio for expired can
        if food_name == "过期罐头" and self._chovy_audio:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.load(self._chovy_audio)
                pygame.mixer.music.play()
            except pygame.error:
                pass

        # repeated food detection
        if food_name == self._last_food:
            self._last_food_count += 1
        else:
            self._last_food = food_name
            self._last_food_count = 1

        # gift pack tracking
        is_gift = reaction.get("is_gift", False)
        if is_gift:
            self._gift_count += 1
        else:
            self._gift_count = 0

        heart = "♥" if self._favorability >= 0 else "♡"
        if is_gift:
            speech = reaction.get("speech", "分析礼包中……")
        elif self._last_food_count >= 3 and reaction.get("good", True) and not reaction.get("no_repeat_warning"):
            speech = "能不能换一个食物喵~吃腻了喵~"
        else:
            speech = reaction.get("speech", "好吃！")
        self._say(f"{speech}  [{heart} {self._favorability}]")

        # HIGHEST PRIORITY: celebration when favorability hits max
        if prev_fav < 10 and self._favorability >= 10:
            self._gift_count = 0
            self._last_food_count = 0
            QTimer.singleShot(400, self._celebrate_max)
            self._feeding = False
            return

        # check for award scene trigger on 3rd consecutive gift
        if is_gift and self._gift_count >= 3:
            self._gift_count = 0
            QTimer.singleShot(400, self._start_award_scene)
            self._feeding = False
            return

        # check for marry scene trigger on 3rd consecutive KFC炸鸡
        if food_name == "KFC炸鸡" and self._last_food_count >= 3:
            self._last_food_count = 0
            QTimer.singleShot(400, self._start_marry_scene)
            self._feeding = False
            return

        mood_name = reaction.get("mood")
        if mood_name and mood_name in self._mood_pixmaps:
            self._show_mood(mood_name, reaction.get("mood_duration", 3000))

        # threshold events — fire on crossing
        if prev_fav < 5 and self._favorability >= 5:
            QTimer.singleShot(800, lambda: self._show_mood("Mood_happy", 5000))

        if self._poof_pixmap:
            pet_cx = self.pos().x() + self.width() // 2
            px = pet_cx - self._poof_pixmap.width() // 2
            py = self.pos().y() + self.height() - self._poof_pixmap.height() - 10
            self._poof_label.setPixmap(self._poof_pixmap)
            self._poof_label.resize(self._poof_pixmap.size())
            self._poof_label.move(px, max(0, py))
            self._poof_label.show()
            QTimer.singleShot(400, self._poof_label.hide)

        self._feeding = False

    def _celebrate_max(self):
        if self._celebrating:
            return
        self._celebrating = True
        self._mood_timer.stop()
        self._clear_mood()

        self._show_mood("Mood_sfl", 8000)

        if self._special_audio and os.path.exists(self._special_audio):
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.load(self._special_audio)
                pygame.mixer.music.play()
            except pygame.error:
                pass

        pet_cx = self.pos().x() + self.width() // 2
        head_y = self.pos().y()

        if self._oh_left_pix:
            self._oh_left_label.setPixmap(self._oh_left_pix)
            self._oh_left_label.resize(self._oh_left_pix.size())
            lx = pet_cx - self._oh_left_pix.width() - 55
            ly = head_y - 10
            self._oh_left_label.move(max(0, lx), max(0, ly))
            self._oh_left_label.show()

        if self._oh_right_pix:
            self._oh_right_label.setPixmap(self._oh_right_pix)
            self._oh_right_label.resize(self._oh_right_pix.size())
            rx = pet_cx + 55
            ry = head_y - 10
            self._oh_right_label.move(max(0, rx), max(0, ry))
            self._oh_right_label.show()

        self._celebrate_timer.start(8000)

    def _end_celebration(self):
        self._oh_left_label.hide()
        self._oh_right_label.hide()
        self._celebrating = False
        self._favorability = 0

    # ── award scene ───────────────────────────────────────────────────

    def _start_award_scene(self):
        if self._celebrating:
            return
        self._celebrating = True
        self._mood_timer.stop()
        self._clear_mood()
        self._anim.stop()

        # load base award pixmap
        if "Mood_award" in self._mood_pixmaps:
            self._award_base_pixmap = self._mood_pixmaps["Mood_award"]
        else:
            self._celebrating = False
            return

        # save pre-award state
        self._pre_award_sprite_idx = self._sprite_idx
        self._pre_award_pos = self.pos()

        # set the award image
        self.label.setPixmap(self._award_base_pixmap)
        self.label.resize(self._award_base_pixmap.size())
        self.resize(self.label.size())

        # play award music
        if self._busy_audio and os.path.exists(self._busy_audio):
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.load(self._busy_audio)
                pygame.mixer.music.play()
            except pygame.error:
                pass

        # build angle sequence: [5,0,5,0, -5,0,-5,0] repeated for ~8s at 100ms per step
        group = [5, 0, 5, 0, -5, 0, -5, 0]
        self._award_angles = group * 10  # 80 steps = 8 seconds
        self._award_anim_index = 0

        self._award_anim_timer.start(100)
        self._award_end_timer.start(8000)

    def _do_award_step(self):
        if self._award_anim_index >= len(self._award_angles):
            self._award_anim_timer.stop()
            return
        angle = self._award_angles[self._award_anim_index]
        self._award_anim_index += 1

        if self._award_base_pixmap is None:
            return

        t = QTransform().rotate(angle)
        rotated = self._award_base_pixmap.transformed(t, Qt.SmoothTransformation)
        self.label.setPixmap(rotated)
        # keep the label centered so the window doesn't visibly shift
        self.label.resize(rotated.size())
        self.resize(rotated.size())
        # re-center the window around the original pet center
        cx = self._pre_award_pos.x() + self._award_base_pixmap.width() // 2
        cy = self._pre_award_pos.y() + self._award_base_pixmap.height() // 2
        nx = cx - rotated.width() // 2
        ny = cy - rotated.height() // 2
        self.move(nx, ny)

    def _end_award_scene(self):
        self._award_anim_timer.stop()
        self._award_anim_index = 0
        self._award_angles = []
        self._award_base_pixmap = None

        # restore original sprite
        if self._pre_award_sprite_idx is not None:
            idx = self._pre_award_sprite_idx
            self._pre_award_sprite_idx = None
            self._show_sprite(idx)
            self.resize(self.label.size())

        # restore position
        if self._pre_award_pos is not None:
            self.move(self._pre_award_pos)
            self._pre_award_pos = None

        self._celebrating = False

    # ── marry scene ───────────────────────────────────────────────────

    def _start_marry_scene(self):
        if self._celebrating or self._marrying:
            return
        self._marrying = True
        self._mood_timer.stop()
        self._clear_mood()
        self._anim.stop()

        if "Mood_marry" not in self._mood_pixmaps:
            self._marrying = False
            return

        self._say("很对很对很对")

        # play music
        if self._lover_audio and os.path.exists(self._lover_audio):
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.load(self._lover_audio)
                pygame.mixer.music.play()
            except pygame.error:
                pass

        # walk animation: left 2 steps, right 2 steps, back to start
        self._rest_pos = self.pos()
        screen = QApplication.primaryScreen().availableGeometry()
        margin = self.width() + 10
        step = 45
        start_x = self._rest_pos.x()
        if start_x - step * 2 < margin:
            step = max(0, (start_x - margin) // 2)

        self._anim.setDuration(1800)
        self._anim.setKeyValues([
            (0.0, QPoint(start_x, self._rest_pos.y())),
            (0.15, QPoint(start_x - step, self._rest_pos.y())),
            (0.3, QPoint(start_x - step * 2, self._rest_pos.y())),
            (0.5, QPoint(start_x - step, self._rest_pos.y())),
            (0.65, QPoint(start_x, self._rest_pos.y())),
            (1.0, QPoint(start_x, self._rest_pos.y())),
        ])

        self._anim.finished.disconnect(self._on_anim_done)
        self._anim.finished.connect(self._on_marry_walk_done)
        self._anim.start()

    def _on_marry_walk_done(self):
        self._anim.finished.disconnect(self._on_marry_walk_done)
        self._anim.finished.connect(self._on_anim_done)
        self._rest_pos = None

        self._show_mood("Mood_marry", 13000)
        QTimer.singleShot(13000, self._end_marry_scene)

    def _end_marry_scene(self):
        self._marrying = False
        self._clear_mood()
        self._start_idle()

    # ── mood ─────────────────────────────────────────────────────────

    def _show_mood(self, mood_name: str, duration_ms: int):
        if mood_name not in self._mood_pixmaps:
            return
        self._pre_mood_sprite_idx = self._sprite_idx
        pix = self._mood_pixmaps[mood_name]
        self.label.setPixmap(pix)
        self.label.resize(pix.size())
        self.resize(self.label.size())
        self._mood_timer.start(duration_ms)

    def _clear_mood(self):
        if self._pre_mood_sprite_idx is not None:
            idx = self._pre_mood_sprite_idx
            self._pre_mood_sprite_idx = None
            self._show_sprite(idx)
            self.resize(self.label.size())

    def _trigger_bad_end(self):
        box = QMessageBox(self)
        box.setWindowTitle("好感度归零")
        box.setText("你对牢鸭太坏了，牢鸭很生气！")
        box.setIcon(QMessageBox.Warning)
        if not self._app_icon.isNull():
            box.setWindowIcon(self._app_icon)
        box.setStandardButtons(QMessageBox.NoButton)
        sorry_btn = box.addButton("对不起", QMessageBox.AcceptRole)
        wrong_btn = box.addButton("我错了", QMessageBox.AcceptRole)
        box.exec_()

        self._say("我最讨厌的就是事后道歉！")
        self._show_mood("Mood_angry", 3000)
        QTimer.singleShot(3500, QApplication.quit)

    # ── about ────────────────────────────────────────────────────────

    def _show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle("关于 桌宠牢鸭")
        box.setText(
            f"<h3>Desktop Duck v{VERSION}</h3>"
            "<p>牢鸭桌宠，爱他就给他一个家</p>"
            "<p>作者：石楠花</p>"
            "<p>把 Audio 和 Pic 文件夹放在 exe 同级目录即可自定义素材。</p>"
            "<p>本次更新归石楠花所有。对于催更行为，将予以“已读并在意但不一定改进”的处理。</p>"
        )
        if not self._app_icon.isNull():
            box.setWindowIcon(self._app_icon)
        box.exec_()

    # ── favorability ──────────────────────────────────────────────────

    def _show_favorability(self):
        levels = {10: "满", 9: "极高", 7: "高", 5: "中", 3: "低", 0: "初始"}
        if self._favorability < 0:
            desc = "坏心情"
        else:
            desc = "初始"
            for threshold, label in sorted(levels.items(), reverse=True):
                if self._favorability >= threshold:
                    desc = label
                    break
        box = QMessageBox(self)
        box.setWindowTitle("好感度")
        box.setText(f"当前好感度: {self._favorability} / 10\n状态: {desc}")
        box.setIcon(QMessageBox.Information)
        box.setStandardButtons(QMessageBox.Ok)
        if not self._app_icon.isNull():
            box.setWindowIcon(self._app_icon)
        box.exec_()

    def _clear_favorability(self):
        self._favorability = 0
        self._gift_count = 0
        self._last_food = None
        self._last_food_count = 0
        self._say("好感度已清零~")

    # ── scheduled bubbles ─────────────────────────────────────────────

    def _check_schedule(self):
        from datetime import datetime
        now = datetime.now()
        slot = now.strftime("%Y-%m-%d %H:%M")
        if slot in self._scheduled_fired:
            return
        for day_of_week, hour, minute, text in SCHEDULE_RULES:
            if day_of_week is not None and now.weekday() != day_of_week:
                continue
            if now.hour == hour and now.minute == minute:
                self._say(text)
                self._scheduled_fired.add(slot)
                # purge old entries (keep only today's)
                today = now.strftime("%Y-%m-%d")
                self._scheduled_fired = {s for s in self._scheduled_fired if s.startswith(today)}
                break

    # ── animations ───────────────────────────────────────────────────

    def _bounce(self):
        self._rest_pos = self.pos()
        self._anim.setDuration(100)
        self._anim.setKeyValues([
            (0.0, self._rest_pos),
            (0.3, QPoint(self._rest_pos.x(), self._rest_pos.y() - 12)),
            (0.6, QPoint(self._rest_pos.x(), self._rest_pos.y() - 4)),
            (1.0, self._rest_pos),
        ])
        self._anim.start()

    def _idle_hop(self):
        self._rest_pos = self.pos()
        self._pick_sprite_for("hop")
        dur = random.randint(200, 350)
        h = random.randint(12, 22)
        self._anim.setDuration(dur)
        self._anim.setKeyValues([
            (0.0, self._rest_pos),
            (0.2, QPoint(self._rest_pos.x(), self._rest_pos.y() - h)),
            (0.5, QPoint(self._rest_pos.x(), self._rest_pos.y() - h // 3)),
            (0.7, QPoint(self._rest_pos.x(), self._rest_pos.y() - h * 2 // 3)),
            (1.0, self._rest_pos),
        ])
        self._anim.start()

    def _idle_shuffle(self):
        self._rest_pos = self.pos()
        offset = random.choice([-30, 30])
        screen = QApplication.primaryScreen().availableGeometry()
        margin = self.width() // 2
        if not (margin < self._rest_pos.x() + offset < screen.right() - margin):
            self._start_idle()
            return
        self._pick_sprite_for("shuffle")
        self._anim.setDuration(400)
        self._anim.setKeyValues([
            (0.0, self._rest_pos),
            (0.35, QPoint(self._rest_pos.x() + offset, self._rest_pos.y())),
            (1.0, self._rest_pos),
        ])
        self._anim.start()

    # ── walking ──────────────────────────────────────────────────────

    def _idle_walk(self):
        self._rest_pos = self.pos()
        screen = QApplication.primaryScreen().availableGeometry()
        margin = self.width() + 10
        direction = random.choice([-1, 1])
        step1 = random.randint(35, 55)
        step2 = step1 + random.randint(25, 40)
        target_x = self._rest_pos.x() + direction * step2

        if not (margin < target_x < screen.right() - margin):
            self._start_idle()
            return

        self._pick_sprite_for("walk")
        self._anim.setDuration(600)
        self._anim.setKeyValues([
            (0.0, self._rest_pos),
            (0.4, QPoint(self._rest_pos.x() + direction * step1, self._rest_pos.y())),
            (1.0, QPoint(target_x, self._rest_pos.y())),
        ])
        self._anim.start()

    # ── window docking ────────────────────────────────────────────────

    def _idle_dock(self):
        rect = _get_active_window_rect()
        if rect is None or rect.width() < 200:
            self._start_idle()
            return
        self._rest_pos = self.pos()
        target_x = rect.x() + 20
        target_y = max(QApplication.primaryScreen().availableGeometry().top(),
                       rect.y() - self.height() + 12)
        if abs(target_x - self._rest_pos.x()) > 400:
            self._start_idle()
            return
        self._dock_return = self._rest_pos
        self._anim.setDuration(300)
        self._anim.setKeyValues([
            (0.0, self._rest_pos),
            (1.0, QPoint(target_x, target_y)),
        ])
        self._anim.start()
        QTimer.singleShot(4000, self._dock_return_home)

    def _dock_return_home(self):
        src = self.pos()
        self._anim.stop()
        self._anim.setDuration(250)
        self._anim.setKeyValues([
            (0.0, src),
            (1.0, self._dock_return),
        ])
        self._anim.start()

    def _on_anim_done(self):
        self._rest_pos = None
        self._start_idle()

    # ── idle timer ───────────────────────────────────────────────────

    def _start_idle(self):
        delay = random.randint(8000, 25000)
        self._idle_timer.start(delay)

    def _do_idle(self):
        choices = ["hop", "shuffle", "walk", "dock", "speak", "badge", "switch", "nothing"]
        weights = [2, 1, 2, 2, 2, 2, 2, 6]
        action = random.choices(choices, weights=weights)[0]

        if action == "hop":
            self._idle_hop()
        elif action == "shuffle":
            self._idle_shuffle()
        elif action == "walk":
            self._idle_walk()
        elif action == "dock":
            self._idle_dock()
        elif action == "speak":
            self._say(random.choice(SPEECH_LINES))
            self._start_idle()
        elif action == "badge":
            self._show_badge()
            self._start_idle()
        elif action == "switch":
            self._random_sprite()
            self._start_idle()
        else:
            self._start_idle()

    # ── auto-start ───────────────────────────────────────────────────

    def _has_startup(self) -> bool:
        return os.path.exists(_startup_shortcut_path())

    def _toggle_autostart(self):
        shortcut = _startup_shortcut_path()
        if os.path.exists(shortcut):
            os.remove(shortcut)
        else:
            exe_path = os.path.join(_EXE_DIR, "DesktopDuck.exe")
            if os.path.exists(exe_path):
                target = exe_path
                args = ""
            else:
                target = "pythonw"
                args = f"\"{os.path.join(_EXE_DIR, 'main.py')}\""

            vbs = os.path.join(_EXE_DIR, "launch.vbs")
            vbs_cmd = f'CreateObject("WScript.Shell").Run "{target} {args}", 0'
            with open(vbs, "w", encoding="utf-8") as f:
                f.write(vbs_cmd + "\n")

            ps_cmd = (
                f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{shortcut}"); '
                f'$s.TargetPath = "wscript.exe"; '
                f'$s.Arguments = "\\"{vbs}\\""; '
                f'$s.WorkingDirectory = "{_EXE_DIR}"; '
                f'$s.Save()'
            )
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", "powershell", f"-Command {ps_cmd}", None, 0
            )


# ── entry ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    sprites, names = _load_sprites(DEFAULT_PET_HEIGHT)
    if not sprites[0].isNull():
        pet = DesktopPet(sprites, names, DEFAULT_PET_HEIGHT)
    else:
        print("No valid PNG sprites found in:", _BASE_DIR)
        sys.exit(1)
    sys.exit(app.exec_())
