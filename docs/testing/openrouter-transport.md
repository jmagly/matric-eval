# OpenRouter transport compatibility

The OpenRouter adapter now uses Inspect's generic
`openai-api/openrouter/<vendor>/<model>` transport and explicitly selects Chat
Completions. Unknown vendor models no longer inherit direct OpenAI model-family
heuristics that can choose Responses or rename `max_tokens`. Attribution headers
are passed as SDK constructor `default_headers`; `extra_headers` is a request
parameter and is not accepted by the client constructor.

Inspect AI 0.3.263's `model/_providers/providers.py::validate_openai_client`
sets `MIN_VERSION = "3.1.0"` and checks it before constructing the compatible
provider. The previous lock selected OpenAI 2.52.0 and therefore failed this
prerequisite before any HTTP request. The package minimum is now OpenAI 3.1.0,
with OpenAI 3.8.0 locked and its HTTP transport dependencies updated. Existing
environments need a locked sync; this crosses the OpenAI SDK major-version
boundary. The transport regression tests cover the locked combination.

Pass the raw OpenRouter model ID, including an `openai/` vendor slug when present.
Already formatted `openai-api/openrouter/` IDs remain unchanged. Previously stored
Inspect identifiers beginning with `openai/` are not automatically migrated:
that prefix is ambiguous with a real vendor slug. New log/checkpoint identifiers
therefore differ from previous runs.

`tests/unit/test_openrouter_transport.py` exercises the installed Inspect and
OpenAI SDK against a localhost server with a fake API key. It checks endpoint,
wire model ID, token limit, attribution headers, routing, reasoning, native JSON
Schema transport, and absence of the key sentinel from evaluation artifacts and
captured application logs. These tests make no OpenRouter calls. Keep credentials
in the API-key parameter, not in `default_headers`, which Inspect may serialize.

The typed `ResponseSchema` test covers basic object properties, required fields,
and `additionalProperties`; it does not establish preservation of all JSON Schema
keywords. A separate `extra_body.response_format` case bypasses Inspect's typed
schema filtering and checks a bounded-edit schema, including `maxItems` and
nested `required`/`additionalProperties`, for exact equality on the wire. The local
server captures transport only; it does not establish remote model schema support.

Run the targeted checks from an isolated checkout:

```bash
uv sync --locked --extra dev --extra study
uv run --locked pytest tests/unit/test_providers.py tests/unit/test_openrouter_transport.py
```

This bounded change does not modify the engine or CLI. Separate findings remain:

- Engine-level shallow `extra_body` merging can replace provider routing when
  thinking or caller settings are supplied. An independent solver's generation
  `extra_body` also supersedes earlier configuration: Inspect 0.3.263's
  `GenerateConfig.merge` replaces each non-null field wholesale. Callers must combine
  routing and reasoning explicitly until merge semantics are addressed.
- Caller `model_args` overrides replace the adapter's defaults wholesale.
- The CLI creates an empty provider config, bypassing the adapter constructor's
  environment-key default. Credential discovery needs its own regression test.
- Generic Inspect schema conversion can omit extended validation keywords;
  applications should verify the constraints they depend on at the HTTP boundary.
