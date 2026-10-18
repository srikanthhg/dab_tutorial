import sys

from scripts import register_model


def test_parse_args_requires_deployment_parameters(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "register_model.py",
            "--model-name", "main.mlflow_demo_dev.demo_agent",
            "--llm-model", "databricks-meta-llama-3-3-70b-instruct",
            "--serving-endpoint", "model-wheel-dev-agent",
        ],
    )
    args = register_model.parse_args()
    assert args.model_name == "main.mlflow_demo_dev.demo_agent"
    assert args.serving_endpoint == "model-wheel-dev-agent"
    assert args.promote_champion is False
