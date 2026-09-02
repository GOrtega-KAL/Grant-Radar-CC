# Favoritos compartidos — endpoint

El panel de Grant-Radar es una página estática en GitHub Pages: no tiene dónde
guardar nada que vean varias personas. Este Worker es ese sitio, y es
deliberadamente lo más pequeño posible.

**Es temporal por diseño.** Cuando la herramienta se aloje en el servidor
propio —previsto para dentro de unos meses (AGENTS.md 59.9)—, migrar consiste
en cambiar `FAVORITES_ENDPOINT` en `index.html` y apuntar al servidor. Nada más
del panel depende de Cloudflare.

## Qué hace

| Método | Ruta | Efecto |
|---|---|---|
| `GET` | `/favoritos` | `{ items: [...], count, limit }` |
| `PUT` | `/favoritos?key=<stable_key>` | alta, o edición de la nota si ya existe |
| `DELETE` | `/favoritos?key=<stable_key>` | baja (idempotente) |

Un favorito se identifica por su **`stable_key`**, el campo que el backend
publica en `convocatorias.json` desde el 02/09/2026. El `id` del JSON **no
sirve**: es un contador posicional y cambia entre publicaciones.

Cuerpo de un `PUT`:

```json
{ "title": "…", "source": "BDNS", "url": "https://…",
  "added_by": "Guillermo", "note": "pedir presupuesto a CIRCE" }
```

`added_by` y `added_at` se fijan en el alta y no se tocan al editar la nota:
cambiar un comentario no cambia de dueño el favorito.

## Despliegue

Hace falta una cuenta de Cloudflare (el plan gratuito sobra) y `wrangler`:

```bash
npm install -g wrangler
wrangler login

cd "scripts/favoritos-worker"
wrangler kv namespace create FAVORITOS
#  → copia el `id` que imprime dentro de wrangler.toml

wrangler deploy
#  → imprime la URL: https://grant-radar-favoritos.<subdominio>.workers.dev
```

Con esa URL, en `index.html`:

```js
const FAVORITES_ENDPOINT = 'https://grant-radar-favoritos.<subdominio>.workers.dev/favoritos';
```

Si se deja vacía, el panel funciona igual pero guarda los favoritos en el
`localStorage` de cada navegador: no se comparten. Es también lo que hace por
su cuenta si el Worker no responde.

## Comprobación

### Antes de desplegar, sin cuenta y sin red

```bash
node probar-worker.mjs      # o: npm test
```

Ejercita el Worker entero con un KV de mentira: CORS y preflight, alta, edición,
baja idempotente, los topes de 200 favoritos / 200 caracteres de nota / 40 de
nombre, y el caso de `wrangler.toml` sin rellenar. **25 comprobaciones, ninguna
red.** Node 18+ trae `Request` y `Response` nativos, así que el Worker corre tal
cual.

Merece la pena pasarlo antes de cada `wrangler deploy`: es donde están los
errores que uno comete escribiendo esto, y verlos en producción cuesta mucho
más.

La suite de Python **no ejecuta este archivo** y no va a hacerlo: es JavaScript
que vive fuera de su alcance. Esta prueba tampoco entra en `unittest`; hay que
lanzarla a mano, y conviene saberlo en vez de suponer que algo la vigila.

### Después de desplegar, contra el endpoint real

Sustituye `$URL` por la del Worker. La cabecera `Origin` es obligatoria: sin
ella el Worker responde `403`, que es justamente lo que debe hacer.

```bash
URL="https://grant-radar-favoritos.<subdominio>.workers.dev/favoritos"
ORG="Origin: https://gortega-kal.github.io"
KEY="BDNS|bdns_id|919481"

# 1. alta  → 201 con el registro
curl -sS -X PUT "$URL?key=$(python -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$KEY")" \
     -H "$ORG" -H 'Content-Type: application/json' \
     -d '{"title":"Prueba","source":"BDNS","url":"https://example.test","added_by":"Guillermo","note":"prueba"}'

# 2. listado → aparece en `items`
curl -sS "$URL" -H "$ORG"

# 3. baja → { "deleted": … }, y el listado vuelve a quedarse sin él
curl -sS -X DELETE "$URL?key=$(python -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$KEY")" -H "$ORG"
curl -sS "$URL" -H "$ORG"
```

Una cuarta, que comprueba el badén de origen:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$URL" -H 'Origin: https://example.com'
# 403
```

**Y la que de verdad demuestra que la lista es compartida**, que ninguna de las
anteriores prueba: abrir el panel en **dos navegadores distintos**, marcar una
convocatoria en uno y verla aparecer en el otro al recuperar el foco de la
ventana.

## Lo que este Worker no es

La URL viaja en el código de una página pública, en un repositorio público. La
comprobación de origen y los topes (200 favoritos, nota de 200 caracteres,
nombre de 40, clave de 250) son **badenes contra el paso casual, no
seguridad**: quien quiera saltárselos solo necesita `curl`. Para una lista
interna de convocatorias sin datos personales es una compensación razonable, y
conviene que quede escrito antes de que alguien la dé por segura.

Tampoco hay autenticación ni control de quién borra qué: cualquiera que abra el
panel puede quitar el favorito de otro. Es una lista de trabajo de un
departamento pequeño, y esa era la forma más simple que funciona.
