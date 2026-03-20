from __future__ import annotations

from property_scanner import PipelineAPI, __version__, get_pipeline_api


def test_public_package_facade__exports_supported_symbols() -> None:
    assert __version__ == "0.1.0"
    assert PipelineAPI.__name__ == "PipelineAPI"
    assert callable(get_pipeline_api)

