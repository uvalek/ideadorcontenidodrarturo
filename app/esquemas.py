"""
La forma que debe tener lo que devuelve cada agente.

Son los mismos esquemas del workflow de n8n, con los cambios acordados:
`potencial_viral` pasó a `potencial`, las ideas llevan `pilar` y `audiencia`,
`datos_importantes` cambió sus campos, y el agente de imágenes ahora entrega
también las tomas para grabar.

Criterio de estrictez: Pydantic valida la ESTRUCTURA (que estén los campos y
sean del tipo correcto). Los CONTEOS (10 ganchos, 5 intros...) se revisan
aparte en `revisar_conteos` y solo generan advertencias. Si un modelo devuelve
9 ganchos perfectos, es una pena, no un motivo para tirar toda la generación.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Base(BaseModel):
    # Si el modelo agrega campos de más, se conservan en vez de estorbar.
    model_config = ConfigDict(extra="allow")


# ── Ideas ────────────────────────────────────────────────────────────

class Idea(Base):
    id: int
    estructura_usada: str = ""
    pilar: str = ""
    audiencia: str = ""
    titulo: str
    subtitulo: str = ""
    gancho_sugerido: str = ""
    problema_que_resuelve: str = ""
    promesa_principal: str = ""
    formato_video: str = ""
    nivel_dificultad: str = ""
    puntos_clave: list[str] = Field(default_factory=list)
    cta_sugerido: str = ""
    keywords_seo: list[str] = Field(default_factory=list)
    potencial: str = ""
    razon_potencial: str = ""


class ResumenEstrategico(Base):
    mejor_idea_para_empezar: int | None = None
    razon: str = ""
    orden_sugerido_publicacion: list[int] = Field(default_factory=list)
    explicacion_orden: str = ""


class SalidaIdeas(Base):
    tema_principal: str = ""
    audiencia_objetivo: str = ""
    ideas: list[Idea]
    resumen_estrategico: ResumenEstrategico = Field(
        default_factory=ResumenEstrategico
    )


# ── Guion de Reels ───────────────────────────────────────────────────

class DesglosePorSecciones(Base):
    gancho_3_5_seg: str = ""
    presentacion_5_8_seg: str = ""
    contenido_30_45_seg: str = ""
    informacion_clave_8_12_seg: str = ""
    cta_5_8_seg: str = ""


class ElementosVisuales(Base):
    primer_segundo: str = ""
    secuencia_principal: list[str] = Field(default_factory=list)
    textos_en_pantalla: list[str] = Field(default_factory=list)


class DatosImportantes(Base):
    servicio_relacionado: str = ""
    precio_si_aplica: str = ""
    ubicacion: str = ""
    contacto_sugerido: str = ""


class SalidaGuion(Base):
    tipo_video: str = ""
    tema_especifico: str = ""
    duracion_total: str = ""
    plataforma_principal: str = ""
    guion_completo: str
    desglose_por_secciones: DesglosePorSecciones = Field(
        default_factory=DesglosePorSecciones
    )
    elementos_visuales: ElementosVisuales = Field(default_factory=ElementosVisuales)
    datos_importantes: DatosImportantes = Field(default_factory=DatosImportantes)
    hashtags_sugeridos: list[str] = Field(default_factory=list)
    descripcion_post: str = ""


# ── Intros de YouTube ────────────────────────────────────────────────

class Intro(Base):
    id: int
    tipo: str = ""
    introduccion: str


class RecomendacionUso(Base):
    mejor_intro_para_empezar: int | None = None
    razon: str = ""


class SalidaIntros(Base):
    tema_principal: str = ""
    audiencia_objetivo: str = ""
    intros: list[Intro]
    recomendacion_uso: RecomendacionUso = Field(default_factory=RecomendacionUso)


# ── Ganchos ──────────────────────────────────────────────────────────

class Gancho(Base):
    id: int
    categoria: str = ""
    texto: str
    por_que_funciona: str = ""
    mejor_plataforma: str = ""


class GanchoRecomendado(Base):
    gancho_id: int
    razon: str = ""


class SalidaGanchos(Base):
    tema_video: str = ""
    target_audiencia: str = ""
    ganchos: list[Gancho]
    top_3_recomendados: list[GanchoRecomendado] = Field(default_factory=list)
    tips_personalizacion: list[str] = Field(default_factory=list)


# ── Tomas e imágenes ─────────────────────────────────────────────────

class Toma(Base):
    id: int
    seccion_guion: str = ""
    que_se_ve: str
    encuadre: str = ""
    que_hace_falta: str = ""
    nota: str = ""


class PromptImagen(Base):
    id: int
    seccion_guion: str = ""
    proposito: str = ""
    prompt_completo: str
    elementos_clave: list[str] = Field(default_factory=list)
    color_sugerido_fondo: str = ""


class NotasCoherencia(Base):
    paleta: str = ""
    iluminacion: str = ""
    continuidad: str = ""


class SalidaImagenes(Base):
    titulo_video: str = ""
    tema_principal: str = ""
    estilo_visual: str = ""
    tomas_para_grabar: list[Toma] = Field(default_factory=list)
    imagenes: list[PromptImagen]
    notas_coherencia: NotasCoherencia = Field(default_factory=NotasCoherencia)
    recomendaciones_produccion: list[str] = Field(default_factory=list)


# ── Revisión de conteos (advertencias, no errores) ───────────────────

TIPOS_PIEZA = Literal["tiktok", "youtube", "ganchos", "prompts_imagen"]

# Cuántos elementos esperamos en cada lista, y cómo se llama para el aviso.
ESPERADOS: dict[str, list[tuple[str, int, str]]] = {
    "ideas": [("ideas", 0, "ideas")],  # el esperado real llega por parámetro
    "tiktok": [],
    "youtube": [("intros", 5, "intros")],
    "ganchos": [("ganchos", 10, "ganchos"), ("top_3_recomendados", 3, "recomendados")],
    "prompts_imagen": [
        ("tomas_para_grabar", 10, "tomas para grabar"),
        ("imagenes", 10, "prompts de imagen"),
    ],
}


def revisar_conteos(
    tipo: str, datos: dict[str, Any], esperado_ideas: int | None = None
) -> list[str]:
    """Devuelve advertencias legibles. Nunca lanza excepción."""
    avisos: list[str] = []

    if tipo == "ideas":
        n = len(datos.get("ideas") or [])
        if esperado_ideas and n != esperado_ideas:
            avisos.append(f"Se pidieron {esperado_ideas} ideas y llegaron {n}.")
        return avisos

    for campo, esperado, nombre in ESPERADOS.get(tipo, []):
        n = len(datos.get(campo) or [])
        if n != esperado:
            avisos.append(f"Se esperaban {esperado} {nombre} y llegaron {n}.")
    return avisos
