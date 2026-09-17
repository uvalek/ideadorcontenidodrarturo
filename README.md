# Ideador de contenido — Adlek

Convierte un tema en material listo para grabar: investiga, genera ideas y por
cada idea escribe un guion de Reels, cinco intros de YouTube, diez ganchos, diez
tomas para grabar y diez prompts de imagen de apoyo.

Sirve para cualquier cliente. Agregar uno nuevo es crear un registro en la base
de datos, sin tocar código.

Se usa desde **adlek.com.mx/admin/contenido**. Esto es solo el motor.

---

## Cómo está armado

```
Panel Next.js (Vercel)              Este servicio (VPS, EasyPanel)
/admin/contenido                    api-contenido.adlek.com.mx
      │                                       │
      │  lee con la llave pública             │  escribe con service_role
      └──────────► Supabase ◄─────────────────┘
                 Adlek DataBase
```

El panel **lee** directo de Supabase. Aquí solo llegan las acciones que gastan
dinero: encolar un tema, reintentarlo, regenerar una pieza y generar imágenes.
Por eso ver el progreso no pasa por el servidor.

Dentro hay un solo proceso con dos cosas: el API y un worker que revisa la
tabla `contenido_generaciones` buscando trabajo pendiente.

---

## Cómo agregar un cliente nuevo

Un cliente es un registro en `contenido_clientes` con un campo `perfil` en
formato JSON. Ese perfil es lo que hace que el contenido suene a esa marca y no
a otra.

Desde el panel, en la sección de Clientes. O a mano, en Supabase → Table Editor
→ `contenido_clientes` → Insert row. Los campos importantes del perfil:

| Campo | Para qué sirve |
|---|---|
| `nombre_marca`, `vocero` | Quién es y quién habla a cámara |
| `presentacion_corta` | Se usa **tal cual** al principio de cada guion |
| `credenciales` | Las únicas que el contenido puede mencionar |
| `servicios` | Lo que se ofrece, por categorías |
| `precios_publicos` | Solo se usan si el tema los pide |
| `tono` | Cómo habla la marca |
| `audiencias` | A quién le habla cada idea |
| `pilares_de_contenido` | Los temas recurrentes de la marca |
| `ctas_permitidos` | Los llamados a la acción. **No se inventan otros** |
| `aviso_cofepris` | Cierra cada descripción de post |

Lo más rápido es copiar
[`referencia/cliente_swiss_dental.json`](referencia/cliente_swiss_dental.json) y
cambiarle los valores.

**Regla de oro:** no pongas en el perfil nada que no puedas respaldar. El
sistema tiene prohibido inventar datos, pero lo que esté en el perfil lo da por
cierto y lo va a decir al aire.

### El campo `conocimiento`

Texto libre que se suma a lo que el modelo sabe del cliente. Ahí va contexto que
no cabe en el perfil estructurado: cómo habla, qué le gusta explicar, su
criterio profesional, qué temas evita.

Se pega tal cual, sin formato especial. Si tienes un informe sobre el cliente,
este es su lugar.

---

## Cómo editar un prompt

Los seis agentes son archivos de texto en [`prompts/`](prompts/). Se abren con
cualquier editor y se cambian sin saber programar.

| Archivo | Qué genera |
|---|---|
| `investigador.md` | La investigación previa del tema |
| `ideas.md` | Las ideas de video |
| `guion_reels.md` | El guion de video corto |
| `intros_youtube.md` | Las cinco introducciones |
| `ganchos.md` | Los diez ganchos |
| `prompts_imagen.md` | Las tomas para grabar y los prompts de imagen |

Y dos bloques que se comparten entre todos:

| Archivo | Qué es |
|---|---|
| `comun/cumplimiento.md` | Las reglas de contenido de salud. **Se editan aquí una vez y aplican a los seis** |
| `comun/salida_json.md` | La instrucción de responder en JSON |
| `comun/modo_anuncio.md` | Cómo cambia todo cuando el contenido es pauta |
| `comun/modo_organico.md` | Lo mismo para contenido normal |

### Contenido u anuncio

Al generar se elige entre los dos, y no cambia solo el cierre:

| | Contenido | Anuncio |
|---|---|---|
| Quién lo va a ver | Alguien que ya te sigue | Un desconocido al que le apareció |
| La primera frase | Puede dar contexto | Nombra el problema, ya |
| La presentación | Al principio | Después de decir algo útil, en una frase |
| El cierre | Guardar, comentar, escribir | A la página, diciendo qué hay ahí |

El anuncio pide una dirección de destino, que se escribe en cada generación y no
en el perfil: la misma clínica puede pautar hacia páginas distintas según la
campaña.

Todos los guiones, de los dos tipos, traen **cinco llamados a la acción** para
elegir sin reescribir el final.

### Las variables

Lo que va entre llaves dobles se sustituye al vuelo. No las borres:

| Variable | Qué trae |
|---|---|
| `{{perfil_cliente}}` | El perfil del cliente, ya formateado |
| `{{conocimiento}}` | El campo `conocimiento` de ese cliente |
| `{{tema}}` | El tema que se escribió en el panel |
| `{{investigacion}}` | Lo que encontró el investigador |
| `{{idea}}` | La idea concreta que toca desarrollar |
| `{{guion}}` | El guion ya escrito (solo en `prompts_imagen.md`) |
| `{{cumplimiento}}` | Inserta el bloque de reglas de salud |
| `{{salida_json}}` | Inserta la instrucción de formato |
| `{{aviso_cofepris}}` | El número de aviso del cliente |

### Después de editar

Probar antes de desplegar, con esto:

```bash
python scripts/probar_flujo.py --ideas 1
```

Corre todo sin tocar la base de datos y deja el resultado en `salidas/` como
`.json` y como `.md`. Es gratis equivocarse ahí. En el servidor, los cambios
entran al redesplegar.

---

## Dónde ver los errores

**Lo primero: el panel.** Cada generación fallida muestra su motivo en
lenguaje normal, con un botón para reintentar.

**Si eso no basta:** EasyPanel → la app → pestaña **Logs**. Ahí sale lo que el
servicio va haciendo. Busca las líneas que empiezan con `ERROR`.

**Para saber si el servicio está vivo:** abre `https://<tu-dominio>/salud` en el
navegador. Responde algo así:

```json
{"ok": true, "modelo": "gpt-5-mini", "investigacion": true,
 "imagenes": false, "generaciones_en_curso": 0}
```

`"imagenes": false` significa que falta la llave de Replicate. `"ok": true` con
`"investigacion": false` significa que falta la de Perplexity: todo lo demás
funciona igual.

### Errores que vas a ver alguna vez

| Lo que dice | Qué pasó | Qué hacer |
|---|---|---|
| La llave de OpenAI no es válida o caducó | La llave está mal o fue revocada | Generar otra y actualizarla en EasyPanel |
| La cuenta de OpenAI se quedó sin saldo | Eso mismo | Recargar |
| Se alcanzó el límite de peticiones | Demasiadas seguidas | Esperar unos minutos y reintentar |
| El proceso se interrumpió a media generación | El servidor se reinició mientras trabajaba | Reintentar; no se pierde nada |
| Ya hay 2 generaciones en curso | El límite de seguridad | Esperar a que terminen |
| Falta configurar Replicate | No hay llave de imágenes | Agregarla, o usar solo las tomas para grabar |

---

## Cuánto cuesta

Medido de verdad, no estimado. Cada generación guarda sus tokens en la base,
así que el número siempre se puede comprobar.

| Qué | Cuánto |
|---|---|
| Una generación de 5 ideas | **$0.17 – 0.20 USD** (unos 3 a 4 pesos) |
| Solo el paso de investigación | menos de $0.01 |
| Las 10 imágenes de una idea | ~$0.25 USD, y solo si las pides |
| Tiempo de una generación de 5 ideas | 3 a 5 minutos |

Las imágenes no se generan solas a propósito: 10 por idea y 5 ideas serían 50
por tema, y casi ninguna se usaría.

**Los topes que impiden un susto:** máximo 2 generaciones a la vez, máximo 10
ideas por tema, y solo los correos de `ADMIN_EMAILS` pueden pedir algo.

---

## Correrlo en tu computadora

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env        # y rellenar las llaves
.venv/bin/uvicorn app.main:app --reload
```

Dos scripts para probar sin desplegar:

```bash
# El flujo completo, sin base de datos. Deja el resultado en salidas/
python scripts/probar_flujo.py --ideas 1

# El ciclo real: encola un tema en Supabase y levanta el worker
python scripts/probar_worker.py --ideas 1
```

---

## Desplegar

Está en [`DESPLIEGUE.md`](DESPLIEGUE.md).

## La base de datos

El SQL está en [`supabase/migraciones/`](supabase/migraciones/), y ya está
aplicado en el proyecto *Adlek DataBase*. Queda como registro y por si hay que
levantar otro entorno.

Las cinco tablas llevan el prefijo `contenido_` para no confundirse con las de
otros proyectos que viven en la misma base.

## De dónde viene esto

Era un flujo de n8n, guardado en
[`referencia/n8n_workflow.json`](referencia/n8n_workflow.json). Al migrarlo se
corrigieron cinco errores que traía: un gancho que se perdía y otro que salía
duplicado, el agente de imágenes que decía analizar un guion que nunca recibía,
un prompt que terminaba invitando al modelo a conversar, dos imágenes de diez
que no se guardaban, y una espera sin límite que podía quedarse girando para
siempre.
