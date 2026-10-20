#!/bin/sh
# Install the Rust compiler Soong uses at the AOSP pin (RustDefaultVersion in
# build/soong/rust/config/global.go) into rust/toolchain/, from the official
# standalone tarball on static.rust-lang.org. Only the rustc and rust-std
# components are installed; no rustup, no cargo, no docs.
#
# --target TRIPLE (repeatable) also installs the standard library for that
# target from its rust-std tarball, for cross builds (RA64_ARCH=x86_64 on an
# arm64 machine needs x86_64-unknown-linux-gnu).
#
# Every tarball is checked against the SHA-256 pinned below and against its
# detached GPG signature, made by the Rust release key whose fingerprint is
# pinned below. The key is imported into a throwaway keyring.
#
# Usage: rust/install-toolchain.sh [--target TRIPLE]...
#        (idempotent; reuses verified downloads)
set -eu

VERSION=1.83.0
TRIPLE=aarch64-unknown-linux-gnu
# rust-1.83.0-aarch64-unknown-linux-gnu.tar.xz, as published in
# https://static.rust-lang.org/dist/rust-1.83.0-aarch64-unknown-linux-gnu.tar.xz.sha256
SHA256=5f02e00bca65f6eebafe2ac6b1bbdecb5f160f260a9c2231a51ed8d382f0ada0
# Rust Language (Tag and Release Signing Key) <rust-key@rust-lang.org>
KEY_FPR=108F66205EAEB0AAA8DD5E1C85AB96E6FA1BE5FE
# rustc's commit hash for 1.83.0. Also appears in the official
# libandroid_runtime.so as /rustc/<hash>/library/...
COMMIT=90b35a6239c3d8bdabc530a6a0816f7ff89a0aaf

# rust-std-1.83.0-<triple>.tar.xz, from the published .sha256 files.
std_sha256() {
    case $1 in
        x86_64-unknown-linux-gnu) echo c88fe6cb22f9d2721f26430b6bdd291e562da759e8629e2b4c7eb2c7cad705f2 ;;
        *) echo "no pinned rust-std hash for $1" >&2; exit 1 ;;
    esac
}

TARGETS=
while [ $# -gt 0 ]; do
    case $1 in
        --target) TARGETS="$TARGETS $2"; shift 2 ;;
        --target=*) TARGETS="$TARGETS ${1#--target=}"; shift ;;
        *) echo "usage: $0 [--target TRIPLE]..." >&2; exit 2 ;;
    esac
done

HERE=$(cd "$(dirname "$0")" && pwd)
TC="$HERE/toolchain"
DL="$TC/dl"
BASE=https://static.rust-lang.org/dist

mkdir -p "$DL"
GNUPGHOME=
cleanup() { [ -z "$GNUPGHOME" ] || rm -rf "$GNUPGHOME"; }
trap cleanup EXIT

# fetch_verified NAME SHA256: download NAME.tar.xz (unless a copy with the
# right hash is there), check the hash and the signature.
fetch_verified() {
    f="$DL/$1.tar.xz"
    if [ ! -f "$f" ] || ! echo "$2  $f" | sha256sum -c --quiet - 2>/dev/null; then
        rm -f "$f"
        curl -fsSL -o "$f.part" "$BASE/$1.tar.xz"
        mv "$f.part" "$f"
    fi
    curl -fsSL -o "$f.asc" "$BASE/$1.tar.xz.asc"
    echo "$2  $f" | sha256sum -c -
    if [ -z "$GNUPGHOME" ]; then
        curl -fsSL -o "$DL/rust-key.gpg.ascii" "$BASE/../rust-key.gpg.ascii"
        GNUPGHOME=$(mktemp -d "$TC/gnupg.XXXXXX")
        export GNUPGHOME
        gpg --batch --quiet --import "$DL/rust-key.gpg.ascii"
        gpg --batch --list-keys --with-colons | grep -q "^fpr:::::::::$KEY_FPR:" \
            || { echo "imported key is not $KEY_FPR" >&2; exit 1; }
    fi
    gpg --batch --status-fd 1 --verify "$f.asc" "$f" 2>/dev/null \
        | grep -q "^\[GNUPG:\] VALIDSIG .* $KEY_FPR\$" \
        || { echo "$1: bad or missing signature by $KEY_FPR" >&2; exit 1; }
    echo "$1: signature OK (primary key $KEY_FPR)"
}

if [ -x "$TC/bin/rustc" ] && "$TC/bin/rustc" -vV | grep -q "commit-hash: $COMMIT"; then
    echo "rustc $VERSION already installed in $TC"
else
    NAME="rust-$VERSION-$TRIPLE"
    fetch_verified "$NAME" "$SHA256"
    # Each component directory mirrors the install prefix (bin/, lib/, ...), so
    # extracting it with the two leading path elements stripped is what
    # install.sh would do, without running a script from the tarball.
    rm -rf "$TC/bin" "$TC/lib" "$TC/libexec" "$TC/share" "$TC/etc"
    tar -xJf "$DL/$NAME.tar.xz" -C "$TC" --strip-components=2 \
        --exclude='*/manifest.in' \
        "$NAME/rustc" "$NAME/rust-std-$TRIPLE"
    "$TC/bin/rustc" -vV
    "$TC/bin/rustc" -vV | grep -q "commit-hash: $COMMIT"
fi

for t in $TARGETS; do
    [ "$t" = "$TRIPLE" ] && continue
    if [ -d "$TC/lib/rustlib/$t/lib" ]; then
        echo "rust-std $VERSION for $t already installed"
        continue
    fi
    NAME="rust-std-$VERSION-$t"
    fetch_verified "$NAME" "$(std_sha256 "$t")"
    tar -xJf "$DL/$NAME.tar.xz" -C "$TC" --strip-components=2 \
        --exclude='*/manifest.in' "$NAME/rust-std-$t"
    [ -d "$TC/lib/rustlib/$t/lib" ] || { echo "rust-std for $t did not install" >&2; exit 1; }
    echo "rust-std $VERSION for $t installed"
done
