#!/usr/bin/env python3
"""
Quick smoke test runner - runs HumanEval, MBPP, GSM8K on all models under 15GB.

Usage:
    uv run python run_smoke.py
    uv run python run_smoke.py --model llama3.2:3b
    uv run python run_smoke.py --max-size 10
"""

import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path


def get_models(max_size_gb: float = 15.0) -> list[tuple[str, float]]:
    """Get Ollama models under size threshold."""
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    models = []

    # Skip embedding models
    exclude = ["embed", "snowflake", "nomic", "minilm", "mxbai"]

    for line in result.stdout.strip().split("\n")[1:]:
        parts = line.split()
        if len(parts) >= 4:
            name = parts[0]
            try:
                size = float(parts[2])
                unit = parts[3]
                size_gb = size / 1024 if unit == "MB" else size

                if size_gb <= max_size_gb and not any(x in name.lower() for x in exclude):
                    models.append((name, size_gb))
            except ValueError:
                continue

    return sorted(models, key=lambda x: x[1])


def run_smoke_eval(model: str) -> dict:
    """Run smoke evaluation on a model using Python API."""
    from inspect_ai import eval as inspect_eval
    from matric_eval.tasks.smoke import smoke_humaneval, smoke_mbpp, smoke_gsm8k

    ollama_model = f"ollama/{model}"
    results = {
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "benchmarks": {},
    }

    tasks = [
        ("humaneval", smoke_humaneval),
        ("mbpp", smoke_mbpp),
        ("gsm8k", smoke_gsm8k),
    ]

    for name, task_fn in tasks:
        print(f"    {name}...", end=" ", flush=True)
        try:
            logs = inspect_eval(
                task_fn(),
                model=ollama_model,
                log_dir="logs",
            )

            if logs and logs[0].results:
                scores = logs[0].results.scores
                if scores:
                    accuracy = scores[0].metrics.get("accuracy", {})
                    score = accuracy.value if hasattr(accuracy, 'value') else accuracy.get("value", 0)
                    results["benchmarks"][name] = {
                        "score": score,
                        "samples": len(logs[0].samples) if logs[0].samples else 0,
                    }
                    print(f"{score:.0%}")
                else:
                    results["benchmarks"][name] = {"score": 0, "error": "no_scores"}
                    print("no scores")
            else:
                results["benchmarks"][name] = {"score": 0, "error": "no_logs"}
                print("no logs")

        except Exception as e:
            results["benchmarks"][name] = {"score": 0, "error": str(e)}
            print(f"error: {e}")

    # Calculate average
    scores = [b["score"] for b in results["benchmarks"].values() if isinstance(b.get("score"), (int, float))]
    results["average"] = sum(scores) / len(scores) if scores else 0

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run smoke tests on Ollama models")
    parser.add_argument("--model", help="Specific model to test")
    parser.add_argument("--max-size", type=float, default=15.0, help="Max model size in GB")
    parser.add_argument("--list", action="store_true", help="List models and exit")
    parser.add_argument("--top", type=int, default=0, help="Only test top N smallest models")
    args = parser.parse_args()

    models = get_models(args.max_size)

    if args.list:
        print(f"\nModels under {args.max_size}GB:")
        for name, size in models:
            print(f"  {name:<45} {size:.1f} GB")
        print(f"\nTotal: {len(models)} models")
        return

    if args.model:
        models = [(args.model, 0)]
    elif args.top > 0:
        models = models[:args.top]

    print(f"\n{'='*60}")
    print("MATRIC-EVAL SMOKE TEST")
    print(f"{'='*60}")
    print(f"Models to test: {len(models)}")
    print(f"Benchmarks: HumanEval (5), MBPP (5), GSM8K (5)")
    print(f"{'='*60}\n")

    all_results = []
    for i, (model, size) in enumerate(models, 1):
        print(f"\n[{i}/{len(models)}] {model} ({size:.1f} GB)")
        print("-" * 50)

        result = run_smoke_eval(model)
        all_results.append(result)

        avg = result.get("average", 0)
        print(f"  Average: {avg:.0%}")

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")

    # Rank by average score
    ranked = sorted(all_results, key=lambda x: x.get("average", 0), reverse=True)

    print(f"\n{'Model':<40} {'HE':>6} {'MBPP':>6} {'GSM8K':>6} {'Avg':>6}")
    print("-" * 64)

    for r in ranked:
        model = r["model"][:38]
        he = r["benchmarks"].get("humaneval", {}).get("score", 0)
        mbpp = r["benchmarks"].get("mbpp", {}).get("score", 0)
        gsm = r["benchmarks"].get("gsm8k", {}).get("score", 0)
        avg = r.get("average", 0)
        print(f"{model:<40} {he:>5.0%} {mbpp:>6.0%} {gsm:>6.0%} {avg:>6.0%}")

    # Save results
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results_file = results_dir / f"smoke-{timestamp}.json"
    results_file.write_text(json.dumps({
        "timestamp": timestamp,
        "models_tested": len(all_results),
        "results": all_results,
    }, indent=2))

    print(f"\nResults saved to: {results_file}")
    print(f"Logs in: logs/")


if __name__ == "__main__":
    main()
