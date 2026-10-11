"""Minimal SELinux CIL reader: enough to slice policies by type and re-emit rules as .te text."""
import re

_TOKEN = re.compile(r'"[^"]*"|[()]|[^\s()"]+')


def parse(text):
    """Parse CIL text into nested Python lists of strings."""
    root, stack = [], []
    cur = root
    for tok in _TOKEN.findall(re.sub(r";[^\n]*", "", text)):
        if tok == "(":
            new = []
            cur.append(new)
            stack.append(cur)
            cur = new
        elif tok == ")":
            if not stack:
                raise ValueError("unbalanced parentheses in CIL")
            cur = stack.pop()
        else:
            cur.append(tok)
    if stack:
        raise ValueError("unterminated CIL expression")
    return root


def flat_names(expr):
    """All identifiers appearing in a (possibly nested) CIL expression."""
    if isinstance(expr, str):
        return [expr]
    out = []
    for item in expr:
        out.extend(flat_names(item))
    return out


def is_plain_list(expr):
    return isinstance(expr, list) and all(isinstance(x, str) for x in expr)


class Policy:
    """One CIL file, indexed for type-centric queries."""

    AV_RULES = ("allow", "dontaudit", "auditallow", "neverallow", "allowx", "dontauditx", "neverallowx")

    def __init__(self, label, text):
        self.label = label
        self.types = set()
        self.attributes = set()
        self.attr_sets = []  # (attribute, expr)
        self.rules = []  # raw statements (lists) for av rules and typetransitions
        self.other = []
        for stmt in parse(text):
            if not isinstance(stmt, list) or not stmt:
                continue
            head = stmt[0]
            if head == "type":
                self.types.add(stmt[1])
            elif head == "typeattribute":
                self.attributes.add(stmt[1])
            elif head == "typeattributeset":
                self.attr_sets.append((stmt[1], stmt[2]))
            elif head in self.AV_RULES or head in ("typetransition", "typechange", "typemember"):
                self.rules.append(stmt)
            else:
                self.other.append(stmt)

    def memberships(self, name):
        """Attributes whose plain member list contains name (boolean set expressions are skipped)."""
        return sorted(a for a, expr in self.attr_sets if is_plain_list(expr) and name in expr)

    def rules_for(self, name):
        src, tgt = [], []
        for stmt in self.rules:
            if stmt[0] in ("typetransition", "typechange", "typemember"):
                if stmt[1] == name:
                    src.append(stmt)
                elif stmt[2] == name or stmt[-1] == name:
                    tgt.append(stmt)
            elif stmt[1] == name:
                src.append(stmt)
            elif stmt[2] == name:
                tgt.append(stmt)
        return src, tgt


def to_te(stmt):
    """Render one CIL rule as a .te statement (None when it has no .te equivalent we emit)."""
    head = stmt[0]
    if head in ("allow", "dontaudit", "auditallow", "neverallow"):
        cls_perms = stmt[3]
        if not isinstance(cls_perms, list) or len(cls_perms) != 2:
            return None
        cls, perms = cls_perms
        perms = " ".join(flat_names(perms))
        return f"{head} {stmt[1]} {stmt[2]}:{cls} {{ {perms} }};"
    if head in ("allowx", "dontauditx", "neverallowx"):
        body = stmt[3]
        if not isinstance(body, list) or len(body) != 3:
            return None
        kind, cls, ranges = body
        parts = []
        for r in ranges if isinstance(ranges, list) else [ranges]:
            if isinstance(r, list) and r and r[0] == "range":
                parts.append(f"{r[1]}-{r[2]}")
            elif isinstance(r, list):
                parts.extend(flat_names(r))
            else:
                parts.append(r)
        keyword = {"allowx": "allowxperm", "dontauditx": "dontauditxperm", "neverallowx": "neverallowxperm"}[head]
        return f"{keyword} {stmt[1]} {stmt[2]}:{cls} {kind} {{ {' '.join(parts)} }};"
    if head == "typetransition":
        if len(stmt) == 5:
            return f"type_transition {stmt[1]} {stmt[2]}:{stmt[3]} {stmt[4]};"
        if len(stmt) == 6:
            return f"type_transition {stmt[1]} {stmt[2]}:{stmt[3]} {stmt[5]} {stmt[4]};"
    return None
