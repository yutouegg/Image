import base64
import io
import os
import time
from typing import List, Optional

import requests
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()

APIYI_BASE = os.getenv("APIYI_BASE", "https://api.apiyi.com")
APIYI_API_KEY = os.getenv("APIYI_API_KEY")

IMAGE_MODEL = "gemini-3-pro-image-preview"


def _require_api_key() -> str:
    if not APIYI_API_KEY:
        raise ValueError("缺少 APIYI_API_KEY，请在服务端环境变量中配置。")
    return APIYI_API_KEY


def _pick_veo_model(video_ratio: str, use_frames: bool, use_fast: bool = False) -> str:
    model = "veo-3.1"
    if video_ratio == "16:9":
        model += "-landscape"
    if use_fast:
        model += "-fast"
    if use_frames:
        model += "-fl"
    return model


async def _apiyi_create_veo_task(prompt: str, model: str, images: Optional[List[UploadFile]] = None) -> str:
    headers = {"Authorization": _require_api_key()}
    if images:
        files = []
        for image in images[:2]:
            image_bytes = await image.read()
            if not image_bytes:
                raise ValueError("参考图为空")
            mime_type = image.content_type or "image/png"
            files.append(("input_reference", (image.filename or "frame.png", image_bytes, mime_type)))
        resp = requests.post(
            f"{APIYI_BASE}/v1/videos",
            headers=headers,
            data={"prompt": prompt, "model": model},
            files=files,
            timeout=300,
        )
    else:
        resp = requests.post(
            f"{APIYI_BASE}/v1/videos",
            headers={**headers, "Content-Type": "application/json"},
            json={"prompt": prompt, "model": model},
            timeout=300,
        )
    resp.raise_for_status()
    payload = resp.json()
    video_id = payload.get("id")
    if not video_id:
        raise ValueError("创建任务失败，未返回 video_id")
    return video_id


def _apiyi_get_veo_status(video_id: str) -> dict:
    resp = requests.get(
        f"{APIYI_BASE}/v1/videos/{video_id}",
        headers={"Authorization": _require_api_key()},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _apiyi_get_veo_content(video_id: str) -> dict:
    resp = requests.get(
        f"{APIYI_BASE}/v1/videos/{video_id}/content",
        headers={"Authorization": _require_api_key()},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def _apiyi_wait_for_veo(video_id: str, timeout: int = 900, interval: int = 6) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        status_data = _apiyi_get_veo_status(video_id)
        status = status_data.get("status")
        if status == "completed":
            return _apiyi_get_veo_content(video_id)
        if status == "failed":
            raise ValueError(f"视频生成失败：{status_data}")
        time.sleep(interval)
    raise TimeoutError("等待视频生成超时")


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
    image: Optional[List[UploadFile]] = File(None),
    prompt: str = Form(...),
    video_ratio: str = Form("16:9"),
    use_fast: bool = Form(False),
):
    images = image or []
    use_frames = bool(images)
    model = _pick_veo_model(video_ratio, use_frames=use_frames, use_fast=use_fast)
    try:
        video_id = await _apiyi_create_veo_task(prompt, model, images=images)
        result = _apiyi_wait_for_veo(video_id)
        video_url = result.get("url")
        if not video_url:
            return JSONResponse({"error": "未获取到视频地址", "raw": result}, status_code=502)
        video_resp = requests.get(video_url, timeout=600)
        video_resp.raise_for_status()
        return StreamingResponse(
            io.BytesIO(video_resp.content),
            media_type="video/mp4",
            headers={"X-Video-Model": model, "X-Video-Id": video_id},
        )
    except Exception as exc:
        return JSONResponse({"error": "生成失败", "raw": str(exc)}, status_code=502)
