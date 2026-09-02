// worker.js — la lista de favoritos compartida de Grant-Radar.
//
// El panel (index.html) es una página estática servida por GitHub Pages: no
// tiene dónde guardar nada que vean varias personas. Esto es el sitio más
// pequeño posible para hacerlo, hasta que la herramienta viva en el servidor
// propio previsto para dentro de unos meses (AGENTS.md 59.9). El día que eso
// ocurra, migrar es cambiar una constante en el panel: FAVORITES_ENDPOINT.
//
// ───────────────────────────────────────────────────────────────────────────
// LA DECISIÓN DE DISEÑO QUE IMPORTA: una clave de KV por favorito.
//
// La alternativa obvia —un único JSON con la lista entera— pierde escrituras
// en silencio. Dos personas que marcan a la vez leen la misma lista, cada una
// añade lo suyo, y la segunda escritura pisa a la primera: uno de los dos
// favoritos desaparece y nadie se entera. Con una clave por favorito, alta y
// baja son escrituras independientes sobre claves distintas y el conflicto no
// llega a existir.
//
// ───────────────────────────────────────────────────────────────────────────
// SOBRE LA SEGURIDAD, dicho sin adornos.
//
// La URL de este Worker viaja en el código de una página pública, en un
// repositorio público. La comprobación de origen y los topes de abajo son
// badenes contra el paso casual, no seguridad: quien quiera saltárselos solo
// necesita curl. Para una lista interna de convocatorias sin datos personales
// es una compensación razonable, y conviene que quede escrito antes de que
// alguien la dé por segura. Si algún día hace falta cerrarla de verdad, el
// sitio es el servidor propio, no este archivo.
//
// ───────────────────────────────────────────────────────────────────────────
// LA CLAVE VA EN LA QUERY STRING, NO EN EL PATH.
//
// Un favorito se identifica por su `stable_key`, que el backend publica en
// convocatorias.json. Diez de las 77 fichas del producto resuelven su
// identidad por url, así que su clave contiene `https://…` con barras. Un
// `%2F` dentro de un path es terreno de normalización de proxies; una query
// string no se normaliza nunca. De ahí `?key=…` y no `/favoritos/…`.

const ALLOWED_ORIGINS = [
  'https://gortega-kal.github.io',
];

// Para probar el panel servido en local antes de publicarlo. Si molesta,
// basta con borrar esta constante y su uso en corsOrigin().
const LOCAL_ORIGIN = /^http:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?$/;

const MAX_FAVORITES = 200;    // Topes deliberadamente bajos: es la lista de
const MAX_KEY_LENGTH = 250;   // trabajo de un departamento, no un almacén.
const MAX_NOTE_LENGTH = 200;  // La clave más larga medida hoy son 129 chars.
const MAX_NAME_LENGTH = 40;
const MAX_TITLE_LENGTH = 300;
const MAX_URL_LENGTH = 500;
const MAX_BODY_BYTES = 4096;

const KV_PREFIX = 'fav:';

function corsOrigin(request) {
  const origin = request.headers.get('Origin') || '';
  if (ALLOWED_ORIGINS.includes(origin)) return origin;
  if (LOCAL_ORIGIN.test(origin)) return origin;
  return '';
}

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  };
}

function json(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      ...corsHeaders(origin),
    },
  });
}

function clean(value, maxLength) {
  if (value === null || value === undefined) return '';
  return String(value).replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

// Una stable_key es `fuente|campo|valor`. Comprobarlo no aporta seguridad,
// pero evita llenar el almacén de claves que ningún panel podría casar.
function validKey(key) {
  return Boolean(key) && key.length <= MAX_KEY_LENGTH && key.includes('|');
}

async function listFavorites(kv) {
  const listed = await kv.list({ prefix: KV_PREFIX });
  // Una lectura por favorito, en paralelo. Con el tope de 200 son 200 lecturas
  // por carga de página: mucho para un blob, nada para el plan gratuito de KV
  // (100.000 lecturas al día). La alternativa —guardar el registro en el
  // `metadata` de la clave y leerlo entero con un solo list()— ahorra las
  // lecturas pero topa en 1.024 bytes por clave, y un título largo con una
  // url larga se acerca demasiado a ese borde para lo que ahorra.
  const values = await Promise.all(
    listed.keys.map(entry => kv.get(entry.name, { type: 'json' }))
  );
  return values.filter(Boolean);
}

async function handlePut(request, kv, key, origin) {
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) {
    return json({ error: 'body_too_large' }, 413, origin);
  }
  let body;
  try {
    body = JSON.parse(raw || '{}');
  } catch (error) {
    return json({ error: 'invalid_json' }, 400, origin);
  }

  const existing = await kv.get(KV_PREFIX + key, { type: 'json' });
  if (!existing) {
    const listed = await kv.list({ prefix: KV_PREFIX });
    if (listed.keys.length >= MAX_FAVORITES) {
      return json({ error: 'too_many_favorites', limit: MAX_FAVORITES }, 409, origin);
    }
  }

  const record = {
    key,
    title: clean(body.title, MAX_TITLE_LENGTH),
    source: clean(body.source, 40),
    url: clean(body.url, MAX_URL_LENGTH),
    note: clean(body.note, MAX_NOTE_LENGTH),
    // Quién lo marcó y cuándo se conservan de la primera vez: editar la nota
    // no cambia de dueño un favorito.
    added_by: existing ? existing.added_by : clean(body.added_by, MAX_NAME_LENGTH),
    added_at: existing ? existing.added_at : new Date().toISOString(),
  };
  await kv.put(KV_PREFIX + key, JSON.stringify(record));
  return json({ item: record }, existing ? 200 : 201, origin);
}

export default {
  async fetch(request, env) {
    const origin = corsOrigin(request);
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      // Sin origen permitido no se contesta el preflight, y el navegador
      // bloquea por su cuenta la petición real.
      return new Response(null, {
        status: origin ? 204 : 403,
        headers: corsHeaders(origin),
      });
    }
    if (!origin) return json({ error: 'origin_not_allowed' }, 403, '');
    if (!url.pathname.startsWith('/favoritos')) {
      return json({ error: 'not_found' }, 404, origin);
    }
    if (!env.FAVORITOS) {
      return json({ error: 'kv_not_bound' }, 500, origin);
    }

    if (request.method === 'GET') {
      const items = await listFavorites(env.FAVORITOS);
      items.sort((a, b) => String(a.added_at).localeCompare(String(b.added_at)));
      return json({ items, count: items.length, limit: MAX_FAVORITES }, 200, origin);
    }

    const key = clean(url.searchParams.get('key'), MAX_KEY_LENGTH + 1);
    if (!validKey(key)) {
      return json({ error: 'invalid_key' }, 400, origin);
    }

    if (request.method === 'PUT') {
      return handlePut(request, env.FAVORITOS, key, origin);
    }
    if (request.method === 'DELETE') {
      await env.FAVORITOS.delete(KV_PREFIX + key);
      // Idempotente a propósito: borrar dos veces no es un error, y el panel
      // escribe de forma optimista sin saber qué había al otro lado.
      return json({ deleted: key }, 200, origin);
    }
    return json({ error: 'method_not_allowed' }, 405, origin);
  },
};
