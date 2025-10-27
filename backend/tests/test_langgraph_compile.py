import importlib


def test_graph_compiles():
    lg = importlib.import_module("app.langgraph.compile")
    assert hasattr(lg, "create_main_graph")
