# -*- coding: utf-8 -*-
"""按 auto_clicker.py 的真实配色与布局，渲染一张高保真界面预览图 (preview.png)。
仅用 Pillow + 系统雅黑字体，无需运行 GUI（沙箱无显示器）。"""
from PIL import Image, ImageDraw, ImageFont

# ---- 配色（与 auto_clicker.py 严格一致）----
BG = "#1a222e"
PANEL = "#222c3a"
PANEL2 = "#2c3849"
CARD = "#1e2734"
BORDER = "#3a4759"
ACCENT = "#22d3ee"
ACCENT2 = "#a78bfa"
TEXT = "#e9f1fa"
TEXT_DIM = "#9fb3c8"
TITLEBAR = "#141b25"

FONT = "C:/Windows/Fonts/msyh.ttc"

def F(size, bold=False):
    return ImageFont.truetype(FONT, size)

W, H = 642, 480
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

def rr(box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)

def txt(pos, s, size, fill, anchor="lm", bold=False):
    d.text(pos, s, font=F(size), fill=fill, anchor=anchor)

# ---------------- 标题栏 ----------------
rr([0, 0, W, 30], 0, fill=TITLEBAR)
# logo
rr([14, 8, 28, 22], 4, fill=ACCENT)
d.polygon([(18, 11), (18, 19), (25, 15)], fill="#062a33")
txt((36, 15), "Auto Clicker Pro  ·  鼠标自动点击器", 12, TEXT, anchor="lm")
# 帮助按钮
rr([W - 12 - 48, 6, W - 12, 24], 4, fill=PANEL2, outline=BORDER)
txt((W - 12 - 24, 15), "帮助", 9, TEXT_DIM, anchor="mm")

# ---------------- 面板坐标 ----------------
BTM_Y = 420
right = [366, 36, 630, BTM_Y]      # 右参数栏
left = [12, 36, 358, BTM_Y]        # 左坐标栏
rr(right, 6, fill=PANEL, outline=BORDER)
rr(left, 6, fill=PANEL, outline=BORDER)

# ================= 右栏 =================
RX0, RY0, RX1, RY1 = right
rin_x = RX0 + 8
rin_w = (RX1 - RX0) - 16

def section(title, y, accent=ACCENT):
    rr([rin_x, y, rin_x + 3, y + 12], 1, fill=accent)
    txt((rin_x + 9, y + 6), title, 9, TEXT, anchor="lm")

section("运行参数", RY0 + 10)
# 卡片网格
card_w = (rin_w - 4) // 2
card_h = 46
gx0 = rin_x
gy0 = RY0 + 26
positions = [(gx0, gy0), (gx0 + card_w + 4, gy0),
             (gx0, gy0 + card_h + 4), (gx0 + card_w + 4, gy0 + card_h + 4)]
cards = [
    ("点击间隔", "1000", "ms"),
    ("双击间隔", "60", "ms"),
    ("循环次数", "0", "次"),
    ("默认点击类型", "左键单击", None),
]
for (cx, cy), (lab, val, unit) in zip(positions, cards):
    rr([cx, cy, cx + card_w, cy + card_h], 5, fill=CARD, outline=BORDER)
    txt((cx + 8, cy + 8), lab, 9, TEXT_DIM, anchor="lm")
    if unit:
        txt((cx + card_w - 8, cy + 30), unit, 9, TEXT_DIM, anchor="rm")
        txt((cx + 8, cy + 30), val, 12, TEXT, anchor="lm")
    else:
        # 下拉样式
        rr([cx + 6, cy + 24, cx + card_w - 6, cy + card_h - 6], 3, fill=PANEL2, outline=BORDER)
        txt((cx + 12, cy + 35), val, 11, TEXT, anchor="lm")
        d.polygon([(cx + card_w - 16, cy + 33), (cx + card_w - 8, cy + 33),
                   (cx + card_w - 12, cy + 39)], fill=ACCENT)

# 分隔线
dy = gy0 + 2 * (card_h + 4) + 6
rr([rin_x, dy, RX1 - 8, dy + 1], 0, fill=BORDER)
section("运行选项", dy + 10, ACCENT2)
# 复选框
def checkbox(x, y, label, checked=False):
    rr([x, y, x + 14, y + 14], 3, fill=ACCENT if checked else "#0d141d",
       outline=ACCENT if checked else "#5c718a", width=1)
    if checked:
        d.line([(x + 3, y + 8), (x + 6, y + 11)], fill="#05262e", width=2)
        d.line([(x + 6, y + 11), (x + 11, y + 4)], fill="#05262e", width=2)
    txt((x + 20, y + 7), label, 9, TEXT, anchor="lm")
cy = dy + 26
checkbox(rin_x, cy, "平滑移动")
checkbox(rin_x + 76, cy, "窗口置顶")
checkbox(rin_x + 152, cy, "启动后最小化")

dy2 = cy + 28
rr([rin_x, dy2, RX1 - 8, dy2 + 1], 0, fill=BORDER)
section("全局快捷键", dy2 + 10, ACCENT2)
def hotkey(y, desc, key):
    txt((rin_x, y + 8), desc, 9, TEXT_DIM, anchor="lm")
    kw = 34
    rr([RX1 - 8 - kw, y, RX1 - 8, y + 18], 3, fill=CARD, outline=BORDER)
    txt((RX1 - 8 - kw / 2, y + 9), key, 9, ACCENT2, anchor="mm")
hotkey(dy2 + 26, "拾取鼠标坐标", "F8")
hotkey(dy2 + 50, "开始 / 停止", "F9")

# ================= 左栏 =================
LX0, LY0, LX1, LY1 = left
lin_x = LX0 + 10
lin_w = (LX1 - LX0) - 20
# 标题行
rr([lin_x, LY0 + 8, lin_x + 3, LY0 + 20], 1, fill=ACCENT)
txt((lin_x + 9, LY0 + 14), "点击坐标序列", 9, TEXT, anchor="lm")
txt((lin_x + 92, LY0 + 14), "共 0 个", 9, TEXT_DIM, anchor="lm")
txt((LX1 - 10, LY0 + 14), "双击单元格可编辑", 9, "#74899f", anchor="rm")
# 工具栏
by = LY0 + 28
btns = [("↑上移", False), ("↓下移", False), ("删除", True), ("清空", True), ("保存", "accent"), ("导入", False)]
bx = lin_x
fnt_btn = F(9)
for label, danger in btns:
    if danger == "accent":
        bg, fg, ol = "#12455a", "#8ceaff", ACCENT
    elif danger:
        bg, fg, ol = "#3d1c26", "#ffa0b0", "#9c3a4a"
    else:
        bg, fg, ol = PANEL2, TEXT, BORDER
    tw = int(d.textbbox((0, 0), label, font=fnt_btn)[2]) + 16
    rr([bx, by, bx + tw, by + 22], 3, fill=bg, outline=ol)
    txt((bx + tw / 2, by + 11), label, 9, fg, anchor="mm")
    bx += tw + 4
# 提示文字
hy = by + 30
txt((lin_x, hy + 7), "把鼠标移到目标位置，按 F8（拾取坐标）即可自动记录坐标", 9, ACCENT, anchor="lm")

# 表格
ty = hy + 18
th = LY1 - 10 - ty
tw_x0 = lin_x
tw_w = lin_w
rr([tw_x0, ty, tw_x0 + tw_w, ty + th], 4, fill=CARD, outline=BORDER)
# 表头
heads = ["#", "X 坐标", "Y 坐标", "点击类型", "间隔(ms)"]
cw = [34, 62, 62, 72, 72]
# 加上滚动条占位，整体右移对齐
cx = tw_x0 + 4
hyy = ty + 4
hh = 22
d.rectangle([tw_x0 + 2, ty + 2, tw_x0 + tw_w - 2, ty + 2 + hh], fill="#2b3748")
for h, w in zip(heads, cw):
    txt((cx + w / 2, ty + 2 + hh / 2), h, 9, "#8ce8f8", anchor="mm")
    cx += w
# 示例数据行
rows = [("1", "1650", "1176", "左键单击", "100")]
ry = ty + 2 + hh + 2
for r in rows:
    cx = tw_x0 + 4
    for i, (val, w) in enumerate(zip(r, cw)):
        txt((cx + w / 2, ry + 11), val, 9, TEXT, anchor="mm")
        cx += w
    d.line([tw_x0 + 2, ry + 22, tw_x0 + tw_w - 2, ry + 22], fill=BORDER)
# 滚动条（装饰）
sb_x = tw_x0 + tw_w - 12
rr([sb_x, ty + 2, sb_x + 10, ty + th - 2], 4, fill=PANEL2)

# ================= 底部 =================
rr([12, BTM_Y, 630, 470], 6, fill=PANEL, outline=BORDER)
# 开始按钮（固定宽度）
sb_w = 150
sb_x = 22
rr([sb_x, BTM_Y + 8, sb_x + sb_w, 470 - 8], 5, fill="#12455a", outline=ACCENT)
# 手绘播放三角（避免依赖字体的 ▶）
c_y = (BTM_Y + 470) // 2
txt_x = sb_x + sb_w / 2 + 6  # 给三角留位置
d.polygon([(sb_x + 42, c_y - 5), (sb_x + 42, c_y + 5), (sb_x + 50, c_y)], fill="#8ceaff")
txt((txt_x, c_y), "开 始  (F9)", 11, "#8ceaff", anchor="mm")
# 状态信息（右对齐）
txt((620, (BTM_Y + 470) / 2), "就绪 · 0 个坐标 · 已点击 0 次", 9, TEXT_DIM, anchor="rm")

img.save("preview.png")
print("saved preview.png", img.size)
