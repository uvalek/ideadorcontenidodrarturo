"""
Prueba el flujo completo desde la terminal, SIN base de datos y SIN imágenes.

Sirve para revisar los prompts antes de conectar nada. Guarda el resultado en
`salidas/` como .json (para verlo todo) y como .md (para leerlo cómodo).

    python scripts/probar_flujo.py
    python scripts/probar_flujo.py --tema "Qué ve un microscopio dental" --ideas 2
    python scripts/probar_flujo.py --sin-investigacion

Antes de correrlo hace falta un archivo `.env` con OPENAI_API_KEY (y
PERPLEXITY_API_KEY si quieres la investigación).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app import flujo  # noqa: E402
from app.config import ajustes  # noqa: E402

TEMA_POR_DEFECTO = "Brackets vs alineadores transparentes: cuál me conviene"
PERFIL = RAIZ / "referencia" / "cliente_swiss_dental.json"
SALIDAS = RAIZ / "salidas"


def bloque(titulo: str) -> None:
    print(f"\n\033[1m{titulo}\033[0m")
    print("─" * min(len(titulo), 70))


async def principal() -> int:
    parser = argparse.ArgumentParser(description="Prueba el ideador de contenido")
    parser.add_argument("--tema", default=TEMA_POR_DEFECTO)
    parser.add_argument("--ideas", type=int, default=5)
    parser.add_argument("--audiencia", default="")
    parser.add_argument("--plataforma", default="ambas")
    parser.add_argument("--perfil", default=str(PERFIL))
    parser.add_argument(
        "--sin-investigacion", action="store_true", help="Salta el paso de Perplexity"
    )
    args = parser.parse_args()

    if not ajustes.openai_api_key:
        print(
            "\n❌ Falta OPENAI_API_KEY.\n\n"
            "   Copia .env.example como .env y pega tu llave ahí:\n"
            "   cp .env.example .env\n"
        )
        return 1

    perfil = json.loads(Path(args.perfil).read_text(encoding="utf-8"))

    print(f"\n  Cliente:       {perfil.get('nombre_marca', '—')}")
    print(f"  Tema:          {args.tema}")
    print(f"  Ideas:         {args.ideas}")
    print(f"  Modelo:        {ajustes.openai_model}")
    print(
        "  Investigación: "
        + (
            "sí (Perplexity)"
            if not args.sin_investigacion and ajustes.hay_perplexity
            else "no"
        )
    )
    print()

    encargo = flujo.Encargo(
        tema=args.tema,
        perfil=perfil,
        audiencia=args.audiencia,
        plataforma=args.plataforma,
        num_ideas=args.ideas,
        usar_investigacion=not args.sin_investigacion,
    )

    arranque = time.monotonic()

    async def avisar(estado: str, pct: int, detalle: str) -> None:
        print(f"  [{pct:3d}%] {estado:18} {detalle}")

    try:
        resultado = await flujo.correr(encargo, avisar)
    except Exception as fallo:
        print(f"\n❌ Falló: {fallo}\n")
        return 1

    segundos = time.monotonic() - arranque

    SALIDAS.mkdir(exist_ok=True)
    sello = datetime.now().strftime("%Y%m%d-%H%M")
    base = SALIDAS / f"{sello}-{_slug(args.tema)}"

    crudo = {
        "tema": resultado.tema,
        "investigacion": resultado.investigacion,
        "ideas": resultado.ideas,
        "piezas": [
            {
                "idea": p.idea,
                "guion": p.guion,
                "intros": p.intros,
                "ganchos": p.ganchos,
                "prompts_imagen": p.prompts_imagen,
                "errores": p.errores,
                "advertencias": p.advertencias,
            }
            for p in resultado.piezas
        ],
        "advertencias": resultado.advertencias,
        "tokens": {
            "entrada": resultado.tokens_entrada,
            "salida": resultado.tokens_salida,
        },
        "segundos": round(segundos, 1),
    }
    base.with_suffix(".json").write_text(
        json.dumps(crudo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    base.with_suffix(".md").write_text(_a_markdown(crudo), encoding="utf-8")

    bloque("Resultado")
    print(f"  Ideas generadas:  {len(resultado.ideas.get('ideas') or [])}")
    print(f"  Tiempo:           {segundos:.0f} s")
    print(
        f"  Tokens:           {resultado.tokens_entrada:,} entrada + "
        f"{resultado.tokens_salida:,} salida"
    )

    errores = [(i + 1, p.errores) for i, p in enumerate(resultado.piezas) if p.errores]
    avisos = list(resultado.advertencias)
    for i, p in enumerate(resultado.piezas):
        avisos += [f"Idea {i + 1}: {a}" for a in p.advertencias]

    if errores:
        bloque("Errores")
        for numero, errs in errores:
            for pieza, msg in errs.items():
                print(f"  Idea {numero} · {pieza}: {msg[:160]}")

    if avisos:
        bloque("Advertencias")
        for a in avisos:
            print(f"  · {a}")

    bloque("Archivos")
    print(f"  {base.with_suffix('.json')}")
    print(f"  {base.with_suffix('.md')}   ← este es el cómodo de leer")
    print()
    return 0


def _slug(texto: str) -> str:
    limpio = "".join(c if c.isalnum() or c == " " else "" for c in texto.lower())
    return "-".join(limpio.split())[:50]


def _a_markdown(d: dict) -> str:
    partes = [f"# {d['tema']}\n"]

    if d.get("investigacion"):
        partes.append("<details>\n<summary>Investigación</summary>\n")
        partes.append(d["investigacion"])
        partes.append("\n</details>\n")

    resumen = (d.get("ideas") or {}).get("resumen_estrategico") or {}
    if resumen:
        partes.append("## Resumen estratégico\n")
        partes.append(f"**Empezar por la idea {resumen.get('mejor_idea_para_empezar')}** — {resumen.get('razon', '')}\n")
        orden = resumen.get("orden_sugerido_publicacion") or []
        if orden:
            partes.append(
                f"**Orden sugerido:** {' → '.join(str(o) for o in orden)}. "
                f"{resumen.get('explicacion_orden', '')}\n"
            )

    for n, p in enumerate(d.get("piezas") or [], start=1):
        idea = p.get("idea") or {}
        partes.append(f"\n---\n\n## Idea {n} · {idea.get('titulo', '')}\n")
        partes.append(f"*{idea.get('subtitulo', '')}*\n")
        meta = [
            ("Pilar", idea.get("pilar")),
            ("Audiencia", idea.get("audiencia")),
            ("Estructura", idea.get("estructura_usada")),
            ("Potencial", idea.get("potencial")),
            ("Formato", idea.get("formato_video")),
        ]
        partes.append(
            "\n".join(f"- **{k}:** {v}" for k, v in meta if v) + "\n"
        )
        if idea.get("puntos_clave"):
            partes.append("**Puntos clave**\n")
            partes.append("\n".join(f"- {x}" for x in idea["puntos_clave"]) + "\n")
        if idea.get("cta_sugerido"):
            partes.append(f"**CTA:** {idea['cta_sugerido']}\n")

        guion = p.get("guion")
        if guion:
            partes.append(f"\n### Guion de Reels — {guion.get('tipo_video', '')}\n")
            partes.append(f"> {guion.get('guion_completo', '')}\n")
            visuales = (guion.get("elementos_visuales") or {}).get(
                "secuencia_principal"
            ) or []
            if visuales:
                partes.append("**Tomas previstas**\n")
                partes.append("\n".join(f"- {t}" for t in visuales) + "\n")
            if guion.get("hashtags_sugeridos"):
                partes.append(" ".join(guion["hashtags_sugeridos"]) + "\n")
            if guion.get("descripcion_post"):
                partes.append(f"\n**Descripción del post**\n\n{guion['descripcion_post']}\n")

        intros = p.get("intros")
        if intros:
            partes.append("\n### Intros de YouTube\n")
            for i in intros.get("intros") or []:
                partes.append(f"**{i.get('id')}. {i.get('tipo', '')}**\n\n{i.get('introduccion', '')}\n")

        ganchos = p.get("ganchos")
        if ganchos:
            top = {g.get("gancho_id") for g in ganchos.get("top_3_recomendados") or []}
            partes.append("\n### Ganchos\n")
            for g in ganchos.get("ganchos") or []:
                marca = " ⭐" if g.get("id") in top else ""
                partes.append(
                    f"{g.get('id')}. *{g.get('categoria', '')}* — {g.get('texto', '')}{marca}"
                )
            partes.append("")

        imgs = p.get("prompts_imagen")
        if imgs:
            partes.append("\n### Tomas para grabar\n")
            for t in imgs.get("tomas_para_grabar") or []:
                partes.append(
                    f"{t.get('id')}. **{t.get('seccion_guion', '')}** — {t.get('que_se_ve', '')} "
                    f"({t.get('encuadre', '')})"
                )
            partes.append("\n### Prompts de imagen\n")
            for im in imgs.get("imagenes") or []:
                partes.append(f"{im.get('id')}. `{im.get('prompt_completo', '')}`\n")

        if p.get("errores"):
            partes.append("\n**Errores**\n")
            for k, v in p["errores"].items():
                partes.append(f"- {k}: {v}")

    return "\n".join(partes)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(principal()))
