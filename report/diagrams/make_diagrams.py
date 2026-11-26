"""Sinh file .drawio cho sơ đồ trong báo cáo. Export PNG: make diagrams."""
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).parent
BOX = "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#256abf;fontSize=12;"
ABC = "rounded=1;whiteSpace=wrap;html=1;fillColor=#e8f1fc;strokeColor=#104281;fontSize=12;fontStyle=1;"
LAYER = "rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#cccccc;align=left;verticalAlign=top;spacingLeft=8;spacingTop=4;fontSize=13;fontStyle=1;fontColor=#555555;"
NOTE = "rounded=0;whiteSpace=wrap;html=1;fillColor=#fffbe6;strokeColor=#d6b656;align=left;spacingLeft=8;fontSize=12;"
EDGE = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeColor=#333333;"
        "fontSize=11;labelBackgroundColor=#ffffff;")
INHERIT = ("edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=0;endSize=10;strokeColor=#104281;"
           "labelBackgroundColor=#ffffff;")
TREE = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=none;strokeColor=#333333;labelBackgroundColor=#ffffff;"


class Doc:
    def __init__(self):
        self.cells, self.n = [], 1

    def box(self, label, x, y, w, h, style=BOX):
        self.n += 1
        self.cells.append(f'<mxCell id="v{self.n}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" '
                          f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return f"v{self.n}"

    def edge(self, a, b, label="", style=EDGE, pts=(), **anchor):
        self.n += 1
        st = style + "".join(f"{k}={v};" for k, v in anchor.items())
        p = "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in pts)
        arr = f'<Array as="points">{p}</Array>' if pts else ""
        self.cells.append(f'<mxCell id="e{self.n}" value="{escape(label)}" style="{st}" edge="1" parent="1" '
                          f'source="{a}" target="{b}"><mxGeometry relative="1" as="geometry">{arr}</mxGeometry></mxCell>')

    def save(self, name):
        body = "".join(self.cells)
        (HERE / f"{name}.drawio").write_text(
            f'<mxfile><diagram name="{name}"><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>'
            f"{body}</root></mxGraphModel></diagram></mxfile>\n", encoding="utf-8")


def architecture():
    d = Doc()
    X = 130                                            # lề trái dành cho tên tầng
    d.box("UI (curses)", 20, 20, 900, 110, LAYER)
    d.box("Editor", 20, 160, 900, 140, LAYER)
    d.box("Core", 20, 330, 900, 280, LAYER)
    app = d.box("ui/app.py<br>vòng lặp, vẽ màn hình", X, 50, 200, 60)
    keys = d.box("ui/keys.py<br>phím → thao tác", X + 260, 50, 200, 60)
    dbg = d.box("ui/debug.py<br>DebugPanel", X + 520, 50, 200, 60)
    ed = d.box("Editor<br>cursor, vùng chọn, tìm, lưu, viewport", X, 200, 200, 70)
    undo = d.box("UndoManager<br>+ Command (Insert/Paste/Delete/Group)", X + 260, 200, 200, 70)
    tr = d.box("TracingBuffer<br>ghi trace (--record)", X + 520, 200, 200, 70)
    fac = d.box("make_buffer(kind, …)<br>factory", X, 380, 200, 60)
    tb = d.box("TextBuffer (ABC)<br>insert · erase · substr<br>line_to_offset · stats", X + 260, 370, 200, 80, ABC)
    impls = [d.box(t, X - 70 + i * 160, 530, 140, 50) for i, t in enumerate(
        ["SplayRope", "TreapRope", "GapBuffer", "PieceTable", "NaiveBuffer<br>(oracle test)"])]
    d.edge(app, keys, "phím", exitX=1, exitY=0.5, entryX=0, entryY=0.5)
    d.edge(app, ed, "visible_lines", exitX=0.5, exitY=1, entryX=0.5, entryY=0)
    d.edge(keys, ed, "gọi thao tác", pts=[(X + 360, 150), (X + 170, 150)], exitX=0.5, exitY=1, entryX=0.85, entryY=0)
    d.edge(ed, undo, "do / undo", exitX=1, exitY=0.5, entryX=0, entryY=0.5)
    d.edge(undo, tb, "insert / erase", exitX=0.5, exitY=1, entryX=0.5, entryY=0)
    d.edge(ed, tb, "đọc", pts=[(X + 170, 320), (X + 300, 320)], exitX=0.85, exitY=1, entryX=0.2, entryY=0)
    d.edge(tr, tb, "bọc", pts=[(X + 620, 390)], exitX=0.5, exitY=1, entryX=1, entryY=0.25)
    d.edge(dbg, tb, "stats()", pts=[(X + 760, 80), (X + 760, 430)], exitX=1, exitY=0.5, entryX=1, entryY=0.75)
    d.edge(fac, tb, "tạo", exitX=1, exitY=0.5, entryX=0, entryY=0.5)
    for b in impls:
        d.edge(b, tb, style=INHERIT, pts=[], exitX=0.5, exitY=0, entryX=0.5, entryY=1)
    d.save("architecture")


def rope():
    d = Doc()
    t = lambda chunk, size, nl, own: f'<b>"{chunk}"</b><br>size {size} · nl {nl}<br>own_nl {own}'
    root = d.box(t("orld", 15, 2, 0), 200, 20, 130, 60)
    c2 = d.box(t("lo\\nw", 7, 1, 1), 60, 130, 130, 60)
    c4 = d.box(t("\\nfoo", 4, 1, 1), 340, 130, 130, 60)
    c1 = d.box(t("hel", 3, 0, 0), 0, 240, 130, 60)
    for a, b in ((root, c2), (root, c4), (c2, c1)):
        d.edge(a, b, style=TREE, exitX=0.5, exitY=1, entryX=0.5, entryY=0)
    d.box("Nội dung: <b>hel · lo\\nw · orld · \\nfoo</b> (thứ tự in-order)<br><br>"
          "Tìm byte ở vị trí 9 (từ gốc):<br>"
          "• 9 ≥ size(trái) = 7 → bỏ qua cây trái, còn 9 − 7 = 2<br>"
          "• 2 &lt; len(\"orld\") = 4 → byte thứ 2 của \"orld\" là <b>l</b><br><br>"
          "Tìm đầu dòng 2 (sau '\\n' thứ 2):<br>"
          "• nl(trái) = 1 &lt; 2, own_nl(gốc) = 0 → sang phải, còn k = 1<br>"
          "• '\\n' đầu của \"\\nfoo\" → offset 7 + 4 + 0 + 1 = 12",
          520, 20, 380, 220, NOTE)
    d.save("rope")


if __name__ == "__main__":
    architecture()
    rope()
