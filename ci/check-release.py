#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check a Maven staging repository against the assets of a GitHub release.

    ci/check-release.py --repo build/central-staging --release release

Central versions are permanent, so every artifact is checked in both directions: a jar that is
only in one of the two is an error, not something to skip. Stops on:

* an artifact missing from the repository, or an extra one;
* a jar or sources jar missing from either side, or differing byte for byte;
* a javadoc jar missing from either side, or with different entries. Its bytes are not compared:
  the generated pages can change with a JDK patch release, and they are not code;
* a checksum file of the release missing, holding an entry for a file that is not there, or a
  release asset that no checksum file lists;
* a library jar without its library, its notices, LICENSE or NOTICE, or a loader jar with a library;
* a POM or module file whose dependencies are not the library artifacts at the versions in this
  repository, or a library POM without the sentences its notices require.

Standard library only; run with python3 -I.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import xml.etree.ElementTree as ET
import zipfile

GROUP = "io.github.lavishsonbhurra"
LOADER = "robolectric-nativeruntime-linux-aarch64"
# Artifact -> where its library is; the loader has none.
LIBRARIES = {
    "robolectric-nativeruntime-sdk35-linux-aarch64": "native/linux/aarch64/sdk35/libandroid_runtime.so",
    "robolectric-nativeruntime-sdk36-linux-aarch64": "native/linux/aarch64/sdk36/libandroid_runtime.so",
    "robolectric-nativeruntime-sdk37-linux-aarch64": "native/linux/aarch64/sdk37/libandroid_runtime.so",
    "robolectric-nativeruntime-compat-linux-aarch64": "native/linux/aarch64/librobolectric-nativeruntime.so",
    "robolectric-nativeruntime-compat-linux-aarch64-x86pixels":
        "native/linux/aarch64/x86-pixels/librobolectric-nativeruntime.so",
}
# The x86-pixels build is opt-in, so the loader does not depend on it.
LOADER_DEPENDENCIES = sorted(a for a in LIBRARIES if not a.endswith("-x86pixels"))
CHECKSUM_FILES = ["SHA256SUMS", "sdk35-SHA256SUMS", "sdk36-SHA256SUMS", "sdk37-SHA256SUMS", "compat-SHA256SUMS"]
# Sentences a licence requires in the documentation: printed at the top of the notices file, and
# wanted in the POM description of the artifact that holds the code.
REQUIRED_IN_POM = (
    "This product includes DNG technology under license by Adobe Systems Incorporated.",
    "This product includes Gain Map technology under license by Adobe.",
)
POM = "{http://maven.apache.org/POM/4.0.0}"


def check_checksums(release, problems):
    listed_anywhere = set()
    for name in CHECKSUM_FILES:
        path = release / name
        if not path.is_file():
            problems.append(f"{name}: not in the release")
            continue
        for line in path.read_text().splitlines():
            digest, _, listed = line.partition("  ")
            target = release / listed.lstrip("*")
            listed_anywhere.add(target.name)
            if not target.is_file():
                problems.append(f"{name}: lists {listed}, which is not in the release")
            elif hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                problems.append(f"{name}: {listed} does not match")
    for asset in sorted(p.name for p in release.iterdir() if p.is_file()):
        if asset not in listed_anywhere and asset not in CHECKSUM_FILES:
            problems.append(f"{asset}: in the release, but in no checksum file")


def versions(repo, problems):
    """artifact -> version, from the directory layout."""
    root = repo.joinpath(*GROUP.split("."))
    found = {}
    for artifact in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
        dirs = [p.name for p in artifact.iterdir() if p.is_dir()]
        if len(dirs) != 1:
            problems.append(f"{artifact.name}: expected one version, found {dirs}")
            continue
        found[artifact.name] = dirs[0]
    expected = {LOADER, *LIBRARIES}
    for missing in sorted(expected - set(found)):
        problems.append(f"{missing}: not in the repository")
    for extra in sorted(set(found) - expected):
        problems.append(f"{extra}: not an artifact of this project")
    return found


def check_jars(repo, release, problems):
    built = {p.name: p for p in repo.rglob("*.jar")}
    held = {p.name: p for p in release.glob("*.jar")}
    for name in sorted(set(built) - set(held)):
        problems.append(f"{name}: built, but not in the release")
    for name in sorted(set(held) - set(built)):
        problems.append(f"{name}: in the release, but not built")
    for name in sorted(set(built) & set(held)):
        if name.endswith("-javadoc.jar"):
            with zipfile.ZipFile(built[name]) as ours, zipfile.ZipFile(held[name]) as theirs:
                if ours.namelist() != theirs.namelist():
                    problems.append(f"{name}: entries differ from the release")
        elif built[name].read_bytes() != held[name].read_bytes():
            problems.append(f"{name}: differs from the release")
    return len(set(built) & set(held))


def check_contents(repo, found, problems):
    for artifact, version in found.items():
        base = repo.joinpath(*GROUP.split("."), artifact, version)
        stem = f"{artifact}-{version}"
        for suffix in (".jar", "-sources.jar", "-javadoc.jar", ".pom", ".module"):
            if not (base / f"{stem}{suffix}").is_file():
                problems.append(f"{stem}{suffix}: missing")
        if not (base / f"{stem}.jar").is_file() or not (base / f"{stem}.pom").is_file():
            continue
        with zipfile.ZipFile(base / f"{stem}.jar") as jar:
            names = set(jar.namelist())
            notices = jar.read("META-INF/THIRD_PARTY_NOTICES").decode() if "META-INF/THIRD_PARTY_NOTICES" in names else ""
        for wanted in ("META-INF/LICENSE", "META-INF/NOTICE"):
            if wanted not in names:
                problems.append(f"{stem}.jar: no {wanted}")
        libraries = {n for n in names if n.endswith(".so")}
        description = ET.parse(base / f"{stem}.pom").getroot().findtext(f"{POM}description") or ""
        if artifact == LOADER:
            if libraries:
                problems.append(f"{stem}.jar: holds {sorted(libraries)}; the loader holds no library")
            continue
        if libraries != {LIBRARIES[artifact]}:
            problems.append(f"{stem}.jar: holds {sorted(libraries)}, expected {LIBRARIES[artifact]}")
        if not notices:
            problems.append(f"{stem}.jar: no META-INF/THIRD_PARTY_NOTICES")
        top = notices.split("=" * 60)[0]
        for sentence in REQUIRED_IN_POM:
            if sentence in top and sentence not in description:
                problems.append(f"{stem}.pom: description lacks: {sentence}")
            if sentence in description and sentence not in top:
                problems.append(f"{stem}.pom: description says what the notices do not: {sentence}")
        for kind in ("sources", "javadoc"):
            path = base / f"{stem}-{kind}.jar"
            if path.is_file():
                with zipfile.ZipFile(path) as jar:
                    wanted = {"META-INF/LICENSE", "META-INF/NOTICE", "SOURCES.txt"} - set(jar.namelist())
                if wanted:
                    problems.append(f"{path.name}: no {sorted(wanted)}")


def check_dependencies(repo, found, problems):
    if LOADER not in found:
        return
    want = {a: found[a] for a in LOADER_DEPENDENCIES if a in found}
    base = repo.joinpath(*GROUP.split("."), LOADER, found[LOADER])
    stem = f"{LOADER}-{found[LOADER]}"
    pom = ET.parse(base / f"{stem}.pom").getroot()
    deps = pom.findall(f"{POM}dependencies/{POM}dependency")
    got = {d.findtext(f"{POM}artifactId"): d.findtext(f"{POM}version") for d in deps}
    if got != want:
        problems.append(f"{stem}.pom: dependencies {got}, expected {want}")
    for d in deps:
        if d.findtext(f"{POM}scope") != "runtime" or d.findtext(f"{POM}groupId") != GROUP:
            problems.append(f"{stem}.pom: {d.findtext(f'{POM}artifactId')}: wrong group or scope")
    # Gradle reads this file instead of the POM, so it has to say the same.
    module = json.loads((base / f"{stem}.module").read_text())
    for variant in module["variants"]:
        got = {d["module"]: d["version"]["requires"] for d in variant.get("dependencies", [])}
        expected = want if variant["name"] == "runtimeElements" else {}
        if got != expected:
            problems.append(f"{stem}.module: {variant['name']}: dependencies {got}, expected {expected}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=pathlib.Path, required=True)
    ap.add_argument("--release", type=pathlib.Path, required=True)
    args = ap.parse_args()

    problems = []
    check_checksums(args.release, problems)
    found = versions(args.repo, problems)
    same = check_jars(args.repo, args.release, problems)
    check_contents(args.repo, found, problems)
    check_dependencies(args.repo, found, problems)
    for problem in problems:
        print("FAIL", problem)
    print(f"{len(found)} artifacts, {same} jars compared with the release, {len(problems)} problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
