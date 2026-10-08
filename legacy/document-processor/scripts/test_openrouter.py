"""Test which OpenRouter models work in HK."""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("OPENROUTER_API_KEY")

# More models to test
MODELS = [
    "meta-llama/llama-3.1-8b-instruct",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.2-3b-instruct",
    "microsoft/phi-3-mini-128k-instruct",
    "microsoft/phi-3-medium-128k-instruct",
    "deepseek/deepseek-chat",
    "qwen/qwen-2.5-7b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "mistralai/mistral-nemo",
    "openai/gpt-4o-mini",
]

def test_model(model: str) -> bool:
    """Test if a model works."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 5,
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json=body)
            if resp.status_code == 200:
                return True
            else:
                return False
    except Exception as e:
        return False


def main():
    print("Testing OpenRouter models from HK...")
    print()

    working = []
    for model in MODELS:
        print(f"Testing {model}...", end=" ", flush=True)
        if test_model(model):
            print("✅")
            working.append(model)
        else:
            print("❌")

    print()
    print("=" * 50)
    print("Working models:")
    for m in working:
        print(f"  ✓ {m}")


if __name__ == "__main__":
    main()
