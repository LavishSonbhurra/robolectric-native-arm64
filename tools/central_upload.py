#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Upload a bundle to the Central Portal and wait for its validation.

Always uploads as USER_MANAGED. A deployment that passes stops at VALIDATED and stays private
until someone presses Publish in the Portal, which is the permanent step, or drops it. This tool
has no publish action on purpose.

    CENTRAL_USERNAME=... CENTRAL_PASSWORD=... central_upload.py --bundle bundle.zip --name NAME

Exits 0 on VALIDATED and 1 on FAILED, printing the Portal's errors. The token pair is the one made
under "Generate User Token" in the Portal, not the account login.
"""
import argparse
import base64
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request
import uuid

API = "https://central.sonatype.com/api/v1/publisher"
FINISHED = {"VALIDATED", "FAILED", "PUBLISHED"}
POLL_SECONDS = 15
TIMEOUT_SECONDS = 1800


def request(url, token, data=None, content_type=None):
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as response:
        return response.read().decode()


def upload(bundle, name, token):
    boundary = uuid.uuid4().hex
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="bundle"; filename="{bundle.name}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        bundle.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    query = urllib.parse.urlencode({"name": name, "publishingType": "USER_MANAGED"})
    return request(f"{API}/upload?{query}", token, body,
                   f"multipart/form-data; boundary={boundary}").strip()


def wait(deployment, token):
    deadline = time.monotonic() + TIMEOUT_SECONDS
    query = urllib.parse.urlencode({"id": deployment})
    while time.monotonic() < deadline:
        status = json.loads(request(f"{API}/status?{query}", token))
        state = status.get("deploymentState")
        print(f"state: {state}", flush=True)
        if state in FINISHED:
            return status
        time.sleep(POLL_SECONDS)
    sys.exit(f"Deployment {deployment} did not finish validating in {TIMEOUT_SECONDS} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bundle", type=pathlib.Path, required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()

    credentials = f"{os.environ['CENTRAL_USERNAME']}:{os.environ['CENTRAL_PASSWORD']}"
    token = base64.b64encode(credentials.encode()).decode()

    deployment = upload(args.bundle, args.name, token)
    print(f"deployment: {deployment}", flush=True)
    status = wait(deployment, token)

    if status.get("deploymentState") == "FAILED":
        print(json.dumps(status.get("errors"), indent=2))
        sys.exit(1)
    print("Validated. Nothing is public yet: publish or drop it at "
          "https://central.sonatype.com/publishing/deployments")


if __name__ == "__main__":
    main()
