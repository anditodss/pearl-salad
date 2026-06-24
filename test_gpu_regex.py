import re

pat = (
    r"(?i)"
    r"(?:^|\] |\b)"
    r"(?:gpu_model|gpu_type|gpu(?:\(s\))?|name)"
    r"\s*[:=]\s*\"?"
    r"([A-Za-z0-9][^\n,\"=]*?)"
    r"(?=\s+\w+=|\s*[,\"\n]|\s*$)"
)
p = re.compile(pat)

tests = [
    ("GPU: RTX3080", "RTX3080"),
    ("gpu_model: NVIDIA GeForce RTX 3080", "NVIDIA GeForce RTX 3080"),
    ("gpu_model=4070s compute_capability=8.9", "4070s"),
    ("target=jp.pearlfortune.org:443 timeout=10s", None),
    ("GPU(s): NVIDIA GeForce RTX 4070", "NVIDIA GeForce RTX 4070"),
    ("name: RTX 3090", "RTX 3090"),
]

all_ok = True
for text, expected in tests:
    m = p.search(text)
    got = m.group(1).strip() if m else None
    ok = got == expected
    status = "OK  " if ok else "FAIL"
    print(f"  [{status}] {text!r} => {got!r}  (expected {expected!r})")
    if not ok:
        all_ok = False

print()
print("All OK!" if all_ok else "FAILURES detected.")
