"""Verify actual native simulator thinking behavior and banking embeddings."""

import argparse
import json
from pathlib import Path

import litellm
from openai import OpenAI
from qwen38_tau_local import API_BASE, EMBEDDER, MODEL, configure_local, external_arguments


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("Refusing to replace canary evidence")
    evidence = {"identity": configure_local(), "status": "running", "repetitions": []}
    try:
        for seed in range(3):
            result = litellm.completion(
                model=MODEL,
                messages=[{"role": "user", "content": "Reply with READY only."}],
                seed=seed,
                api_key="LOCAL_NO_CREDENTIAL",
                **external_arguments(),
            )
            message = result.choices[0].message.model_dump()
            passed = (
                bool(message.get("content", "").strip())
                and not message.get("reasoning_content")
                and not message.get("reasoning")
            )
            evidence["repetitions"].append(
                {
                    "seed": seed,
                    "passed": passed,
                    "message": message,
                    "usage": result.usage.model_dump(),
                }
            )
            if not passed:
                raise RuntimeError(
                    "Simulator did not honor nonempty visible output with thinking disabled"
                )
        vectors = OpenAI(
            api_key="LOCAL_NO_CREDENTIAL", base_url=API_BASE + "/v1"
        ).embeddings.create(model=EMBEDDER, input=["tau embedding canary"])
        evidence["embedding_dimensions"] = len(vectors.data[0].embedding)
        if evidence["embedding_dimensions"] != 768:
            raise RuntimeError("Embedding dimensions differ from amended study")
        evidence["status"] = "passed"
    except BaseException as exc:
        evidence["status"] = "failed"
        evidence["failure_type"] = type(exc).__name__
        raise
    finally:
        with args.output.open("x") as output:
            json.dump(evidence, output, indent=2)


if __name__ == "__main__":
    main()
