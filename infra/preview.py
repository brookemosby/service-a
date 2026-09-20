#!/usr/bin/env python3
"""Resolve and apply preview environments. Run from GitHub Actions only."""

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

INFRA_DIR = Path(__file__).resolve().parent
ROOT = INFRA_DIR.parent
sys.path.insert(0, str(INFRA_DIR))

from env_id import normalize_env_id  # noqa: E402

DEFAULT_BRANCH = "main"
REPO_A = "service-a"
REPO_B = "service-b"

GITHUB_OWNER = os.environ["GITHUB_OWNER"]
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
ECR_SERVICE_A_URI = os.environ["ECR_SERVICE_A_URI"]
ECR_SERVICE_B_URI = os.environ["ECR_SERVICE_B_URI"]
AWS_ACCOUNT_ID = os.environ["AWS_ACCOUNT_ID"]
AWS_REGION = os.environ["AWS_REGION"]
PREVIEW_EVENT = os.environ.get("PREVIEW_EVENT", "deploy")
TRIGGER_REPO = os.environ.get("TRIGGER_REPO")
TRIGGER_BRANCH = os.environ.get("TRIGGER_BRANCH")
TRIGGER_SHA = os.environ.get("TRIGGER_SHA")


def github_request(path):
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def open_branch_map(repo):
    query = urllib.parse.urlencode({"state": "open", "per_page": 100})
    prs = github_request(f"/repos/{GITHUB_OWNER}/{repo}/pulls?{query}")
    return {pr["head"]["ref"]: pr["head"]["sha"] for pr in prs}


def image_ref(ecr_uri, branch, sha):
    if branch == DEFAULT_BRANCH:
        return f"{ecr_uri}:main"
    return f"{ecr_uri}:sha-{sha[:7]}"


def service_image(branch, branches, ecr_uri):
    if branch in branches:
        return image_ref(ecr_uri, branch, branches[branch])
    return image_ref(ecr_uri, DEFAULT_BRANCH, None)


def active_branches(include_trigger):
    a_branches = open_branch_map(REPO_A)
    b_branches = open_branch_map(REPO_B)

    if include_trigger and TRIGGER_BRANCH and TRIGGER_BRANCH != DEFAULT_BRANCH and TRIGGER_REPO:
        branches = a_branches if TRIGGER_REPO == REPO_A else b_branches
        if TRIGGER_SHA:
            branches.setdefault(TRIGGER_BRANCH, TRIGGER_SHA)

    return a_branches, b_branches


def environment_for_branch(branch, a_branches, b_branches):
    return {
        "env_id": normalize_env_id(branch),
        "service_a_image": service_image(branch, a_branches, ECR_SERVICE_A_URI),
        "service_b_image": service_image(branch, b_branches, ECR_SERVICE_B_URI),
    }


def build_payload():
    include_trigger = PREVIEW_EVENT != "teardown"
    a_branches, b_branches = active_branches(include_trigger)
    environments = [
        environment_for_branch(branch, a_branches, b_branches)
        for branch in sorted(set(a_branches) | set(b_branches))
    ]

    payload = {"environments": environments}
    if PREVIEW_EVENT == "teardown" and TRIGGER_BRANCH and TRIGGER_BRANCH != DEFAULT_BRANCH:
        if TRIGGER_BRANCH not in a_branches and TRIGGER_BRANCH not in b_branches:
            payload["destroy_env_ids"] = [normalize_env_id(TRIGGER_BRANCH)]

    return payload


def ensure_cdk_dependencies():
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "-r", "infra/requirements.txt"],
        cwd=ROOT,
    )


def run_cdk(action, env_id, env=None):
    safe_env_id = normalize_env_id(env_id)
    service_a_image = (env or {}).get("service_a_image", f"{ECR_SERVICE_A_URI}:main")
    service_b_image = (env or {}).get("service_b_image", f"{ECR_SERVICE_B_URI}:main")

    command = [
        "npx",
        "--yes",
        "aws-cdk@2",
        action,
        f"Preview-{safe_env_id}",
        "-c",
        f"account={AWS_ACCOUNT_ID}",
        "-c",
        f"region={AWS_REGION}",
        "-c",
        f"env_id={safe_env_id}",
        "-c",
        f"service_a_image={service_a_image}",
        "-c",
        f"service_b_image={service_b_image}",
        "--app",
        "python3 infra/app.py",
    ]
    if action == "deploy":
        command.extend(["--require-approval", "never"])
    else:
        command.append("--force")

    subprocess.check_call(command, cwd=ROOT)


def sync():
    payload = build_payload()
    print(json.dumps(payload, indent=2))
    ensure_cdk_dependencies()

    for env_id in payload.get("destroy_env_ids", []):
        run_cdk("destroy", env_id)

    for env in payload["environments"]:
        run_cdk("deploy", env["env_id"], env)


if __name__ == "__main__":
    sync()
