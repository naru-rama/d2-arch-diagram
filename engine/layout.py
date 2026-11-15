"""行と列のマス目で、ノードと枠の位置を決める。

ノードの基準点はアイコンの中心。同じ列では基準点の x を、同じ行では基準点の y をそろえる。
1 列だけの枠は中の基準点の x を、1 行だけの枠は y を自分の基準点にするので、入れ子をまたいでも線がまっすぐ通る。
ノードと詰め物だけの行列は列幅と行の高さを均等にし、真ん中の列が枠の中心に来るようにする。
"""
import math

ICON = 48
GROUP_ICON = 32
FONT_SIZE = 13
LINE_H = 17
LABEL_GAP = 6
PAD = 24
HEADER_GAP = 20
H_GAP = 64
V_GAP = 48
MARGIN = 16
EDGE_FONT = 12
EDGE_LABEL_PAD = 3
EDGE_LABEL_CLEAR = 8
ARROW = 12
BRANCH_ROOM = 48
CLEAR = 24

GROUP_KINDS = {
    "aws-cloud", "region", "vpc", "az", "public-subnet", "private-subnet", "security-group", "account",
    "auto-scaling-group", "corporate-data-center", "server-contents", "ec2-instance-contents", "spot-fleet", "generic",
}
LABEL_ONLY = {"az", "security-group", "generic"}


def kind_of(obj):
    if "spacer" in obj.classes:
        return "spacer"
    if "plain" in obj.classes:
        return "plain"
    if obj.children or "group" in obj.classes or GROUP_KINDS & set(obj.classes):
        return "group"
    return "node"


def group_kind(obj):
    return next((c for c in obj.classes if c in GROUP_KINDS), "generic")


class Layout:
    def __init__(self, diagram, font):
        self.d = diagram
        self.font = font

    def text_width(self, text, size=FONT_SIZE):
        return max((self.font.width(line, size) for line in text.split("\n")), default=0)

    def measure(self, obj):
        obj.kind = kind_of(obj)
        if obj.kind == "spacer":
            obj.w, obj.h, obj.ax, obj.ay = ICON, ICON, ICON / 2, ICON / 2
            return
        if obj.kind == "node":
            lines = obj.label.split("\n") if obj.label else []
            obj.text_w = self.text_width(obj.label) if obj.label else 0
            obj.w = max(ICON, obj.text_w)
            obj.h = ICON + (LABEL_GAP + LINE_H * len(lines) if lines else 0)
            obj.ax, obj.ay = obj.w / 2, ICON / 2
            return
        for child in obj.children:
            self.measure(child)
        self.grid(obj)

    def grid(self, obj):
        kids = obj.children
        n = len(kids)
        cols_attr = obj.attrs.get("grid-columns")
        rows_attr = obj.attrs.get("grid-rows")
        if cols_attr:
            cols = int(cols_attr)
            rows = math.ceil(n / cols)
            cells = [(k, i // cols, i % cols) for i, k in enumerate(kids)]
        elif rows_attr:
            rows = int(rows_attr)
            cols = math.ceil(n / rows)
            cells = [(k, i % rows, i // rows) for i, k in enumerate(kids)]
        elif self.d.direction == "right":
            rows, cols = 1, n
            cells = [(k, 0, i) for i, k in enumerate(kids)]
        else:
            rows, cols = n, 1
            cells = [(k, i, 0) for i, k in enumerate(kids)]
        rows, cols = max(rows, 1), max(cols, 1)
        h_gap = float(obj.attrs.get("horizontal-gap", H_GAP))
        v_gap = float(obj.attrs.get("vertical-gap", V_GAP))

        left = [0.0] * cols
        right = [0.0] * cols
        top = [0.0] * rows
        bottom = [0.0] * rows
        for k, r, c in cells:
            left[c] = max(left[c], k.ax)
            right[c] = max(right[c], k.w - k.ax)
            top[r] = max(top[r], k.ay)
            bottom[r] = max(bottom[r], k.h - k.ay)
        if cells and all(k.kind in ("node", "spacer") for k, _, _ in cells):
            left = [max(left)] * cols
            right = [max(right)] * cols
            top = [max(top)] * rows
            bottom = [max(bottom)] * rows

        widest = max([h_gap] + [self.label_room(cells, c) for c in range(cols - 1)])
        h_gaps = [widest] * (cols - 1) + [0.0]
        col_x, x = [], 0.0
        for c in range(cols):
            col_x.append(x)
            x += left[c] + right[c] + h_gaps[c]
        row_y, y = [], 0.0
        for r in range(rows):
            row_y.append(y)
            y += top[r] + bottom[r] + v_gap
        content_w = x
        content_h = y - v_gap if rows else 0

        if obj.kind == "plain" or obj.id == "":
            pad, head, header_w = 0.0, 0.0, 0.0
        else:
            pad = PAD
            label_w = self.text_width(obj.label) if obj.label else 0
            if group_kind(obj) in LABEL_ONLY:
                head, header_end = LINE_H + HEADER_GAP, 10 + label_w
            else:
                head, header_end = GROUP_ICON + HEADER_GAP, GROUP_ICON + 10 + label_w
            header_w = header_end + PAD
            if cols == 1 and self.d.direction == "down":
                header_w = max(header_w, 2 * (header_end + CLEAR) + ICON)
        obj.w = max(content_w + 2 * pad, header_w)
        offset_x = (obj.w - content_w) / 2
        obj.h = head + content_h + pad if head else content_h + 2 * pad
        offset_y = head if head else pad
        obj.ax = offset_x + (left[0] if cols == 1 else content_w / 2)
        obj.ay = offset_y + (top[0] if rows == 1 else content_h / 2)
        for k, r, c in cells:
            k.rel_x = offset_x + col_x[c] + left[c] - k.ax
            k.rel_y = offset_y + row_y[r] + top[r] - k.ay

    def label_room(self, cells, c):
        """列 c と c+1 の間を横切る矢印のラベルが、枠の外に収まる幅。"""
        left = {d for k, _, col in cells if col == c for d in descendants(k)}
        right = {d for k, _, col in cells if col == c + 1 for d in descendants(k)}
        widths = [
            self.font.width(e.label, EDGE_FONT) + 2 * EDGE_LABEL_PAD
            for e in self.d.edges
            if e.label and ({e.src, e.dst} & left) and ({e.src, e.dst} & right)
        ]
        return max(widths) + 2 * EDGE_LABEL_CLEAR + ARROW + BRANCH_ROOM if widths else 0.0

    def place(self, obj, x, y):
        obj.x, obj.y = x, y
        for child in obj.children:
            self.place(child, x + child.rel_x, y + child.rel_y)

    def run(self):
        root = self.d.root
        root.kind = "plain"
        for child in root.children:
            self.measure(child)
        self.grid(root)
        self.place(root, MARGIN, MARGIN)
        return root.w + 2 * MARGIN, root.h + 2 * MARGIN


def icon_box(obj):
    cx = obj.x + obj.ax
    return [cx - ICON / 2, obj.y, cx + ICON / 2, obj.y + ICON]


def label_box(obj):
    if not obj.label:
        return None
    cx = obj.x + obj.ax
    lines = obj.label.count("\n") + 1
    half = max(obj.text_w, ICON) / 2
    return [cx - half, obj.y + ICON + 2, cx + half, obj.y + ICON + LABEL_GAP + LINE_H * lines + 2]


def header_box(obj, font):
    label_w = font.width(obj.label, FONT_SIZE) if obj.label else 0
    if group_kind(obj) in LABEL_ONLY:
        return [obj.x, obj.y, obj.x + 10 + label_w + 6, obj.y + LINE_H + 8]
    return [obj.x, obj.y, obj.x + GROUP_ICON + 10 + label_w + 6, obj.y + GROUP_ICON]


def header_band(obj):
    if group_kind(obj) in LABEL_ONLY:
        return LINE_H + HEADER_GAP
    return GROUP_ICON + HEADER_GAP


def descendants(obj):
    yield obj.id
    for child in obj.children:
        yield from descendants(child)
