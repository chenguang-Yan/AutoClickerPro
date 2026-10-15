# -*- coding: utf-8 -*-
"""
Auto Clicker Pro - 科技感鼠标自动点击器 (Windows)

零第三方依赖：tkinter + ctypes(Win32 API)
功能：
  1. 毫秒级点击间隔（手动输入）
  2. 多坐标批量点击，快捷键拾取坐标，支持删除/清空/排序/双击编辑
  3. 点击类型：左键单击 / 右键单击 / 左键双击 / 右键双击（全局默认 + 每点独立）
  4. 全局热键、启动倒计时、循环次数、随机抖动、平滑移动、配置存取
"""

import ctypes
import json
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ---------------------------------------------------------------------------
# DPI 感知（必须早于任何窗口创建，保证坐标 1:1 精确）
# ---------------------------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.WinDLL("user32", use_last_error=True)

# ---------------------------------------------------------------------------
# Win32 结构体与常量
# ---------------------------------------------------------------------------
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTUNION)]


user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetCursorPos.restype = ctypes.c_bool
user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetDoubleClickTime.restype = ctypes.c_uint
user32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
user32.MapVirtualKeyW.restype = ctypes.c_uint
user32.GetKeyNameTextW.argtypes = [ctypes.c_long, ctypes.POINTER(ctypes.c_wchar), ctypes.c_int]
user32.GetKeyNameTextW.restype = ctypes.c_int

_VX = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
_VY = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
_VW = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) or user32.GetSystemMetrics(0) or 1
_VH = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN) or user32.GetSystemMetrics(1) or 1

VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
VK_LWIN, VK_RWIN = 0x5B, 0x5C
MOD_VKS = {VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN}
VK_NORMALIZE = {
    0xA0: VK_SHIFT, 0xA1: VK_SHIFT,
    0xA2: VK_CONTROL, 0xA3: VK_CONTROL,
    0xA4: VK_MENU, 0xA5: VK_MENU,
}
# 需要跳过的虚拟键（未定义 / 会误报）
VK_SKIP = {0x0A, 0x0B, 0x0E, 0x0F, 0x16, 0x1A, 0x3A, 0x88, 0x89, 0x8A, 0x8B,
           0x8C, 0x8D, 0x8E, 0x8F, 0x92, 0x95, 0x97, 0xB8, 0xB9, 0xBA,
           0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9, 0xCA, 0xCB, 0xCC,
           0xCD, 0xCE, 0xCF, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6,
           0xD7, 0xD8, 0xD9, 0xDA, 0xE0, 0xE9, 0xEA, 0xF6, 0xF7, 0xF8,
           0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF}


def cursor_pos():
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def _norm_abs(x, y):
    ax = int(round((x - _VX) * 65535.0 / max(1, _VW - 1)))
    ay = int(round((y - _VY) * 65535.0 / max(1, _VH - 1)))
    return max(0, min(65535, ax)), max(0, min(65535, ay))


def mouse_move(x, y):
    """绝对定位移动鼠标"""
    ax, ay = _norm_abs(int(x), int(y))
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.u.mi.dx = ax
    inp.u.mi.dy = ay
    inp.u.mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE
    return user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def mouse_button(down_flag, up_flag):
    """按下并抬起一个鼠标键"""
    evs = []
    for flag in (down_flag, up_flag):
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.u.mi.dwFlags = flag
        evs.append(inp)
    arr = (INPUT * 2)(*evs)
    return user32.SendInput(2, arr, ctypes.sizeof(INPUT))


def vk_name(vk):
    """把虚拟键码转换成可读名称"""
    special = {
        VK_SHIFT: "Shift", VK_CONTROL: "Ctrl", VK_MENU: "Alt",
        VK_LWIN: "Win", VK_RWIN: "Win",
        0x08: "Backspace", 0x09: "Tab", 0x0C: "Clear", 0x0D: "Enter",
        0x1B: "Esc", 0x20: "Space", 0x21: "PgUp", 0x22: "PgDn",
        0x23: "End", 0x24: "Home", 0x25: "←", 0x26: "↑", 0x27: "→",
        0x28: "↓", 0x2C: "PrtSc", 0x2D: "Insert", 0x2E: "Delete",
        0x13: "Pause", 0x91: "ScrollLock", 0x14: "CapsLock",
        0x90: "NumLock", 0x2A: "Print", 0x2B: "Execute",
    }
    if vk in special:
        return special[vk]
    if 0x60 <= vk <= 0x69:
        return "Num%d" % (vk - 0x60)
    if 0x70 <= vk <= 0x87:
        return "F%d" % (vk - 0x6F)
    try:
        scan = user32.MapVirtualKeyW(vk, 0)
        if scan:
            buf = ctypes.create_unicode_buffer(64)
            if user32.GetKeyNameTextW(scan << 16, buf, 64):
                return buf.value
    except Exception:
        pass
    if 0x30 <= vk <= 0x5A:
        return chr(vk)
    return "VK%02X" % vk


def format_hotkey(vks):
    if not vks:
        return "未设置"
    order = {VK_CONTROL: 0, VK_MENU: 1, VK_SHIFT: 2, VK_LWIN: 3, VK_RWIN: 4}
    mods = sorted([v for v in vks if v in order], key=lambda v: order[v])
    others = sorted([v for v in vks if v not in order])
    return " + ".join(vk_name(v) for v in mods + others)


def pressed_keys():
    """当前按下的所有键（归一化，排除鼠标键）"""
    out = set()
    for vk in range(0x08, 0x100):
        if vk in VK_SKIP:
            continue
        try:
            if user32.GetAsyncKeyState(vk) & 0x8000:
                out.add(VK_NORMALIZE.get(vk, vk))
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# 主题配色
# ---------------------------------------------------------------------------
BG = "#1a222e"        # 窗口底色（浅化，保证文字清晰）
PANEL = "#222c3a"     # 面板
PANEL2 = "#2c3849"    # 按钮 / 输入框
CARD = "#1e2734"      # 表格 / 输入区
BORDER = "#3a4759"    # 分隔线 / 边框
ACCENT = "#22d3ee"    # 青色强调
ACCENT2 = "#a78bfa"   # 紫色强调
OK = "#34d399"
DANGER = "#fb7185"
TEXT = "#e9f1fa"      # 主文字（高对比）
TEXT_DIM = "#9fb3c8"  # 次要文字
FONT = "Microsoft YaHei UI"
MONO = "Consolas"

CLICK_TYPES = [
    ("左键单击", "left"),
    ("右键单击", "right"),
    ("左键双击", "left_double"),
    ("右键双击", "right_double"),
]
TYPE_LABEL = {code: label for label, code in CLICK_TYPES}
TYPE_CODE = {label: code for label, code in CLICK_TYPES}
DEFAULT_TYPE = "left"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "autoclicker_config.json")


# ---------------------------------------------------------------------------
# 主应用
# ---------------------------------------------------------------------------
class AutoClicker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Auto Clicker Pro  ·  鼠标自动点击器")
        self.root.geometry("642x450")
        self.root.minsize(640, 400)
        self.root.configure(bg=BG)

        self.points = []          # [{"x","y","type","delay","_iid"}]
        self._iid_seq = 0
        self.running = False
        self.stop_evt = threading.Event()
        self.worker = None
        self.ui_queue = queue.Queue()
        self.hotkeys_enabled = True
        self._rearm = False
        self.stats = {"visits": 0, "cycles": 0}
        self.capture_open = False

        self.vars = {
            "interval": tk.StringVar(value="1000"),
            "dbl_gap": tk.StringVar(value="60"),
            "default_type": tk.StringVar(value=TYPE_LABEL[DEFAULT_TYPE]),
            "loops": tk.StringVar(value="0"),
            "offset": tk.StringVar(value="0"),
            "jitter": tk.StringVar(value="0"),
            "smooth": tk.BooleanVar(value=False),
            "topmost": tk.BooleanVar(value=False),
            "minimize": tk.BooleanVar(value=False),
        }
        self.hotkeys = {
            "pick": [0x77],   # F8 拾取坐标
            "toggle": [0x78],  # F9 开始/停止
        }

        self._init_style()
        self._load_icon()
        self._build_ui()
        self._load_params(silent=True)

        self.root.after(60, self._drain)
        self.root.after(80, self._hotkey_tick)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Escape>", lambda e: self._stop() if self.running else None)

    # ----------------------------- 样式 -----------------------------
    def _load_icon(self):
        for base in (getattr(sys, "_MEIPASS", None), BASE_DIR):
            if not base:
                continue
            p = os.path.join(base, "app.ico")
            if os.path.exists(p):
                try:
                    self.root.iconbitmap(default=p)
                    return
                except Exception:
                    pass
    def _init_style(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=PANEL, foreground=TEXT, fieldbackground=CARD,
                     borderwidth=0, font=(FONT, 9))
        st.configure("TCombobox", fieldbackground=CARD, background=PANEL2,
                     foreground=TEXT, arrowcolor=ACCENT, borderwidth=1,
                     relief="flat", padding=(6, 5), selectbackground=PANEL2,
                     selectforeground=ACCENT, lightcolor=BORDER, darkcolor=BORDER)
        st.map("TCombobox",
               fieldbackground=[("readonly", CARD), ("focus", CARD)],
               foreground=[("readonly", TEXT)],
               background=[("readonly", PANEL2)],
               selectbackground=[("readonly", "#26485e")],
               selectforeground=[("readonly", ACCENT)],
               bordercolor=[("focus", ACCENT)])
        st.configure("TScrollbar", background=PANEL2, troughcolor=BG,
                     borderwidth=0, arrowcolor=TEXT_DIM, relief="flat")
        st.map("TScrollbar", background=[("active", "#3b4a5f")])
        st.configure("TCheckbutton", background=PANEL2, foreground=TEXT,
                     indicatorcolor="#0d141d", indicatorbackground="#0d141d",
                     indicatorforeground="#5c718a",
                     borderwidth=0, focuscolor=PANEL2, font=(FONT, 8))
        st.map("TCheckbutton",
               foreground=[("active", ACCENT)],
               indicatorcolor=[("selected", ACCENT), ("!selected", "#0d141d")],
               indicatorbackground=[("selected", ACCENT), ("!selected", "#0d141d")],
               indicatorforeground=[("selected", "#062a33"), ("!selected", "#5c718a")],
               background=[("active", PANEL2)])
        st.configure("Treeview", background=CARD, fieldbackground=CARD,
                     foreground=TEXT, borderwidth=0, relief="flat",
                     rowheight=24, font=(MONO, 9))
        st.configure("Treeview.Heading", background="#2b3748", foreground="#8ce8f8",
                     borderwidth=0, relief="flat", font=(FONT, 8, "bold"),
                     padding=(4, 5))
        st.map("Treeview",
               background=[("selected", "#1d4a5e")],
               foreground=[("selected", "#b9f4ff")])
        st.map("Treeview.Heading", background=[("active", "#35455a")])
        self.root.option_add("*TCombobox*Listbox.background", CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#26485e")
        self.root.option_add("*TCombobox*Listbox.selectForeground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.font", (MONO, 10))

    # ----------------------------- UI -----------------------------
    def _panel(self, parent, **kw):
        f = tk.Frame(parent, bg=PANEL, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=BORDER, **kw)
        return f

    def _section_title(self, parent, text, accent=ACCENT):
        f = tk.Frame(parent, bg=parent["bg"])
        f.pack(fill="x", padx=10, pady=(4, 1))
        tk.Frame(f, bg=accent, width=3, height=12).pack(side="left")
        tk.Label(f, text=text, bg=parent["bg"], fg=TEXT, font=(FONT, 9, "bold")).pack(
            side="left", padx=6)
        return f

    def _btn(self, parent, text, cmd, kind="normal", width=None, padx=8):
        style_map = {
            "normal": (PANEL2, TEXT, "#3a4a60", BORDER),
            "accent": ("#12455a", "#8ceaff", "#1a6b85", ACCENT),
            "danger": ("#3d1c26", "#ffa0b0", "#57242f", "#9c3a4a"),
            "ghost": (BG, TEXT_DIM, "#26313f", BORDER),
        }
        bg, fg, abg, bd = style_map[kind]
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                      activebackground=abg, activeforeground=fg,
                      relief="flat", bd=0, padx=padx, pady=4,
                      font=(FONT, 8, "bold"), cursor="hand2",
                      highlightthickness=1, highlightbackground=bd,
                      highlightcolor=bd)
        if width:
            b.config(width=width)
        b.bind("<Enter>", lambda e, w=b, c=abg: w.config(bg=c))
        b.bind("<Leave>", lambda e, w=b, c=bg: w.config(bg=c))
        return b

    def _card_field(self, parent, label, var, unit=""):
        """标签在上、输入框在下的卡片式输入（两列网格用）"""
        cell = tk.Frame(parent, bg=parent["bg"])
        txt = label + (("  (%s)" % unit) if unit else "")
        tk.Label(cell, text=txt, bg=parent["bg"], fg=TEXT_DIM,
                 font=(FONT, 8)).pack(anchor="w", padx=2, pady=(0, 3))
        vcmd = (self.root.register(lambda p: p == "" or p.isdigit()), "%P")
        ent = tk.Entry(cell, textvariable=var, bg=CARD, fg=TEXT,
                       insertbackground=ACCENT, relief="flat", bd=0,
                       highlightthickness=1, highlightbackground=BORDER,
                       highlightcolor=ACCENT, font=(MONO, 11), justify="center",
                       validate="key", validatecommand=vcmd)
        ent.pack(fill="x", ipady=5)
        return cell

    def _card_combo(self, parent, label, var, values):
        cell = tk.Frame(parent, bg=parent["bg"])
        tk.Label(cell, text=label, bg=parent["bg"], fg=TEXT_DIM,
                 font=(FONT, 8)).pack(anchor="w", padx=2, pady=(0, 3))
        cb = ttk.Combobox(cell, values=values, width=10, state="readonly",
                          textvariable=var, justify="center", font=(MONO, 10))
        cb.pack(fill="x")
        return cell

    def _build_ui(self):
        # ---------- 顶栏 ----------
        head = tk.Frame(self.root, bg=BG, height=44)
        head.pack(fill="x", padx=12, pady=(8, 4))
        head.pack_propagate(False)

        logo = tk.Canvas(head, width=28, height=28, bg=BG, highlightthickness=0)
        logo.pack(side="left")
        for r, c in ((12, "#3c6f80"), (8, "#1f9cb8"), (4, ACCENT)):
            logo.create_oval(14 - r, 14 - r, 14 + r, 14 + r, outline=c, width=2)
        logo.create_oval(12, 12, 16, 16, fill=ACCENT, outline=ACCENT)

        tf = tk.Frame(head, bg=BG)
        tf.pack(side="left", padx=8)
        tk.Label(tf, text="AUTO CLICKER PRO", bg=BG, fg=TEXT,
                 font=(FONT, 12, "bold")).pack(anchor="w")
        tk.Label(tf, text="多坐标批量自动点击", bg=BG, fg=TEXT_DIM,
                 font=(FONT, 8)).pack(anchor="w")

        self._btn(head, "帮助", self._show_help, "ghost", padx=8).pack(
            side="right", padx=(0, 5))

        # ---------- 主体 ----------
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0, minsize=264)
        body.rowconfigure(0, weight=1)

        left = self._panel(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = self._panel(body)
        right.config(width=264)
        right.pack_propagate(False)
        right.grid(row=0, column=1, sticky="nsew")
        self.right_panel = right

        self._build_left(left)
        self._build_right(right)
        self._build_bottom()

    def _build_left(self, parent):
        t = tk.Frame(parent, bg=PANEL)
        t.pack(fill="x", padx=10, pady=(8, 2))
        tk.Frame(t, bg=ACCENT, width=3, height=12).pack(side="left")
        tk.Label(t, text="点击坐标序列", bg=PANEL, fg=TEXT,
                 font=(FONT, 9, "bold")).pack(side="left", padx=6)
        self.count_lbl = tk.Label(t, text="共 0 个", bg=PANEL, fg=TEXT_DIM,
                                  font=(FONT, 8))
        self.count_lbl.pack(side="left", padx=6)
        tk.Label(t, text="双击单元格可编辑", bg=PANEL, fg="#74899f",
                 font=(FONT, 8)).pack(side="right")

        tools = tk.Frame(parent, bg=PANEL)
        tools.pack(fill="x", padx=10, pady=(5, 5))
        row1 = tk.Frame(tools, bg=PANEL)
        row1.pack(fill="x")
        self._btn(row1, "↑上移", self.move_up, "ghost", padx=6).pack(side="left", padx=2)
        self._btn(row1, "↓下移", self.move_down, "ghost", padx=6).pack(side="left", padx=2)
        self._btn(row1, "删除", self.delete_selected, "danger", padx=6).pack(side="left", padx=(8, 2))
        self._btn(row1, "清空", self.clear_all, "danger", padx=6).pack(side="left", padx=2)
        self._btn(row1, "保存", self._save_points_dialog, "accent", padx=6).pack(side="left", padx=(8, 2))
        self._btn(row1, "导入", self._load_points_dialog, "ghost", padx=6).pack(side="left", padx=2)

        # 添加坐标：纯文字提示（无按钮效果），置于坐标框上方
        hint = tk.Frame(parent, bg=PANEL)
        hint.pack(fill="x", padx=10, pady=(0, 3))
        tk.Label(hint, text="把鼠标移到目标位置，按 F8（拾取坐标）即可自动记录坐标",
                 bg=PANEL, fg=ACCENT, font=(FONT, 8)).pack(side="left")

        wrap = tk.Frame(parent, bg=CARD, highlightthickness=1,
                        highlightbackground=BORDER)
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        cols = ("no", "x", "y", "type", "delay")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings",
                                 selectmode="extended", height=8)
        heads = {"no": "#", "x": "X 坐标", "y": "Y 坐标", "type": "点击类型",
                 "delay": "间隔(ms)"}
        widths = {"no": 34, "x": 62, "y": 62, "type": 72, "delay": 72}
        for c in cols:
            self.tree.heading(c, text=heads[c], anchor="center")
            anchor = "center" if c in ("no", "type", "delay") else "center"
            stretch = c in ("type", "delay")
            self.tree.column(c, width=widths[c], anchor=anchor,
                             stretch=stretch, minwidth=34)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        vs.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.tag_configure("odd", background="#1a2431")
        self.tree.bind("<Double-1>", self._on_cell_dblclick)
        self.tree.bind("<Delete>", lambda e: self.delete_selected())
        self.tree.bind("<Button-3>", self._popup_menu)

        self._menu = tk.Menu(self.root, tearoff=0, bg=PANEL2, fg=TEXT,
                             activebackground="#26485e", activeforeground=ACCENT,
                             borderwidth=1, relief="flat", font=(FONT, 8))
        self._menu.add_command(label="删除选中坐标", command=self.delete_selected)
        self._menu.add_command(label="复制该坐标", command=self.duplicate_selected)
        self._menu.add_separator()
        self._menu.add_command(label="清空全部", command=self.clear_all)

        empty = tk.Label(wrap, text="尚未添加坐标\n把鼠标移到目标位置，按 %s 即可自动记录"
                         % format_hotkey(self.hotkeys["pick"]),
                         bg=CARD, fg="#78899d", font=(FONT, 9), justify="center")
        self.empty_lbl = empty

    def _check(self, parent, text, var, cmd=None, padx=0):
        """自绘复选框：未选中为深底空框，选中为青底 + 深色的对勾 √"""
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(side="left", padx=padx)
        cv = tk.Canvas(row, width=16, height=16, bg=parent["bg"],
                       highlightthickness=0, cursor="hand2")
        cv.pack(side="left")
        lbl = tk.Label(row, text=text, bg=parent["bg"], fg=TEXT,
                       font=(FONT, 8), cursor="hand2")
        lbl.pack(side="left", padx=(4, 0))

        def draw(*_a):
            cv.delete("all")
            on = bool(var.get())
            cv.create_rectangle(1, 1, 14, 14, outline=ACCENT if on else "#5c718a",
                                fill=ACCENT if on else "#0d141d", width=1)
            if on:
                # 对勾：短撇 + 长捺
                cv.create_line(3.5, 8.0, 6.0, 10.5, fill="#05262e", width=2,
                               capstyle="round")
                cv.create_line(6.0, 10.5, 12.0, 4.0, fill="#05262e", width=2,
                               capstyle="round")

        def toggle(_e=None):
            var.set(not var.get())
            draw()
            if cmd:
                cmd()

        cv.bind("<Button-1>", toggle)
        lbl.bind("<Button-1>", toggle)
        try:
            var.trace_add("write", draw)
        except Exception:
            pass
        draw()
        return row

    def _build_right(self, parent):
        self._section_title(parent, "运行参数")

        # 数值参数：两列网格，标签在上、输入框在下（卡片风）
        grid = tk.Frame(parent, bg=parent["bg"])
        grid.pack(fill="x", padx=8, pady=(4, 2))
        for c in range(2):
            grid.columnconfigure(c, weight=1, pad=2)

        specs = [
            ("点击间隔", self.vars["interval"], "ms"),
            ("双击间隔", self.vars["dbl_gap"], "ms"),
            ("循环次数", self.vars["loops"], "次"),
        ]
        for i, (label, var, unit) in enumerate(specs):
            cell = self._card_field(grid, label, var, unit)
            r, c = divmod(i, 2)
            cell.grid(row=r, column=c, sticky="ew", padx=2, pady=3)
        type_cell = self._card_combo(grid, "默认点击类型",
                                     self.vars["default_type"],
                                     [l for l, _ in CLICK_TYPES])
        type_cell.grid(row=1, column=1, sticky="ew", padx=2, pady=3)

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=8, pady=5)
        self._section_title(parent, "运行选项", ACCENT2)
        opts = tk.Frame(parent, bg=parent["bg"])
        opts.pack(fill="x", padx=6, pady=(2, 4))
        self._check(opts, "平滑移动", self.vars["smooth"]).pack(side="left", padx=(0, 6))
        self._check(opts, "窗口置顶", self.vars["topmost"],
                    self._apply_topmost).pack(side="left", padx=(0, 6))
        self._check(opts, "启动后最小化", self.vars["minimize"]).pack(side="left")

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=8, pady=5)
        self._section_title(parent, "全局快捷键", ACCENT2)

        self.hk_rows = {}
        for key, desc in (("pick", "拾取鼠标坐标"), ("toggle", "开始 / 停止")):
            r = tk.Frame(parent, bg=parent["bg"])
            r.pack(fill="x", padx=8, pady=2)
            tk.Label(r, text=desc, bg=parent["bg"], fg=TEXT_DIM,
                     font=(FONT, 8)).pack(side="left")
            kb = tk.Label(r, text=format_hotkey(self.hotkeys[key]), bg=CARD,
                          fg=ACCENT2, font=(MONO, 8, "bold"), padx=6, pady=2,
                          highlightthickness=1, highlightbackground=BORDER,
                          cursor="hand2")
            kb.pack(side="right")
            kb.bind("<Button-1>", lambda e, k=key: self._capture_dialog(k))
            self.hk_rows[key] = kb

    def _build_bottom(self):
        bot = self._panel(self.root)
        bot.pack(fill="x", padx=12, pady=(0, 10))
        inner = tk.Frame(bot, bg=PANEL)
        inner.pack(fill="x", padx=10, pady=(8, 8))
        inner.columnconfigure(0, weight=0, minsize=150)  # 开始按钮固定宽度
        inner.columnconfigure(1, weight=1)   # 状态信息占剩余空间
        inner.rowconfigure(0, weight=1)

        self.start_btn = tk.Button(
            inner, text="▶  开 始  (F9)", command=self._toggle,
            bg="#12455a", fg="#8ceaff", activebackground="#1a6b85",
            activeforeground="#ffffff", relief="flat", bd=0, pady=10,
            font=(FONT, 11, "bold"), cursor="hand2",
            highlightthickness=1, highlightbackground=ACCENT,
            highlightcolor=ACCENT)
        self.start_btn.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.start_btn.bind("<Enter>", self._btn_enter)
        self.start_btn.bind("<Leave>", self._btn_leave)

        self.info_lbl = tk.Label(inner, text="就绪 · 0 个坐标 · 已点击 0 次",
                                 bg=PANEL, fg=TEXT_DIM, font=(FONT, 8),
                                 anchor="e")
        self.info_lbl.grid(row=0, column=1, sticky="nsew")

    def _btn_enter(self, _e):
        if self.running:
            self.start_btn.config(bg="#1c6b3e")
        else:
            self.start_btn.config(bg="#1a6b85")

    def _btn_leave(self, _e):
        if self.running:
            self.start_btn.config(bg="#13502f")
        else:
            self.start_btn.config(bg="#12455a")

    # ------------------------- 表格操作 -------------------------
    def _new_iid(self):
        self._iid_seq += 1
        return "i%d" % self._iid_seq

    def add_point(self, x, y, ctype=None, delay=None, quiet=False):
        p = {"x": int(x), "y": int(y),
             "type": ctype or TYPE_CODE.get(self.vars["default_type"].get(), DEFAULT_TYPE),
             "delay": delay, "_iid": self._new_iid()}
        self.points.append(p)
        self.refresh_table()
        self.tree.see(p["_iid"])
        self.tree.selection_set(p["_iid"])
        if not quiet:
            self._flash("已记录坐标 (%d, %d)" % (p["x"], p["y"]))
        self._autosave()

    def add_current(self):
        x, y = cursor_pos()
        self.add_point(x, y)

    def duplicate_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        i = self._index_of(sel[0])
        if i is None:
            return
        src = self.points[i]
        new = dict(src)
        new["_iid"] = self._new_iid()
        self.points.insert(i + 1, new)
        self.refresh_table()
        self._autosave()

    def _index_of(self, iid):
        for i, p in enumerate(self.points):
            if p["_iid"] == iid:
                return i
        return None

    def delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            self._flash("请先选中要删除的坐标")
            return
        self.points = [p for p in self.points if p["_iid"] not in sel]
        self.refresh_table()
        self._flash("已删除 %d 个坐标" % len(sel))
        self._autosave()

    def clear_all(self):
        if not self.points:
            return
        if not messagebox.askyesno("确认", "确定要清空全部 %d 个坐标吗？" % len(self.points)):
            return
        self.points = []
        self.refresh_table()
        self._flash("已清空坐标列表")
        self._autosave()

    def move_up(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            return
        i = self._index_of(sel[0])
        if i is None or i == 0:
            return
        self.points[i - 1], self.points[i] = self.points[i], self.points[i - 1]
        self.refresh_table()
        self.tree.selection_set(sel[0])
        self._autosave()

    def move_down(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            return
        i = self._index_of(sel[0])
        if i is None or i >= len(self.points) - 1:
            return
        self.points[i + 1], self.points[i] = self.points[i], self.points[i + 1]
        self.refresh_table()
        self.tree.selection_set(sel[0])
        self._autosave()

    def refresh_table(self):
        for it in self.tree.get_children():
            self.tree.delete(it)
        for i, p in enumerate(self.points):
            d = p.get("delay")
            self.tree.insert("", "end", iid=p["_iid"],
                             values=(i + 1, p["x"], p["y"],
                                     TYPE_LABEL.get(p["type"], p["type"]),
                                     "全局" if d is None else str(d)),
                             tags=("odd",) if i % 2 else ())
        self.count_lbl.config(text="共 %d 个" % len(self.points))
        self._update_info()
        if self.points:
            self.empty_lbl.place_forget()
        else:
            self.empty_lbl.place(in_=self.tree, relx=0.5, rely=0.5, anchor="center")

    def _popup_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid and iid not in self.tree.selection():
            self.tree.selection_set(iid)
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    def _on_cell_dblclick(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row or col == "#1":
            return
        i = self._index_of(row)
        if i is None:
            return
        x, y, w, h = self.tree.bbox(row, col)
        p = self.points[i]

        if col == "#4":  # 点击类型
            cb = ttk.Combobox(self.tree, values=[l for l, _ in CLICK_TYPES],
                              state="readonly", justify="center", font=(MONO, 10))
            cb.set(TYPE_LABEL.get(p["type"], p["type"]))
            cb.place(x=x, y=y, width=w, height=h)
            cb.focus_set()

            def commit(_e=None):
                val = cb.get()
                if val in TYPE_CODE:
                    p["type"] = TYPE_CODE[val]
                cb.destroy()
                self.refresh_table()
                self._autosave()

            cb.bind("<<ComboboxSelected>>", commit)
            cb.bind("<FocusOut>", commit)
            cb.bind("<Escape>", lambda e: (cb.destroy(), self.refresh_table()))
            return

        key = {"#2": "x", "#3": "y", "#5": "delay"}[col]
        cur = "" if p.get(key) is None else str(p[key])
        vcmd = (self.root.register(
            lambda s: s == "" or (s.lstrip("-").isdigit() and len(s) < 10)), "%P")
        ed = tk.Entry(self.tree, bg="#2c4a5e", fg="#b9f4ff", insertbackground=ACCENT,
                      relief="flat", bd=0, justify="center", font=(MONO, 10),
                      highlightthickness=1, highlightbackground=ACCENT,
                      validate="key", validatecommand=vcmd)
        ed.insert(0, cur)
        ed.select_range(0, "end")
        ed.place(x=x, y=y, width=w, height=h)
        ed.focus_set()

        def commit(_e=None):
            raw = ed.get().strip()
            try:
                if key == "delay":
                    p["delay"] = None if raw == "" else max(0, int(raw))
                else:
                    if raw == "":
                        raise ValueError
                    p[key] = int(raw)
            except ValueError:
                pass
            ed.destroy()
            self.refresh_table()
            self._autosave()

        ed.bind("<Return>", commit)
        ed.bind("<FocusOut>", commit)
        ed.bind("<Escape>", lambda e: (ed.destroy(), self.refresh_table()))

    # ------------------------- 快捷键设置 -------------------------
    def _capture_dialog(self, key):
        if self.capture_open:
            return
        self.capture_open = True
        self.hotkeys_enabled = False
        top = tk.Toplevel(self.root)
        top.title("设置快捷键")
        top.configure(bg=PANEL)
        top.resizable(False, False)
        top.transient(self.root)
        top.geometry("+%d+%d" % (self.root.winfo_rootx() + 160,
                                 self.root.winfo_rooty() + 130))
        top.grab_set()
        top.protocol("WM_DELETE_WINDOW", lambda: finish(None))

        tk.Frame(top, bg=PANEL).pack(fill="x", padx=20, pady=(18, 0))
        tk.Label(top, text="请按下新的快捷键组合", bg=PANEL, fg=TEXT,
                 font=(FONT, 12, "bold")).pack(padx=20, pady=(16, 4))
        tk.Label(top, text="支持 Ctrl / Alt / Shift / Win + 普通键，例如 Ctrl+F8",
                 bg=PANEL, fg=TEXT_DIM, font=(FONT, 9)).pack(padx=20)

        box = tk.Label(top, text="等待按键…", bg=CARD, fg=TEXT_DIM,
                       font=(MONO, 14, "bold"), padx=24, pady=16,
                       highlightthickness=1, highlightbackground=BORDER)
        box.pack(padx=20, pady=18)

        btns = tk.Frame(top, bg=PANEL)
        btns.pack(fill="x", padx=20, pady=(0, 18))
        ok_btn = self._btn(btns, "确定", None, "accent", padx=18)
        ok_btn.config(state="disabled")
        ok_btn.pack(side="right", padx=(8, 0))
        self._btn(btns, "重来", lambda: restart(), "ghost", padx=14).pack(side="right")
        self._btn(btns, "取消", lambda: finish(None), "ghost", padx=14).pack(side="left")

        q = queue.Queue()
        state = {"stop": None, "keys": None}

        def poll():
            stop = state["stop"]
            while stop is not None and not stop.is_set():
                ks = pressed_keys()
                if ks and any(v not in MOD_VKS for v in ks):
                    q.put(sorted(ks))
                    stop.set()
                    return
                time.sleep(0.02)

        def start_poll():
            ev = threading.Event()
            state["stop"] = ev
            threading.Thread(target=poll, daemon=True).start()

        def drain():
            try:
                while True:
                    ks = q.get_nowait()
                    state["keys"] = ks
                    box.config(text=format_hotkey(ks), fg=ACCENT2)
                    ok_btn.config(state="normal")
            except queue.Empty:
                pass
            if top.winfo_exists():
                top.after(50, drain)

        def restart():
            if state["stop"]:
                state["stop"].set()
            state["keys"] = None
            box.config(text="等待按键…", fg=TEXT_DIM)
            ok_btn.config(state="disabled")
            start_poll()

        def finish(keys):
            if state["stop"]:
                state["stop"].set()
            self.capture_open = False
            try:
                top.grab_release()
                top.destroy()
            except tk.TclError:
                pass
            if keys:
                self.hotkeys[key] = keys
                self.hk_rows[key].config(text=format_hotkey(keys))
                if key == "pick":
                    self.refresh_table()
                self._autosave()
            self._rearm = True
            self.hotkeys_enabled = True

        ok_btn.config(command=lambda: finish(state["keys"]))
        start_poll()
        top.after(50, drain)

    # ------------------------- 热键监听 -------------------------
    def _hotkey_tick(self):
        """在主线程轮询检测全局热键（避免跨线程调用 Tk）"""
        try:
            if self.hotkeys_enabled and not self.capture_open:
                ks = pressed_keys()
                if self._rearm:
                    if not ks:
                        self._rearm = False
                else:
                    for name in ("pick", "toggle"):
                        need = self.hotkeys.get(name) or []
                        if not need:
                            continue
                        if set(need).issubset(ks):
                            if not getattr(self, "_hk_held_%s" % name, False):
                                setattr(self, "_hk_held_%s" % name, True)
                                self._on_hotkey(name)
                        else:
                            setattr(self, "_hk_held_%s" % name, False)
        except Exception:
            pass
        self.root.after(50, self._hotkey_tick)

    def _on_hotkey(self, name):
        if name == "pick":
            x, y = cursor_pos()
            self.add_point(x, y)
        elif name == "toggle":
            if self.running:
                self._stop()
            else:
                self._start()

    def _drain(self):
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                tag = msg[0]
                if tag == "flash":
                    self._flash(msg[1])
                elif tag == "select":
                    if msg[1]:
                        self.tree.selection_set(msg[1])
                        self.tree.see(msg[1])
                elif tag == "info":
                    self._update_info()
                elif tag == "stopped":
                    self._after_stop()
        except queue.Empty:
            pass
        self.root.after(60, self._drain)

    # ------------------------- 运行控制 -------------------------
    def _int(self, key, default=0):
        try:
            v = int(self.vars[key].get())
            return max(0, v)
        except (ValueError, tk.TclError):
            return default

    def _toggle(self):
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self):
        if self.running:
            return
        if not self.points:
            messagebox.showwarning("提示", "请先添加至少一个点击坐标。\n"
                                           "把鼠标移到目标位置后按 %s 即可记录。"
                                   % format_hotkey(self.hotkeys["pick"]))
            return
        self.running = True
        self.stop_evt.clear()
        self.stats = {"visits": 0, "cycles": 0}
        self.start_btn.config(text="●  运 行 中", fg=OK, bg="#13502f",
                             highlightbackground=OK)
        if self.vars["minimize"].get():
            self.root.iconify()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def _stop(self):
        if not self.running:
            return
        self.stop_evt.set()
        self.ui_queue.put(("stopped",))

    def _after_stop(self):
        self.running = False
        self.start_btn.config(bg="#12455a", text="▶  开 始  (F9)",
                              fg="#8ceaff", highlightbackground=ACCENT)
        self._update_info()
        try:
            self.root.deiconify()
        except tk.TclError:
            pass

    def _worker_loop(self):
        max_loops = self._int("loops", 0)
        interval = self._int("interval", 1000)
        dbl_gap = self._int("dbl_gap", 60)
        offset = self._int("offset", 0)
        jitter = self._int("jitter", 0)
        smooth = self.vars["smooth"].get()

        cyc = 0
        while not self.stop_evt.is_set():
            cyc += 1
            self.stats["cycles"] = cyc
            pts = [dict(p) for p in self.points]
            if not pts:
                break
            for idx, p in enumerate(pts):
                if self.stop_evt.is_set():
                    break
                self.ui_queue.put(("select", p.get("_iid")))
                px, py = p["x"], p["y"]
                if offset:
                    px += random.randint(-offset, offset)
                    py += random.randint(-offset, offset)
                self.do_click(px, py, p.get("type", DEFAULT_TYPE), smooth, dbl_gap)
                self.stats["visits"] += 1
                self.ui_queue.put(("info",))
                d = p.get("delay")
                wait = interval if d is None else d
                if jitter and wait > 0:
                    wait = max(0, int(wait * (1 + random.uniform(-jitter, jitter) / 100.0)))
                if idx < len(pts) - 1 or max_loops == 0 or cyc < max_loops:
                    if not self.sleep_ms(wait):
                        break
            if max_loops and cyc >= max_loops:
                break
            if self.stop_evt.is_set():
                break
        self.ui_queue.put(("stopped",))

    def sleep_ms(self, ms):
        if ms <= 0:
            return not self.stop_evt.is_set()
        end = time.perf_counter() + ms / 1000.0
        while not self.stop_evt.is_set():
            rest = end - time.perf_counter()
            if rest <= 0:
                break
            time.sleep(min(0.05, rest))
        return not self.stop_evt.is_set()

    @staticmethod
    def do_click(x, y, ctype, smooth, dbl_gap=60):
        if smooth:
            try:
                sx, sy = cursor_pos()
                steps = 12
                for i in range(1, steps + 1):
                    mouse_move(sx + (x - sx) * i / steps, sy + (y - sy) * i / steps)
                    time.sleep(0.006)
            except Exception:
                mouse_move(x, y)
        else:
            mouse_move(x, y)
        time.sleep(0.012)

        if ctype == "left_double":
            mouse_button(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
            time.sleep(max(0.01, dbl_gap / 1000.0))
            mouse_button(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
        elif ctype == "right_double":
            mouse_button(MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
            time.sleep(max(0.01, dbl_gap / 1000.0))
            mouse_button(MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
        elif ctype == "right":
            mouse_button(MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
        else:
            mouse_button(MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)

    # ------------------------- 状态显示 -------------------------
    def _flash(self, text):
        self.info_lbl.config(text=text, fg=ACCENT)
        self.root.after(2200, self._update_info)

    def _update_info(self):
        n = len(self.points)
        self.info_lbl.config(
            text="坐标 %d 个  ·  已执行 %d 次点击  ·  第 %d 轮"
                 % (n, self.stats["visits"], self.stats["cycles"]),
            fg=TEXT_DIM)

    def _apply_topmost(self):
        self.root.attributes("-topmost", bool(self.vars["topmost"].get()))

    # ------------------------- 配置存取（参数与坐标分离） -------------------------
    # 参数：间隔、类型、快捷键、选项等，改动后自动保存到 autoclicker_config.json
    # 坐标：需手动点「保存」才单独存到一个坐标文件，下次「导入」恢复

    def _collect_params(self):
        return {
            "version": 1,
            "settings": {
                "interval": self._int("interval", 1000),
                "dbl_gap": self._int("dbl_gap", 60),
                "loops": self._int("loops", 0),
                "offset": self._int("offset", 0),
                "jitter": self._int("jitter", 0),
                "default_type": TYPE_CODE.get(self.vars["default_type"].get(), DEFAULT_TYPE),
                "smooth": bool(self.vars["smooth"].get()),
                "topmost": bool(self.vars["topmost"].get()),
                "minimize": bool(self.vars["minimize"].get()),
            },
            "hotkeys": {k: list(v) for k, v in self.hotkeys.items()},
        }

    def _collect_points(self):
        return {
            "version": 1,
            "points": [{"x": p["x"], "y": p["y"], "type": p["type"], "delay": p.get("delay")}
                       for p in self.points],
        }

    def _apply_params(self, data):
        s = data.get("settings", {})
        for k in ("interval", "dbl_gap", "loops", "offset", "jitter"):
            if k in s:
                self.vars[k].set(str(s[k]))
        if "default_type" in s:
            self.vars["default_type"].set(TYPE_LABEL.get(s["default_type"], TYPE_LABEL[DEFAULT_TYPE]))
        for k in ("smooth", "topmost", "minimize"):
            if k in s:
                self.vars[k].set(bool(s[k]))
        hk = data.get("hotkeys", {})
        for k in ("pick", "toggle"):
            if hk.get(k):
                self.hotkeys[k] = list(hk[k])
                self.hk_rows[k].config(text=format_hotkey(self.hotkeys[k]))
        self._apply_topmost()

    def _apply_points(self, data):
        self.points = []
        for p in data.get("points", []):
            self.points.append({
                "x": int(p.get("x", 0)), "y": int(p.get("y", 0)),
                "type": p.get("type", DEFAULT_TYPE),
                "delay": p.get("delay", None),
                "_iid": self._new_iid(),
            })
        self.refresh_table()

    def _save_points_dialog(self):
        path = filedialog.asksaveasfilename(
            title="保存坐标", defaultextension=".json",
            initialfile="coordinates.json",
            filetypes=[("JSON 坐标", "*.json"), ("所有文件", "*.*")],
            initialdir=BASE_DIR)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._collect_points(), f, ensure_ascii=False, indent=2)
            self._flash("已保存 %d 个坐标" % len(self.points))
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _load_points_dialog(self):
        path = filedialog.askopenfilename(
            title="载入坐标", filetypes=[("JSON 坐标", "*.json"), ("所有文件", "*.*")],
            initialdir=BASE_DIR)
        if not path:
            return
        self._load_points(path)

    def _load_points(self, path, silent=False):
        if not os.path.exists(path):
            if not silent:
                messagebox.showinfo("提示", "未找到坐标文件")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._apply_points(json.load(f))
            if not silent:
                self._flash("已载入 %d 个坐标" % len(self.points))
        except Exception as e:
            if not silent:
                messagebox.showerror("载入失败", str(e))

    def _load_params(self, path=None, silent=False):
        path = path or CONFIG_PATH
        if not os.path.exists(path):
            if not silent:
                messagebox.showinfo("提示", "未找到参数文件")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._apply_params(json.load(f))
            if not silent:
                self._flash("参数已载入")
        except Exception as e:
            if not silent:
                messagebox.showerror("载入失败", str(e))

    def _autosave(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._collect_params(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------------------------- 其他 -------------------------
    def _show_help(self):
        messagebox.showinfo(
            "使用说明",
            "1. 点击间隔：单位毫秒，1000 = 1 秒；每个坐标还可单独设置间隔（留空则用全局值）。\n\n"
            "2. 添加坐标：把鼠标移到目标位置，按「拾取坐标」快捷键（默认 F8）即可自动记录；"
            "也可点「＋添加当前坐标」按钮。\n\n"
            "3. 坐标管理：双击 X / Y / 间隔 单元格可直接编辑；双击「点击类型」可切换\n"
            "   左键单击 / 右键单击 / 左键双击 / 右键双击；支持上移、下移、删除、清空。\n\n"
            "4. 运行：点「开始」按钮或按 F9 即开始；运行时按钮显示「运行中」(绿色)，\n"
            "   再次点按钮或按 F9 即停止。可设置循环次数（0 = 无限）、坐标随机偏移与\n"
            "   间隔随机抖动以模拟真人操作。\n\n"
            "5. 紧急停止：随时按 F9 或 Esc 即可停止。\n\n"
            "提示：部分以管理员权限运行的程序需要本软件同样以管理员身份运行才能点击。\n"
            "参数（间隔/类型/快捷键等）修改后自动保存到 autoclicker_config.json；\n"
            "坐标不会自动保存、关闭后自动清空。若要保留坐标，在坐标区点「保存」存成单独文件，\n"
            "下次点「导入」恢复即可。")

    def _on_close(self):
        if self.running:
            self.stop_evt.set()
        # 关闭窗口即清空坐标，且坐标不写入配置文件
        self.points = []
        try:
            self.refresh_table()
            self._autosave()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.refresh_table()
        self.empty_lbl.config(text="尚未添加坐标\n把鼠标移到目标位置，按 %s 即可自动记录"
                                   % format_hotkey(self.hotkeys["pick"]))
        self.root.mainloop()


def main():
    app = AutoClicker()
    app.run()


if __name__ == "__main__":
    main()
