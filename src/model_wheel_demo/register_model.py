from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedModelInput
from mlflow.models.resources import DatabricksServingEndpoint

from model_wheel_demo.agent import build_agent


class AgentModel(mlflow.pyfunc.PythonModel):
    """MLflow pyfunc wrapper for the packaged LLM agent."""

    def __init__(self, llm_endpoint: str):
        self.llm_endpoint = llm_endpoint

    def predict(self, context: Any, model_input: Any) -> list[str]:
        records = (
            model_input.to_dict(orient="records")
            if hasattr(model_input, "to_dict")
            else model_input
        )
        agent = build_agent(self.llm_endpoint)
        outputs = []
        for record in records:
            prompt = record.get("input")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(
                    "Each input record must contain a non-empty 'input' string."
                )
            result = agent.invoke({"input": prompt})
            outputs.append(str(result.get("output", result)))
        return outputs


def package_source() -> str:
    """Return the package directory for MLflow's model code path."""
    import model_wheel_demo

    package_dir = Path(model_wheel_demo.__file__).resolve().parent
    if not (package_dir / "__init__.py").is_file():
        raise FileNotFoundError(
            f"Python package is missing its __init__.py: {package_dir}"
        )
    return str(package_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--llm-model", required=True)
    parser.add_argument("--serving-endpoint", required=True)
    parser.add_argument("--experiment-name", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = WorkspaceClient()
    mlflow.set_registry_uri("databricks-uc")

    # Explicitly select/create the Workspace MLflow experiment before starting
    # a run. Log its identity so the job output confirms where the run is saved.
    mlflow.set_experiment(args.experiment_name)
    experiment = mlflow.get_experiment_by_name(args.experiment_name)
    if experiment is None:
        raise RuntimeError(
            f"MLflow experiment {args.experiment_name!r} was not created or found."
        )
    print(
        f"Using MLflow experiment: name={experiment.name}, "
        f"experiment_id={experiment.experiment_id}"
    )

    with mlflow.start_run(experiment_id=experiment.experiment_id) as run:
        model_info = mlflow.pyfunc.log_model(
            name="agent",
            python_model=AgentModel(args.llm_model),
            registered_model_name=args.model_name,
            input_example=[{"input": "Say hello"}],
            code_paths=[package_source()],
            resources=[DatabricksServingEndpoint(endpoint_name=args.llm_model)],
            pip_requirements=[
                "databricks-langchain==0.6.0",
                "langchain==0.3.14",
                "langchain-core==0.3.29",
            ],
        )
        print(f"MLflow run ID: {run.info.run_id}")
        print(f"Logged MLflow model URI: {model_info.model_uri}")

    version = model_info.registered_model_version
    if not version:
        raise RuntimeError("MLflow did not return a registered model version.")

    # Validate the saved artifact before changing Model Serving.
    mlflow.pyfunc.load_model(model_info.model_uri)
    print(f"MLflow model artifact loaded successfully: {model_info.model_uri}")

    serving_model = ServedModelInput(
        model_name=args.model_name,
        model_version=version,
        workload_size="Small",
        scale_to_zero_enabled=True,
    )
    endpoint_names = {item.name for item in client.serving_endpoints.list()}

    if args.serving_endpoint in endpoint_names:
        client.serving_endpoints.update_config(
            name=args.serving_endpoint,
            served_models=[serving_model],
        )
    else:
        client.serving_endpoints.create(
            name=args.serving_endpoint,
            config=EndpointCoreConfigInput(
                name=args.serving_endpoint,
                served_models=[serving_model],
            ),
        )

    # Fail fast when serving reports a terminal failed/not-ready state.
    deadline = time.monotonic() + 45 * 60
    while time.monotonic() < deadline:
        endpoint = client.serving_endpoints.get(name=args.serving_endpoint)
        ready = getattr(getattr(endpoint, "state", None), "ready", None)
        ready_value = getattr(ready, "value", ready)
        ready_text = str(ready_value).upper()
        if ready_text == "READY":
            break
        if "NOT_READY" in ready_text or "FAILED" in ready_text:
            raise RuntimeError(
                f"Serving endpoint {args.serving_endpoint!r} entered state "
                f"{ready_value!s}; inspect serving logs. Champion alias was not changed."
            )
        print(f"Waiting for serving endpoint readiness; current state={ready_value!s}")
        time.sleep(30)
    else:
        raise TimeoutError(
            f"Serving endpoint {args.serving_endpoint!r} did not become READY "
            "within 45 minutes. Champion alias was not changed."
        )

    response = client.serving_endpoints.query(
        name=args.serving_endpoint,
        dataframe_records=[{"input": "Say hello"}],
    )
    if response is None:
        raise RuntimeError("Serving endpoint health query returned no response.")
    response_error = getattr(response, "error", None)
    if response_error:
        raise RuntimeError(f"Serving endpoint health query failed: {response_error}")

    client.registered_models.set_alias(args.model_name, "Champion", version)
    print(
        f"Deployment and smoke test succeeded: model={args.model_name}, "
        f"version={version}, endpoint={args.serving_endpoint}; Champion promoted."
    )


if __name__ == "__main__":
    main()
