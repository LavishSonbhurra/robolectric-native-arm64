"""Which library this checkout builds, and where its inputs live.

RA64_TARGET (environment) picks the target:

  sdk36   (default) libandroid_runtime.so for SDK 36: config/aosp.toml,
          config/projects.toml, config/sources.lock.json,
          overrides/overrides.toml, patches/, sources in src/.
  compat  librobolectric-nativeruntime.so for SDK <= 34 (the library in
          org.robolectric:nativeruntime-dist-compat): the same files under
          config/compat/ (aosp.toml, projects.toml, sources.lock.json,
          overrides.toml, patches/), sources in src-compat/.

The default keeps every path the SDK 36 build has always used.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = os.environ.get("RA64_TARGET", "") or "sdk36"

if NAME == "sdk36":
    CONFIG = os.path.join(ROOT, "config")
    OVERRIDES = os.path.join(ROOT, "overrides", "overrides.toml")
    PATCHES = os.path.join(ROOT, "patches")
    SRC = os.path.join(ROOT, "src")
elif NAME == "compat":
    CONFIG = os.path.join(ROOT, "config", "compat")
    OVERRIDES = os.path.join(CONFIG, "overrides.toml")
    PATCHES = os.path.join(CONFIG, "patches")
    SRC = os.path.join(ROOT, "src-compat")
else:
    raise SystemExit(f"RA64_TARGET={NAME}: unknown target (have sdk36, compat)")

AOSP_TOML = os.path.join(CONFIG, "aosp.toml")
PROJECTS_TOML = os.path.join(CONFIG, "projects.toml")
LOCK = os.path.join(CONFIG, "sources.lock.json")
