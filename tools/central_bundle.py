#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Sign a Maven repository directory and pack it into a Central Portal bundle.

Takes the directory that `./gradlew publish...ToStagingRepository` wrote and makes a zip with the
same layout, plus a detached .asc signature for every artifact. Gradle's maven-metadata files are
left out, since Central generates its own, and missing .md5 or .sha1 files are a hard error.

    central_bundle.py --repo build/central-staging --key <fingerprint> --out bundle.zip

The key comes from the gpg keyring in GNUPGHOME, and its passphrase from the file named by
--passphrase-file. Timestamps in the zip are fixed. The .asc files are not reproducible, because
a signature holds its own creation time.
"""
import argparse
import hashlib
import pathlib
import subprocess
import sys
import zipfile

CHECKSUMS = (".md5", ".sha1", ".sha256", ".sha512")
ZIP_TIME = (1980, 2, 1, 0, 0, 0)


def is_artifact(path):
    return path.suffix not in CHECKSUMS and path.suffix != ".asc"


def check_checksums(path):
    """The problems with the .md5 and .sha1 files next to `path`."""
    data = path.read_bytes()
    problems = []
    for suffix, digest in ((".md5", hashlib.md5), (".sha1", hashlib.sha1)):
        sidecar = path.with_name(path.name + suffix)
        if not sidecar.is_file():
            problems.append(f"{sidecar}: missing")
        elif sidecar.read_text().strip() != digest(data).hexdigest():
            problems.append(f"{sidecar}: wrong checksum")
    return problems


def sign(path, key, passphrase_file):
    asc = path.with_name(path.name + ".asc")
    asc.unlink(missing_ok=True)
    subprocess.run(
        ["gpg", "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback",
         "--passphrase-file", str(passphrase_file), "--local-user", key,
         "--armor", "--detach-sign", "--output", str(asc), str(path)],
        check=True,
    )
    subprocess.run(["gpg", "--batch", "--quiet", "--verify", str(asc), str(path)],
                   check=True, stderr=subprocess.DEVNULL)
    return asc


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", type=pathlib.Path, required=True)
    ap.add_argument("--key", required=True, help="full key fingerprint")
    ap.add_argument("--passphrase-file", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    files = sorted(
        p for p in args.repo.rglob("*")
        if p.is_file() and not p.name.startswith("maven-metadata")
    )
    artifacts = [p for p in files if is_artifact(p)]
    if not any(p.suffix == ".pom" for p in artifacts):
        sys.exit(f"{args.repo}: no POM found")

    problems = [problem for p in artifacts for problem in check_checksums(p)]
    if problems:
        sys.exit("\n".join(problems))

    signatures = [sign(p, args.key, args.passphrase_file) for p in artifacts]
    members = sorted(set(files) | set(signatures))

    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in members:
            info = zipfile.ZipInfo(path.relative_to(args.repo).as_posix(), ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, path.read_bytes())

    print(f"{args.out}: {len(artifacts)} artifacts, {len(members)} files, "
          f"{args.out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
