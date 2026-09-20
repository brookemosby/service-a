# service-a

Service A + AWS CDK for ephemeral preview environments. Service B is a separate repo.

## Bootstrap

```bash
pip install -r infra/requirements.txt
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://${ACCOUNT_ID}/us-east-1
cdk deploy BaselineStack \
  -c account=${ACCOUNT_ID} \
  -c github_org=YOUR_ORG \
  -c github_repo_a=service-a \
  -c github_repo_b=service-b
```

GitHub secrets (service-a): `AWS_DEPLOY_ROLE_ARN`, `AWS_ACCOUNT_ID`, `ECR_SERVICE_A_URI`, `ECR_SERVICE_B_URI`. Service-b also needs `GH_DISPATCH_TOKEN`.

Repo names (`service-a`, `service-b`) are hardcoded in `infra/preview.py`. The orchestrator workflow sets `GITHUB_OWNER`; other required env vars must be present or the job fails fast.

## Preview linking (branch names only)

Each active branch name gets one stack: `Preview-{branch}`. A service uses that branch if its repo has it open, otherwise `main`.

| Situation | Env id | Service A | Service B |
|-----------|--------|-----------|-----------|
| Branch `foo` in A only | `foo` | `foo` | `main` |
| Branch `foo` in B only | `foo` | `main` | `foo` |
| Branch `foo` in both | `foo` | `foo` | `foo` |

When one side merges/closes but the other still has the branch, the shared stack is **redeployed** with the closed side on `:main`. The stack is destroyed only when neither repo has that branch open.

URLs: `http://{alb-dns}/preview/{env_id}/a/items` and `/b/items`

Previews are managed via GitHub Actions (`preview.yml` → `orchestrate.yml` → `infra/preview.py`).
