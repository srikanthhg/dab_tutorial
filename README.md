# model-wheel on Databricks Asset Bundles

A standalone DAB deployment of the `model-wheel` agent. This repository is intentionally separate from `srikanthhg/model-wheel`; the original repository is not modified by this migration.

## Project structure

```text
dab_tutorial/
├── databricks.yml
├── resources/
│   └── model_job.yml
├── src/
│   └── model_wheel_demo/
│       ├── __init__.py
│       ├── agent.py
│       ├── greeting.py
│       └── register_model.py
├── tests/
│   ├── __init__.py
│   ├── test_agent.py
│   └── test_register_model.py
├── .github/
│   └── workflows/
│       ├── deploy.yml
│       └── cleanup-dev-endpoint.yml
├── pyproject.toml
└── README.md
```

- `databricks.yml`: bundle name, artifact build, shared variables, and `dev`/`prod` targets.
- `resources/`: declarative Databricks jobs and compute configuration.
- `src/model_wheel_demo/`: importable Python package and the `register-model` wheel entry point.
- `tests/`: automated tests.
- `.github/workflows/`: CI/CD and guarded cleanup.

## What this deploys

- A Python wheel containing the `model_wheel_demo` agent and greeting tool.
- A DAB bundle with separate development and production Unity Catalog schemas and serving endpoints.
- A serverless Python wheel task (where supported by the workspace) that logs/registers an MLflow PyFunc model and configures Model Serving.
- GitHub Actions CI and target-specific deployment.
- A guarded workflow that can delete only the development serving endpoint.

The registration job waits for the serving endpoint to report `READY`, sends a small inference smoke test, and only then moves the Unity Catalog `Champion` alias. If readiness or the smoke test fails, the alias is not promoted.

## Architecture

1. GitHub Actions installs the package and test dependencies, lints, builds the wheel, installs it, and runs tests.
2. Databricks CLI validates and deploys the bundle.
3. The bundle job runs on serverless job compute using the built wheel.
4. The job logs the agent as an MLflow PyFunc model and registers a version in Unity Catalog.
5. The job creates or updates the target serving endpoint and waits for readiness.
6. The job invokes a smoke test. Only after it succeeds does the job set the new version's `Champion` alias.

## Environments

| Target | Unity Catalog model | Serving endpoint |
| --- | --- | --- |
| `dev` | `main.mlflow_demo_dev.demo_agent` | `model-wheel-dev-agent` |
| `prod` | `main.mlflow_demo.demo_agent` | `model-wheel-agent` |

The targets use separate schemas and endpoints so a development release does not promote the production model's Champion alias. Create both schemas before deploying:

```sql
CREATE SCHEMA IF NOT EXISTS main.mlflow_demo_dev;
CREATE SCHEMA IF NOT EXISTS main.mlflow_demo;
```

Grant the deployment service principal the privileges needed to create registered models and versions, set aliases, use the LLM serving endpoint, and create/update the target serving endpoints. Ensure the serving identity can access the LLM endpoint.

## GitHub setup

Create GitHub Actions environments named `development` and `production`.

Configure these **environment secrets** in both environments:

- `DATABRICKS_HOST`: workspace URL, such as `https://<workspace-host>`
- `DATABRICKS_CLIENT_ID`: Databricks service principal application/client ID

The workflow uses Databricks CLI OAuth with GitHub OIDC (`DATABRICKS_AUTH_TYPE=github-oidc`). Configure a matching GitHub OIDC federation policy for the service principal. Do not store a personal access token in the repository. Protect the `production` environment with required reviewers.

The default LLM endpoint is `databricks-meta-llama-3-3-70b-instruct`; it must already exist in the workspace.

## Local validation

Use Python 3.11 and a current Databricks CLI:

```bash
python -m pip install --upgrade build pytest ruff
python -m pip install -e ".[dev]"
python -m build
pytest -q
ruff check .

export DATABRICKS_HOST="https://<workspace-host>"
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run -t dev model_wheel_deploy
```

Production deployment is a manual GitHub Actions workflow-dispatch choice and should only be run after reviewing the production environment and approval.

## CI/CD behavior

- Pull request to `main`: lint, build and test only.
- Push to `main`: test, then deploy to `dev`.
- Manual workflow dispatch: select `dev` or `prod`; the production GitHub environment can enforce reviewer approval.

## Cleanup safety

The **Delete development serving endpoint** workflow requires the exact phrase `DELETE model-wheel-dev-agent` and deletes only the hard-coded development endpoint. It does not delete Unity Catalog models, model versions, aliases, or the production endpoint.

Avoid running `databricks bundle destroy -t prod` as a routine cleanup command. Review the target and resources before destroying bundle-managed resources.

## Validation caveat

The repository configuration and Python code still need to be validated against your actual Databricks workspace using `databricks bundle validate -t dev`. Serverless compatibility and allowed dependency versions can vary by workspace, cloud, and region. If your workspace rejects the declared serverless environment or a dependency, resolve that validation error before deployment; do not silently switch to an unrelated existing cluster.
