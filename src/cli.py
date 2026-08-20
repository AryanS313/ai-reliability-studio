from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from src import database
from src.aggregation import LaunchGateConfig, evaluate_candidates
from src.chunker import chunk_documents
from src.document_loader import load_documents
from src.evaluator import read_eval_dataset, run_evaluation
from src.reporting import csv_report, html_report, json_report
from src.storage import SQLiteRepository
from src.targets import ExternalHTTPTarget, ExternalTargetConfig, SecretResolver

EXIT_SUCCESS = 0
EXIT_GATE_FAILURE = 2
EXIT_EXECUTION_ERROR = 3
EXIT_CONFIGURATION_ERROR = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ars", description="AI Reliability Studio reliability runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Run a non-interactive evaluation")
    run.add_argument("--dataset", required=True)
    run.add_argument("--document", action="append", required=True)
    run.add_argument("--prompt", required=True)
    run.add_argument("--candidate-prompt")
    run.add_argument("--model", default="mock-model")
    run.add_argument("--api-key-env")
    run.add_argument("--external-target")
    run.add_argument("--gate-config")
    run.add_argument("--database", default=".ars-ci.sqlite3")
    run.add_argument("--output", default="ars-report.json")
    run.add_argument("--format", choices=["json", "csv", "html"], default="json")
    run.add_argument("--top-k", type=int, default=3)
    run.add_argument("--similarity-threshold", type=float, default=0.05)
    run.add_argument("--max-concurrency", type=int, default=4)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command != "run":
        return EXIT_CONFIGURATION_ERROR
    try:
        repository = SQLiteRepository(args.database)
        database.set_repository(repository)
        context = repository.local_context()
        project_id = repository.create_project(
            context,
            {
                "name": "CI Evaluation",
                "use_case": "non-interactive reliability gate",
                "industry": "",
                "notes": "Created by ars CLI",
            },
        )
        documents = load_documents(args.document)
        chunks = chunk_documents(documents)
        repository.save_documents_and_chunks(context, documents, chunks, project_id)
        dataset_path = Path(args.dataset)
        dataset = read_eval_dataset(dataset_path.name, dataset_path.read_bytes())
        prompts = {"Baseline": Path(args.prompt).read_text(encoding="utf-8")}
        if args.candidate_prompt:
            prompts["Candidate"] = Path(args.candidate_prompt).read_text(encoding="utf-8")
        target = None
        api_key = os.getenv(args.api_key_env, "") if args.api_key_env else None
        if args.external_target:
            external = json.loads(Path(args.external_target).read_text(encoding="utf-8"))
            secret_names = {
                value.removeprefix("secret://"): os.getenv(value.removeprefix("secret://"), "")
                for value in external.get("headers", {}).values()
                if isinstance(value, str) and value.startswith("secret://")
            }
            target = ExternalHTTPTarget(ExternalTargetConfig(**external), SecretResolver(secret_names))
        results = run_evaluation(
            dataset,
            chunks,
            prompts,
            args.model,
            args.top_k,
            args.similarity_threshold,
            3500,
            0.03,
            "ci",
            project_id=project_id,
            api_key=api_key,
            target_adapter=target,
            max_concurrency=args.max_concurrency,
        )
        report = {"json": json_report, "csv": csv_report, "html": html_report}[args.format](results)
        Path(args.output).write_text(report, encoding="utf-8")
        gate_values = json.loads(Path(args.gate_config).read_text(encoding="utf-8")) if args.gate_config else {}
        gates = LaunchGateConfig(**gate_values)
        evaluations = evaluate_candidates(results, gates)
        if any(
            result["verdict"] not in {"Ready for Internal Testing", "Ready for Controlled Beta"}
            for result in evaluations.values()
        ):
            return EXIT_GATE_FAILURE
        if bool((results["execution_status"] != "passed").any()):
            return EXIT_EXECUTION_ERROR
        return EXIT_SUCCESS
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_CONFIGURATION_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
