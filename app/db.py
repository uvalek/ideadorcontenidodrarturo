"""
Acceso a Supabase desde el backend, con la service_role key.

Esa llave salta las políticas RLS por diseño: este proceso es quien escribe
los resultados de las generaciones. Vive solo en el .env del VPS y nunca
viaja al navegador.

El panel, en cambio, lee con la llave pública y sus propias políticas. Son
dos caminos distintos a los mismos datos, con permisos distintos.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.config import ajustes


@lru_cache
def cliente() -> Client:
    if not ajustes.supabase_url or not ajustes.supabase_service_role_key:
        raise RuntimeError(
            "Faltan SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en el .env"
        )
    return create_client(ajustes.supabase_url, ajustes.supabase_service_role_key)


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── clientes ─────────────────────────────────────────────────

def obtener_cliente_contenido(cliente_id: str) -> dict[str, Any] | None:
    r = (
        cliente()
        .table("contenido_clientes")
        .select("id, nombre, slug, perfil, conocimiento, activo")
        .eq("id", cliente_id)
        .maybe_single()
        .execute()
    )
    return r.data if r else None


# ── generaciones ─────────────────────────────────────────────

ESTADOS_ACTIVOS = ["investigando", "generando_ideas", "generando_piezas"]


def siguiente_pendiente() -> dict[str, Any] | None:
    r = (
        cliente()
        .table("contenido_generaciones")
        .select("*")
        .eq("estado", "pendiente")
        .order("creada_en")
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def contar_activas() -> int:
    r = (
        cliente()
        .table("contenido_generaciones")
        .select("id", count="exact")
        .in_("estado", ESTADOS_ACTIVOS)
        .execute()
    )
    return r.count or 0


def tomar(generacion_id: str) -> bool:
    """
    Marca una generación como tomada. Devuelve False si otro proceso se
    adelantó.

    El `.eq("estado", "pendiente")` es lo que hace esto seguro: si dos workers
    intentan tomar la misma fila, solo uno encuentra la condición cierta y el
    otro actualiza cero filas.
    """
    r = (
        cliente()
        .table("contenido_generaciones")
        .update({"estado": "investigando", "progreso": 1, "latido_en": ahora()})
        .eq("id", generacion_id)
        .eq("estado", "pendiente")
        .execute()
    )
    return bool(r.data)


def actualizar_generacion(generacion_id: str, **campos: Any) -> None:
    cliente().table("contenido_generaciones").update(campos).eq("id", generacion_id).execute()


def latir(generacion_id: str, estado: str, progreso: int, detalle: str) -> None:
    actualizar_generacion(
        generacion_id,
        estado=estado,
        progreso=progreso,
        detalle=detalle,
        latido_en=ahora(),
    )


def rescatar_colgadas(minutos: int = 5) -> list[str]:
    """
    Devuelve a 'error' las generaciones que se quedaron a medias.

    Pasa cuando el contenedor se reinicia mientras trabajaba: la fila queda en
    un estado intermedio y nadie la va a terminar nunca. Se detectan porque su
    latido dejó de avanzar.
    """
    limite = datetime.now(timezone.utc).timestamp() - minutos * 60
    corte = datetime.fromtimestamp(limite, tz=timezone.utc).isoformat()

    r = (
        cliente()
        .table("contenido_generaciones")
        .select("id")
        .in_("estado", ESTADOS_ACTIVOS)
        .lt("latido_en", corte)
        .execute()
    )
    ids = [fila["id"] for fila in (r.data or [])]

    for gid in ids:
        actualizar_generacion(
            gid,
            estado="error",
            error_msg=(
                "El proceso se interrumpió a media generación, probablemente "
                "por un reinicio del servidor. Puedes reintentarlo."
            ),
        )
    return ids


# ── ideas, piezas e imágenes ─────────────────────────────────

def guardar_idea(generacion_id: str, orden: int, data: dict[str, Any]) -> str:
    r = (
        cliente()
        .table("contenido_ideas")
        .insert({"generacion_id": generacion_id, "orden": orden, "data": data})
        .execute()
    )
    return r.data[0]["id"]


def guardar_pieza(
    idea_id: str,
    tipo: str,
    data: dict[str, Any] | None,
    error_msg: str | None = None,
) -> None:
    (
        cliente()
        .table("contenido_piezas")
        .upsert(
            {
                "idea_id": idea_id,
                "tipo": tipo,
                "data": data,
                "estado": "error" if error_msg else "completado",
                "error_msg": error_msg,
            },
            on_conflict="idea_id,tipo",
        )
        .execute()
    )


def obtener_pieza(pieza_id: str) -> dict[str, Any] | None:
    r = (
        cliente()
        .table("contenido_piezas")
        .select("id, idea_id, tipo, contenido_ideas(id, data, generacion_id)")
        .eq("id", pieza_id)
        .maybe_single()
        .execute()
    )
    return r.data if r else None


def obtener_idea(idea_id: str) -> dict[str, Any] | None:
    r = (
        cliente()
        .table("contenido_ideas")
        .select("id, orden, data, generacion_id, contenido_generaciones(id, cliente_id, investigacion)")
        .eq("id", idea_id)
        .maybe_single()
        .execute()
    )
    return r.data if r else None


def obtener_generacion(generacion_id: str) -> dict[str, Any] | None:
    r = (
        cliente()
        .table("contenido_generaciones")
        .select("*")
        .eq("id", generacion_id)
        .maybe_single()
        .execute()
    )
    return r.data if r else None


def crear_filas_imagenes(idea_id: str, prompts: list[str]) -> list[dict[str, Any]]:
    """Una fila por prompt, todas en 'pendiente'. Se crean las 10, siempre."""
    filas = [
        {"idea_id": idea_id, "orden": i, "prompt": p, "estado": "pendiente"}
        for i, p in enumerate(prompts, start=1)
    ]
    r = (
        cliente()
        .table("contenido_imagenes")
        .upsert(filas, on_conflict="idea_id,orden")
        .execute()
    )
    return r.data or []


def actualizar_imagen(imagen_id: str, **campos: Any) -> None:
    cliente().table("contenido_imagenes").update(campos).eq("id", imagen_id).execute()


def imagenes_de(idea_id: str) -> list[dict[str, Any]]:
    r = (
        cliente()
        .table("contenido_imagenes")
        .select("*")
        .eq("idea_id", idea_id)
        .order("orden")
        .execute()
    )
    return r.data or []


# ── Storage ──────────────────────────────────────────────────

def subir_imagen(contenido: bytes, generacion_id: str, tipo_mime: str) -> str:
    """Sube la imagen al bucket y devuelve su URL pública."""
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}.get(
        tipo_mime, "jpg"
    )
    ruta = f"{generacion_id}/{uuid.uuid4().hex}.{extension}"

    cliente().storage.from_(ajustes.bucket_imagenes).upload(
        ruta, contenido, {"content-type": tipo_mime, "upsert": "false"}
    )
    return cliente().storage.from_(ajustes.bucket_imagenes).get_public_url(ruta)
