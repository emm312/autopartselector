"""Minimal, lossless .kicad_sch editing: parse s-exprs with byte spans, splice edits into the text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Atom:
    start: int
    end: int
    text: str  # unescaped value
    quoted: bool


@dataclass
class Node:
    start: int
    end: int = -1
    items: list["Node | Atom"] = field(default_factory=list)

    @property
    def head(self) -> str | None:
        return self.items[0].text if self.items and isinstance(self.items[0], Atom) else None

    def children(self, head: str) -> list["Node"]:
        return [c for c in self.items if isinstance(c, Node) and c.head == head]

    def child(self, head: str) -> "Node | None":
        cs = self.children(head)
        return cs[0] if cs else None

    def atom(self, i: int) -> Atom | None:
        return self.items[i] if len(self.items) > i and isinstance(self.items[i], Atom) else None


_ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}


def parse(text: str) -> Node:
    stack: list[Node] = []
    root: Node | None = None
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "(":
            node = Node(i)
            if stack:
                stack[-1].items.append(node)
            stack.append(node)
            i += 1
        elif c == ")":
            node = stack.pop()
            node.end = i + 1
            if not stack:
                root = node
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while text[j] != '"':
                if text[j] == "\\":
                    buf.append(_ESC.get(text[j + 1], text[j + 1]))
                    j += 2
                else:
                    buf.append(text[j])
                    j += 1
            stack[-1].items.append(Atom(i, j + 1, "".join(buf), True))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            stack[-1].items.append(Atom(i, j, text[i:j], False))
            i = j
    if root is None or stack:
        raise ValueError("unbalanced s-expression")
    return root


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


@dataclass
class Symbol:
    node: Node
    lib_id: str
    props: dict[str, Node]  # name -> property node
    refs: list[str]  # one reference per placement of this sheet in the hierarchy

    def prop(self, name: str) -> str | None:
        p = self.props.get(name)
        return p.atom(2).text if p is not None and p.atom(2) else None

    @property
    def ref(self) -> str:
        return self.refs[0] if self.refs else self.prop("Reference") or "?"

    @property
    def in_bom(self) -> bool:
        n = self.node.child("in_bom")
        return not (n is not None and n.atom(1) and n.atom(1).text == "no")


class Schematic:
    def __init__(self, path: Path):
        self.path = path
        self.text = path.read_text(encoding="utf-8")
        self.root = parse(self.text)
        self.edits: list[tuple[int, int, str]] = []
        # Hierarchy paths this file is placed at ("/<root uuid>/<sheet uuid>/..."), filled by load_hierarchy.
        self.instance_paths: set[str] = set()

    @property
    def uuid(self) -> str | None:
        u = self.root.child("uuid")
        return u.atom(1).text if u is not None and u.atom(1) else None

    def _instance_refs(self, sym: Node) -> list[str]:
        refs = []
        inst = sym.child("instances")
        for proj in inst.children("project") if inst is not None else ():
            for path in proj.children("path"):
                ref = path.child("reference")
                if path.atom(1) and path.atom(1).text in self.instance_paths and ref is not None and ref.atom(1):
                    refs.append(ref.atom(1).text)
        return refs

    def symbols(self) -> list[Symbol]:
        out = []
        for n in self.root.children("symbol"):
            lib = n.child("lib_id")
            if lib is None or lib.atom(1) is None:
                continue
            props = {}
            for p in n.children("property"):
                name = p.atom(1)
                if name is not None and p.atom(2) is not None:
                    props[name.text] = p
            sym = Symbol(n, lib.atom(1).text, props, self._instance_refs(n))
            if not sym.refs and sym.prop("Reference"):
                sym.refs = [sym.prop("Reference")]
            out.append(sym)
        return out

    def subsheets(self) -> list[tuple[Path, str | None]]:
        """(file, sheet uuid) for each sheet placed on this page."""
        out = []
        for sheet in self.root.children("sheet"):
            u = sheet.child("uuid")
            for p in sheet.children("property"):
                name = p.atom(1)
                if name is not None and name.text in ("Sheetfile", "Sheet file") and p.atom(2):
                    out.append((self.path.parent / p.atom(2).text, u.atom(1).text if u is not None and u.atom(1) else None))
        return out

    def set_property(self, sym: Symbol, name: str, value: str) -> bool:
        """Set or add a property. Returns True if the file text changes."""
        existing = sym.props.get(name)
        if existing is not None:
            a = existing.atom(2)
            if a.text == value:
                return False
            self.edits.append((a.start, a.end, quote(value)))
            return True
        # Clone a hidden property (Datasheet, else Footprint, else the last one) as a template.
        tmpl = sym.props.get("Datasheet") or sym.props.get("Footprint") or list(sym.props.values())[-1]
        t_name, t_val = tmpl.atom(1), tmpl.atom(2)
        body = (
            self.text[tmpl.start:t_name.start] + quote(name)
            + self.text[t_name.end:t_val.start] + quote(value)
            + self.text[t_val.end:tmpl.end]
        )
        last = list(sym.props.values())[-1]
        line_start = self.text.rfind("\n", 0, last.start) + 1
        indent = self.text[line_start:last.start]
        if indent.strip():
            indent = " "
            self.edits.append((last.end, last.end, " " + body))
        else:
            self.edits.append((last.end, last.end, "\n" + indent + body))
        return True

    def render(self) -> str:
        out = self.text
        # Apply back-to-front; for inserts at the same offset, apply the later one first so the
        # final text keeps them in call order.
        order = sorted(range(len(self.edits)), key=lambda i: (self.edits[i][0], self.edits[i][1], i), reverse=True)
        for start, end, rep in (self.edits[i] for i in order):
            out = out[:start] + rep + out[end:]
        return out


def load_hierarchy(root_path: Path) -> tuple[list[Schematic], list[str]]:
    """Load the root sheet and every sub-sheet file once. Returns (sheets, warnings)."""
    seen: dict[Path, Schematic] = {}
    warnings: list[str] = []
    root = Schematic(root_path.resolve())
    seen[root.path] = root
    root_inst = f"/{root.uuid}" if root.uuid else "/"
    todo = [(root, root_inst)]
    while todo:
        sch, inst = todo.pop()
        if inst in sch.instance_paths:
            continue  # recursive sheet reference
        sch.instance_paths.add(inst)
        if inst == root_inst:
            sch.instance_paths.add("/")  # older files use "/" for the root sheet
        for f, sheet_uuid in sch.subsheets():
            f = f.resolve()
            if not f.exists():
                warnings.append(f"sub-sheet file not found: {f} (referenced from {sch.path.name})")
                continue
            if f not in seen:
                seen[f] = Schematic(f)
            todo.append((seen[f], f"{inst.rstrip('/')}/{sheet_uuid}"))
    return list(seen.values()), warnings


PASSIVE_NAME = re.compile(r"^(R|C|L)(_Small)?(_US)?$")


def passive_kind(sym: Symbol) -> str | None:
    name = sym.lib_id.split(":", 1)[-1]
    m = PASSIVE_NAME.match(name)
    return m.group(1) if m else None
