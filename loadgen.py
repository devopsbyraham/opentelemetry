"""Generates fake traffic so you have data to look at.  Usage: python loadgen.py [count]"""
import random
import sys
import time

import requests

URL = "http://localhost:5000/checkout"
ITEMS = ["laptop", "mouse", "mouse", "keyboard", "ghost"]  # ghost = unknown item

count = int(sys.argv[1]) if len(sys.argv) > 1 else 100
for i in range(count):
    item = random.choice(ITEMS)
    try:
        r = requests.get(URL, params={"item": item, "qty": 1}, timeout=10)
        print(f"{i:03d} {item:9s} -> {r.status_code}")
    except Exception as e:
        print(f"{i:03d} {item:9s} -> ERROR {e}")
    time.sleep(random.uniform(0.1, 0.5))
