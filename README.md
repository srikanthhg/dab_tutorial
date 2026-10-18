# model-wheel on Databricks Asset Bundles

A standalone DAB-based deployment of the `model-wheel` agent. This repository is intentionally separate from `srikanthhg/model-wheel`; it does not modify that repository.

## What this deploys

- A Python wheel containing `model_wheel_demo` and its `greeting` tool.
- A Databricks Asset Bundle with `dev` and `prod` targets.
- A serverless Python-script job (when supported by the workspace) that logs an MLflow PyFunc model, registers it in Unity Catalog, creates or updates Model Serving, and assigns the `Champion` alias after the serving configuration request succeeds.
- GitHub Actions CI and target-specific deployment.
- A guarded workflow that can delete only the development serving endpoint.

## Architecture

1. GitHub Actions installs build/test tools, lints, builds the wheel, installs it, and runs tests.
2. Databricks CLI validates and deploys the bundle.
3. The bundle job runs on serverless job compute using the wheel and declared Python dependencies.
4. The job logs the agent as an MLflow PyFunc model and registers it in Unity Catalog.
5. The job creates or updates the target serving endpoint, then sets the model version's `Champion` alias.
6. Verify the endpoint is ready and query it before treating the release as production-ready.

## Environments

| Target | Unity Catalog model | Serving endpoint |
| --- | --- | --- |
| `dev` | `main.mlflow_demo_dev.demo_agent` | `model-wheel-dev-agent` |
| `prod` | `main.mlflow_demo.demo_agent` | `model-wheel-agent` |

The targets use different schemas and endpoints so development releases do not promote a production model's Champion alias. Create both schemas before deploying:

```sql
CREATE SCHEMA IF NOT EXISTS main.mlflow_demo_dev;
CREATE SCHEMA IF NOT EXISTS main.mlflow_demo;
```

Grant the deployment service principal the privileges needed to create registered models and versions, set aliases, use the LLM serving endpoint, and create/update the target serving endpoints. Ensure the model serving identity can access the LLM endpoint.

## GitHub setup

Create GitHub Actions environments named `development` and `production`.

Configure these **environment secrets** in both environments:

- `DATABRICKS_HOST`: workspace URL, such as `https://<workspace-host>`
- `DATABRICKS_CLIENT_ID`: Databricks service principal application/client ID

The workflow uses Databricks CLI OAuth with GitHub OIDC (`DATABRICKS_AUTH_TYPE=github-oidc`). Configure a matching GitHub OIDC federation policy for the service principal. Do not store a personal access token in the repository. Protect the `production` environment with required reviewers.

The default LLM endpoint is `databricks-meta-llama-3-3-70b-instruct`. It must already exist in the workspace.

## Local validation

Use Python 3.12 and a current Databricks CLI.

```bash
python -m pip install --upgrade build pytest ruff
python -m build
python -m pip install dist/*.whl
pytest -q
ruff check .

export DATABRICKS_HOST="https://<workspace-host>"
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev model_wheel_deploy
```

Production is deliberately a manual GitHub Actions workflow-dispatch choice and should only be run after reviewing the production environment and approval.

## CI/CD behavior

- Pull request to `main`: lint, build and test only.
- Push to `main`: test, then deploy to `dev`.
- Manual workflow dispatch: select `dev` or `prod`. The `production` GitHub environment can enforce reviewer approval.

## Cleanup safety

The **Delete development serving endpoint** workflow requires the exact phrase `DELETE model-wheel-dev-agent` and deletes only the hard-coded development endpoint. It does not delete Unity Catalog models, model versions, aliases, or the production endpoint.

Avoid running `databricks bundle destroy -t prod` as a routine cleanup command. Review the target and resources before destroying bundle-managed resources.

## Serverless compatibility and release caveats

Serverless support and dependency constraints vary by workspace, cloud and region. This bundle declares a serverless environment for a Python script task; validate it against your workspace. If the workspace rejects this task/environment combination or a dependency is unsupported, adjust the task to a serverless-supported form or deliberately switch to a bundle-managed job cluster. Do not silently use an unrelated existing cluster.

The workflow does not claim that the serving endpoint is healthy just because a create/update request was accepted. Check endpoint state and run an inference smoke test after deployment before relying on it.
