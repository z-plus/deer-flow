from importlib import import_module

from mini_deerflow.learning_stages import LEARNING_STAGES


def test_learning_manifest_has_twelve_ordered_stages() -> None:
    assert [stage.number for stage in LEARNING_STAGES] == list(range(1, 13))
    assert len({stage.name for stage in LEARNING_STAGES}) == 12


def test_every_stage_package_is_importable() -> None:
    packages = {package for stage in LEARNING_STAGES for package in stage.packages}

    for package in packages:
        import_module(f"mini_deerflow.{package}")

