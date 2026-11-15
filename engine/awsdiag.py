"""D2 の書き方で書いた AWS 構成図を、決まった計算だけで SVG と PNG にする。

usage:
  awsdiag.py render <in.d2> <out dir>   SVG・確認用 PNG・チェック結果を書き出す
  awsdiag.py icons [検索語]             使えるアイコン名を表示する
同じ入力からは常に同じ SVG が出る（乱数や探索の打ち切りを使わない）。
"""
import base64
import html
import io
import itertools
import json
import os
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("AWSDIAG_ROOT", "/opt/aws-diagram")
sys.path.insert(0, HERE)

import catalog
from d2parse import parse
from layout import FONT_SIZE, GROUP_ICON, ICON, LABEL_GAP, LABEL_ONLY, LINE_H, Layout, group_kind, header_band, header_box, icon_box, label_box
from ttf_width import Font

FONT_FILE = os.path.join(ROOT, "fonts", "BIZUDPGothic-Regular.ttf")
ICON_DIR = os.path.join(ROOT, "icons")
EDGE_FONT = 12
RADIUS = 8
LABEL_PAD = 3
LABEL_CLEAR = 8
HUG = 14
FAN_OFFSET = 24
FAN_SPREAD = 16
ROUTE = {"segmentPenalty": 200, "crossingPenalty": 300, "shapeBufferDistance": 14, "idealNudgingDistance": 16}
GROUP_STYLE = {
    "aws-cloud": ("#232F3E", ""),
    "region": ("#00A4A6", "3 3"),
    "vpc": ("#8C4FFF", ""),
    "az": ("#00A4A6", "8 4"),
    "public-subnet": ("#7AA116", ""),
    "private-subnet": ("#00A4A6", ""),
    "security-group": ("#DD344C", ""),
    "account": ("#E7157B", ""),
    "auto-scaling-group": ("#ED7100", "8 4"),
    "corporate-data-center": ("#7D8998", ""),
    "server-contents": ("#7D8998", ""),
    "ec2-instance-contents": ("#ED7100", ""),
    "spot-fleet": ("#ED7100", ""),
    "generic": ("#7D8998", "8 4"),
}
STRUCTURE = {"svc", "group", "plain", "spacer"} | set(GROUP_STYLE)


def b64(s):
    return base64.b64encode(s.encode()).decode()


def center(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def fail(message):
    print(f"エラー: {message}", file=sys.stderr)
    sys.exit(1)


class Diagram:
    def __init__(self, src_path):
        self.base = os.path.dirname(os.path.abspath(src_path))
        self.font = Font(FONT_FILE)
        self.icons = catalog.build(ICON_DIR)
        self.d = parse(open(src_path, encoding="utf-8").read())
        self.width, self.height = Layout(self.d, self.font).run()
        self.objs = self.d.objects
        self.nodes = {k: o for k, o in self.objs.items() if o.kind == "node"}
        self.groups = {k: o for k, o in self.objs.items() if o.kind == "group"}
        for n in self.nodes.values():
            n.icon_file = self.resolve_icon(n)
        for e in self.d.edges:
            for end in (e.src, e.dst):
                if end not in self.nodes:
                    fail(f"矢印 {e.src} -> {e.dst} の {end} がノードではありません（枠や存在しない ID は矢印の端にできません）")

    def resolve_icon(self, n):
        if n.icon:
            path = os.path.join(self.base, n.icon)
            if os.path.isfile(path):
                return path
            if n.icon in self.icons:
                return os.path.join(ICON_DIR, self.icons[n.icon])
            fail(f"{n.id} の icon「{n.icon}」が見つかりません")
        for c in n.classes:
            if c in self.icons:
                return os.path.join(ICON_DIR, self.icons[c])
        names = [c for c in n.classes if c not in STRUCTURE]
        fail(f"{n.id} のアイコンが決まりません（class {names} は索引にありません。`icons` で名前を探してください）")

    def sides(self, e):
        (sx, sy), (tx, ty) = center(icon_box(self.nodes[e.src])), center(icon_box(self.nodes[e.dst]))
        dx, dy = tx - sx, ty - sy
        if self.d.direction == "down":
            a, b = ("bottom", "top") if dy > 30 else ("top", "bottom") if dy < -30 else ("right", "left") if dx > 0 else ("left", "right")
        else:
            a, b = ("right", "left") if dx > 30 else ("left", "right") if dx < -30 else ("bottom", "top") if dy > 0 else ("top", "bottom")
        forced_from = next((c[5:] for c in e.classes if c.startswith("from-")), None)
        forced_to = next((c[3:] for c in e.classes if c.startswith("to-")), None)
        return forced_from or a, forced_to or b

    def pins(self):
        ends = defaultdict(list)
        for i, e in enumerate(self.d.edges):
            e.pins = [None, None]
            a, b = self.sides(e)
            other_src, other_dst = center(icon_box(self.nodes[e.dst])), center(icon_box(self.nodes[e.src]))
            ends[(e.src, a)].append((other_src[0] if a in ("top", "bottom") else other_src[1], i, 0))
            ends[(e.dst, b)].append((other_dst[0] if b in ("top", "bottom") else other_dst[1], i, 1))
        for (node_id, side), items in sorted(ends.items()):
            node = self.nodes[node_id]
            icon, label = icon_box(node), label_box(node)
            mid = center(icon)[0 if side in ("top", "bottom") else 1]
            items.sort()
            straight = [it for it in items if abs(it[0] - mid) < 1]
            slots = len(items) + (1 if straight and len(items) % 2 == 0 else 0)
            order = list(range(slots))
            if straight:
                order.remove(slots // 2)
                rest = [it for it in items if it is not straight[0]]
                placed = [(slots // 2, straight[0])] + list(zip(order, rest))
            else:
                placed = list(zip(order, items))
            for j, (_, i, which) in placed:
                frac = (j + 1) / (slots + 1)
                if side in ("top", "bottom"):
                    x = icon[0] + (icon[2] - icon[0]) * frac
                    on_label = side == "bottom" and label is not None
                    y = icon[1] if side == "top" else (label[3] if on_label else icon[3])
                    pin = {"node": node_id, "shape": "label" if on_label else "icon", "x": x, "y": y, "side": side}
                else:
                    y = icon[1] + (icon[3] - icon[1]) * frac
                    pin = {"node": node_id, "shape": "icon", "x": icon[0] if side == "left" else icon[2], "y": y, "side": side}
                self.d.edges[i].pins[which] = pin

    def route(self):
        if not self.d.edges:
            return
        self.pins()
        spec = {
            "params": ROUTE,
            "nodes": {k: {"icon": icon_box(o), "label": label_box(o)} for k, o in sorted(self.nodes.items())},
            "headers": [header_box(g, self.font) for g in self.groups.values() if g.label and "plain" not in g.classes],
            "edges": [{"pins": e.pins} for e in self.d.edges],
        }
        out = subprocess.run(["node", os.path.join(HERE, "route.mjs")], input=json.dumps(spec), capture_output=True, text=True, check=True)
        for e, pts in zip(self.d.edges, json.loads(out.stdout)):
            e.pts = [tuple(p) for p in pts]
        self.mirror()
        for e in self.d.edges:
            e.pts = self.straighten(simplify(e.pts))
        self.pull_bends()

    def mirror(self):
        azs = sorted((g for g in self.groups.values() if group_kind(g) == "az"), key=lambda g: g.x)
        if len(azs) != 2:
            return
        a, b = azs
        axis = (a.x + a.w / 2 + b.x + b.w / 2) / 2
        mapped = lambda nid: b.id + nid[len(a.id) :] if nid.startswith(a.id + ".") else nid
        by_pair = {(e.src, e.dst): e for e in self.d.edges}
        for e in self.d.edges:
            inside = [n.startswith(a.id + ".") for n in (e.src, e.dst)]
            twin = by_pair.get((mapped(e.src), mapped(e.dst)))
            if not any(inside) or not twin or twin is e:
                continue
            if all(inside):
                twin.pts = [(x + b.x - a.x, y + b.y - a.y) for x, y in e.pts]
            else:
                shared = self.nodes[e.dst if inside[0] else e.src]
                if abs(shared.x + shared.ax - axis) > 1:
                    continue
                twin.pts = [(2 * axis - x, y) for x, y in e.pts]
            if twin.label == e.label:
                twin.label = ""

    def pull_bends(self):
        """同じノードから分かれる矢印は、出てすぐに曲げる（後ろの水平・垂直の区間をラベルのために長く取る）。"""
        fans = defaultdict(list)
        for e in self.d.edges:
            if len(e.pts) == 4 and seg_axis(e.pts, 0) and seg_axis(e.pts, 0) == seg_axis(e.pts, 2) != seg_axis(e.pts, 1):
                k = 0 if seg_axis(e.pts, 0) == "h" else 1
                turn = 1 if e.pts[2][1 - k] > e.pts[1][1 - k] else -1
                fans[(e.src, e.pins[0]["side"], turn)].append(e)
        for (src, side, _), group in sorted(fans.items(), key=lambda kv: kv[0]):
            if sum(len(g) for (s, sd, _), g in fans.items() if s == src and sd == side) < 2:
                continue
            k = 0 if side in ("left", "right") else 1
            sign = 1 if side in ("right", "bottom") else -1
            group.sort(key=lambda e: abs(e.pts[1][k] - e.pts[0][k]))
            for rank, e in enumerate(group):
                new = e.pts[0][k] + sign * (FAN_OFFSET + rank * FAN_SPREAD)
                if abs(new - e.pts[0][k]) >= abs(e.pts[3][k] - e.pts[0][k]) - FAN_OFFSET:
                    continue
                put = (lambda p, v=new: (v, p[1])) if k == 0 else (lambda p, v=new: (p[0], v))
                e.pts = [e.pts[0], put(e.pts[1]), put(e.pts[2]), e.pts[3]]

    def walls(self):
        for g in self.groups.values():
            if "plain" in g.classes:
                continue
            x1, y1, x2, y2 = g.x, g.y, g.x + g.w, g.y + g.h
            yield g, "h", y1, x1, x2
            yield g, "h", y2, x1, x2
            yield g, "v", x1, y1, y2
            yield g, "v", x2, y1, y2

    def obstacles(self, axis):
        for _, kind, pos, lo, hi in self.walls():
            if kind == axis:
                yield pos, lo, hi
        boxes = [icon_box(n) for n in self.nodes.values()] + [b for b in (label_box(n) for n in self.nodes.values()) if b]
        boxes += [header_box(g, self.font) for g in self.groups.values() if g.label and "plain" not in g.classes]
        for x1, y1, x2, y2 in boxes:
            yield from ((y1, x1, x2), (y2, x1, x2)) if axis == "h" else ((x1, y1, y2), (x2, y1, y2))

    def straighten(self, pts):
        """枠線に沿う区間と、枠の見出しの帯を通る区間を、枠の外の隙間の中央へ移す（端の区間は動かさない）。"""
        for _ in range(4):
            moved = False
            for i in range(1, len(pts) - 2):
                axis = seg_axis(pts, i)
                if not axis:
                    continue
                k = 1 if axis == "h" else 0
                pos = pts[i][k]
                lo, hi = sorted((pts[i][1 - k], pts[i + 1][1 - k]))
                for g, kind, wall, wlo, whi in self.walls():
                    if kind != axis or min(hi, whi) - max(lo, wlo) < 1:
                        continue
                    band = axis == "h" and wall == g.y and wall < pos < wall + header_band(g)
                    if not band and abs(pos - wall) >= HUG:
                        continue
                    side = -1 if band else (1 if pos >= wall else -1)
                    far = [o for o, olo, ohi in self.obstacles(axis) if (o - wall) * side > 1 and min(hi, ohi) - max(lo, olo) > 0]
                    if not far:
                        continue
                    nearest = min(far, key=lambda o: abs(o - wall))
                    if abs(nearest - wall) < 2 * HUG:
                        continue
                    new = (wall + nearest) / 2
                    put = (lambda p: (p[0], new)) if axis == "h" else (lambda p: (new, p[1]))
                    pts = pts[:i] + [put(pts[i]), put(pts[i + 1])] + pts[i + 2 :]
                    moved = True
                    break
                if moved:
                    break
            if not moved:
                break
        return pts

    def place_labels(self):
        labeled = [e for e in self.d.edges if e.label]
        for e in labeled:
            e.label_w = max(self.font.width(line, EDGE_FONT) for line in e.label.split("\n")) + 2 * LABEL_PAD
            e.label_h = (EDGE_FONT + 4) * (e.label.count("\n") + 1)
        done = set()
        for key in ("src", "dst"):
            groups = defaultdict(list)
            for e in labeled:
                if id(e) not in done:
                    groups[getattr(e, key)].append(e)
            for _, group in sorted(groups.items()):
                if len(group) < 2:
                    continue
                best = None
                for axis in ("h", "v"):
                    for combo in itertools.product(*(segments(e, axis) for e in group)):
                        members = list(zip(group, combo))
                        pos = self.label_center(members, axis)
                        if pos is None:
                            continue
                        score = sum(i == len(e.pts) - 2 for e, i in members)
                        if not best or score > best[0]:
                            best = (score, axis, members, pos)
                if best:
                    _, axis, members, pos = best
                    for e, i in members:
                        e.label_at = at(e, i, axis, pos)
                        done.add(id(e))
        for e in labeled:
            if id(e) in done:
                continue
            order = sorted(range(len(e.pts) - 1), key=lambda i: (i != len(e.pts) - 2, -seg_len(e.pts, i), i))
            for i in order:
                axis = seg_axis(e.pts, i)
                pos = axis and self.label_center([(e, i)], axis)
                if pos is not None:
                    e.label_at = at(e, i, axis, pos)
                    break
            else:
                i = max(range(len(e.pts) - 1), key=lambda i: seg_len(e.pts, i))
                e.label_at = ((e.pts[i][0] + e.pts[i + 1][0]) / 2, (e.pts[i][1] + e.pts[i + 1][1]) / 2)

    def label_center(self, members, axis):
        half = max((e.label_w if axis == "h" else e.label_h) for e, _ in members) / 2 + LABEL_CLEAR
        lo, hi, blocked = -1e9, 1e9, []
        for e, i in members:
            a, b = usable(e.pts, i)
            lo, hi = max(lo, a + half), min(hi, b - half)
            cross = e.pts[i][1] if axis == "h" else e.pts[i][0]
            for g in self.groups.values():
                if "plain" in g.classes:
                    continue
                x1, y1, x2, y2 = g.x, g.y, g.x + g.w, g.y + g.h
                span, walls = ((y1, y2), (x1, x2)) if axis == "h" else ((x1, x2), (y1, y2))
                if span[0] < cross < span[1]:
                    blocked += [(w - half, w + half) for w in walls]
                if g.label and axis == "v" and x1 < cross < x2:
                    blocked.append((y1 - half, y1 + header_band(g) + half))
                if g.label and axis == "h":
                    hx1, hy1, hx2, hy2 = header_box(g, self.font)
                    if hy1 - 4 < cross < hy2 + 4:
                        blocked.append((hx1 - half, hx2 + half))
        k = 0 if axis == "h" else 1
        for e, i in members:
            cross = e.pts[i][1] if axis == "h" else e.pts[i][0]
            for other in self.d.edges:
                if other is e:
                    continue
                for j in range(len(other.pts) - 1):
                    other_axis = seg_axis(other.pts, j)
                    if other_axis is None:
                        continue
                    if other_axis != axis:
                        lo2, hi2 = sorted((other.pts[j][1 - k], other.pts[j + 1][1 - k]))
                        if lo2 <= cross <= hi2:
                            blocked.append((other.pts[j][k] - half, other.pts[j][k] + half))
                        continue
                    reach = (e.label_h if axis == "h" else e.label_w) / 2 + 2
                    if abs(other.pts[j][1 - k] - cross) < reach:
                        lo2, hi2 = sorted((other.pts[j][k], other.pts[j + 1][k]))
                        blocked.append((lo2 - half, hi2 + half))
        if lo > hi:
            return None
        mid = (lo + hi) / 2
        options = [min(max(v, lo), hi) for v in [mid] + [v for blk in blocked for v in blk]]
        options = [v for v in options if not any(b0 < v < b1 for b0, b1 in blocked)]
        return min(options, key=lambda v: (abs(v - mid), v)) if options else None

    def render(self, out_path):
        texts = [o.label for o in self.objs.values() if o.label] + [e.label for e in self.d.edges if e.label]
        font = subset_font("".join(sorted(set("".join(texts)))))
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.width:g} {self.height:g}" width="{self.width:g}" height="{self.height:g}">',
            "<defs><style>"
            f'@font-face{{font-family:"diagram";src:url(data:font/woff;base64,{font}) format("woff")}}'
            'text{font-family:"diagram",sans-serif;fill:#000000}'
            "</style>"
            '<marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="10" markerHeight="10" orient="auto" markerUnits="userSpaceOnUse">'
            '<path d="M 1 1 L 10 5 L 1 9" fill="none" stroke="#000000" stroke-width="1" /></marker></defs>',
            f'<rect width="{self.width:g}" height="{self.height:g}" fill="#FFFFFF" />',
        ]
        for g in sorted(self.groups.values(), key=lambda g: (g.id.count("."), g.id)):
            if "plain" not in g.classes:
                parts.append(self.render_group(g))
        for e in self.d.edges:
            if hasattr(e, "pts"):
                parts.append(self.render_edge(e))
        for n in self.nodes.values():
            parts.append(self.render_node(n))
        parts.append("</svg>")
        open(out_path, "w", encoding="utf-8").write("\n".join(parts) + "\n")

    def render_group(self, g):
        kind = group_kind(g)
        color, dash = GROUP_STYLE[kind]
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        out = [f'<g class="{b64(g.id)} group {" ".join(g.classes)}"><g class="shape">']
        out.append(f'<rect x="{g.x:g}" y="{g.y:g}" width="{g.w:g}" height="{g.h:g}" fill="none" stroke="{color}" stroke-width="1"{dash_attr} /></g>')
        if kind not in LABEL_ONLY:
            uri = data_uri(os.path.join(ICON_DIR, catalog.GROUP_FILES[kind]))
            out.append(f'<image href="{uri}" x="{g.x:g}" y="{g.y:g}" width="{GROUP_ICON}" height="{GROUP_ICON}" />')
            tx, ty = g.x + GROUP_ICON + 10, g.y + GROUP_ICON / 2 + FONT_SIZE * 0.35
        else:
            tx, ty = g.x + 10, g.y + LINE_H
        if g.label:
            out.append(f'<text x="{tx:g}" y="{ty:g}" style="text-anchor:start;font-size:{FONT_SIZE}px">{html.escape(g.label)}</text>')
        out.append("</g>")
        return "".join(out)

    def render_node(self, n):
        box = icon_box(n)
        out = [f'<g class="{b64(n.id)} svc {" ".join(n.classes)}"><g class="shape">']
        out.append(f'<image href="{data_uri(n.icon_file)}" x="{box[0]:g}" y="{box[1]:g}" width="{ICON}" height="{ICON}" /></g>')
        if n.label:
            cx = n.x + n.ax
            for k, line in enumerate(n.label.split("\n")):
                y = n.y + ICON + LABEL_GAP + FONT_SIZE + k * LINE_H
                out.append(f'<text x="{cx:g}" y="{y:g}" style="text-anchor:middle;font-size:{FONT_SIZE}px">{html.escape(line)}</text>')
        out.append("</g>")
        return "".join(out)

    def render_edge(self, e):
        dash = ' stroke-dasharray="5 4"' if "async" in e.classes else ""
        ident = b64(f"({e.src} -> {e.dst})[0]")
        out = [f'<g class="{ident} {" ".join(e.classes)}">']
        out.append(f'<path d="{path_d(e.pts)}" fill="none" stroke="#000000" stroke-width="1"{dash} class="connection" marker-end="url(#arrow)" />')
        if e.label:
            x, y = e.label_at
            out.append(f'<rect x="{x - e.label_w / 2:g}" y="{y - e.label_h / 2:g}" width="{e.label_w:g}" height="{e.label_h:g}" fill="#FFFFFF" />')
            for k, line in enumerate(e.label.split("\n")):
                ty = y - e.label_h / 2 + (EDGE_FONT + 4) * k + EDGE_FONT
                out.append(f'<text x="{x:g}" y="{ty:g}" style="text-anchor:middle;font-size:{EDGE_FONT}px">{html.escape(line)}</text>')
        out.append("</g>")
        return "".join(out)


def data_uri(path):
    return "data:image/svg+xml;base64," + base64.b64encode(open(path, "rb").read()).decode()


def subset_font(text):
    import logging

    from fontTools import subset

    logging.getLogger("fontTools").setLevel(logging.ERROR)

    options = subset.Options()
    options.flavor = "woff"
    font = subset.load_font(FONT_FILE, options)
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    buf = io.BytesIO()
    subset.save_font(font, buf, options)
    return base64.b64encode(buf.getvalue()).decode()


def simplify(pts):
    out = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - out[-1][0]) < 0.01 and abs(p[1] - out[-1][1]) < 0.01:
            continue
        if len(out) >= 2 and (out[-2][0] == out[-1][0] == p[0] or out[-2][1] == out[-1][1] == p[1]):
            out[-1] = p
            continue
        out.append(p)
    return out


def seg_axis(pts, i):
    a, b = pts[i], pts[i + 1]
    return "h" if a[1] == b[1] else "v" if a[0] == b[0] else None


def seg_len(pts, i):
    return abs(pts[i][0] - pts[i + 1][0]) + abs(pts[i][1] - pts[i + 1][1])


def segments(e, axis):
    return [i for i in range(len(e.pts) - 1) if seg_axis(e.pts, i) == axis]


def usable(pts, i):
    a, b = pts[i], pts[i + 1]
    k = 0 if seg_axis(pts, i) == "h" else 1
    lo_pad = RADIUS if i > 0 else 0
    hi_pad = RADIUS if i + 1 < len(pts) - 1 else 12
    if a[k] <= b[k]:
        return a[k] + lo_pad, b[k] - hi_pad
    return b[k] + hi_pad, a[k] - lo_pad


def at(e, i, axis, pos):
    return (pos, e.pts[i][1]) if axis == "h" else (e.pts[i][0], pos)


def toward(p, q, r):
    d = abs(p[0] - q[0]) + abs(p[1] - q[1]) or 1
    return (p[0] + (q[0] - p[0]) * r / d, p[1] + (q[1] - p[1]) * r / d)


def path_d(pts):
    out = [f"M {pts[0][0]:g} {pts[0][1]:g}"]
    for prev, cur, nxt in zip(pts, pts[1:], pts[2:]):
        r = min(RADIUS, seg_len([prev, cur], 0) / 2, seg_len([cur, nxt], 0) / 2)
        a, b = toward(cur, prev, r), toward(cur, nxt, r)
        out.append(f"L {a[0]:g} {a[1]:g} Q {cur[0]:g} {cur[1]:g} {b[0]:g} {b[1]:g}")
    out.append(f"L {pts[-1][0]:g} {pts[-1][1]:g}")
    return " ".join(out)


def render(src, out_dir):
    name = os.path.splitext(os.path.basename(src))[0]
    os.makedirs(out_dir, exist_ok=True)
    svg = os.path.join(out_dir, f"{name}.svg")
    diagram = Diagram(src)
    diagram.route()
    diagram.place_labels()
    diagram.render(svg)
    png = os.path.join(out_dir, f"{name}.png")
    out = subprocess.run(["node", os.path.join(HERE, "check.mjs"), os.path.abspath(svg), os.path.abspath(png), diagram.d.direction], capture_output=True, text=True, check=True)
    result = json.loads(out.stdout)
    print(f"{name}.svg {result['width']}x{result['height']}、チェックの問題 {len(result['issues'])} 件")
    for issue in result["issues"]:
        print(f"  {issue['type']}: {issue['detail']}")


def icons(query):
    for key, filename in sorted(catalog.build(ICON_DIR).items()):
        if not query or query.lower() in key or query.lower() in filename.lower():
            print(f"{key}\t{filename}")


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "render":
        render(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 2 and sys.argv[1] == "icons":
        icons(sys.argv[2] if len(sys.argv) > 2 else "")
    else:
        fail(__doc__)


if __name__ == "__main__":
    main()
