// probar-worker.mjs — prueba de humo del Worker, ANTES de desplegarlo.
//
//   node probar-worker.mjs      (o: npm test)
//
// La suite de Python no ejecuta este JavaScript y no va a hacerlo, así que sin
// esto la primera comprobación del Worker sería en producción. Node 18+ trae
// `Request` y `Response` nativos, de modo que el Worker corre aquí tal cual,
// con un KV de mentira: no hace falta desplegar nada ni tener cuenta.
//
// Lo que cubre y lo que no. Cubre el contrato entero —CORS, ciclo de alta,
// edición, baja, y los topes—, que es donde están los errores que uno comete
// escribiendo esto. **No** cubre que el despliegue funcione: eso solo lo dice
// `wrangler deploy` y, sobre todo, la prueba a dos navegadores del README, que
// es lo único que demuestra que la lista es de verdad compartida.

import worker from './worker.js';

const ORIGEN = 'https://gortega-kal.github.io';
const BASE = 'https://w.test/favoritos';
const CLAVE = 'BDNS|url|https://boletin.dpz.es/BOPZ/x.do?id=1&n=2';

// KV de mentira: lo justo que usa el Worker.
function kvFalso() {
  const datos = new Map();
  return {
    datos,
    async get(k) { const v = datos.get(k); return v === undefined ? null : JSON.parse(v); },
    async put(k, v) { datos.set(k, v); },
    async delete(k) { datos.delete(k); },
    async list({ prefix }) {
      return { keys: [...datos.keys()].filter(k => k.startsWith(prefix)).map(name => ({ name })) };
    },
  };
}

const env = { FAVORITOS: kvFalso() };
let fallos = 0;
function comprobar(nombre, condicion, detalle = '') {
  if (condicion) { console.log(`  ok    ${nombre}`); }
  else { console.log(`  FALLA ${nombre} ${detalle}`); fallos++; }
}

const pedir = (metodo, url, opciones = {}) => worker.fetch(new Request(url, {
  method: metodo,
  headers: { Origin: opciones.origen ?? ORIGEN, ...(opciones.body ? { 'Content-Type': 'application/json' } : {}) },
  ...(opciones.body ? { body: JSON.stringify(opciones.body) } : {}),
}), env);

console.log('CORS y metodos');
let r = await pedir('OPTIONS', BASE);
comprobar('preflight desde el origen permitido -> 204', r.status === 204, `(${r.status})`);
comprobar('cabecera Allow-Origin correcta',
  r.headers.get('Access-Control-Allow-Origin') === ORIGEN);
r = await pedir('OPTIONS', BASE, { origen: 'https://intruso.test' });
comprobar('preflight desde otro origen -> 403', r.status === 403, `(${r.status})`);
r = await pedir('GET', BASE, { origen: 'https://intruso.test' });
comprobar('GET desde otro origen -> 403', r.status === 403, `(${r.status})`);
r = await pedir('PATCH', BASE + '?key=' + encodeURIComponent(CLAVE));
comprobar('metodo no soportado -> 405', r.status === 405, `(${r.status})`);

console.log('\nCiclo de vida de un favorito');
r = await pedir('GET', BASE);
let cuerpo = await r.json();
comprobar('lista vacia al empezar', r.status === 200 && cuerpo.items.length === 0);

const url = BASE + '?key=' + encodeURIComponent(CLAVE);
r = await pedir('PUT', url, { body: { title: 'Edicto  con   espacios', source: 'BDNS', url: 'https://x.test', added_by: 'Guillermo', note: 'pedir presupuesto' } });
cuerpo = await r.json();
comprobar('alta -> 201', r.status === 201, `(${r.status})`);
comprobar('la clave con barras y & sobrevive entera', cuerpo.item.key === CLAVE,
  `\n        esperado: ${CLAVE}\n        recibido: ${cuerpo.item?.key}`);
comprobar('los espacios del titulo se normalizan', cuerpo.item.title === 'Edicto con espacios');

r = await pedir('GET', BASE);
cuerpo = await r.json();
comprobar('aparece en el listado', cuerpo.count === 1 && cuerpo.items[0].key === CLAVE);

const antes = cuerpo.items[0];
await new Promise(res => setTimeout(res, 5));
r = await pedir('PUT', url, { body: { title: 'otro', source: 'BDNS', added_by: 'Otra persona', note: 'nota editada' } });
cuerpo = await r.json();
comprobar('edicion -> 200, no 201', r.status === 200, `(${r.status})`);
comprobar('la nota cambia', cuerpo.item.note === 'nota editada');
comprobar('el dueno NO cambia al editar', cuerpo.item.added_by === 'Guillermo',
  `(${cuerpo.item.added_by})`);
comprobar('la fecha de alta NO cambia', cuerpo.item.added_at === antes.added_at);

r = await pedir('DELETE', url);
comprobar('baja -> 200', r.status === 200, `(${r.status})`);
r = await pedir('DELETE', url);
comprobar('borrar dos veces no es un error (idempotente)', r.status === 200);
r = await pedir('GET', BASE);
cuerpo = await r.json();
comprobar('la lista vuelve a estar vacia', cuerpo.count === 0);

console.log('\nBadenes');
r = await pedir('PUT', BASE + '?key=sinbarra');
comprobar('clave sin formato fuente|campo|valor -> 400', r.status === 400, `(${r.status})`);
r = await pedir('PUT', BASE);
comprobar('PUT sin clave -> 400', r.status === 400, `(${r.status})`);
r = await pedir('PUT', BASE + '?key=' + encodeURIComponent('A|b|' + 'x'.repeat(400)));
comprobar('clave demasiado larga -> 400', r.status === 400, `(${r.status})`);
r = await pedir('PUT', url, { body: { note: 'n'.repeat(500), added_by: 'g'.repeat(200) } });
cuerpo = await r.json();
comprobar('la nota se recorta a 200', cuerpo.item.note.length === 200, `(${cuerpo.item.note.length})`);
comprobar('el nombre se recorta a 40', cuerpo.item.added_by.length === 40, `(${cuerpo.item.added_by.length})`);
await pedir('DELETE', url);

// El tope de 200: se llena el KV a mano y se comprueba que rechaza el 201.
for (let i = 0; i < 200; i++) env.FAVORITOS.datos.set(`fav:X|id|${i}`, JSON.stringify({ key: `X|id|${i}` }));
r = await pedir('PUT', url, { body: { title: 'uno mas' } });
comprobar('con la lista llena, un alta nueva -> 409', r.status === 409, `(${r.status})`);
r = await pedir('PUT', BASE + '?key=' + encodeURIComponent('X|id|5'), { body: { note: 'editar si se puede' } });
comprobar('pero editar uno existente SI se puede con la lista llena', r.status === 200, `(${r.status})`);

console.log('\nSin KV enlazado (wrangler.toml mal rellenado)');
r = await worker.fetch(new Request(BASE, { headers: { Origin: ORIGEN } }), {});
comprobar('lo dice con un 500 claro en vez de reventar', r.status === 500, `(${r.status})`);
comprobar('y el error es identificable', (await r.json()).error === 'kv_not_bound');

console.log(fallos ? `\n${fallos} COMPROBACION(ES) FALLIDA(S)` : '\nTodo correcto.');
process.exit(fallos ? 1 : 0);
