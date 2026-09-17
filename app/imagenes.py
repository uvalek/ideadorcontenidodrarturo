"""
Generación de las imágenes de apoyo de una idea, bajo demanda.

Bajo demanda y no automática: 10 imágenes por idea y 5 ideas por tema serían
50 llamadas por generación, y la mayoría no se usarían nunca.

Se crean las 10 filas SIEMPRE, antes de generar nada. Así, si una falla, queda
registrada con su error en vez de desaparecer — en el workflow de n8n se
generaban 10 y se guardaban 8, y no había forma de saber cuáles faltaban.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from app import db
from app.config import ajustes
from app.proveedores import replicate as rp

log = logging.getLogger("imagenes")

MIMES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class SinReplicate(Exception):
    """Falta configurar la llave de Replicate."""


def prompts_de_la_idea(idea: dict) -> list[str]:
    """Saca los `prompt_completo` de la pieza de imágenes de esa idea."""
    r = (
        db.cliente()
        .table("piezas")
        .select("data")
        .eq("idea_id", idea["id"])
        .eq("tipo", "prompts_imagen")
        .maybe_single()
        .execute()
    )
    datos = (r.data or {}).get("data") if r else None
    if not datos:
        return []
    return [
        im.get("prompt_completo", "")
        for im in (datos.get("imagenes") or [])
        if im.get("prompt_completo")
    ]


async def _una(
    cliente: httpx.AsyncClient,
    fila: dict,
    generacion_id: str,
    limite: asyncio.Semaphore,
) -> bool:
    async with limite:
        db.actualizar_imagen(fila["id"], estado="generando", error_msg=None)
        try:
            url_temporal = await rp.generar(cliente, fila["prompt"])

            # Replicate borra sus URLs al cabo de un tiempo, así que la imagen
            # se copia a Supabase Storage y esa es la que se guarda.
            descarga = await cliente.get(url_temporal, timeout=httpx.Timeout(120.0))
            descarga.raise_for_status()

            tipo = descarga.headers.get("content-type", "image/jpeg").split(";")[0]
            if tipo not in MIMES.values():
                tipo = MIMES.get(url_temporal.rsplit(".", 1)[-1].lower(), "image/jpeg")

            url = db.subir_imagen(descarga.content, generacion_id, tipo)
            db.actualizar_imagen(fila["id"], estado="completado", url=url, error_msg=None)
            return True

        except Exception as fallo:  # noqa: BLE001 — el fallo se guarda, no se propaga
            log.warning("Imagen %s falló: %s", fila["orden"], fallo)
            db.actualizar_imagen(
                fila["id"], estado="error", error_msg=str(fallo)[:400]
            )
            return False


async def generar_de_idea(idea_id: str) -> dict:
    """Genera las imágenes de una idea. Una que falle no detiene a las demás."""
    if not ajustes.hay_replicate:
        raise SinReplicate(
            "Falta configurar Replicate. Agrega REPLICATE_API_TOKEN en las "
            "variables de entorno del servidor y vuelve a intentarlo."
        )

    idea = db.obtener_idea(idea_id)
    if not idea:
        raise ValueError("Esa idea ya no existe.")

    prompts = prompts_de_la_idea(idea)
    if not prompts:
        raise ValueError(
            "Esta idea no tiene prompts de imagen guardados. Regenera la pieza "
            "de «Tomas e imágenes» primero."
        )

    filas = db.crear_filas_imagenes(idea_id, prompts)
    generacion_id = idea["generacion_id"]
    limite = asyncio.Semaphore(ajustes.max_concurrencia_llm)

    async with httpx.AsyncClient() as cliente:
        resultados = await asyncio.gather(
            *(_una(cliente, f, generacion_id, limite) for f in filas)
        )

    logradas = sum(1 for r in resultados if r)

    generacion = db.obtener_generacion(generacion_id)
    if generacion:
        db.actualizar_generacion(
            generacion_id,
            num_imagenes=(generacion.get("num_imagenes") or 0) + logradas,
        )

    return {
        "pedidas": len(filas),
        "logradas": logradas,
        "fallidas": len(filas) - logradas,
        "imagenes": db.imagenes_de(idea_id),
    }
