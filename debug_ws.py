import requests
import os
import json

url = "http://anythingllm:3001/api/v1/workspace/pierrick"
headers = {"Authorization": "Bearer K6DB9NA-FGQ4M72-G76PG4P-9FTG53C"}

try:
    print(f"Fetching {url}...")
    r = requests.get(url, headers=headers)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(json.dumps(data, indent=2))
    else:
        print(r.text)
except Exception as e:
    print(f"Error: {e}")
