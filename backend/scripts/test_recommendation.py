import json
import urllib.request

url = 'http://127.0.0.1:8000/api/course-recommendation/plan'
payload = {"term_id": "2026-1"}

data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"})

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode('utf-8')
        print(body)
except Exception as e:
    print('ERROR', type(e).__name__, e)
    try:
        import http.client
        if hasattr(e, 'read'):
            body = e.read().decode('utf-8', errors='replace')
            print('Response body:\n', body)
    except Exception:
        pass
    raise
