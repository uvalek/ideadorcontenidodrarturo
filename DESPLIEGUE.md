# Desplegar en EasyPanel

Tiempo: unos 15 minutos la primera vez. Después, cada actualización es un clic.

---

## Antes de empezar

Ten a la mano estas cuatro cosas. Si te falta alguna, consíguela primero:

| Qué | Dónde se saca |
|---|---|
| Llave de **OpenAI** | platform.openai.com → API keys → Create new secret key |
| Llave de **Perplexity** | perplexity.ai/settings/api → Generate |
| **URL y service_role key** de Supabase | Dashboard → Adlek DataBase → Project Settings → API Keys |
| Un **subdominio** libre | Por ejemplo `api-contenido.adlek.com.mx` |

⚠️ La **service_role key** da acceso total a tu base de datos. Solo se pega en
EasyPanel. Nunca en GitHub, nunca en el panel, nunca en un chat.

---

## 1. Crear la app

1. Entra a EasyPanel y abre tu proyecto (o crea uno nuevo: **+ Project**).
2. **+ Service** → **App**.
3. Nombre: `ideador-contenido`. Créala.

## 2. Conectar el repositorio

En la pestaña **Source**:

- **Source Type:** GitHub
- **Owner:** `uvalek`
- **Repository:** `ideadorcontenidodrarturo`
- **Branch:** `main`
- **Build path:** `/` (déjalo así)

Si es la primera vez que conectas GitHub, EasyPanel te va a pedir autorización.
Acéptala solo para ese repositorio.

## 3. Elegir cómo se construye

Pestaña **Build**:

- **Build Method:** **Dockerfile**
- **File:** `Dockerfile`

Este es el paso que se salta todo el mundo. Si dejas el método automático
(Nixpacks), EasyPanel intenta adivinar cómo arrancar la app y se equivoca,
porque este servicio necesita un solo proceso y sin `--workers`.

## 4. Las variables de entorno

Pestaña **Environment**. Pega esto y **rellena lo que está vacío**:

```
SUPABASE_URL=https://krechsbybhebtjopekum.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
ADMIN_EMAILS=alekhammer13@gmail.com
ORIGENES_PERMITIDOS=https://adlek.com.mx
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini
PERPLEXITY_API_KEY=
PERPLEXITY_MODEL=sonar-pro
REPLICATE_API_TOKEN=
REPLICATE_MODELO=minimax/image-01
MAX_GENERACIONES_ACTIVAS=2
MAX_IDEAS=10
MAX_CONCURRENCIA_LLM=4
REPLICATE_TIMEOUT_SEG=180
REPLICATE_MAX_INTENTOS=3
BUCKET_IMAGENES=contenido-imagenes
```

`REPLICATE_API_TOKEN` puede quedarse vacío: todo funciona menos el botón de
generar imágenes, que aparecerá deshabilitado con su aviso.

Guarda.

### Qué hace cada una, por si alguna vez hay que tocarla

| Variable | Para qué |
|---|---|
| `ADMIN_EMAILS` | Quién puede pedir generaciones. Separados por coma |
| `ORIGENES_PERMITIDOS` | Desde qué sitios se acepta una llamada |
| `OPENAI_MODEL` | El modelo. Se cambia aquí, sin tocar código |
| `MAX_GENERACIONES_ACTIVAS` | Cuántos temas a la vez. Súbelo solo si hace falta: cada uno cuesta |
| `MAX_IDEAS` | Tope de ideas por tema |
| `MAX_CONCURRENCIA_LLM` | Llamadas simultáneas. Si ves errores de "rate limit", bájalo a 2 |

## 5. El puerto

Pestaña **Domains** → **Add Domain**:

- **Host:** `api-contenido.adlek.com.mx`
- **Port:** `8000`  ← este número importa
- **HTTPS:** activado

Si el puerto no es 8000, el dominio responde error 502 aunque la app esté
perfectamente viva.

## 6. Apuntar el dominio

Donde administres el DNS de `adlek.com.mx`, agrega:

| Tipo | Nombre | Valor |
|---|---|---|
| A | `api-contenido` | La IP de tu VPS |

Tarda entre unos minutos y un par de horas en propagarse.

## 7. Desplegar

Botón **Deploy**. La primera construcción tarda 2 a 4 minutos.

---

## Comprobar que quedó bien

Abre en el navegador:

```
https://api-contenido.adlek.com.mx/salud
```

Tiene que responder:

```json
{"ok": true, "modelo": "gpt-5-mini", "investigacion": true,
 "imagenes": false, "generaciones_en_curso": 0}
```

Y en **Logs** deben aparecer estas dos líneas:

```
INFO  api     API arriba. Modelo gpt-5-mini · investigación sí · imágenes no configuradas
INFO  worker  Worker en marcha
```

**Si sale "Worker en marcha" pero no aparece nada más**, está bien: el worker
espera callado hasta que haya trabajo.

---

## Si algo no funciona

| Lo que ves | Qué suele ser |
|---|---|
| Error 502 en el dominio | El puerto no es 8000, o la app no arrancó. Mira los Logs |
| El navegador no encuentra el dominio | El DNS todavía no propaga. Espera |
| `El worker no pudo conectarse a Supabase` en los logs | Falta o está mal `SUPABASE_URL` o `SUPABASE_SERVICE_ROLE_KEY` |
| `"investigacion": false` en `/salud` | Falta `PERPLEXITY_API_KEY`. Todo lo demás sigue funcionando |
| El panel dice "Failed to fetch" | `ORIGENES_PERMITIDOS` no incluye el sitio desde el que llamas |
| Generaciones que se quedan en "pendiente" | El worker no está corriendo. Revisa los Logs y redespliega |
| El build falla | Revisa que **Build Method** sea Dockerfile y no Nixpacks |

---

## Actualizar

Cuando haya cambios (un prompt editado, por ejemplo):

```bash
git add -A
git commit -m "Ajusta el prompt de ganchos"
git push
```

Y en EasyPanel, **Deploy**. Si activaste *Auto Deploy* en la pestaña Source, se
despliega solo con cada push.

Los prompts viven dentro de la imagen, así que un cambio en ellos **exige
redesplegar** para que tenga efecto.

---

## Después del despliegue

Falta una variable más, pero en Vercel, no aquí: el panel necesita saber a
dónde llamar.

Proyecto **adlek-admin** en Vercel → Settings → Environment Variables:

```
NEXT_PUBLIC_API_CONTENIDO=https://api-contenido.adlek.com.mx
```

Y redesplegar el panel para que la tome.
