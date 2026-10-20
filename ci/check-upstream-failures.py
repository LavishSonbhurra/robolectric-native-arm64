#!/usr/bin/env python3
"""Compare the failures of an upstream-suite run with the list of known failures.

Usage: check-upstream-failures.py JUNIT_DIR --expected ci/upstream-expected-failures.txt
JUNIT_DIR holds the XML files, either flat or in one sub-directory per module
(robotests, nativegraphics, ctesque). Exit status 1 if a test fails that is not listed.
Listed tests that pass are reported but do not fail the job. Standard library only.
"""
import argparse
import glob
import os
import sys
import xml.etree.ElementTree as ET


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("junit")
    ap.add_argument("--expected", required=True)
    a = ap.parse_args()
    expected = set()
    for line in open(a.expected):
        if line.strip() and not line.startswith("#"):
            module, cls, name = line.rstrip("\n").split("\t")
            expected.add((module, cls, name))
    failed, total, passed = set(), 0, 0
    for path in sorted(glob.glob(os.path.join(a.junit, "**", "*.xml"), recursive=True)):
        rel = os.path.relpath(path, a.junit).split(os.sep)
        module = rel[0] if len(rel) > 1 else ""
        for case in ET.parse(path).getroot().iter("testcase"):
            if case.find("skipped") is not None:
                continue
            total += 1
            if case.find("failure") is not None or case.find("error") is not None:
                failed.add((module, case.get("classname"), case.get("name")))
            else:
                passed += 1
    new = sorted(f for f in failed if f not in expected)
    fixed = sorted(e for e in expected if e not in failed)
    print(f"{total} tests run, {passed} passed, {len(failed)} failed, {len(failed) - len(new)} of them known")
    for f in new:
        print("NEW FAILURE", *f, sep="\t")
    for f in fixed:
        print("now passing", *f, sep="\t")
    sys.exit(1 if new else 0)


if __name__ == "__main__":
    main()
