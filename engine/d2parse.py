"""D2 のうち、構成図に使う範囲だけを読む。

読むもの: オブジェクト（ラベル、class、icon、grid-rows、grid-columns、vertical-gap、horizontal-gap）、
矢印（a -> b: ラベル {class: ...}）、トップレベルの direction。
classes ブロック、style、near、glob（* や ( で始まる行）は D2 で下書きを見るためのもので、ここでは読み飛ばす。
"""
from dataclasses import dataclass, field

KNOWN = {"class", "icon", "grid-rows", "grid-columns", "vertical-gap", "horizontal-gap", "label", "direction"}
IGNORED = {"style", "shape", "width", "height", "near", "tooltip", "link", "top", "left", "grid-gap", "vars", "layers", "scenarios", "steps", "constraint"}


@dataclass
class Obj:
    id: str
    label: str
    classes: list = field(default_factory=list)
    icon: str = ""
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    parent: "Obj" = None


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    classes: list = field(default_factory=list)


@dataclass
class Diagram:
    root: Obj
    edges: list
    direction: str = "down"
    objects: dict = field(default_factory=dict)


class Parser:
    def __init__(self, text):
        self.s = text
        self.i = 0

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def skip_space(self, newlines=True):
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "#":
                while self.i < len(self.s) and self.s[self.i] != "\n":
                    self.i += 1
            elif c in " \t\r" or (newlines and c in "\n;"):
                self.i += 1
            else:
                break

    def read_until(self, stops):
        out, quote = [], None
        while self.i < len(self.s):
            c = self.s[self.i]
            if quote:
                if c == "\\" and self.i + 1 < len(self.s):
                    out.append(c + self.s[self.i + 1])
                    self.i += 2
                    continue
                if c == quote:
                    quote = None
                out.append(c)
            elif c in "\"'":
                quote = c
                out.append(c)
            elif c == "#" or c in stops:
                break
            elif c == "-" and self.s.startswith("->", self.i) and "->" in stops:
                break
            else:
                out.append(c)
            self.i += 1
        return "".join(out).strip()

    def read_value(self):
        self.skip_space(newlines=False)
        if self.peek() == "[":
            self.i += 1
            raw = self.read_until("]")
            self.i += 1
            return [unquote(v) for v in raw.split(";") if v.strip()]
        if self.peek() == "|":
            end = self.s.index("|", self.i + 1)
            value = self.s[self.i + 1 : end]
            self.i = end + 1
            return value.strip()
        return unquote(self.read_until("{};\n"))

    def block(self):
        stmts = []
        while True:
            self.skip_space()
            if self.i >= len(self.s) or self.peek() == "}":
                self.i += 1
                return stmts
            key = self.read_until(":{};\n")
            value, body = None, None
            self.skip_space(newlines=False)
            if self.peek() == ":":
                self.i += 1
                value = self.read_value()
                self.skip_space(newlines=False)
            if self.peek() == "{":
                self.i += 1
                body = self.block()
            stmts.append((key, value, body))


def unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    return v.replace("\\n", "\n")


def parse(text):
    stmts = Parser(text + "\n}").block()
    root = Obj(id="", label="")
    edges = []
    diagram = Diagram(root=root, edges=edges)
    build(root, stmts, diagram, top=True)
    index(root, diagram.objects)
    return diagram


def build(obj, stmts, diagram, top=False):
    for key, value, body in stmts:
        if not key or key.startswith("*") or key.startswith("(") or key == "classes" or key in IGNORED:
            continue
        if "->" in key:
            src, dst = (unquote(p) for p in key.split("->", 1))
            edge = Edge(src=join(obj.id, src), dst=join(obj.id, dst), label=value or "")
            for k, v, _ in body or []:
                if k == "class":
                    edge.classes = v if isinstance(v, list) else [v]
            edges_append(diagram, edge)
            continue
        if key == "direction" and top:
            diagram.direction = value
            continue
        if key in KNOWN:
            set_attr(obj, key, value)
            continue
        if "." in key:
            continue
        child = Obj(id=join(obj.id, key), label=key if value is None else value, parent=obj)
        if isinstance(child.label, list):
            child.label = key
        obj.children.append(child)
        if body:
            build(child, body, diagram)


def edges_append(diagram, edge):
    diagram.edges.append(edge)


def set_attr(obj, key, value):
    if key == "class":
        obj.classes = value if isinstance(value, list) else [value]
    elif key == "icon":
        obj.icon = value
    elif key == "label":
        obj.label = value
    else:
        obj.attrs[key] = value


def join(prefix, name):
    name = name.strip()
    return f"{prefix}.{name}" if prefix else name


def index(obj, table):
    for child in obj.children:
        table[child.id] = child
        index(child, table)
