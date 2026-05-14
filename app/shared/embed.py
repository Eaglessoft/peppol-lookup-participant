from pydantic import BaseModel

from app.shared.config import Settings


class EmbedConfig(BaseModel):
    component_name: str = "peppol-lookup"
    api_base_path: str
    auto_css: bool = True


def build_embed_config(settings: Settings) -> EmbedConfig:
    base_path = settings.normalized_context_path or "/"
    return EmbedConfig(api_base_path=base_path)

