import urllib.request
import json
import time

def make_request(method, url, data=None):
    req_data = json.dumps(data).encode('utf-8') if data else None
    headers = {'Content-Type': 'application/json'} if data else {}
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        res = urllib.request.urlopen(req)
        return json.loads(res.read().decode('utf-8'))
    except Exception as e:
        print(f"Error {url}: {e}")
        if hasattr(e, 'read'): print(e.read().decode('utf-8'))
        return None

print("1. Testing POST /api/locations")
loc_resp = make_request('POST', 'http://localhost:8001/api/locations', {
    "name": "Test Village",
    "lat": -1.2,
    "lon": 36.8,
    "households": 120
})
print("Result:", loc_resp)

if not loc_resp:
    exit(1)

loc_id = loc_resp["loc_id"]

print("\n2. Testing GET /api/locations")
list_resp = make_request('GET', 'http://localhost:8001/api/locations')
print("Result (first item):", list_resp["locations"][0] if list_resp and list_resp.get("locations") else list_resp)

print(f"\n3. Testing GET /api/locations/{loc_id}")
detail_resp = make_request('GET', f'http://localhost:8001/api/locations/{loc_id}')
if detail_resp:
    timeline = detail_resp.get("latest_run", {}).get("outputs", {}).get("optimization_result", {}).get("actionable_timeline")
    print("Actionable Timeline extracted:", timeline)

print(f"\n4. Testing GET /api/locations/{loc_id}/satellite")
sat_resp = make_request('GET', f'http://localhost:8001/api/locations/{loc_id}/satellite')
print("Satellite Preview URL:", sat_resp)
