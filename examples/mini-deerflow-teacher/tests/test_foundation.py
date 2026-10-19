from mini_deerflow import __version__
from mini_deerflow.models import create_chat_model


def test_package_is_importable() -> None:
    assert __version__ == "0.1.0"
    assert callable(create_chat_model)


def test_fake_model_is_deterministic(fake_model) -> None:
    fake_model.responses.extend(["first", "second"])

    assert fake_model.invoke(["request-1"]) == "first"
    assert fake_model.invoke(["request-2"]) == "second"
    assert fake_model.requests == [["request-1"], ["request-2"]]
