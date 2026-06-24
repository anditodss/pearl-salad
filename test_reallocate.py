import urllib.request
import urllib.error
req = urllib.request.Request('http://localhost:8000/api/instances/24/reallocate', method='POST')
try:
    res = urllib.request.urlopen(req)
    print(res.read().decode())
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode())
