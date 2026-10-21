"""Evaluate an AOSP release config (build/release) the way Soong's
release_config tool does, for the parts we need:

* build flag values (RELEASE_*), used by select(release_flag(...)) and by the
  aconfig rules (default permission, read-only enforcement);
* the ordered list of aconfig value sets (RELEASE_ACONFIG_VALUE_SETS).

Reference: build/soong/cmd/release_config/release_config_lib/release_config.go
(GenerateReleaseConfig). Rules replicated here:

* a config of type RELEASE_CONFIG implicitly inherits "root" first;
* inherited configs are generated fully, then the config's own flag_values/
  directory is applied on top;
* build-prefix configs (two letters, two digits, letter: "bp2a") force
  RELEASE_PLATFORM_VERSION to their upper-cased name;
* the build-variant config (user/userdebug/eng) is only inherited when
  RELEASE_BUILD_USE_VARIANT_FLAGS is non-empty.
"""

import glob
import os
import re


def parse_textproto(text):
    """Minimal protobuf text-format parser (enough for build/release files).

    Returns a dict mapping field name to a list of values; nested messages
    become dicts of the same shape."""
    toks = re.findall(r'"(?:[^"\\]|\\.)*"|[{}:]|[^\s{}:"]+', re.sub(r"#[^\n]*", "", text))
    pos = 0

    def msg(end):
        nonlocal pos
        out = {}
        while pos < len(toks) and toks[pos] != end:
            name = toks[pos]
            pos += 1
            if toks[pos] == ":":
                pos += 1
            if toks[pos] == "{":
                pos += 1
                v = msg("}")
                pos += 1
            else:
                t = toks[pos]
                pos += 1
                if t.startswith('"'):
                    v = bytes(t[1:-1], "utf-8").decode("unicode_escape")
                elif t in ("true", "false"):
                    v = t == "true"
                else:
                    v = t
            out.setdefault(name, []).append(v)
        return out

    return msg(None)


def _value(v):
    """Release flag Value message -> Soong's string form ("" for false/unset)."""
    if not v:
        return ""
    v = v[0]
    if "bool_value" in v:
        return "true" if v["bool_value"][0] else ""
    if "string_value" in v:
        return v["string_value"][0]
    if "unspecified_value" in v:
        return ""
    if "obsolete" in v:
        return ""
    return ""


class NoReleaseConfig:
    """For trees that predate build/release (Android 12): no flags, no
    aconfig value sets."""

    name = None
    decls = {}
    flags = {}
    value_sets = []
    chain = []
    variant_applied = None

    def flag(self, name):
        return None


class ReleaseConfig:
    def __init__(self, release_dir, name, variant=""):
        self.dir = release_dir
        self.name = name
        self.decls = {}
        for p in glob.glob(os.path.join(release_dir, "flag_declarations", "*.textproto")):
            with open(p) as f:
                d = parse_textproto(f.read())
            self.decls[d["name"][0]] = {
                "value": _value(d.get("value")),
                "workflow": d.get("workflow", [""])[0],
            }
        self.configs = {}
        for p in glob.glob(os.path.join(release_dir, "release_configs", "*.textproto")):
            with open(p) as f:
                d = parse_textproto(f.read())
            self.configs[d["name"][0]] = d
        self.chain = []
        self.flags = {k: v["value"] for k, v in self.decls.items()}
        self.value_sets = []
        self._generate(name, set())
        if self.flags.get("RELEASE_BUILD_USE_VARIANT_FLAGS") and variant:
            self._generate(variant, set())
            self.variant_applied = variant
        else:
            self.variant_applied = None
        seen = set()
        self.value_sets = [v for v in self.value_sets if not (v in seen or seen.add(v))]

    def _generate(self, name, stack):
        if name in stack:
            raise ValueError(f"release config loop at {name}")
        d = self.configs[name]
        ctype = d.get("release_config_type", ["RELEASE_CONFIG"])[0]
        inherits = list(d.get("inherits", []))
        if ctype == "RELEASE_CONFIG" and name != "root" and "root" in self.configs:
            inherits = ["root"] + inherits
        for inh in inherits:
            self._generate(inh, stack | {name})
        self.chain.append(name)
        self.value_sets.extend(d.get("aconfig_value_sets", []))
        if re.match(r"^[a-z][a-z][0-9][0-9a-z]$", name) and "RELEASE_PLATFORM_VERSION" in self.flags:
            self.flags["RELEASE_PLATFORM_VERSION"] = name.upper()
        for p in sorted(glob.glob(os.path.join(self.dir, "flag_values", name, "*.textproto"))):
            with open(p) as f:
                fv = parse_textproto(f.read())
            self.flags[fv["name"][0]] = _value(fv.get("value"))

    def flag(self, name):
        """Soong-style value: string, "" for false/unset, None if undeclared."""
        return self.flags.get(name)
