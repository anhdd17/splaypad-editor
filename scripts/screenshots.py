"""Chụp ảnh màn hình SplayPad cho README: chạy app thật trong pty, dựng màn hình bằng pyte, vẽ ra PNG.

    .venv/bin/python scripts/screenshots.py          # → docs/img/*.png
"""

import shutil
import unicodedata
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from ptyterm import PtyApp  # noqa: E402

OUT = ROOT / "docs" / "img"
FONTS = ["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]
WIDE_FONTS = ["/System/Library/Fonts/Hiragino Sans GB.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]
BG, FG = (30, 32, 38), (215, 218, 224)
PALETTE = {                                             # màu ANSI kiểu terminal nền tối
    "black": (40, 42, 48), "red": (224, 80, 80), "green": (120, 200, 120), "brown": (229, 192, 90),
    "yellow": (229, 192, 90), "blue": (52, 101, 164), "magenta": (190, 120, 200), "cyan": (80, 190, 200),
    "white": (225, 225, 225), "brightblack": (110, 115, 125),
}


def color(name, default):
    if name == "default":
        return default
    if isinstance(name, str) and len(name) == 6:
        try:
            return tuple(int(name[i : i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return PALETTE.get(name, default)


def render(app: PtyApp, path: Path, scale: int = 2) -> None:
    font = next((ImageFont.truetype(f, 13 * scale) for f in FONTS if Path(f).exists()), ImageFont.load_default())
    wide = next((ImageFont.truetype(f, 13 * scale) for f in WIDE_FONTS if Path(f).exists()), font)
    cw, ch = int(font.getlength("M")), int(15 * scale * 1.2)
    scr = app.screen
    img = Image.new("RGB", (cw * scr.columns + 16 * scale, ch * scr.lines + 16 * scale), BG)
    d = ImageDraw.Draw(img)
    pad = 8 * scale
    for y in range(scr.lines):
        row = scr.buffer[y]
        for x in range(scr.columns):
            c = row[x]
            fg, bg = color(c.fg, FG), color(c.bg, BG)
            if c.reverse:
                fg, bg = bg, fg
            if c.bold and c.fg in PALETTE:
                fg = tuple(min(255, v + 30) for v in fg)
            px, py = pad + x * cw, pad + y * ch
            if bg != BG:
                d.rectangle([px, py, px + cw - 1, py + ch - 1], fill=bg)
            if c.data.strip():
                f = wide if unicodedata.east_asian_width(c.data[0]) in "WF" else font
                d.text((px, py + scale), c.data, font=f, fill=fg)
    cx, cy = scr.cursor.x, scr.cursor.y
    if not scr.cursor.hidden:
        d.rectangle([pad + cx * cw, pad + cy * ch + ch - 3 * scale, pad + (cx + 1) * cw - 1, pad + cy * ch + ch - 1],
                    fill=(240, 240, 240))
    img.save(path)
    print(path)


def sample(dirpath: Path) -> Path:
    p = dirpath / "server.log"
    lines = []
    for i in range(1, 400):
        lvl = ("INFO", "INFO", "WARN", "INFO", "ERROR")[i % 5]
        lines.append(f"2026-11-26T10:{i // 60:02d}:{i % 60:02d}.{i * 37 % 1000:03d} {lvl:<5} [worker-{i % 8}] "
                     f"request id={1000 + i} path=/api/v1/items/{i * 13 % 997} status={200 if i % 5 else 500} "
                     f"latency_ms={i * 7 % 300}")
    lines[11] = "\tnote: tab stop và chữ rộng – 日本語 テキスト ✓"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())
    env = {"XDG_STATE_HOME": str(tmp / "state"), "SPLAYPAD_CLIPBOARD": "internal"}
    try:
        f = sample(tmp)
        app = PtyApp([f], cols=110, rows=28, env=env)
        app.wait_for("F1")
        app.send(*["\x1bOB"] * 11, *["\x1bOC"] * 4, *["\x1b[1;2C"] * 9)   # dòng 12, Shift+→ chọn "tab stop"
        render(app, OUT / "editor.png")
        app.send("\x1b", "\x1bOQ", *["\x1bOB"] * 30, "x")  # F2: debug panel, cuộn xuống, gõ một ký tự
        render(app, OUT / "debug-panel.png")
        app.send("\x06", "status=500")                   # Ctrl-F: ô tìm kiếm
        render(app, OUT / "find.png")
        app.send("\x1b", "\x1bOP")                       # F1: trợ giúp
        render(app, OUT / "help.png")
        app.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
