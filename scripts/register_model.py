from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path
from typing import Any

import mlflow
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedModelInput,
    ServedModelInputWorkloadSize,
)
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
                raise ValueError("Each input record must contain a non-empty 'input' string.")
            result = agent.invoke({"input": prompt})
            outputs.append(str(result.get("output", result)))
        return outputs


def package_source() -> str:
    """Copy the installed package into an MLflow code path."""
    import model_wheel_demo

    package_dir = Path(model_wheel_demo.__file__).parent
    target = Path(tempfile.mkdtemp(prefix="model-wheel-source-")) / "model_wheel_demo"
    shutil.copytree(package_dir, target)
    return str(target.parent)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--llm-model", required=True)
    parser.add_argument("--serving-endpoint", required=True)
    parser.add_argument("--promote-champion", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = WorkspaceClient()
    mlflow.set_registry_uri("databricks-uc")

    # Register a new model version. Do not move Champion until serving config
    # has been accepted, unless an operator explicitly opts into promotion.
    with mlflow.start_run() as run:
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

    version = model_info.registered_model_version
    if not version:
        raise RuntimeError("MLflow did not return a registered model version.")

    serving_model = ServedModelInput(
        model_name=args.model_name,
        model_version=version,
        workload_size=ServedModelInputWorkloadSize.SMALL,
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

    if args.promote_champion:
        client.registered_models.set_alias(args.model_name, "Champion", version)
        print(f"Champion alias now points to version {version}.")
    else:
        print(
            "Champion alias unchanged. Validate serving endpoint health, then "
            "run the promotion workflow to move Champion."
        )

    print(
        f"Deployment submitted: model={args.model_name}, version={version}, "
        f"endpoint={args.serving_endpoint}"
    )


if __name__ == "__main__":
    main()
