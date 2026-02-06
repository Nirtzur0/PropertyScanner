import importlib


def test_src_submodule_import__does_not_require_public_api_imports():
    # Arrange / Act
    mod = importlib.import_module("src.platform.domain.models")

    # Assert
    assert hasattr(mod, "Base")
