"""
utils/client_cache.py
=======================
Caches SaladClient instances so we don't rebuild the requests.Session
and its retry adapter on every sync cycle.
"""
import threading
from typing import Dict

from api.salad_client import SaladClient
from utils.config import get_config

_clients: Dict[str, SaladClient] = {}
_lock = threading.Lock()

def get_salad_client(account_name: str) -> SaladClient:
    """Return a cached SaladClient for the given account name."""
    with _lock:
        if account_name in _clients:
            return _clients[account_name]
            
        cfg = get_config()
        acc_cfg = next((a for a in cfg.accounts if a.name == account_name), None)
        if not acc_cfg:
            raise ValueError(f"Account '{account_name}' not found in config")
            
        client = SaladClient(api_key=acc_cfg.api_key, account_name=account_name)
        _clients[account_name] = client
        return client

def clear_client_cache() -> None:
    with _lock:
        _clients.clear()
