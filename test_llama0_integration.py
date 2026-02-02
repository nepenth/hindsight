#!/usr/bin/env python3
"""Test llama0 integration in hindsight project"""

from llama0 import Llama0
import time

# Use the downloaded model
model_path = "/Users/nicoloboschi/dev/locallm/models/tinyllama-1.1b-q4.gguf"

print("=" * 70)
print("Testing llama0 integration in hindsight")
print("=" * 70)

# Test 1: Basic usage
print("\n[Test 1] Basic generation")
print("-" * 70)

with Llama0(model_path, port=9201, verbose=False) as llm:
    print(f"✓ Server started at {llm.url}")

    prompt = "What is AI? Answer in one sentence."
    print(f"\nPrompt: {prompt}")

    start = time.time()
    response = llm.generate(prompt, max_tokens=50)
    elapsed = time.time() - start

    print(f"Response: {response.strip()}")
    print(f"Time: {elapsed:.2f}s")

print("\n" + "=" * 70)
print("\n✓ Test completed! llama0 works in hindsight project")
print("=" * 70)
