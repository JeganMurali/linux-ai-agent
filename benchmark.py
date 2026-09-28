#!/usr/bin/env python

import time
from kokki.agent import KokkiAgent

test_cases = [
    ("hi", "Casual chat"),
    ("what can you do?", "Capability check"),
    ("check my CPU", "System query"),
    ("open VS Code", "App launch"),
    ("list files in home", "File operation"),
]

print("🧪 Kokki Agent Benchmark\n")
print("=" * 60)

kokki = KokkiAgent()
total_time = 0
total_tokens = 0

for user_input, description in test_cases:
    start = time.time()
    response = kokki.chat(user_input)
    latency = time.time() - start
    tokens = len(response.split())
    
    print(f"\n📝 Test: {description}")
    print(f"   Input: '{user_input}'")
    print(f"   Latency: {latency:.2f}s")
    print(f"   Response tokens: {tokens}")
    print(f"   Response: {response[:100]}...")
    
    total_time += latency
    total_tokens += tokens

print("\n" + "=" * 60)
print(f"\n📊 Results:")
print(f"   Total tests: {len(test_cases)}")
print(f"   Avg latency: {total_time / len(test_cases):.2f}s")
print(f"   Avg tokens/response: {total_tokens // len(test_cases)}")
print(f"   Total time: {total_time:.2f}s")
