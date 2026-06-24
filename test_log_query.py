import logging
import datetime
logging.basicConfig(level=logging.DEBUG)
from utils.config import get_config
from api.salad_client import SaladClient
cfg = get_config()
client = SaladClient(cfg.accounts[3].api_key, "dharmaadita00@gmail.com")
now = datetime.datetime.utcnow()
since = now - datetime.timedelta(minutes=10)
res = client._post("/organizations/onin/log-entries", json={
    "query": "text_log contains \"proof_per_sec\" or text_log contains \"hashrate\"",
    "start_time": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "end_time": now.strftime("%Y-%m-%dT%H:%M:%SZ")
})
print("Found count:", len(res.get("items", [])))
