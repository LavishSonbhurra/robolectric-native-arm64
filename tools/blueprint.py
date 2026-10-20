"""A small Blueprint (Android.bp) parser and evaluator.

Covers the language as used by AOSP Android.bp files: variable assignment
(`=` and `+=`), modules with `name: value` properties, strings, integers,
booleans, lists, maps, `+` concatenation (strings, lists, maps), and Soong's
`select()` expressions including tuple conditions, `any @ binding` patterns
and `unset`.

Evaluation is eager: every select() is resolved while the file is read, using
a caller-supplied `SelectContext`, because we only ever evaluate one
configuration (host, linux_glibc, arm64). Unset values are represented by the
`UNSET` sentinel and dropped from the property maps.

Scoping follows Blueprint: variables are visible in the rest of the file and
in Android.bp files of sub-directories (callers pass the parent scope).
"""

import re

UNSET = object()


class BlueprintError(Exception):
    pass


_TOKEN_RE = re.compile(r"""
    (?P<ws>\s+)
  | (?P<lcomment>//[^\n]*)
  | (?P<bcomment>/\*.*?\*/)
  | (?P<string>"(?:[^"\\\n]|\\.)*")
  | (?P<raw>`[^`]*`)
  | (?P<int>-?[0-9]+)
  | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>\+=|[{}\[\]():,=+@])
""", re.VERBOSE | re.DOTALL)

_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'", "r": "\r", "a": "\a",
            "b": "\b", "f": "\f", "v": "\v"}


def _unquote(s):
    body = s[1:-1]
    if "\\" not in body:
        return body
    out = []
    i = 0
    while i < len(body):
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        n = body[i + 1]
        if n in _ESCAPES:
            out.append(_ESCAPES[n])
            i += 2
        elif n == "x":
            out.append(chr(int(body[i + 2:i + 4], 16)))
            i += 4
        elif n == "u":
            out.append(chr(int(body[i + 2:i + 6], 16)))
            i += 6
        elif n in "01234567":
            out.append(chr(int(body[i + 1:i + 4], 8)))
            i += 4
        else:
            raise BlueprintError(f"bad escape \\{n} in {s}")
    return "".join(out)


def tokenize(text, fname):
    toks = []
    pos = 0
    line = 1
    n = len(text)
    while pos < n:
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise BlueprintError(f"{fname}:{line}: cannot tokenize near {text[pos:pos + 30]!r}")
        kind = m.lastgroup
        val = m.group(kind)
        if kind == "string":
            toks.append(("str", _unquote(val), line))
        elif kind == "raw":
            toks.append(("str", val[1:-1], line))
        elif kind == "int":
            toks.append(("int", int(val), line))
        elif kind == "ident":
            toks.append(("ident", val, line))
        elif kind == "op":
            toks.append(("op", val, line))
        line += val.count("\n")
        pos = m.end()
    toks.append(("eof", None, line))
    return toks


# ---- AST ----------------------------------------------------------------

class Node:
    __slots__ = ()


class Lit(Node):
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v


class Var(Node):
    __slots__ = ("name", "line")

    def __init__(self, name, line):
        self.name = name
        self.line = line


class ListN(Node):
    __slots__ = ("items",)

    def __init__(self, items):
        self.items = items


class MapN(Node):
    __slots__ = ("items",)  # list of (key, Node)

    def __init__(self, items):
        self.items = items


class Plus(Node):
    __slots__ = ("args",)

    def __init__(self, args):
        self.args = args


class Unset(Node):
    __slots__ = ()


class Select(Node):
    __slots__ = ("conds", "cases", "line")
    # conds: list of (func_name, [str args])
    # cases: list of (patterns tuple, Node); a pattern is
    #   ("default",) | ("any", binding or None) | ("value", python value)

    def __init__(self, conds, cases, line):
        self.conds = conds
        self.cases = cases
        self.line = line


class Parser:
    def __init__(self, text, fname):
        self.toks = tokenize(text, fname)
        self.i = 0
        self.fname = fname

    def peek(self, k=0):
        return self.toks[self.i + k]

    def next(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def err(self, msg):
        t = self.peek()
        raise BlueprintError(f"{self.fname}:{t[2]}: {msg} (at {t[1]!r})")

    def expect(self, kind, val=None):
        t = self.next()
        if t[0] != kind or (val is not None and t[1] != val):
            self.i -= 1
            self.err(f"expected {val or kind}")
        return t

    def accept(self, kind, val=None):
        t = self.peek()
        if t[0] == kind and (val is None or t[1] == val):
            self.i += 1
            return t
        return None

    def parse_file(self):
        """Returns a list of ("assign", name, op, node, line) and ("module", type, props, line)."""
        defs = []
        while self.peek()[0] != "eof":
            t = self.expect("ident")
            if self.accept("op", "=") or (self.peek()[1] == "+=" and self.next()):
                op = self.toks[self.i - 1][1]
                defs.append(("assign", t[1], op, self.parse_expr(), t[2]))
            elif self.accept("op", "{"):
                defs.append(("module", t[1], self.parse_props("}"), t[2]))
            elif self.accept("op", "("):
                defs.append(("module", t[1], self.parse_props(")"), t[2]))
            else:
                self.err("expected assignment or module")
        return defs

    def parse_props(self, close):
        items = []
        while not self.accept("op", close):
            k = self.expect("ident")[1]
            if not self.accept("op", ":"):
                self.expect("op", "=")
            items.append((k, self.parse_expr()))
            if not self.accept("op", ","):
                self.expect("op", close)
                break
        return items

    def parse_expr(self):
        args = [self.parse_value()]
        while self.accept("op", "+"):
            args.append(self.parse_value())
        return args[0] if len(args) == 1 else Plus(args)

    def parse_value(self):
        t = self.next()
        kind, v, line = t
        if kind == "str" or kind == "int":
            return Lit(v)
        if kind == "op" and v == "[":
            items = []
            while not self.accept("op", "]"):
                items.append(self.parse_expr())
                if not self.accept("op", ","):
                    self.expect("op", "]")
                    break
            return ListN(items)
        if kind == "op" and v == "{":
            return MapN(self.parse_props("}"))
        if kind == "ident":
            if v == "true":
                return Lit(True)
            if v == "false":
                return Lit(False)
            if v == "unset":
                return Unset()
            if v == "select" and self.peek()[1] == "(":
                return self.parse_select(line)
            return Var(v, line)
        self.i -= 1
        self.err("expected a value")

    def parse_condition(self):
        name = self.expect("ident")[1]
        self.expect("op", "(")
        args = []
        while not self.accept("op", ")"):
            args.append(self.expect("str")[1])
            if not self.accept("op", ","):
                self.expect("op", ")")
                break
        return (name, args)

    def parse_pattern(self):
        t = self.next()
        if t[0] == "str":
            return ("value", t[1])
        if t[0] == "ident":
            if t[1] == "default":
                return ("default",)
            if t[1] == "true":
                return ("value", True)
            if t[1] == "false":
                return ("value", False)
            if t[1] == "any":
                if self.accept("op", "@"):
                    return ("any", self.expect("ident")[1])
                return ("any", None)
        self.i -= 1
        self.err("bad select pattern")

    def parse_select(self, line):
        self.expect("op", "(")
        conds = []
        if self.accept("op", "("):
            while not self.accept("op", ")"):
                conds.append(self.parse_condition())
                if not self.accept("op", ","):
                    self.expect("op", ")")
                    break
        else:
            conds.append(self.parse_condition())
        self.expect("op", ",")
        self.expect("op", "{")
        cases = []
        while not self.accept("op", "}"):
            if self.accept("op", "("):
                pats = []
                while not self.accept("op", ")"):
                    pats.append(self.parse_pattern())
                    if not self.accept("op", ","):
                        self.expect("op", ")")
                        break
            else:
                p = self.parse_pattern()
                pats = [p] if p[0] != "default" else [p] * len(conds)
            self.expect("op", ":")
            cases.append((tuple(pats), self.parse_expr()))
            if not self.accept("op", ","):
                self.expect("op", "}")
                break
        self.accept("op", ",")
        self.expect("op", ")")
        return Select(conds, cases, line)


# ---- evaluation -----------------------------------------------------------

class SelectContext:
    """Answers select() conditions. Subclass and override `condition`.

    Must return a Python value (str or bool) or None when the variable is not
    set in this configuration (then only `default` cases match)."""

    def condition(self, func, args):
        raise BlueprintError(f"unsupported select condition {func}({', '.join(args)})")


def _plus(a, b, where):
    if a is UNSET:
        return b
    if b is UNSET:
        return a
    if isinstance(a, str) and isinstance(b, str):
        return a + b
    if isinstance(a, int) and isinstance(b, int) and not isinstance(a, bool):
        return a + b
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _plus(out[k], v, where) if k in out else v
        return out
    raise BlueprintError(f"{where}: cannot add {type(a).__name__} and {type(b).__name__}")


class Evaluator:
    def __init__(self, ctx, fname):
        self.ctx = ctx
        self.fname = fname

    def ev(self, node, scope):
        if isinstance(node, Lit):
            return node.v
        if isinstance(node, Var):
            if node.name not in scope:
                raise BlueprintError(f"{self.fname}:{node.line}: undefined variable {node.name}")
            return scope[node.name]
        if isinstance(node, ListN):
            out = []
            for it in node.items:
                v = self.ev(it, scope)
                if v is UNSET:
                    continue
                out.append(v)
            # Lists of lists only appear through select() results that were
            # spliced; Blueprint lists are flat.
            return out
        if isinstance(node, MapN):
            out = {}
            for k, vn in node.items:
                v = self.ev(vn, scope)
                if v is not UNSET:
                    out[k] = v
            return out
        if isinstance(node, Plus):
            acc = UNSET
            for a in node.args:
                acc = _plus(acc, self.ev(a, scope), self.fname)
            return acc
        if isinstance(node, Unset):
            return UNSET
        if isinstance(node, Select):
            return self.ev_select(node, scope)
        raise BlueprintError(f"bad node {node!r}")

    def ev_select(self, node, scope):
        vals = [self.ctx.condition(f, a) for f, a in node.conds]
        for pats, expr in node.cases:
            if len(pats) != len(vals):
                raise BlueprintError(f"{self.fname}:{node.line}: select pattern arity mismatch")
            bind = {}
            ok = True
            for p, v in zip(pats, vals):
                if p[0] == "default":
                    continue
                if p[0] == "any":
                    if v is None:
                        ok = False
                        break
                    if p[1]:
                        bind[p[1]] = v
                    continue
                if v is None or p[1] != v:
                    ok = False
                    break
            if ok:
                sc = scope if not bind else {**scope, **bind}
                return self.ev(expr, sc)
        # No case matched: Soong treats this as unset.
        return UNSET


def parse_file(path, ctx, parent_scope=None):
    """Parse and evaluate one Android.bp file.

    Returns (modules, scope) where modules is a list of
    (module_type, props_dict, line) and scope maps variable names to values.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    defs = Parser(text, path).parse_file()
    scope = dict(parent_scope or {})
    local = set()
    ev = Evaluator(ctx, path)
    modules = []
    for d in defs:
        if d[0] == "assign":
            _, name, op, node, line = d
            v = ev.ev(node, scope)
            if op == "+=":
                if name not in scope:
                    raise BlueprintError(f"{path}:{line}: += to undefined variable {name}")
                v = _plus(scope[name], v, path)
            scope[name] = v
            local.add(name)
        else:
            _, mtype, props, line = d
            out = {}
            for k, vn in props:
                v = ev.ev(vn, scope)
                if v is not UNSET:
                    out[k] = v
            modules.append((mtype, out, line))
    return modules, scope
