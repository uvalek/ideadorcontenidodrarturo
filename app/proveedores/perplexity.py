"""
La investigación previa. Devuelve Markdown, no JSON.

Si no hay llave configurada, se devuelve cadena vacía y el resto del flujo
sigue funcionando sin investigación: es un paso opcional a propósito.
"""

from __future__ import annotations

import httpx

from app.config import ajustes

URL = "https://api.perplexity.ai/chat/completions"


class ErrorInvestigacion(Exception):
    """No se pudo investigar el tema."""


async def investigar(cliente: httpx.AsyncClient, sistema: str, tema: str) -> str:
    if not ajustes.hay_perplexity:
        return ""

    respuesta = await cliente.post(
        URL,
        json={
            "model": ajustes.perplexity_model,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": f"Investiga este tema: {tema}"},
            ],
        },
        headers={"Authorization": f"Bearer {ajustes.perplexity_api_key}"},
        timeout=httpx.Timeout(180.0, connect=15.0),
    )

    if respuesta.status_code != 200:
        raise ErrorInvestigacion(
            f"Perplexity respondió {respuesta.status_code}. {respuesta.text[:300]}"
        )

    datos = respuesta.json()
    return datos["choices"][0]["message"]["content"]
