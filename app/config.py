"""
Configuración: todo lo que cambia entre tu máquina y el VPS vive aquí.

Ningún otro archivo lee variables de entorno directamente. Si hace falta un
ajuste nuevo, se agrega a esta clase y al .env.example, y ya está disponible
en todo el proyecto como `ajustes.lo_que_sea`.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    bucket_imagenes: str = "contenido-imagenes"

    # Acceso
    admin_emails: str = ""
    origenes_permitidos: str = "https://adlek.com.mx"

    # Proveedores
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    perplexity_api_key: str = ""
    perplexity_model: str = "sonar-pro"
    replicate_api_token: str = ""
    replicate_modelo: str = "minimax/image-01"

    # Límites
    max_generaciones_activas: int = 2
    max_ideas: int = 10
    max_concurrencia_llm: int = 4
    replicate_timeout_seg: int = 180
    replicate_max_intentos: int = 3

    @property
    def correos_admin(self) -> set[str]:
        return {c.strip().lower() for c in self.admin_emails.split(",") if c.strip()}

    @property
    def origenes(self) -> list[str]:
        return [o.strip() for o in self.origenes_permitidos.split(",") if o.strip()]

    @property
    def hay_perplexity(self) -> bool:
        return bool(self.perplexity_api_key)

    @property
    def hay_replicate(self) -> bool:
        return bool(self.replicate_api_token)


@lru_cache
def obtener_ajustes() -> Ajustes:
    return Ajustes()


ajustes = obtener_ajustes()
