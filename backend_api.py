import base64
import io
import os
import time
from typing import Optional

import requests
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()

APIYI_BASE = os.getenv("APIYI_BASE", "https://api.apiyi.com")
APIYI_API_KEY = os.getenv("APIYI_API_KEY")

IMAGE_MODEL = "gemini-3-pro-image-preview"
VIDEO_MODEL = "sora_video2"


def _require_api_key() -> str:
    if not APIYI_API_KEY:
        raise ValueError("缺少 APIYI_API_KEY，请在服务端环境变量中配置。")
    return APIYI_API_KEY


def _extract_video_url(text: str) -> Optional[str]:
    if not text:
        return None
    for token in text.split():
        if token.startswith("http") and token.endswith(".mp4"):
            return token
    return None


@app.post("/image_generate")
async def image_generate(
    prompt: str = Form(...),
    aspect_ratio: Optional[str] = Form(None),
    image_size: Optional[str] = Form(None),
):
    key = _require_api_key()
    endpoint = f"{APIYI_BASE}/v1beta/models/{IMAGE_MODEL}:generateContent"
    generation_config = {"responseModalities": ["IMAGE"]}
    image_config = {}
    if aspect_ratio:
        image_config["aspectRatio"] = aspect_ratio
    if image_size:
        image_config["imageSize"] = image_size
    if image_config:
        generation_config["imageConfig"] = image_config

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    resp = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=300,
    )
    resp.raise_for_status()
    return JSONResponse(resp.json())


@app.post("/image_edit")
async def image_edit(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    aspect_ratio: Optional[str] = Form(None),
    image_size: Optional[str] = Form(None),
):
    key = _require_api_key()
    image_bytes = await image.read()
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime_type = image.content_type or "image/png"

    endpoint = f"{APIYI_BASE}/v1beta/models/{IMAGE_MODEL}:generateContent"
    generation_config = {"responseModalities": ["IMAGE"]}
    image_config = {}
    if aspect_ratio:
        image_config["aspectRatio"] = aspect_ratio
    if image_size:
        image_config["imageSize"] = image_size
    if image_config:
        generation_config["imageConfig"] = image_config

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": b64}},
            ]
        }],
        "generationConfig": generation_config,
    }
    resp = requests.post(
        endpoint,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload,
        timeout=360,
    )
    resp.raise_for_status()
    return JSONResponse(resp.json())


def _pick_sora_model(video_ratio: str, duration_s: int) -> str:
    is_landscape = video_ratio == "16:9"
    use_15s = duration_s >= 13
    if is_landscape:
        return "sora_video2-landscape-15s" if use_15s else "sora_video2-landscape"
    return "sora_video2-15s" if use_15s else "sora_video2"


def _should_retry_video_error(body: str) -> bool:
    if not body:
        return False
    lower = body.lower()
    return "heavy load" in lower or "overloaded" in lower


@app.post("/generate_video")
async def generate_video(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    video_ratio: str = Form("16:9"),
    video_duration: int = Form(10),
):
    key = _require_api_key()
    image_bytes = await image.read()
    if not image_bytes:
        return JSONResponse({"error": "参考图为空"}, status_code=400)
    mime_type = image.content_type or "image/png"
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    parts = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
    ]

    payload = {
        "model": _pick_sora_model(video_ratio, int(video_duration)),
        "stream": True,
        "messages": [
            {"role": "user", "content": parts},
        ],
    }

    max_retries = 3
    base_delay = 2
    resp = None
    for attempt in range(max_retries):
        resp = requests.post(
            f"{APIYI_BASE}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=600,
            stream=True,
        )
        if resp.status_code < 400:
            break
        body = resp.text
        if _should_retry_video_error(body) and attempt < max_retries - 1:
            time.sleep(base_delay * (2 ** attempt))
            continue
        return JSONResponse({"error": "生成失败", "raw": body}, status_code=502)

    text_chunks: List[str] = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            line = line[len("data: "):]
        if line == "[DONE]":
            break
        try:
            data = json.loads(line)
        except ValueError:
            continue
        delta = (data.get("choices") or [{}])[0].get("delta") or {}
        content = delta.get("content")
        if content:
            text_chunks.append(content)

    video_url = _extract_video_url("".join(text_chunks))
    if not video_url:
        return JSONResponse({"error": "未解析到视频地址"}, status_code=502)

    video_resp = requests.get(video_url, timeout=600)
    video_resp.raise_for_status()
    return StreamingResponse(
        io.BytesIO(video_resp.content),
        media_type="video/mp4",
        headers={"X-Video-Model": VIDEO_MODEL},
    )
