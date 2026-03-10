from src.interfaces import cli


def test_passthrough_command_forwards_dash_flags(monkeypatch):
    captured = {}

    def fake_run_module(module, args):
        captured["module"] = module
        captured["args"] = args
        return 0

    monkeypatch.setattr(cli, "_run_module", fake_run_module)

    exit_code = cli.main(
        [
            "calibrators",
            "--input",
            "samples.jsonl",
            "--coverage-report-output",
            "coverage.json",
            "--coverage-floor",
            "0.80",
        ]
    )

    assert exit_code == 0
    assert captured["module"] == "src.valuation.workflows.calibration"
    assert captured["args"] == [
        "--input",
        "samples.jsonl",
        "--coverage-report-output",
        "coverage.json",
        "--coverage-floor",
        "0.80",
    ]


def test_benchmark_command_forwards_dash_flags(monkeypatch):
    captured = {}

    def fake_run_module(module, args):
        captured["module"] = module
        captured["args"] = args
        return 0

    monkeypatch.setattr(cli, "_run_module", fake_run_module)

    exit_code = cli.main(
        [
            "benchmark",
            "--listing-type",
            "sale",
            "--max-fusion-eval",
            "40",
            "--output-json",
            "tmp/benchmark.json",
        ]
    )

    assert exit_code == 0
    assert captured["module"] == "src.ml.training.benchmark"
    assert captured["args"] == [
        "--listing-type",
        "sale",
        "--max-fusion-eval",
        "40",
        "--output-json",
        "tmp/benchmark.json",
    ]


def test_retriever_ablation_command_forwards_dash_flags(monkeypatch):
    captured = {}

    def fake_run_module(module, args):
        captured["module"] = module
        captured["args"] = args
        return 0

    monkeypatch.setattr(cli, "_run_module", fake_run_module)

    exit_code = cli.main(
        [
            "retriever-ablation",
            "--listing-type",
            "sale",
            "--max-targets",
            "24",
            "--output-json",
            "tmp/retriever_ablation.json",
        ]
    )

    assert exit_code == 0
    assert captured["module"] == "src.ml.training.retriever_ablation"
    assert captured["args"] == [
        "--listing-type",
        "sale",
        "--max-targets",
        "24",
        "--output-json",
        "tmp/retriever_ablation.json",
    ]
