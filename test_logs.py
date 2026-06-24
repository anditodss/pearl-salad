import json
from api.salad_client import SaladClient
from utils.config import get_config
import datetime
import logging
logging.basicConfig(level=logging.DEBUG)

cfg = get_config()
api_key = cfg.accounts[0].api_key
name = cfg.accounts[0].name
client = SaladClient(api_key, name)
org = "memememe0"
group = "wkwkw"

query_str = 'resource.labels.machine_id="63485369-75f9-f857-ba59-5f7e4d6d2471"'
print(f"Query string: {query_str}")

now = datetime.datetime.utcnow()
end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
start_time = (now - datetime.timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

body = {
    "query": query_str,
    "start_time": start_time,
    "end_time": end_time
}

try:
    res = client._post(f"/organizations/{org}/log-entries", json=body)
    print(json.dumps(res, indent=2))
except Exception as e:
    print(f"Error: {e}")
