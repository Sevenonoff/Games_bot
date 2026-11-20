"""Проба генерации фона зоны через CometAPI: gemini / seedream / gpt-image.

python gen.py <model> <name> [prompt-file]
Ключ читается из файла и нигде не печатается.
"""
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

KEY = Path("/home/clawuser/projects/Games_bot/.cometapi_key").read_text().strip()
BASE = "https://api.cometapi.com"
OUT = Path(__file__).with_name("out")
OUT.mkdir(exist_ok=True)

PROMPT_FILE = Path(__file__).with_name("prompt_meadow.txt")
PROMPT = PROMPT_FILE.read_text().strip() if PROMPT_FILE.exists() else ""


def call(method, url, body=None, headers=None, timeout=300):
    h = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    h.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read()[:800].decode(errors='replace')}")


def save(name, raw):
    p = OUT / name
    p.write_bytes(raw)
    print("saved", p, len(raw), "bytes")


def gemini(model, name, prompt, images=(), aspect="16:9", size="1K"):
    parts = []
    for p in images:
        mime = "image/png" if str(p).endswith(".png") else "image/jpeg"
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(Path(p).read_bytes()).decode()}})
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": aspect, "imageSize": size}}}
    t = time.time()
    r = call("POST", f"{BASE}/v1beta/models/{model}:generateContent", body, {"x-goog-api-key": KEY})
    parts = [p for p in r["candidates"][0]["content"]["parts"] if "inlineData" in p and not p.get("thought")]
    save(name + ".png", base64.b64decode(parts[-1]["inlineData"]["data"]))
    print("usage", r.get("usageMetadata"), f"{time.time() - t:.0f}s")


def seedream(model, name, prompt, size="2560x1440"):
    t = time.time()
    r = call("POST", f"{BASE}/v1/images/generations",
             {"model": model, "prompt": prompt, "size": size, "response_format": "url", "watermark": False,
              "async": True})
    tid = r["data"]["task_id"]
    while True:
        time.sleep(4)
        s = call("GET", f"{BASE}/v1/images/generations/{tid}")
        st = s["data"]["status"]
        if st in ("success", "failure", "SUCCESS", "FAILURE"):
            break
        if time.time() - t > 400:
            raise SystemExit("timeout")
    if st.lower() != "success":
        raise SystemExit(f"failed: {json.dumps(s)[:800]}")
    url = s["data"]["data"][0]["url"]
    with urllib.request.urlopen(url, timeout=120) as resp:
        save(name + ".jpg", resp.read())
    print(f"{time.time() - t:.0f}s", {k: v for k, v in s["data"].items() if k not in ("data",)})


def gpt(model, name, prompt, size="1536x1024", quality="medium"):
    t = time.time()
    r = call("POST", f"{BASE}/v1/images/generations",
             {"model": model, "prompt": prompt, "size": size, "quality": quality, "output_format": "png", "n": 1})
    save(name + ".png", base64.b64decode(r["data"][0]["b64_json"]))
    print("usage", r.get("usage"), r.get("size"), r.get("quality"), f"{time.time() - t:.0f}s")


if __name__ == "__main__" and sys.argv[1] == "edit":
    # python gen.py edit <name> <prompt-file> <aspect> <size> [image ...]
    _, _, name, pf, aspect, size, *imgs = sys.argv
    gemini("gemini-3-pro-image-preview", name, Path(pf).read_text().strip(), imgs, aspect, size)
elif __name__ == "__main__":
    kind, model, name = sys.argv[1], sys.argv[2], sys.argv[3]
    prompt = PROMPT if len(sys.argv) < 5 else Path(sys.argv[4]).read_text().strip()
    {"gemini": gemini, "seedream": seedream, "gpt": gpt}[kind](model, name, prompt)
