import datetime
from utils.config import get_config
from api.salad_client import SaladClient
cfg = get_config()
client = SaladClient(cfg.accounts[3].api_key, 'dharmaadita00@gmail.com')
start = (datetime.datetime.utcnow() - datetime.timedelta(minutes=10)).isoformat() + "Z"
end = datetime.datetime.utcnow().isoformat() + "Z"
res = client._post('/organizations/onin/log-entries', json={'query': 'text_log contains "hashrate"', 'start_time': start, 'end_time': end})
print('Keys:', res.keys())
