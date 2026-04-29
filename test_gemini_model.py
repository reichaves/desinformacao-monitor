"""
Quick test to verify gemini-3.1-flash-lite-preview works for all
modalities used in the disinformation pipeline.

Usage:
    $env:GEMINI_API_KEY="your_key_here"
    python test_gemini_model.py
"""

import json
import os
import sys

from google import genai
from google.genai import types

MODEL = "gemini-3.1-flash-lite-preview"

key = os.environ.get("GEMINI_API_KEY", "")
if not key:
    print("ERROR: GEMINI_API_KEY not set.")
    sys.exit(1)

client = genai.Client(api_key=key)
passed = 0
failed = 0


def ok(label):
    global passed
    passed += 1
    print(f"  [PASS] {label}")


def fail(label, exc):
    global failed
    failed += 1
    print(f"  [FAIL] {label}: {exc}")


# ------------------------------------------------------------------
# Test 1: plain text generation
# ------------------------------------------------------------------
print("\n=== Test 1: plain text ===")
try:
    resp = client.models.generate_content(
        model=MODEL,
        contents="O que e desinformacao? Responda em uma frase.",
        config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=100),
    )
    text = resp.text.strip()
    assert len(text) > 10, "Response too short"
    print(f"  Response: {text[:120]}")
    ok("text generation")
except Exception as e:
    fail("text generation", e)


# ------------------------------------------------------------------
# Test 2: structured JSON output (used by content_analyzer)
# ------------------------------------------------------------------
print("\n=== Test 2: structured JSON output ===")
try:
    prompt = (
        'Retorne APENAS JSON valido, sem markdown:\n'
        '{"severidade": 0, "tipo": "nenhum", "resumo": "teste ok"}'
    )
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=100),
    )
    raw = resp.text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    parsed = json.loads(raw)
    assert "severidade" in parsed
    print(f"  Parsed: {parsed}")
    ok("structured JSON")
except Exception as e:
    fail("structured JSON", e)


# ------------------------------------------------------------------
# Test 3: image understanding (used by visual_analyzer)
# ------------------------------------------------------------------
print("\n=== Test 3: image understanding (real PNG via Pillow) ===")
try:
    import io
    from PIL import Image, ImageDraw, ImageFont

    # Generate a real 200x100 image with text (simulates a video frame)
    img = Image.new("RGB", (200, 100), color=(30, 30, 80))
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 190, 90], outline=(255, 255, 0), width=2)
    draw.text((20, 35), "FAKE NEWS TEST", fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    resp = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
            "Descreva o que voce ve nesta imagem em uma frase curta.",
        ],
        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=80),
    )
    text = resp.text.strip()
    print(f"  Response: {text}")
    ok("image understanding")
except Exception as e:
    fail("image understanding", e)


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
print(f"\n{'='*40}")
print(f"  Model : {MODEL}")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")
print(f"{'='*40}\n")

if failed > 0:
    sys.exit(1)
