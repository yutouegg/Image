# 项目Streamlit前端
import base64
import io
import random
import time
from typing import Dict, List, Optional, Tuple

import requests
import streamlit as st
from PIL import Image

from templates import VIDEO_TEMPLATES
from prompt_engine import build_video_prompt


st.set_page_config(
    page_title="吴璇的摄影工厂",
    page_icon="🎬",
    layout="wide",
)


def _inject_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg-1: #f7f7fb;
            --bg-2: #ffffff;
            --card: rgba(255, 255, 255, 0.9);
            --card-strong: rgba(255, 255, 255, 0.98);
            --text: #0f172a;
            --muted: #475569;
            --accent: #f97316;
            --accent-2: #2563eb;
            --accent-3: #10b981;
        }

        html, body, [class*="css"]  {
            font-family: "Manrope", "Noto Sans SC", "PingFang SC", sans-serif;
            color: var(--text);
        }

        .stApp {
            background: radial-gradient(1200px circle at 5% 5%, #e2e8f0, transparent 55%),
                        radial-gradient(1000px circle at 95% 12%, #fde68a, transparent 45%),
                        linear-gradient(180deg, #f8fafc, #f5f3ff 40%, #ffffff);
        }

        .hero {
            padding: 28px 28px 22px 28px;
            border-radius: 18px;
            background: linear-gradient(120deg, rgba(249, 115, 22, 0.18), rgba(37, 99, 235, 0.14));
            border: 1px solid rgba(15, 23, 42, 0.08);
            box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
        }

        .hero h1 {
            font-family: "Cormorant Garamond", "Noto Serif SC", serif;
            font-weight: 600;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }

        .tag {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            color: var(--muted);
            background: rgba(255,255,255,0.8);
            border: 1px solid rgba(15, 23, 42, 0.08);
        }

        .card {
            background: var(--card);
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
        }

        .card-strong {
            background: var(--card-strong);
            border: 1px solid rgba(15, 23, 42, 0.1);
            border-radius: 16px;
            padding: 18px;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.1);
        }

        .metric {
            background: rgba(248, 250, 252, 0.95);
            border-radius: 12px;
            padding: 14px;
            border: 1px solid rgba(148, 163, 184, 0.35);
        }

        .stButton>button {
            background: linear-gradient(120deg, #f97316, #fb7185);
            color: #0f172a;
            border: none;
            border-radius: 12px;
            padding: 0.65rem 1.2rem;
            font-weight: 600;
            box-shadow: 0 10px 20px rgba(249, 115, 22, 0.28);
        }

        .stButton>button:hover {
            opacity: 0.95;
        }

        .stTextInput>div>div>input,
        .stTextInput>div>div,
        .stTextArea>div>div>textarea,
        .stTextArea>div>div,
        .stSelectbox>div>div,
        .stSelectbox [data-baseweb="select"]>div,
        .stSelectbox input,
        .stMultiSelect>div>div,
        .stMultiSelect [data-baseweb="select"]>div,
        .stMultiSelect input {
            background-color: #ffffff !important;
            border-radius: 10px !important;
            color: var(--text) !important;
            border: 1px solid rgba(15, 23, 42, 0.12) !important;
        }

        .stSelectbox input,
        .stMultiSelect input {
            caret-color: transparent !important;
            cursor: pointer !important;
        }

        .stFileUploader>div {
            background-color: rgba(255, 255, 255, 0.9);
            border-radius: 12px;
            border: 1px dashed rgba(15, 23, 42, 0.2);
        }

        .stTabs [data-baseweb="tab"] {
            font-size: 15px;
            padding: 10px 18px;
            border-radius: 12px;
            background: rgba(248, 250, 252, 0.9);
            margin-right: 8px;
        }

        .stTabs [aria-selected="true"] {
            background: rgba(249, 115, 22, 0.18) !important;
            color: #c2410c !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _extract_text_from_file(uploaded_file) -> Tuple[str, str]:
    if uploaded_file is None:
        return "", ""
    try:
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return "", "无法读取文档内容。"

    name = (uploaded_file.name or "").lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text.strip(), ""
        except Exception as exc:
            return "", f"PDF 解析失败：{exc}"

    if name.endswith(".docx"):
        try:
            from docx import Document  # type: ignore

            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
            return text.strip(), ""
        except Exception as exc:
            return "", f"DOCX 解析失败：{exc}"

    try:
        return data.decode("utf-8", errors="ignore").strip(), ""
    except Exception:
        return "", "文档解析失败，请转换为 TXT / PDF / DOCX。"


def _guess_mime_type(filename: str, fallback: str = "image/png") -> str:
    if not filename:
        return fallback
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".webp"):
        return "image/webp"
    return fallback


def _file_to_base64(uploaded_file) -> Tuple[str, str]:
    if hasattr(uploaded_file, "getvalue"):
        data = uploaded_file.getvalue()
    else:
        data = uploaded_file.read()
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    mime_type = uploaded_file.type or _guess_mime_type(getattr(uploaded_file, "name", ""), "image/png")
    return base64.b64encode(data).decode("utf-8"), mime_type


APIYI_BASE = "https://api.apiyi.com"
IMAGE_MODEL = "gemini-3-pro-image-preview"


def _require_api_key() -> str:
    key = st.secrets.get("APIYI_API_KEY")
    if not key:
        raise ValueError("缺少 APIYI_API_KEY，请在 Streamlit Secrets 中配置。")
    return key


def _apiyi_generate_image(
    prompt: str,
    aspect_ratio: Optional[str] = None,
    image_size: Optional[str] = None,
) -> Tuple[List[Image.Image], str, dict]:
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

    data = {}
    max_retries = 4
    base_delay = 1.5
    timeout_map = {"1K": 180, "2K": 300, "4K": 360}
    timeout = timeout_map.get(image_size or "1K", 180)
    for attempt in range(max_retries):
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {_require_api_key()}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        if response.status_code in {429, 500, 503, 504} and attempt < max_retries - 1:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                sleep_for = float(retry_after)
            else:
                sleep_for = base_delay * (2 ** attempt) + random.uniform(0, 0.7)
            time.sleep(min(sleep_for, 12))
            continue
        if response.status_code >= 400:
            raise ValueError(response.text)
        data = response.json()
        break

    images_out: List[Image.Image] = []
    texts: List[str] = []
    try:
        part = data["candidates"][0]["content"]["parts"][0]
        inline_data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
    except (KeyError, IndexError, TypeError, AttributeError):
        inline_data = None
    if inline_data:
        images_out.append(Image.open(io.BytesIO(base64.b64decode(inline_data))))
    return images_out, "\n".join(texts).strip(), data


def _apiyi_edit_image(
    image_files: List,
    prompt: str,
    aspect_ratio: Optional[str] = None,
    image_size: Optional[str] = None,
) -> Tuple[List[Image.Image], str, dict]:
    endpoint = f"{APIYI_BASE}/v1beta/models/{IMAGE_MODEL}:generateContent"
    if not image_files:
        raise ValueError("请至少选择一张图片进行编辑。")
    parts = [{"text": prompt}]
    for image_file in image_files:
        image_b64, mime_type = _file_to_base64(image_file)
        if not image_b64:
            raise ValueError("上传图片为空或无法读取，请重新上传后再试。")
        parts.append({"inline_data": {"mime_type": mime_type, "data": image_b64}})
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
            "parts": parts
        }],
        "generationConfig": generation_config,
    }

    data = {}
    max_retries = 4
    base_delay = 1.5
    timeout_map = {"1K": 180, "2K": 300, "4K": 360}
    timeout = timeout_map.get(image_size or "1K", 180)
    for attempt in range(max_retries):
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {_require_api_key()}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        if response.status_code in {429, 500, 503, 504} and attempt < max_retries - 1:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                sleep_for = float(retry_after)
            else:
                sleep_for = base_delay * (2 ** attempt) + random.uniform(0, 0.7)
            time.sleep(min(sleep_for, 12))
            continue
        if response.status_code >= 400:
            raise ValueError(response.text)
        data = response.json()
        break

    images_out: List[Image.Image] = []
    texts: List[str] = []
    try:
        part = data["candidates"][0]["content"]["parts"][0]
        inline_data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
    except (KeyError, IndexError, TypeError, AttributeError):
        inline_data = None
    if inline_data:
        images_out.append(Image.open(io.BytesIO(base64.b64decode(inline_data))))
    return images_out, "\n".join(texts).strip(), data


def _pick_veo_model(video_ratio: str, use_frames: bool, use_fast: bool = False) -> str:
    model = "veo-3.1"
    if video_ratio == "16:9":
        model += "-landscape"
    if use_fast:
        model += "-fast"
    if use_frames:
        model += "-fl"
    return model


def _apiyi_create_veo_task(prompt: str, model: str, image_files: Optional[List] = None) -> str:
    headers = {"Authorization": _require_api_key()}
    if image_files:
        files = []
        for image_file in image_files[:2]:
            image_b64, mime_type = _file_to_base64(image_file)
            if not image_b64:
                raise ValueError("参考图为空或无法读取，请重新上传后再试。")
            image_bytes = base64.b64decode(image_b64)
            filename = getattr(image_file, "name", "frame.png")
            files.append(("input_reference", (filename, image_bytes, mime_type)))
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
    if resp.status_code >= 400:
        raise ValueError(resp.text)
    payload = resp.json()
    video_id = payload.get("id")
    if not video_id:
        raise ValueError("创建任务失败，未返回 video_id。")
    return video_id


def _apiyi_get_veo_status(video_id: str) -> dict:
    resp = requests.get(
        f"{APIYI_BASE}/v1/videos/{video_id}",
        headers={"Authorization": _require_api_key()},
        timeout=120,
    )
    if resp.status_code >= 400:
        raise ValueError(resp.text)
    return resp.json()


def _apiyi_get_veo_content(video_id: str) -> dict:
    resp = requests.get(
        f"{APIYI_BASE}/v1/videos/{video_id}/content",
        headers={"Authorization": _require_api_key()},
        timeout=120,
    )
    if resp.status_code >= 400:
        raise ValueError(resp.text)
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
    raise TimeoutError("等待视频生成超时。")


def _apiyi_download_video(url: str) -> bytes:
    resp = requests.get(url, timeout=600)
    resp.raise_for_status()
    return resp.content


_inject_style()

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="tag">XUAN AI</div>
        <h1>吴璇的摄影工厂</h1>
        <p>产品图上传、需求文档整合、运镜视频设计、图生图与文生图一体化。为电商视觉团队准备的高端工作台。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")

with st.sidebar:
    st.subheader("🔐模型")
    # st.caption("API Key 已在 Streamlit Secrets 配置，不需要前台输入。")
    st.caption("图像模型：gemini-3-pro-image-preview")
    st.caption("视频模型：VEO 3.1（按画幅与帧模式自动选型）")
    response_text = st.toggle("返回文本说明", value=True)

    st.divider()

    st.subheader("🧾 产品信息")
    product_name = st.text_input("产品名称", "高级香氛喷雾")
    product_category = st.text_input("品类", "香氛 / 香水")
    target_market = st.selectbox("目标市场", ["Amazon", "Taobao", "TikTok Shop", "独立站"])
    price_tier = st.selectbox("价格段", ["高端", "中高", "大众", "低价爆款"])
    style_tags = st.multiselect(
        "风格标签",
        ["高端质感", "极简", "科技", "自然", "奢华", "未来感", "复古", "清透"]
    )

    st.subheader("📄 需求与素材")
    product_doc = st.file_uploader("上传产品需求文档", type=["txt", "md", "pdf", "docx"])
    product_images = st.file_uploader(
        "上传产品图片",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )

    st.caption("文档内容仅用于提示词拼接；敏感信息请先脱敏。")


text_from_doc, doc_parse_warning = _extract_text_from_file(product_doc) if product_doc else ("", "")


left, right = st.columns([1.1, 1])

with left:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("🎥 运镜视频策划")
    template_name = st.selectbox("运镜模板", list(VIDEO_TEMPLATES.keys()))
    custom_motion = st.text_input("自定义运镜", "slow push in + subtle parallax")
    mood = st.text_input("氛围关键词", "高端、克制、轻微烟雾")
    shot_list = st.text_area(
        "镜头脚本",
        "1) 开场特写：瓶身质感细节\n2) 中景旋转：标签与logo\n3) 收束：产品与卖点字幕",
        height=120,
    )
    generate_video_brief = st.button("生成视频策划书")

    if generate_video_brief:
        template_config = VIDEO_TEMPLATES[template_name]
        prompt = build_video_prompt(template_config, product_name, target_market)
        prompt = (
            f"{prompt}\n"
            f"Product name: {product_name}\n"
            f"Category: {product_category}\n"
            f"Price tier: {price_tier}\n"
            f"Style tags: {', '.join(style_tags) if style_tags else 'N/A'}\n"
            f"Custom motion: {custom_motion}\n"
            f"Mood: {mood}\n"
            f"Shot list:\n{shot_list}\n"
            f"Doc highlights: {text_from_doc[:800]}"
        )

        st.markdown("**生成的运镜策划 Prompt**")
        st.code(prompt)

    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown('<div class="card-strong">', unsafe_allow_html=True)
    st.subheader("📦 资料预览")
    if product_images:
        preview_cols = st.columns(3)
        for idx, img_file in enumerate(product_images[:6]):
            image = Image.open(img_file)
            preview_cols[idx % 3].image(image, caption=img_file.name)
    else:
        st.info("上传产品图片后会在此预览")

    if product_doc:
        st.caption(f"需求文档：{product_doc.name} ({product_doc.size} bytes)")
        if doc_parse_warning:
            st.warning(doc_parse_warning)
        if text_from_doc:
            st.code(text_from_doc[:600])
    else:
        st.caption("需求文档可用于补充卖点、材质和禁用信息")

    st.markdown("</div>", unsafe_allow_html=True)


st.write("")

video_tab, image_gen_tab, image_edit_tab = st.tabs([
    "🎞️ 图生视频 (VEO 3.1)",
    "🖼️ 文生图 (Nano Banana)",
    "🧩 图生图 / 修图 (Nano Banana)",
])

with video_tab:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("图生视频 - 用于产品运镜")
    st.caption("图生视频由 API易 VEO 3.1 生成（按画幅与帧模式自动选择型号，时长固定 8 秒）。")

    video_prompt = st.text_area(
        "视频提示词",
        "拍摄一瓶高端香氛，镜头从瓶身logo缓慢推近，浅景深，微微旋转，背景柔和灯带。",
        height=120,
    )
    video_ratio = st.selectbox("画幅", ["16:9", "9:16"])
    use_fast = st.toggle("快速模式（速度更快，成本更低）", value=False)
    video_refs = []
    if product_images:
        video_refs = st.multiselect(
            "参考图片（可选 0-2 张，2 张为首尾帧模式）",
            product_images,
            default=product_images[:1],
            format_func=lambda f: f.name,
        )

    if st.button("生成运镜视频"):
        st.session_state["last_video_versions"] = []
        with st.spinner("VEO 3.1 视频生成中..."):
            final_prompt = video_prompt.strip()
            use_frames = bool(video_refs)
            model_name = _pick_veo_model(video_ratio, use_frames=use_frames, use_fast=use_fast)
            try:
                if len(video_refs) > 2:
                    st.info("VEO 3.1 帧转视频最多支持 2 张参考图，已取前两张。")
                video_id = _apiyi_create_veo_task(final_prompt, model_name, image_files=video_refs[:2])
                result = _apiyi_wait_for_veo(video_id)
                video_url = result.get("url")
                if not video_url:
                    raise ValueError("未获取到视频下载地址。")
                video_bytes = _apiyi_download_video(video_url)
                st.session_state["last_video_versions"].append({
                    "model": model_name,
                    "video_id": video_id,
                    "url": video_url,
                    "bytes": video_bytes,
                    "resolution": result.get("resolution"),
                    "duration": result.get("duration"),
                })
            except Exception as exc:
                st.error(f"视频生成失败：{exc}")

    if "last_video_versions" in st.session_state and st.session_state["last_video_versions"]:
        st.markdown("**高清下载**")
        for item in st.session_state["last_video_versions"]:
            video_bytes = item["bytes"]
            model_name = item["model"]
            resolution = item.get("resolution")
            duration = item.get("duration")
            meta = f"{resolution or '未知分辨率'} / {duration or '8'}s"
            st.caption(f"{model_name} · {meta}")
            st.video(video_bytes)
            st.download_button(
                f"下载 {model_name} (MP4)",
                data=video_bytes,
                file_name=f"veo_video_{model_name}.mp4",
                mime="video/mp4",
            )

    st.markdown("</div>", unsafe_allow_html=True)

with image_gen_tab:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("文生图 - 海报 / 场景 / 视觉资产")

    aspect_ratio = st.selectbox(
        "画幅比例",
        ["1:1", "4:5", "3:4", "2:3", "5:4", "4:3", "3:2", "16:9", "9:16", "21:9"],
        index=1,
    )
    image_size = st.selectbox("输出尺寸 (Pro 可用)", ["1K", "2K", "4K"], index=1)

    prompt = st.text_area(
        "提示词",
        f"为{product_name}制作一张{target_market}高端电商主图，背景为柔和渐变光，突出{', '.join(style_tags) if style_tags else '高级质感'}。",
        height=140,
    )

    if st.button("生成图片"):
        try:
            with st.spinner("Nano Banana 生成图片中..."):
                images, text, raw = _apiyi_generate_image(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                )

            if text:
                st.code(text)
            if images:
                for img in images:
                    st.image(img, use_container_width=True)
            else:
                st.warning("未返回图片。可以尝试更明确的提示词或更换模型。")
        except Exception as exc:
            st.error(f"生成失败：{exc}")

    st.markdown("</div>", unsafe_allow_html=True)

with image_edit_tab:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("图生图 / 修图 - 场景替换与细节强化")

    if not product_images:
        st.info("请在侧边栏上传产品图片后再开始编辑。")
    else:
        edit_images = st.multiselect(
            "选择要编辑的图片（可多选）",
            product_images,
            default=product_images[:1],
            format_func=lambda f: f.name,
        )
        edit_prompt = st.text_area(
            "编辑指令",
            "保留产品主体不变，背景换成浅灰色高端摄影棚，加入微弱体积光和柔和阴影。",
            height=120,
        )
        edit_aspect_ratio = st.selectbox(
            "画幅比例",
            ["1:1", "4:5", "3:4", "2:3", "5:4", "4:3", "3:2", "16:9", "9:16", "21:9"],
            index=0,
        )
        edit_image_size = st.selectbox("输出尺寸 (Pro 可用)", ["1K", "2K", "4K"], index=1, key="edit_size")

        if st.button("开始修图"):
            try:
                with st.spinner("Nano Banana 修图中..."):
                    images, text, raw = _apiyi_edit_image(
                        edit_images,
                        prompt=edit_prompt,
                        aspect_ratio=edit_aspect_ratio,
                        image_size=edit_image_size,
                    )

                if text:
                    st.code(text)
                if images:
                    for img in images:
                        st.image(img, use_container_width=True)
                else:
                    st.warning("未返回图片。可以尝试更明确的编辑指令或更换模型。")
            except Exception as exc:
                st.error(f"修图失败：{exc}")

    st.markdown("</div>", unsafe_allow_html=True)


st.markdown(
    """
    <div class="card" style="margin-top: 26px;">
        <h3>工作流程建议</h3>
        <ol>
            <li>上传产品主图与需求文档，确认卖点与禁用信息。</li>
            <li>使用运镜模板输出视频策划，再将 prompt 投喂至视频模型。</li>
            <li>用文生图制作海报或场景，图生图完成精修与背景替换。</li>
        </ol>
    </div>
    """,
    unsafe_allow_html=True,
)
