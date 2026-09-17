"""
Generación de imágenes con Replicate.

Esto arregla el bug más molesto del workflow original: allá el polling era
`If (status == succeeded)` → `Wait 10s` → volver a preguntar, **sin ninguna
salida**. Una imagen que fallaba dejaba el flujo girando para siempre.

Aquí hay dos límites duros:
  - `REPLICATE_TIMEOUT_SEG`: cuánto se espera por una imagen antes de rendirse.
  - `REPLICATE_MAX_INTENTOS`: cuántas veces se vuelve a intentar desde cero.

Cuando se agotan, esa imagen queda marcada como error y las demás continúan.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from app.config import ajustes

BASE = "https://api.replicate.com/v1"
ESPERA_ENTRE_SONDEOS = 3.0


class ErrorImagen(Exception):
    """No se pudo generar una imagen."""


def _cabeceras() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {ajustes.replicate_api_token}",
        "Content-Type": "application/json",
    }


def _url_de(salida) -> str:
    """Replicate a veces devuelve una URL y a veces una lista de URLs."""
    if isinstance(salida, str):
        return salida
    if isinstance(salida, list) and salida:
        return str(salida[0])
    raise ErrorImagen("Replicate terminó sin devolver ninguna imagen.")


async def _un_intento(cliente: httpx.AsyncClient, prompt: str) -> str:
    creacion = await cliente.post(
        f"{BASE}/models/{ajustes.replicate_modelo}/predictions",
        json={"input": {"prompt": prompt, "aspect_ratio": "1:1"}},
        headers=_cabeceras(),
        timeout=httpx.Timeout(60.0, connect=15.0),
    )
    if creacion.status_code not in (200, 201):
        raise ErrorImagen(
            f"Replicate respondió {creacion.status_code} al pedir la imagen. "
            f"{creacion.text[:200]}"
        )

    prediccion = creacion.json()
    id_prediccion = prediccion.get("id")
    limite = time.monotonic() + ajustes.replicate_timeout_seg

    while True:
        estado = prediccion.get("status")

        if estado == "succeeded":
            return _url_de(prediccion.get("output"))

        if estado in ("failed", "canceled"):
            motivo = prediccion.get("error") or estado
            raise ErrorImagen(f"Replicate no pudo generar la imagen: {motivo}")

        if time.monotonic() > limite:
            raise ErrorImagen(
                f"La imagen tardó más de {ajustes.replicate_timeout_seg} segundos. "
                "Se canceló la espera."
            )

        await asyncio.sleep(ESPERA_ENTRE_SONDEOS)
        sondeo = await cliente.get(
            f"{BASE}/predictions/{id_prediccion}",
            headers=_cabeceras(),
            timeout=httpx.Timeout(30.0, connect=15.0),
        )
        if sondeo.status_code != 200:
            raise ErrorImagen(
                f"Replicate respondió {sondeo.status_code} al consultar el avance."
            )
        prediccion = sondeo.json()


async def generar(cliente: httpx.AsyncClient, prompt: str) -> str:
    """La URL temporal de la imagen en Replicate. Reintenta hasta el límite."""
    if not ajustes.hay_replicate:
        raise ErrorImagen(
            "Falta configurar Replicate: no hay REPLICATE_API_TOKEN."
        )

    ultimo: Exception | None = None
    for intento in range(1, ajustes.replicate_max_intentos + 1):
        try:
            return await _un_intento(cliente, prompt)
        except ErrorImagen as fallo:
            ultimo = fallo
            if intento < ajustes.replicate_max_intentos:
                await asyncio.sleep(2 * intento)

    raise ErrorImagen(
        f"No se pudo generar la imagen tras {ajustes.replicate_max_intentos} "
        f"intentos. Último error: {ultimo}"
    )
