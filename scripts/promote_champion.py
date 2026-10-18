from __future__ import annotations

import argparse

from databricks.sdk import WorkspaceClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--model-version", required=True)
    args = parser.parse_args()

    if not args.model_version.isdigit():
        raise ValueError("--model-version must be a numeric Unity Catalog model version.")

    client = WorkspaceClient()
    client.registered_models.set_alias(
        args.model_name,
        "Champion",
        args.model_version,
    )
    print(
        f"Promoted {args.model_name} version {args.model_version} "
        "to the Champion alias."
    )


if __name__ == "__main__":
    main()
