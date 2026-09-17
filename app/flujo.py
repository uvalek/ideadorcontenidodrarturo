"""
El flujo completo: tema → investigación → ideas → piezas.

Este archivo no sabe nada de Supabase ni de FastAPI a propósito. Recibe un
encargo y devuelve un resultado. Eso permite correrlo desde la terminal
(`scripts/probar_flujo.py`) sin base de datos, y desde el worker con ella.

Orden dentro de cada idea, y aquí está el arreglo del bug del workflow:

    guion_reels ──────────────┐
    intros_youtube (paralelo) │
    ganchos        (paralelo) │
                              └──► prompts_imagen  (recibe el guion ya escrito)

En n8n los cuatro agentes salían en paralelo desde la idea, así que el de
imágenes decía "analiza el guion" sin haberlo visto nunca.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Awaitable, Callable

import httpx

from app import esquemas, perfil as perfil_mod, plantillas
from app.config import ajustes
from app.proveedores import openai as oa
from app.proveedores import perplexity as px

# Un callback opcional para ir contando el avance: (estado, progreso, detalle)
Avisar = Callable[[str, int, str], Awaitable[None]]


@dataclass
class Encargo:
    tema: str
    perfil: dict[str, Any]
    conocimiento: str = ""
    audiencia: str = ""
    plataforma: str = "ambas"
    objetivo: str = "organico"
    landing_url: str = ""
    num_ideas: int = 5
    usar_investigacion: bool = True


@dataclass
class PiezasDeIdea:
    idea: dict[str, Any]
    guion: dict[str, Any] | None = None
    intros: dict[str, Any] | None = None
    ganchos: dict[str, Any] | None = None
    prompts_imagen: dict[str, Any] | None = None
    errores: dict[str, str] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)


@dataclass
class Resultado:
    tema: str
    investigacion: str = ""
    ideas: dict[str, Any] = field(default_factory=dict)
    piezas: list[PiezasDeIdea] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    advertencias: list[str] = field(default_factory=list)


SIN_CONOCIMIENTO = (
    "(Sin notas adicionales para este cliente.)"
)

SIN_INVESTIGACION = (
    "(Sin investigación externa. No uses cifras, estudios ni fuentes: no hay "
    "material verificado para respaldarlos. Habla solo desde el criterio "
    "profesional y el perfil del cliente.)"
)


def _cerrar_con_aviso(guion: dict[str, Any], aviso: str) -> None:
    """
    Garantiza que `descripcion_post` termine con el aviso de publicidad.

    El prompt ya lo pide, pero esto es una regla de cumplimiento: conviene que
    no dependa de que el modelo haga caso. Si ya está, no se duplica.
    """
    if not aviso:
        return
    linea = f"Aviso de publicidad COFEPRIS: {aviso}"
    texto = (guion.get("descripcion_post") or "").rstrip()
    if linea in texto:
        return
    guion["descripcion_post"] = f"{texto}\n\n{linea}".strip()


def _resumen_idea(idea: dict[str, Any]) -> str:
    """Lo que ve un agente de pieza sobre la idea que le tocó."""
    campos = [
        ("Título", idea.get("titulo")),
        ("Subtítulo", idea.get("subtitulo")),
        ("Estructura", idea.get("estructura_usada")),
        ("Pilar de contenido", idea.get("pilar")),
        ("Audiencia", idea.get("audiencia")),
        ("Gancho sugerido", idea.get("gancho_sugerido")),
        ("Problema que resuelve", idea.get("problema_que_resuelve")),
        ("Promesa principal", idea.get("promesa_principal")),
        ("CTA sugerido", idea.get("cta_sugerido")),
    ]
    lineas = [f"{k}: {v}" for k, v in campos if v]
    puntos = idea.get("puntos_clave") or []
    if puntos:
        lineas.append("Puntos clave:\n" + "\n".join(f"- {p}" for p in puntos))
    return "\n".join(lineas)


async def investigar(cliente: httpx.AsyncClient, encargo: Encargo) -> str:
    sistema = plantillas.construir(
        "investigador",
        perfil_cliente=perfil_mod.formatear(encargo.perfil),
        conocimiento=encargo.conocimiento or SIN_CONOCIMIENTO,
        tema=encargo.tema,
        fecha=date.today().isoformat(),
        aviso_cofepris=perfil_mod.aviso_cofepris(encargo.perfil),
    )
    return await px.investigar(cliente, sistema, encargo.tema)


async def sugerir_temas(
    cliente: httpx.AsyncClient,
    perfil: dict[str, Any],
    conocimiento: str,
    cuantos: int,
    ya_usados: list[str],
    uso: oa.Uso,
) -> esquemas.SalidaTemas:
    """
    Propone temas a partir del perfil, sin desarrollarlos.

    Es el paso previo para quien no conoce el nicho y no sabe qué pedir. No
    investiga ni escribe nada: una sola llamada, rápida y barata.
    """
    lista = (
        "\n".join(f"- {t}" for t in ya_usados)
        if ya_usados
        else "(Ninguno todavía: es la primera vez que se generan temas para este cliente.)"
    )

    sistema = plantillas.construir(
        "temas",
        perfil_cliente=perfil_mod.formatear(perfil),
        conocimiento=conocimiento or SIN_CONOCIMIENTO,
        ya_usados=lista,
        cuantos=cuantos,
        aviso_cofepris=perfil_mod.aviso_cofepris(perfil),
    )
    return await oa.agente(
        cliente,
        sistema,
        f"Propón {cuantos} temas para este cliente.",
        esquemas.SalidaTemas,
        uso=uso,
        etiqueta="temas",
    )


async def generar_ideas(
    cliente: httpx.AsyncClient,
    encargo: Encargo,
    investigacion: str,
    uso: oa.Uso,
) -> esquemas.SalidaIdeas:
    sistema = plantillas.construir(
        "ideas",
        perfil_cliente=perfil_mod.formatear(encargo.perfil),
        conocimiento=encargo.conocimiento or SIN_CONOCIMIENTO,
        objetivo=encargo.objetivo,
        landing_url=encargo.landing_url,
        tema=encargo.tema,
        audiencia=encargo.audiencia or "La que mejor le quede a cada idea",
        plataforma=encargo.plataforma,
        num_ideas=encargo.num_ideas,
        investigacion=investigacion or SIN_INVESTIGACION,
        aviso_cofepris=perfil_mod.aviso_cofepris(encargo.perfil),
    )
    return await oa.agente(
        cliente,
        sistema,
        f"Genera las {encargo.num_ideas} ideas para el tema: {encargo.tema}",
        esquemas.SalidaIdeas,
        uso=uso,
        etiqueta="ideas",
    )


async def _pieza(
    cliente: httpx.AsyncClient,
    nombre: str,
    esquema,
    variables: dict[str, Any],
    instruccion: str,
    uso: oa.Uso,
    limite: asyncio.Semaphore,
):
    async with limite:
        sistema = plantillas.construir(nombre, **variables)
        return await oa.agente(
            cliente, sistema, instruccion, esquema, uso=uso, etiqueta=nombre
        )


async def piezas_de_una_idea(
    cliente: httpx.AsyncClient,
    encargo: Encargo,
    idea: dict[str, Any],
    investigacion: str,
    uso: oa.Uso,
    limite: asyncio.Semaphore,
) -> PiezasDeIdea:
    salida = PiezasDeIdea(idea=idea)

    comunes = {
        "perfil_cliente": perfil_mod.formatear(encargo.perfil),
        "conocimiento": encargo.conocimiento or SIN_CONOCIMIENTO,
        "objetivo": encargo.objetivo,
        "landing_url": encargo.landing_url,
        "idea": _resumen_idea(idea),
        "investigacion": investigacion or SIN_INVESTIGACION,
        "aviso_cofepris": perfil_mod.aviso_cofepris(encargo.perfil),
    }
    titulo = idea.get("titulo", "")

    # El guion va primero y solo: el agente de imágenes lo necesita.
    guion_tarea = _pieza(
        cliente, "guion_reels", esquemas.SalidaGuion, comunes,
        f"Escribe el guion de Reels para: {titulo}", uso, limite,
    )
    intros_tarea = _pieza(
        cliente, "intros_youtube", esquemas.SalidaIntros, comunes,
        f"Escribe las 5 introducciones para: {titulo}", uso, limite,
    )
    ganchos_tarea = _pieza(
        cliente, "ganchos", esquemas.SalidaGanchos, comunes,
        f"Escribe los 10 ganchos para: {titulo}", uso, limite,
    )

    resultados = await asyncio.gather(
        guion_tarea, intros_tarea, ganchos_tarea, return_exceptions=True
    )

    for clave, res in zip(("guion", "intros", "ganchos"), resultados):
        if isinstance(res, Exception):
            salida.errores[clave] = str(res)
        else:
            salida.__setattr__(clave, res.model_dump())

    if salida.guion:
        _cerrar_con_aviso(salida.guion, perfil_mod.aviso_cofepris(encargo.perfil))
        salida.advertencias += esquemas.revisar_conteos("tiktok", salida.guion)
    if salida.intros:
        salida.advertencias += esquemas.revisar_conteos("youtube", salida.intros)
    if salida.ganchos:
        salida.advertencias += esquemas.revisar_conteos("ganchos", salida.ganchos)

    # Ahora sí, las imágenes, con el guion en la mano.
    if salida.guion:
        try:
            imagenes = await _pieza(
                cliente,
                "prompts_imagen",
                esquemas.SalidaImagenes,
                {**comunes, "guion": _guion_para_prompt(salida.guion)},
                f"Propón las tomas y las imágenes de apoyo para: {titulo}",
                uso,
                limite,
            )
            salida.prompts_imagen = imagenes.model_dump()
            salida.advertencias += esquemas.revisar_conteos(
                "prompts_imagen", salida.prompts_imagen
            )
        except Exception as fallo:
            salida.errores["prompts_imagen"] = str(fallo)
    else:
        salida.errores["prompts_imagen"] = (
            "No se generaron tomas ni imágenes porque el guion falló: "
            "este agente necesita el guion para trabajar."
        )

    return salida


def _guion_para_prompt(guion: dict[str, Any]) -> str:
    """El guion en texto, tal como lo tiene que leer el agente de imágenes."""
    partes = [f"GUION COMPLETO:\n{guion.get('guion_completo', '')}"]

    desglose = guion.get("desglose_por_secciones") or {}
    if desglose:
        lineas = "\n".join(
            f"- {k.replace('_', ' ')}: {v}" for k, v in desglose.items() if v
        )
        partes.append(f"DESGLOSE POR SECCIONES:\n{lineas}")

    visuales = guion.get("elementos_visuales") or {}
    secuencia = visuales.get("secuencia_principal") or []
    if secuencia:
        partes.append(
            "TOMAS YA PREVISTAS EN EL GUION:\n"
            + "\n".join(f"- {t}" for t in secuencia)
        )

    return "\n\n".join(partes)


async def correr(encargo: Encargo, avisar: Avisar | None = None) -> Resultado:
    """El flujo completo, de principio a fin."""

    async def paso(estado: str, pct: int, detalle: str = "") -> None:
        if avisar:
            await avisar(estado, pct, detalle)

    resultado = Resultado(tema=encargo.tema)
    uso = oa.Uso()
    limite = asyncio.Semaphore(ajustes.max_concurrencia_llm)

    async with httpx.AsyncClient() as cliente:
        # 1. Investigación (opcional)
        if encargo.usar_investigacion and ajustes.hay_perplexity:
            await paso("investigando", 5, "Buscando evidencia sobre el tema")
            try:
                resultado.investigacion = await investigar(cliente, encargo)
            except Exception as fallo:
                resultado.advertencias.append(
                    f"La investigación falló y se siguió sin ella: {fallo}"
                )
        elif encargo.usar_investigacion:
            resultado.advertencias.append(
                "Se pidió investigación pero no hay llave de Perplexity "
                "configurada. Se generó sin ella."
            )

        # 2. Ideas
        await paso("generando_ideas", 20, f"Pensando {encargo.num_ideas} ideas")
        ideas = await generar_ideas(cliente, encargo, resultado.investigacion, uso)
        resultado.ideas = ideas.model_dump()
        resultado.advertencias += esquemas.revisar_conteos(
            "ideas", resultado.ideas, encargo.num_ideas
        )

        lista = resultado.ideas.get("ideas") or []
        if not lista:
            raise oa.ErrorAgente("No se generó ninguna idea utilizable.")

        # 3. Piezas de cada idea
        await paso("generando_piezas", 35, f"Escribiendo el material de {len(lista)} ideas")

        hechas = 0
        total = len(lista)
        piezas: list[PiezasDeIdea | None] = [None] * total

        async def una(indice: int, idea: dict[str, Any]) -> None:
            nonlocal hechas
            piezas[indice] = await piezas_de_una_idea(
                cliente, encargo, idea, resultado.investigacion, uso, limite
            )
            hechas += 1
            await paso(
                "generando_piezas",
                35 + int(60 * hechas / total),
                f"Idea {hechas} de {total} lista",
            )

        await asyncio.gather(*(una(i, idea) for i, idea in enumerate(lista)))
        resultado.piezas = [p for p in piezas if p is not None]

    resultado.tokens_entrada = uso.entrada
    resultado.tokens_salida = uso.salida
    await paso("completado", 100, "Listo")
    return resultado
