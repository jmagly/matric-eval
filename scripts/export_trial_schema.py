"""Export the aligned trial schema on the authorized validation host."""

import json
from pathlib import Path

from matric_eval.results.trials import TrialEvaluation

if __name__ == "__main__":
    schema = TrialEvaluation.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://matric.dev/schemas/evaluation-trials-v1.schema.json"
    Path("schemas/evaluation-trials-v1.schema.json").write_text(
        json.dumps(schema, indent=2, allow_nan=False) + "\n"
    )
