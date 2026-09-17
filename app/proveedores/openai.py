"""
Llamadas a OpenAI. Siempre en modo JSON, siempre validadas con Pydantic.

Si el modelo devuelve algo que no encaja en el esquema, se reintenta UNA vez
diciéndole qué estuvo mal. Si vuelve a fallar, se levanta `ErrorAgente` con un
mensaje que una persona pueda leer.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import ajustes

URL = "https://api.openai.com/v1/chat/completions"
T = TypeVar("T", bound=BaseModel)


class ErrorAgente(Exception):
    """Un agente no pudo entregar un resultado utilizable."""


class Uso:
    """Acumula los tokens de toda una generación, para saber cuánto costó."""

    def __init__(self) -> None:
        self.entrada = 0
        self.salida = 0

    def sumar(self, datos: dict[str, Any] | None) -> None:
        if not datos:
            return
        self.entrada += datos.get("prompt_tokens", 0) or 0
        self.salida += datos.get("completion_tokens", 0) or 0

    @property
    def total(self) -> int:
        return self.entrada + self.salida


async def _pedir(
    cliente: httpx.AsyncClient, sistema: str, usuario: str, uso: Uso | None
) -> str:
    cuerpo: dict[str, Any] = {
        "model": ajustes.openai_model,
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": usuario},
        ],
        "response_format": {"type": "json_object"},
    }

    respuesta = await cliente.post(
        URL,
        json=cuerpo,
        headers={"Authorization": f"Bearer {ajustes.openai_api_key}"},
        timeout=httpx.Timeout(240.0, connect=15.0),
    )

    if respuesta.status_code != 200:
        detalle = respuesta.text[:400]
        raise ErrorAgente(
            f"OpenAI respondió {respuesta.status_code}. {detalle}"
        )

    datos = respuesta.json()
    if uso is not None:
        uso.sumar(datos.get("usage"))
    return datos["choices"][0]["message"]["content"]


async def agente(
    cliente: httpx.AsyncClient,
    sistema: str,
    usuario: str,
    esquema: type[T],
    *,
    uso: Uso | None = None,
    etiqueta: str = "agente",
) -> T:
    """Corre un agente y devuelve su salida ya validada."""
    texto = await _pedir(cliente, sistema, usuario, uso)

    try:
        return esquema.model_validate(json.loads(texto))
    except (json.JSONDecodeError, ValidationError) as fallo:
        # Un reintento, diciéndole exactamente qué estuvo mal.
        correccion = (
            f"{usuario}\n\n---\n\nTu respuesta anterior no se pudo usar. "
            f"El error fue:\n{fallo}\n\n"
            "Responde de nuevo con el JSON completo y válido, siguiendo el "
            "esquema al pie de la letra. Solo el JSON, nada más."
        )
        texto = await _pedir(cliente, sistema, correccion, uso)
        try:
            return esquema.model_validate(json.loads(texto))
        except (json.JSONDecodeError, ValidationError) as segundo:
            raise ErrorAgente(
                f"El agente «{etiqueta}» devolvió un formato que no se pudo leer, "
                f"ni siquiera tras reintentar. Detalle: {segundo}"
            ) from segundo
