import io
import mimetypes
import os
import tempfile
import time
from typing import Optional

import requests
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types

app = FastAPI()


def _get_genai_client(api_key: Optional[str] = None) -> genai.Client:

    resolved_key = 'AIzaSyCsb9lMQ68Ns0MCfhdZXnWk6FTRfcc4jBw'
    if not resolved_key:
        raise ValueError("缺少 GEMINI_API_KEY/GOOGLE_API_KEY，无法调用 Veo")
    return genai.Client(api_key=resolved_key)


def _upload_to_types_image(image_bytes: bytes, mime_type: str) -> types.Image:
    suffix = mimetypes.guess_extension(mime_type or "") or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        return types.Image.from_file(tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _download_video_bytes(video: types.Video, api_key: str) -> bytes:
    if getattr(video, "video_bytes", None):
        return video.video_bytes
    if getattr(video, "uri", None):
        resp = requests.get(
            video.uri,
            headers={"x-goog-api-key": api_key},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.content
    raise ValueError("Veo 未返回视频内容。")


@app.post("/generate_video")
async def generate_video(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    duration: int = Form(...),
    ratio: str = Form(...),
    resolution: Optional[str] = Form(None),
    model: str = Form("veo-3.1-generate-preview"),
    generate_audio: bool = Form(True),
    enhance_prompt: bool = Form(True),
    api_key: Optional[str] = Form(None),
):
    image_bytes = await image.read()
    mime_type = image.content_type or "image/png"

    client = _get_genai_client(api_key)
    gen_image = _upload_to_types_image(image_bytes, mime_type)

    config_kwargs = {
        "number_of_videos": 1,
        "duration_seconds": duration,
        "aspect_ratio": ratio,
        "generate_audio": generate_audio,
        "enhance_prompt": enhance_prompt,
    }
    if resolution:
        config_kwargs["resolution"] = resolution

    operation = client.models.generate_videos(
        model=model,
        prompt=prompt,
        image=gen_image,
        config=types.GenerateVideosConfig(**config_kwargs),
    )

    while not operation.done:
        time.sleep(10)
        operation = client.operations.get(operation)

    response = getattr(operation, "response", None) or getattr(operation, "result", None)
    generated_videos = getattr(response, "generated_videos", None) if response else None
    if not generated_videos and isinstance(response, dict):
        generated_videos = response.get("videos")

    if not generated_videos:
        raise ValueError("Veo 未返回生成结果。")

    first_video = generated_videos[0]
    video = getattr(first_video, "video", None) or first_video
    video_bytes = _download_video_bytes(video, api_key or os.getenv("GEMINI_API_KEY") or "")

    return StreamingResponse(
        io.BytesIO(video_bytes),
        media_type="video/mp4",
        headers={
            "X-Video-Model": model,
            "X-Video-Resolution": resolution or "default",
        },
    )
