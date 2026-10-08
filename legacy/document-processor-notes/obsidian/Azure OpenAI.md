# Azure OpenAI

**Account:** `c21net-bas-openai-swe-prod`
**Region:** Sweden Central
**Endpoint:** `https://c21net-bas-openai-swe-prod-ed82e.openai.azure.com/`

Also on France Central: `c21net-bas-oai-fc-ea-prod` (embeddings only).

## Deployments (Sweden)

| Deployment | Model | Version | Used by |
|---|---|---|---|
| `gpt-5-mini` | gpt-5-mini | 2025-08-07 | [[Assistant]] (chat) |
| `gpt-5.4` | gpt-5.4 | 2026-03-05 | Reserved (higher quality, tested working) |
| `text-embedding-3-small` | text-embedding-3-small | 1 | [[Search]] |
| `text-embedding-3-large` | text-embedding-3-large | 1 | Reserved |

## Why Azure OpenAI works in HK

OpenAI direct API (`openai/gpt-*` via OpenRouter) is regionally blocked in HK. Azure OpenAI is Microsoft-hosted infrastructure — no HK block. Same models, no restrictions.

## GPT-5 series parameter constraints (CRITICAL)

GPT-5 / o1 / o3 are **reasoning models** and reject these standard params with HTTP 400 "operation not allowed in this deployment":
- `temperature`
- `top_p`
- `presence_penalty`
- `frequency_penalty`
- `max_tokens` — must use `max_completion_tokens` instead

Detection in [[Assistant]]:
```python
is_reasoning_model = deployment.startswith(("gpt-5", "o1", "o3"))
if is_reasoning_model:
    kwargs["model_kwargs"] = {"max_completion_tokens": 1500}
else:
    kwargs["temperature"] = 0.3
    kwargs["max_tokens"] = 1200
```

**API version tested working:** `2025-04-01-preview`

## Env vars

```
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_KEY
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5-mini   # for [[Assistant]]
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small  # for [[Search]] / [[Indexer]]
```

## Connects to

[[Assistant]] — chat completions
[[Search]] — query embeddings
[[Indexer]] — document embeddings
