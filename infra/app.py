#!/usr/bin/env python3

import sys
from pathlib import Path

import aws_cdk as cdk

sys.path.insert(0, str(Path(__file__).resolve().parent))

from baseline_stack import BaselineStack
from env_id import normalize_env_id
from preview_stack import PreviewStack

app = cdk.App()

github_org = app.node.try_get_context("github_org") or "YOUR_GITHUB_ORG"
github_repo_a = app.node.try_get_context("github_repo_a") or "service-a"
github_repo_b = app.node.try_get_context("github_repo_b") or "service-b"

BaselineStack(
    app,
    "BaselineStack",
    github_org=github_org,
    github_repo_a=github_repo_a,
    github_repo_b=github_repo_b,
    env=cdk.Environment(
        account=app.node.try_get_context("account"),
        region=app.node.try_get_context("region") or "us-east-1",
    ),
)

env_id = app.node.try_get_context("env_id")
if env_id:
    normalized_env_id = normalize_env_id(env_id)
    PreviewStack(
        app,
        f"Preview-{normalized_env_id}",
        env_id=normalized_env_id,
        service_a_image=app.node.try_get_context("service_a_image"),
        service_b_image=app.node.try_get_context("service_b_image"),
        env=cdk.Environment(
            account=app.node.try_get_context("account"),
            region=app.node.try_get_context("region") or "us-east-1",
        ),
    )

app.synth()
