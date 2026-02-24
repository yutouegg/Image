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
VIDEO_MODEL = "veo-3.1-fl"


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


@app.post("/generate_video")
async def generate_video(
    image: UploadFile = File(...),
    prompt: str = Form(...),
):
    key = _require_api_key()
    image_bytes = await image.read()
    create_resp = requests.post(
        f"{APIYI_BASE}/v1/videos",
        headers={"Authorization": key},
        data={"prompt": prompt, "model": VIDEO_MODEL},
        files={"input_reference": (image.filename, image_bytes, image.content_type or "image/png")},
        timeout=60,
    )
    create_resp.raise_for_status()
    video_id = create_resp.json().get("id")
    if not video_id:
        return JSONResponse({"error": "创建视频任务失败", "raw": create_resp.json()}, status_code=502)

    status = "queued"
    for _ in range(120):
        status_resp = requests.get(
            f"{APIYI_BASE}/v1/videos/{video_id}",
            headers={"Authorization": key},
            timeout=20,
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()
        status = status_data.get("status")
        if status == "completed":
            break
        if status == "failed":
            return JSONResponse({"error": "视频生成失败", "raw": status_data}, status_code=502)
        time.sleep(5)

    if status != "completed":
        return JSONResponse({"error": "视频生成超时", "video_id": video_id}, status_code=504)

    content_resp = requests.get(
        f"{APIYI_BASE}/v1/videos/{video_id}/content",
        headers={"Authorization": key},
        timeout=20,
    )
    content_resp.raise_for_status()
    content_data = content_resp.json()
    video_url = content_data.get("url") or _extract_video_url(str(content_data))
    if not video_url:
        return JSONResponse({"error": "未获取到视频地址", "raw": content_data}, status_code=502)

    video_resp = requests.get(video_url, timeout=300)
    video_resp.raise_for_status()
    return StreamingResponse(
        io.BytesIO(video_resp.content),
        media_type="video/mp4",
        headers={"X-Video-Model": VIDEO_MODEL},
    )
