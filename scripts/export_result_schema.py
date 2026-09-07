"""Export the reviewed v2 preview schema; run on the authorized validation host."""

import json
from pathlib import Path

from matric_eval.results.contract import ResultEnvelope

if __name__ == "__main__":
    destination = Path("schemas/evaluation-result-v2.schema.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    schema = ResultEnvelope.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://matric.dev/schemas/evaluation-result-v2.schema.json"
    destination.write_text(json.dumps(schema, indent=2, allow_nan=False) + "\n")
