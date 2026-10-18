from model_wheel_demo.agent import greeting_tool
from model_wheel_demo.greeting import greeting


def test_greeting_tool_returns_package_greeting():
    assert greeting_tool.invoke({"name": "Databricks"}) == greeting("Databricks")
