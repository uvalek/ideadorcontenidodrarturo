"""
El API. Arranca el worker al levantar y expone las acciones que gastan dinero.

Reparto de trabajo con el panel: el panel LEE directo de Supabase con su llave
pública y las políticas RLS (igual que hace con las propuestas). Aquí solo
llegan las acciones que cuestan: encolar una generación, reintentarla,
regenerar una pieza y generar imágenes.

Por eso el polling del progreso no pasa por este servidor.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import db, esquemas, flujo, imagenes as img, plantillas, worker
from app.config import ajustes
from app.perfil import formatear as formatear_perfil
from app.proveedores import openai as oa
from app.seguridad import SocioActual

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
)
log = logging.getLogger("api")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    tarea = asyncio.create_task(worker.bucle())
    log.info(
        "API arriba. Modelo %s · investigación %s · imágenes %s",
        ajustes.openai_model,
        "sí" if ajustes.hay_perplexity else "no configurada",
        "sí" if ajustes.hay_replicate else "no configuradas",
    )
    yield
    tarea.cancel()


app = FastAPI(
    title="Adlek — Ideador de contenido",
    version="1.0.0",
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ajustes.origenes,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# Todo lo que cuelga de aquí exige sesión de un correo autorizado.
privado = APIRouter(dependencies=[SocioActual])


# ── Salud (la única ruta abierta: la usa EasyPanel) ──────────

@app.get("/salud")
async def salud() -> dict:
    return {
        "ok": True,
        "modelo": ajustes.openai_model,
        "investigacion": ajustes.hay_perplexity,
        "imagenes": ajustes.hay_replicate,
        "generaciones_en_curso": len(worker._en_curso),
    }


# ── Generaciones ─────────────────────────────────────────────

class NuevaGeneracion(BaseModel):
    cliente_id: str
    tema: str = Field(min_length=3, max_length=500)
    audiencia: str = ""
    plataforma: str = "ambas"
    num_ideas: int = Field(default=5, ge=1, le=10)
    usar_investigacion: bool = True


@privado.post("/generaciones", status_code=status.HTTP_201_CREATED)
async def crear_generacion(cuerpo: NuevaGeneracion) -> dict:
    if cuerpo.num_ideas > ajustes.max_ideas:
        raise HTTPException(400, f"El máximo es {ajustes.max_ideas} ideas por tema.")

    if db.contar_activas() >= ajustes.max_generaciones_activas:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Ya hay {ajustes.max_generaciones_activas} generaciones en curso. "
            "Espera a que terminen y vuelve a intentarlo.",
        )

    cliente = db.obtener_cliente_contenido(cuerpo.cliente_id)
    if not cliente or not cliente.get("activo"):
        raise HTTPException(404, "Ese cliente no existe o está desactivado.")

    fila = (
        db.cliente()
        .table("generaciones")
        .insert(
            {
                "cliente_id": cuerpo.cliente_id,
                "tema": cuerpo.tema.strip(),
                "audiencia": cuerpo.audiencia.strip(),
                "plataforma": cuerpo.plataforma,
                "num_ideas": cuerpo.num_ideas,
                "usar_investigacion": cuerpo.usar_investigacion,
                "estado": "pendiente",
            }
        )
        .execute()
    )
    return {"id": fila.data[0]["id"], "estado": "pendiente"}


@privado.post("/generaciones/{generacion_id}/reintentar")
async def reintentar(generacion_id: str) -> dict:
    generacion = db.obtener_generacion(generacion_id)
    if not generacion:
        raise HTTPException(404, "Esa generación no existe.")
    if generacion["estado"] not in ("error", "completado"):
        raise HTTPException(409, "Esa generación sigue en curso.")
    if db.contar_activas() >= ajustes.max_generaciones_activas:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Hay demasiadas generaciones en curso. Espera un momento.",
        )

    # Se borran los resultados anteriores: las ideas se van en cascada y con
    # ellas sus piezas e imágenes.
    db.cliente().table("ideas").delete().eq("generacion_id", generacion_id).execute()
    db.actualizar_generacion(
        generacion_id,
        estado="pendiente",
        progreso=0,
        detalle="",
        error_msg=None,
        advertencias=[],
        investigacion="",
        latido_en=None,
    )
    return {"id": generacion_id, "estado": "pendiente"}


# ── Regenerar una pieza suelta ───────────────────────────────

AGENTES = {
    "tiktok": ("guion_reels", esquemas.SalidaGuion, "Escribe el guion de Reels para"),
    "youtube": ("intros_youtube", esquemas.SalidaIntros, "Escribe las 5 introducciones para"),
    "ganchos": ("ganchos", esquemas.SalidaGanchos, "Escribe los 10 ganchos para"),
    "prompts_imagen": ("prompts_imagen", esquemas.SalidaImagenes, "Propón las tomas y las imágenes de apoyo para"),
}


@privado.post("/piezas/{pieza_id}/regenerar")
async def regenerar_pieza(pieza_id: str) -> dict:
    pieza = db.obtener_pieza(pieza_id)
    if not pieza:
        raise HTTPException(404, "Esa pieza no existe.")

    idea_fila = pieza.get("ideas") or {}
    idea = idea_fila.get("data") or {}
    generacion = db.obtener_generacion(idea_fila.get("generacion_id"))
    if not generacion:
        raise HTTPException(404, "La generación de esa pieza ya no existe.")

    cliente_contenido = db.obtener_cliente_contenido(generacion["cliente_id"])
    if not cliente_contenido:
        raise HTTPException(404, "El cliente de esa pieza ya no existe.")

    plantilla, esquema, instruccion = AGENTES[pieza["tipo"]]
    variables = {
        "perfil_cliente": formatear_perfil(cliente_contenido.get("perfil") or {}),
        "conocimiento": (cliente_contenido.get("conocimiento") or "").strip()
        or flujo.SIN_CONOCIMIENTO,
        "idea": flujo._resumen_idea(idea),
        "investigacion": generacion.get("investigacion") or flujo.SIN_INVESTIGACION,
        "aviso_cofepris": (cliente_contenido.get("perfil") or {}).get("aviso_cofepris", ""),
    }

    # El agente de imágenes necesita el guion, así que se lee de su hermana.
    if pieza["tipo"] == "prompts_imagen":
        hermana = (
            db.cliente()
            .table("piezas")
            .select("data")
            .eq("idea_id", pieza["idea_id"])
            .eq("tipo", "tiktok")
            .maybe_single()
            .execute()
        )
        guion = (hermana.data or {}).get("data") if hermana else None
        if not guion:
            raise HTTPException(
                409,
                "No se puede regenerar esta pieza sin el guion. Regenera "
                "primero el guion de Reels.",
            )
        variables["guion"] = flujo._guion_para_prompt(guion)

    db.cliente().table("piezas").update({"estado": "generando"}).eq(
        "id", pieza_id
    ).execute()

    try:
        async with httpx.AsyncClient() as http:
            salida = await oa.agente(
                http,
                plantillas.construir(plantilla, **variables),
                f"{instruccion}: {idea.get('titulo', '')}",
                esquema,
                etiqueta=plantilla,
            )
        datos = salida.model_dump()

        if pieza["tipo"] == "tiktok":
            flujo._cerrar_con_aviso(datos, variables["aviso_cofepris"])

        db.guardar_pieza(pieza["idea_id"], pieza["tipo"], datos)
        return {
            "id": pieza_id,
            "estado": "completado",
            "advertencias": esquemas.revisar_conteos(pieza["tipo"], datos),
        }

    except Exception as fallo:  # noqa: BLE001
        mensaje = worker._legible(fallo)
        db.guardar_pieza(pieza["idea_id"], pieza["tipo"], None, mensaje)
        raise HTTPException(502, mensaje) from fallo


# ── Imágenes bajo demanda ────────────────────────────────────

@privado.post("/ideas/{idea_id}/imagenes")
async def generar_imagenes(idea_id: str) -> dict:
    try:
        return await img.generar_de_idea(idea_id)
    except img.SinReplicate as fallo:
        raise HTTPException(503, str(fallo)) from fallo
    except ValueError as fallo:
        raise HTTPException(409, str(fallo)) from fallo


app.include_router(privado)
