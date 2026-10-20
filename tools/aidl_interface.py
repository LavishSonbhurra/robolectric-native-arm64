"""Expand aidl_interface modules into the modules Soong's aidl plugin creates.

Mirrors system/tools/aidl/build (aidl_interface.go, aidl_interface_backends.go,
aidl_gen_rule.go) for the C++ backends we need (ndk and cpp):

  <name>-V<ver>-<lang>-source   aidl code generation (Gen of kind "aidl")
  <name>-V<ver>-<lang>          cc_library compiling the generated code

for every frozen version plus the next version. Unstable interfaces have no
version suffix. Only what is needed to compile against the generated code
is modelled (no API dump checks, no rust/java backends).
"""

import os
import re

AIDL_API_DIR = "aidl_api"


def versioned_name(name, version):
    return name if version == "" else f"{name}-V{version}"


def parse_versioned(s):
    m = re.match(r"^(.*)-V(\d+)$", s)
    return (m.group(1), m.group(2)) if m else (s, "")


class Iface:
    def __init__(self, name, mdir, props):
        self.name = name
        self.dir = mdir
        self.p = props
        self.unstable = bool(props.get("unstable"))
        if props.get("versions"):
            self.versions = list(props["versions"])
        else:
            self.versions = [v["version"] for v in props.get("versions_with_info", [])]
        self.frozen = bool(props.get("frozen"))

    def next_version(self):
        if self.unstable:
            return ""
        if not self.versions:
            return "1"
        return str(int(self.versions[-1]) + 1)

    def latest_version(self):
        return self.versions[-1] if self.versions else "0"

    def imports_for_version(self, version):
        for v in self.p.get("versions_with_info", []):
            if v["version"] == version:
                return list(v.get("imports", []))
        return list(self.p.get("imports", []))

    def srcs_for_version(self, src_root, version):
        """Returns (list of (absolute file, path relative to aidl root), root abs)."""
        import glob
        base = os.path.join(src_root, self.dir)
        if version == self.next_version():
            root = os.path.join(base, self.p.get("local_include_dir", ""))
            files = []
            for pat in self.p.get("srcs", []):
                if pat.startswith(":"):
                    return None  # filegroup sources: resolved by the caller
                hits = sorted(glob.glob(os.path.join(base, pat), recursive=True))
                files += hits
            return [(f, os.path.relpath(f, root)) for f in files], root
        root = os.path.join(base, AIDL_API_DIR, self.name, version)
        files = sorted(glob.glob(os.path.join(root, "**", "*.aidl"), recursive=True))
        return [(f, os.path.relpath(f, root)) for f in files], root

    def import_with_version(self, version, an_import, other):
        if parse_versioned(an_import)[1]:
            return an_import
        if other.unstable:
            return an_import
        if version == self.next_version() or not other.versions:
            return versioned_name(other.name, other.next_version())
        return versioned_name(other.name, other.latest_version())

    def gen_trace(self, lang):
        b = self.p.get("backend", {}).get(lang, {})
        return b.get("gen_trace", True) if lang in ("cpp", "ndk") else bool(b.get("gen_trace"))

    def min_sdk(self, lang):
        return self.p.get("backend", {}).get(lang, {}).get("min_sdk_version", self.p.get("min_sdk_version"))

    def lang_enabled(self, lang):
        return self.p.get("backend", {}).get(lang, {}).get("enabled", True)

    def flags_for_version(self, version):
        if version == self.next_version() and not self.frozen:
            return ["-Weverything", "-Wno-missing-permission-annotation"] + list(self.p.get("flags", []))
        return []


def expand(gen):
    """Register synthetic modules for every aidl_interface in the index."""
    from bp2cmake import Module
    idx = gen.index
    ifaces = {}
    for name, m in list(idx.modules.items()):
        if m.type != "aidl_interface":
            continue
        _, props = gen.res.resolve(name)
        ifaces[name] = Iface(name, m.dir, props)
    gen.aidl_ifaces = ifaces
    for name, it in ifaces.items():
        m = idx.modules[name]
        versions = [it.next_version()] + list(it.versions)
        for lang in ("ndk", "cpp"):
            if not it.lang_enabled(lang):
                continue
            for v in versions:
                vn = versioned_name(name, v)
                src_name = f"{vn}-{lang}-source"
                lib_name = f"{vn}-{lang}"
                imports = [parse_versioned(i) for i in it.imports_for_version(v)]
                import_libs = []
                for iname, _ in imports:
                    other = ifaces.get(iname)
                    if other is None:
                        continue
                    orig = next(x for x in it.imports_for_version(v) if parse_versioned(x)[0] == iname)
                    import_libs.append(it.import_with_version(v, orig, other) + "-" + lang)
                deps = ["libbinder_ndk"] if lang == "ndk" else ["libbinder", "libutils"]
                backend = it.p.get("backend", {}).get(lang, {})
                props = {
                    "name": lib_name,
                    "host_supported": it.p.get("host_supported", False),
                    "defaults": ["aidl-cpp-module-defaults"],
                    "generated_sources": [src_name],
                    "generated_headers": [src_name],
                    "export_generated_headers": [src_name],
                    "shared_libs": deps + list(backend.get("additional_shared_libraries", [])) +
                    (["libcutils"] if lang == "cpp" and it.gen_trace(lang) else []) + import_libs,
                    "export_shared_lib_headers": deps + import_libs,
                    "cflags": list(backend.get("cflags", [])) + ["-Wextra", "-Wall", "-Werror", "-Wextra-semi"],
                    "include_build_directory": False,
                }
                if lang == "ndk":
                    props["target"] = {"platform": {"cflags": ["-DBINDER_STABILITY_SUPPORT"]}}
                lm = Module("cc_library", props, m.dir, m.file, m.line)
                idx.modules.setdefault(lib_name, lm)
                sm = Module("aidl_gen", {"name": src_name, "iface": name, "version": v, "lang": lang},
                            m.dir, m.file, m.line)
                idx.modules.setdefault(src_name, sm)
