"""行と列のマス目で、ノードと枠の位置を決める。

ノードの基準点はアイコンの中心。同じ列では基準点の x を、同じ行では基準点の y をそろえる。
列（行）が奇数の枠は、真ん中の列（行）の基準線を自分の基準点にするので、入れ子をまたいでも線がまっすぐ通る。
ノードと詰め物だけの行列は列幅と行の高さを均等にし、真ん中の列が枠の中心に来るようにする。
見えない枠に並べたノードは、列（行）ごとに、同じ列（行）の隣のマスにいる矢印の相手に寄せる。
同じ列の枠は幅を、同じ行の枠は高さをそろえ、列（行）の数が同じなら中の列幅（行の高さ）も共有する。
"""
import math
from collections import defaultdict

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
NEAR = 16

GROUP_KINDS = {
    "aws-cloud", "region", "vpc", "az", "public-subnet", "private-subnet", "security-group", "account",
    "auto-scaling-group", "corporate-data-center", "server-contents", "ec2-instance-contents", "spot-fleet", "generic",
    "k8s-cluster", "k8s-namespace", "k8s-node",
}
# 中に要素があれば枠、なければアイコンのノードになる種類
FRAME_OR_NODE = {"k8s-pod", "k8s-deployment"}
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
    return next((c for c in obj.classes if c in GROUP_KINDS | FRAME_OR_NODE), "generic")


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
        self.share_tracks(cells)
        self.align_stacks(cells)
        self.clear_headers(cells)

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

        floor = getattr(obj, "floor", {})
        if "x" in floor:
            left = [max(a, b) for a, b in zip(left, floor["x"][0])]
            right = [max(a, b) for a, b in zip(right, floor["x"][1])]
            h_gap = max(h_gap, floor["x"][2])
        if "y" in floor:
            top = [max(a, b) for a, b in zip(top, floor["y"][0])]
            bottom = [max(a, b) for a, b in zip(bottom, floor["y"][1])]
            v_gap = max(v_gap, floor["y"][2])
        self.stretch_frames(cells, rows, cols)

        widest = max([h_gap] + [self.label_room(cells, c) for c in range(cols - 1)])
        obj.tracks = {"x": (left, right, widest), "y": (top, bottom, v_gap)}
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
        mc, mr = cols // 2, rows // 2
        obj.ax = offset_x + (col_x[mc] + left[mc] if cols % 2 else content_w / 2)
        obj.ay = offset_y + (row_y[mr] + top[mr] if rows % 2 else content_h / 2)
        for k, r, c in cells:
            k.rel_x = offset_x + col_x[c] + left[c] - k.ax
            k.rel_y = offset_y + row_y[r] + top[r] - k.ay
        if obj.kind == "plain" and kids and all(k.kind in ("node", "spacer") for k in kids):
            obj.loose = cells
            obj.gaps = {"y": v_gap, "x": widest}

    def share_tracks(self, cells):
        """同じ列に縦に並べた枠どうしで列の数が同じなら列幅と間隔を、同じ行に横に並べた枠どうしで行の数が同じなら行の高さと間隔を共有する。"""
        for axis in ("x", "y"):
            groups = defaultdict(list)
            for k, r, c in cells:
                n = len(k.tracks[axis][0]) if k.kind == "group" else 0
                if n > 1:
                    groups[(c if axis == "x" else r, n)].append(k)
            for (_, n), members in sorted(groups.items()):
                if len(members) < 2:
                    continue
                before = [max(k.tracks[axis][0][i] for k in members) for i in range(n)]
                after = [max(k.tracks[axis][1][i] for k in members) for i in range(n)]
                gap = max(k.tracks[axis][2] for k in members)
                for k in members:
                    k.floor = {**getattr(k, "floor", {}), axis: (before, after, gap)}
                    self.grid(k)

    def align_stacks(self, cells):
        """見えない枠のマス目（ノードと詰め物だけ。枠の中に入れ子になったものも含む）の列と行を、
        同じ列（行）の隣のマスにいる矢印の相手の位置に寄せる。

        列（行）の順と最小の間隔は保つ。ぶつかるときは、相手が 1 か所の列（行）をちょうどそろえ、相手が複数の列（行）や枠を譲らせる
        （少しだけずれた線は、はっきりずれた線より見苦しいため）。相手のいない列（行）は元の位置に弱く留める。
        L 字にするために出入りする辺を指定した矢印は、そろえる相手にしない。
        """
        for cell, r, c in cells:
            for loose in [d for d in walk(cell) if getattr(d, "loose", None)]:
                for axis in ("x", "y"):
                    line = [k for k, r2, c2 in cells if k is not cell and (c2 == c if axis == "x" else r2 == r)]
                    where = {d.id: (offset_in(k, d, axis), d) for k in line for d in walk(k) if d.kind in ("node", "group")}
                    if where and self.align_loose(cell, loose, axis, where):
                        parent = loose.parent
                        while parent is not cell.parent:
                            self.grid(parent)
                            parent = parent.parent

    def align_loose(self, cell, loose, axis, where):
        across = {"left", "right"} if axis == "x" else {"top", "bottom"}
        units = defaultdict(list)
        for k, r2, c2 in loose.loose:
            units[c2 if axis == "x" else r2].append(k)
        order = sorted(units)
        base = [offset_in(cell, units[u][0], axis) for u in order]
        targets, weights, anchored = [], [], []
        for u, b in zip(order, base):
            ids = {k.id for k in units[u]}
            partners, frames = [], []
            for e in self.d.edges:
                other = e.dst if e.src in ids else e.src
                if (e.src in ids) == (e.dst in ids) or other not in where:
                    continue
                if {cl.split("-", 1)[1] for cl in e.classes if cl.startswith(("from-", "to-"))} & across:
                    continue
                pos, obj = where[other]
                (frames if obj.kind == "group" else partners).append(pos)
            spots = partners or frames
            anchored.append(bool(partners))
            targets.append(sum(spots) / len(spots) if spots else b)
            weights.append(1e-3 if not spots else 1.0 if partners and max(partners) - min(partners) < 1 else 0.5)
        if all(w < 1e-2 for w in weights):
            return False
        before = [max(extent(k, axis)[0] for k in units[u]) for u in order]
        after = [max(extent(k, axis)[1] for k in units[u]) for u in order]
        cum = [0.0]
        for a, b in zip(after, before[1:]):
            cum.append(cum[-1] + a + loose.gaps[axis] + b)
        placed = [z + o for z, o in zip(isotonic([t - o for t, o in zip(targets, cum)], weights), cum)]
        placed = self.settle(placed, weights, anchored, cum, where, axis)
        shift = offset_in(cell, loose, axis)
        placed = [p - shift for p in placed]
        lo = min(p - b for p, b in zip(placed, before))
        hi = max(p + a for p, a in zip(placed, after))
        for u, p in zip(order, placed):
            for k in units[u]:
                if axis == "x":
                    k.rel_x = p - lo - k.ax
                else:
                    k.rel_y = p - lo - k.ay
        if axis == "x":
            loose.ax, loose.w = -lo, hi - lo
        else:
            loose.ay, loose.h = -lo, hi - lo
        return True

    def settle(self, placed, weights, anchored, cum, where, axis):
        """相手が 1 か所に決まらない列（行）を近くにあるノードの線にそろえ、相手のノードがない列（行）は枠線から離す
        （ほぼそろった線と、枠線に沿う線を作らない）。

        後ろの列（行）は押し出すだけで、ちょうどそろえた列（行）が動くなら、その調整はやめる。
        """
        lines = [pos for pos, obj in where.values() if obj.kind == "node"]
        walls = [w for pos, obj in where.values() if obj.kind == "group" for w in (pos - extent(obj, axis)[0], pos + extent(obj, axis)[1])]
        for i in range(len(placed)):
            if weights[i] >= 1:
                continue
            p = placed[i]
            near = [q for q in lines if abs(q - p) < NEAR]
            if near:
                p = min(near, key=lambda q: (abs(q - p), q))
            for wall in sorted(walls) if not anchored[i] else []:
                if abs(p - wall) < CLEAR + 8:
                    p = wall + CLEAR + 8
            low = placed[i - 1] + (cum[i] - cum[i - 1]) if i else -1e9
            p = max(p, low)
            moved = list(placed)
            moved[i] = p
            for j in range(i + 1, len(moved)):
                moved[j] = max(moved[j], moved[j - 1] + (cum[j] - cum[j - 1]))
            if all(abs(a - b) < 0.01 for a, b, w in zip(moved, placed, weights) if w >= 1):
                placed = moved
        return placed

    def clear_headers(self, cells):
        """下の向きの図で、上から入る線が枠の見出しを貫くなら、枠を見出しの側（左）に広げて線から見出しを外す。"""
        if self.d.direction != "down":
            return
        for frame, r, c in cells:
            if frame.kind != "group":
                continue
            column = [(k, r2) for k, r2, c2 in cells if c2 == c]
            above = {d.id for k, r2 in column if r2 < r for d in walk(k)}
            below = {d.id: k for k, r2 in column if r2 >= r for d in walk(k) if d.kind == "node"}
            inside = {d.id for d in walk(frame)}
            end = header_end(frame, self.font) + CLEAR
            need = 0.0
            frames_below = {d.id: k for k, r2 in column if r2 >= r for d in walk(k) if d.kind == "group"}
            cell_of = {d.id: k for k, _ in column for d in walk(k)}
            for e in self.d.edges:
                if any(cl in e.classes for cl in ("to-left", "to-right", "to-bottom")) or e.src in inside:
                    continue
                if e.src in cell_of and e.src not in above:
                    continue
                if e.dst in below:
                    x = offset_in(below[e.dst], self.d.objects[e.dst], "x") - ICON / 2
                elif e.dst in frames_below and e.src in above:
                    # 枠につなぐ線は、上の相手からまっすぐ下りてくる
                    x = offset_in(cell_of[e.src], self.d.objects[e.src], "x") - ICON / 2
                else:
                    continue
                left = -frame.ax
                if x + ICON > left and x < left + end:
                    need = max(need, left + end - x)
            if need > 0:
                for child in frame.children:
                    child.rel_x += need
                frame.ax += need
                frame.w += need

    def stretch_frames(self, cells, rows, cols):
        frames = [(k, r, c) for k, r, c in cells if k.kind == "group"]
        for axis, n in (("x", cols), ("y", rows)):
            for i in range(n):
                members = [k for k, r, c in frames if (c if axis == "x" else r) == i]
                if len(members) < 2:
                    continue
                before = max(extent(k, axis)[0] for k in members)
                after = max(extent(k, axis)[1] for k in members)
                for k in members:
                    shift = before - extent(k, axis)[0]
                    for child in k.children:
                        if axis == "x":
                            child.rel_x += shift
                        else:
                            child.rel_y += shift
                    if axis == "x":
                        k.ax, k.w = before, before + after
                    else:
                        k.ay, k.h = before, before + after

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


def header_end(obj, font):
    """枠の左端から見出しの文字の右端まで。"""
    label_w = font.width(obj.label, FONT_SIZE) if obj.label else 0
    if group_kind(obj) in LABEL_ONLY:
        return 10 + label_w
    return GROUP_ICON + 10 + label_w


def header_band(obj):
    if group_kind(obj) in LABEL_ONLY:
        return LINE_H + HEADER_GAP
    return GROUP_ICON + HEADER_GAP


def walk(obj):
    yield obj
    for child in obj.children:
        yield from walk(child)


def extent(obj, axis):
    """基準点から手前と奥への大きさ。"""
    if axis == "x":
        return obj.ax, obj.w - obj.ax
    return obj.ay, obj.h - obj.ay


def anchor_in(parent, obj, axis):
    """parent の基準点から見た、子 obj の基準点の位置。"""
    if axis == "x":
        return obj.rel_x + obj.ax - parent.ax
    return obj.rel_y + obj.ay - parent.ay


def offset_in(top, obj, axis):
    """top の基準点から見た、子孫 obj の基準点の位置。"""
    pos = obj.ax if axis == "x" else obj.ay
    while obj is not top:
        pos += obj.rel_x if axis == "x" else obj.rel_y
        obj = obj.parent
    return pos - (top.ax if axis == "x" else top.ay)


def isotonic(targets, weights):
    """前から順に減らない値の列。順序に反する隣どうしは 1 つの塊にまとめ、塊の中でいちばん重いもの（同じなら前のもの）の目標に合わせる。"""
    blocks = []
    for t, w in zip(targets, weights):
        blocks.append([t, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            t2, w2, n = blocks.pop()
            if w2 > blocks[-1][1]:
                blocks[-1][0], blocks[-1][1] = t2, w2
            blocks[-1][2] += n
    out = []
    for t, _, n in blocks:
        out += [t] * n
    return out


def descendants(obj):
    yield obj.id
    for child in obj.children:
        yield from descendants(child)
