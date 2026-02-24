# 项目Streamlit前端
import base64
import io
import json
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
        .stTextArea>div>textarea,
        .stSelectbox>div>div {
            background-color: rgba(255, 255, 255, 0.96) !important;
            border-radius: 10px !important;
            color: var(--text) !important;
            border: 1px solid rgba(15, 23, 42, 0.12) !important;
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


def _image_to_base64(image: Image.Image, mime_type: str = "image/png") -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _file_to_base64(uploaded_file) -> Tuple[str, str]:
    data = uploaded_file.read()
    uploaded_file.seek(0)
    mime_type = uploaded_file.type or "image/png"
    return base64.b64encode(data).decode("utf-8"), mime_type


def _backend_generate_image(
    endpoint: str,
    model: str,
    prompt: str,
    images: Optional[List[Tuple[str, str]]] = None,
    aspect_ratio: Optional[str] = None,
    image_size: Optional[str] = None,
) -> Tuple[List[Image.Image], str, dict]:
    payload = {
        "prompt": prompt,
        "model": model,
        "aspect_ratio": aspect_ratio or "",
        "image_size": image_size or "",
    }

    files = None
    if images:
        data, mime_type = images[0]
        files = {"image": ("edit.png", base64.b64decode(data), mime_type)}

    data = {}
    max_retries = 4
    base_delay = 1.5
    for attempt in range(max_retries):
        response = requests.post(endpoint, data=payload, files=files, timeout=180)
        if response.status_code in {429, 500, 503, 504} and attempt < max_retries - 1:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                sleep_for = float(retry_after)
            else:
                sleep_for = base_delay * (2 ** attempt) + random.uniform(0, 0.7)
            time.sleep(min(sleep_for, 12))
            continue
        response.raise_for_status()
        data = response.json()
        break

    images_out: List[Image.Image] = []
    texts: List[str] = []

    for candidate in data.get("candidates", []):
        content = candidate.get("content", {})
        for part in content.get("parts", []):
            if "text" in part:
                texts.append(part["text"])
            elif "inline_data" in part and part["inline_data"].get("data"):
                raw = base64.b64decode(part["inline_data"]["data"])
                images_out.append(Image.open(io.BytesIO(raw)))

    return images_out, "\n".join(texts).strip(), data


def _backend_list_models(model_type: str) -> List[str]:
    try:
        resp = requests.get(
            "http://localhost:8000/list_models",
            params={"model_type": model_type},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("models", [])
    except Exception:
        return []


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
    st.subheader("🔐 API 与模型")
    st.caption("API Key 已在服务端配置，不需要前台输入。")
    if "model_options" not in st.session_state:
        st.session_state["model_options"] = _backend_list_models("image") or [
            "gemini-2.5-flash-image",
            "gemini-3-pro-image-preview",
        ]

    if st.button("刷新模型列表"):
        models = _backend_list_models("image")
        if models:
            st.session_state["model_options"] = models
            st.success(f"已加载 {len(models)} 个图片模型。")
        else:
            st.warning("未发现模型或后端不可用，已保留默认列表。")

    model = st.selectbox(
        "Nano Banana 模型",
        st.session_state["model_options"],
        help="Flash 更快，Pro 更强细节与文字控制",
    )
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
    "🎞️ 图生视频 (Veo 接入位)",
    "🖼️ 文生图 (Nano Banana)",
    "🧩 图生图 / 修图 (Nano Banana)",
])

with video_tab:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("图生视频 - 用于产品运镜")
    st.caption("Nano Banana 仅提供图片生成；图生视频需要接入 Veo 或其他视频模型。此处提供可直接对接后端的视频生成入口。")

    video_prompt = st.text_area(
        "视频提示词",
        "拍摄一瓶高端香氛，镜头从瓶身logo缓慢推近，浅景深，微微旋转，背景柔和灯带。",
        height=120,
    )
    video_duration = st.selectbox("视频时长 (秒)", [8], index=0)
    video_ratio = st.selectbox("画幅", ["16:9", "9:16"])
    video_model_options = _backend_list_models("video") or [
        "veo-3.1",
        "veo-3.1-fast",
        "veo-3.1-landscape",
    ]
    video_models = st.multiselect(
        "输出版本 (模型变体)",
        video_model_options,
        default=[video_model_options[0]],
        help="Veo 3.1 变体决定横竖屏与速度，若选择 landscape 则为横屏 16:9。",
    )

    if st.button("生成运镜视频 (调用后端)"):
        if not product_images:
            st.error("请先上传至少一张产品图片。")
        else:
            if not video_models:
                st.warning("请至少选择一个模型版本。")
            else:
                st.session_state["last_video_versions"] = {}
                with st.spinner("后端生成视频中..."):
                    for model_name in video_models:
                        final_prompt = (
                            f"{video_prompt}\n"
                            f"Aspect ratio: {video_ratio}\n"
                            f"Duration: {video_duration}s"
                        )
                        response = requests.post(
                            "http://localhost:8000/generate_video",
                            files={"image": product_images[0]},
                            data={
                                "prompt": final_prompt,
                                "model": model_name,
                            },
                            timeout=300,
                        )

                        if response.status_code == 200:
                            st.session_state["last_video_versions"][model_name] = response.content
                        else:
                            st.error(f"{model_name} 版本生成失败，请检查后端日志。")

    if "last_video_versions" in st.session_state and st.session_state["last_video_versions"]:
        st.markdown("**高清下载**")
        for model_name, video_bytes in st.session_state["last_video_versions"].items():
            st.video(video_bytes)
            st.download_button(
                f"下载 {model_name} (MP4)",
                data=video_bytes,
                file_name=f"nanobanana_video_{model_name}.mp4",
                mime="video/mp4",
            )

    st.markdown("</div>", unsafe_allow_html=True)

with image_gen_tab:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.subheader("文生图 - 海报 / 场景 / 视觉资产")

    aspect_ratio = st.selectbox("画幅比例", ["1:1", "4:5", "3:4", "16:9"], index=1)
    image_size = st.selectbox("输出尺寸 (Pro 可用)", ["1K", "2K", "4K"], index=1)

    prompt = st.text_area(
        "提示词",
        f"为{product_name}制作一张{target_market}高端电商主图，背景为柔和渐变光，突出{', '.join(style_tags) if style_tags else '高级质感'}。",
        height=140,
    )

    if st.button("生成图片"):
        try:
            with st.spinner("Nano Banana 生成图片中..."):
                images, text, raw = _backend_generate_image(
                    endpoint="http://localhost:8000/image_generate",
                    model=model,
                    prompt=prompt,
                    images=None,
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
        edit_image = st.selectbox("选择要编辑的图片", product_images, format_func=lambda f: f.name)
        edit_prompt = st.text_area(
            "编辑指令",
            "保留产品主体不变，背景换成浅灰色高端摄影棚，加入微弱体积光和柔和阴影。",
            height=120,
        )
        edit_aspect_ratio = st.selectbox("画幅比例", ["1:1", "4:5", "3:4", "16:9"], index=0)
        edit_image_size = st.selectbox("输出尺寸 (Pro 可用)", ["1K", "2K", "4K"], index=1, key="edit_size")

        if st.button("开始修图"):
            try:
                with st.spinner("Nano Banana 修图中..."):
                    image_data, mime_type = _file_to_base64(edit_image)
                    images, text, raw = _backend_generate_image(
                        endpoint="http://localhost:8000/image_edit",
                        model=model,
                        prompt=edit_prompt,
                        images=[(image_data, mime_type)],
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
