import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("MINIMAX_API_KEY")
base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
model = os.getenv("MINIMAX_EMBEDDING_MODEL", "embo-01")

print(f"API Key: {api_key[:10]}... (length: {len(api_key) if api_key else 0})")
print(f"Base URL: {base_url}")
print(f"Model: {model}")

if not api_key:
    print("❌ No API key found!")
    exit(1)

client = OpenAI(api_key=api_key, base_url=base_url)

try:
    response = client.embeddings.create(
        model=model,
        input=["测试文本", "Hello world"]
    )
    print(f"✅ Success! Got {len(response.data)} embeddings")
    print(f"Embedding dimension: {len(response.data[0].embedding)}")
except Exception as e:
    print(f"❌ Error: {e}")