import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("MINIMAX_API_KEY")
base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
model = os.getenv("MINIMAX_MODEL_NAME", "abab6.5g-chat")

print(f"API Key: {api_key[:10]}...")
print(f"Base URL: {base_url}")
print(f"Model: {model}")

client = OpenAI(api_key=api_key, base_url=base_url)

try:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "你好，请简单介绍一下你自己"}],
        temperature=0.1,
    )
    print(f"✅ LLM works! Response: {response.choices[0].message.content[:100]}...")
except Exception as e:
    print(f"❌ LLM failed: {e}")