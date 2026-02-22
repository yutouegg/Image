# prompt_engine.py

def build_video_prompt(template_config, product_desc, market):

    base_prompt = f"""
    A professional product commercial video.
    Product: {product_desc}
    Market: {market}
    Camera motion: {template_config['motion']}
    Lighting: {template_config['lighting']}
    Style: {template_config['style']}
    High detail, realistic, 4K, commercial advertisement.
    """

    return base_prompt.strip()
