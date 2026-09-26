import httpx
import asyncio

async def test_model(model_name):
    api_key = "AIzaSyBLOePrTVkCEghpZa3_4-2x2ZPVFeN8Ut0"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": "Hello, write 'OK' if you hear me."}]}]
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload)
            print(f"Model: {model_name} | Status: {r.status_code}")
            if r.status_code == 200:
                print(f"Success! Response: {r.json()['candidates'][0]['content']['parts'][0]['text'].strip()}")
                return True
            else:
                print(f"Failed! Content: {r.text[:200]}")
                return False
    except Exception as e:
        print(f"Error for {model_name}: {e}")
        return False

async def main():
    for model in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-flash-latest"]:
        await test_model(model)
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(main())
