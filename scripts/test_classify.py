"""Test classification directly."""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("OPENROUTER_API_KEY")

PROMPT = """You are a document classifier. Analyze the text and classify it into ONE of these categories:

1. **listing** - A property listing for a SINGLE property
2. **listing_list** - A TABLE or LIST of MULTIPLE properties
3. **news** - A news article about property/real estate
4. **contact** - A business card or contact information

Respond with ONLY a JSON object:
{"type": "listing" | "listing_list" | "news" | "contact", "confidence": 0.0-1.0, "reason": "brief explanation"}

TEXT TO CLASSIFY:
---
SINO GROUP Fullerton Centre 19 Hung To Road, Kwun Tong, Kowloon OFFICE Contact Information: Leasing Person In Charge: Esther Lam 2172 6506 Supplementary Information: Lot No: Kwun Tong Inland Lot No. 449 Landlord: Super One Investment Limited
---

JSON response:"""


def test():
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    body = {
        "model": "deepseek/deepseek-chat",
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 150,
        "temperature": 0.1,
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers=headers, json=body)
        print(f"Status: {response.status_code}")
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    print(f"Raw response:\n{content}")
    print()

    # Try parsing
    import json
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last line (``` markers)
        content = "\n".join(lines[1:-1])
    content = content.strip()

    print(f"Cleaned:\n{content}")

    try:
        result = json.loads(content)
        print(f"\nParsed: {result}")
    except Exception as e:
        print(f"\nParse error: {e}")


if __name__ == "__main__":
    test()
