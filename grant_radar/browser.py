# browser.py — sesión Chromium única compartida por las fuentes sin API
#
# Tres conectores (CDTI, IDAE y BOE/MITECO) necesitan JavaScript
# para ver su inventario, así que comparten una sola instancia de Chromium en
# vez de arrancar un navegador por petición. Se usa como gestor de contexto
# desde `run_pipeline()`; si Chromium no arranca, el objeto queda inservible a
# propósito (`html()` devuelve "") y cada fuente cae a su respaldo en vez de
# romper la ejecución entera.
#
# `html()` recuerda además qué ámbitos han respondido con un bloqueo de WAF
# para no insistir contra ellos durante el resto de la recopilación.
#
# `status()` existe para lo que `html()` no puede decir: esta devuelve "" tanto
# ante un 404 definitivo como ante un bloqueo o un fallo de red, y quien
# verifica un catálogo curado necesita distinguirlos (ver AGENTS.md, sección 44).
#
# Sin caché, sin reglas de negocio, sin Claude.

import logging
from urllib.parse import urlparse

from playwright.sync_api import (
    BrowserContext,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

log = logging.getLogger("grant_radar")


class PlaywrightBrowser:
    """Una única sesión Chromium compartida por todas las fuentes web."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self.context: BrowserContext | None = None
        self._blocked_scopes = set()

    def __enter__(self):
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self.context = self._browser.new_context(
                locale="es-ES",
                timezone_id="Europe/Madrid",
                viewport={"width": 1440, "height": 1000},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                ignore_https_errors=True,
            )
            self.context.set_default_timeout(15_000)
            self.context.set_default_navigation_timeout(30_000)
            log.info("Chromium iniciado para las fuentes sin API")
        except Exception as exc:
            log.error(f"No se pudo iniciar Chromium; se usarán los respaldos disponibles: {exc}")
            if self._playwright:
                self._playwright.stop()
            self._playwright = None
            self._browser = None
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.context:
            self.context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self.context = None

    def status(self, url: str) -> int | None:
        """
        Devuelve el código HTTP de `url`, o `None` si no se pudo determinar.

        Existe para distinguir lo que `html()` no puede: esa función devuelve
        "" tanto ante un 404 definitivo como ante un bloqueo de WAF o un fallo
        de red, y quien verifica un catálogo curado necesita saber cuál de las
        dos cosas ha pasado. Un `None` nunca debe interpretarse como error de
        la URL: significa que la comprobación no es concluyente.

        No participa en el registro de ámbitos bloqueados: comprobar una URL
        rota no debe cerrar el resto del dominio para la recopilación.
        """
        if not self.context:
            return None
        page = self.context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded")
            return response.status if response else None
        except Exception as exc:
            log.debug(f"No se pudo comprobar el estado de {url}: {exc}")
            return None
        finally:
            page.close()

    def html(self, url: str, wait_selector: str = "body") -> str:
        """Navega, espera al DOM renderizado y devuelve su HTML."""
        if not self.context:
            return ""
        parsed_url = urlparse(url)
        host = parsed_url.netloc.casefold()
        path = parsed_url.path.casefold().rstrip("/")
        block_scope = host
        if host.endswith("idae.es"):
            block_scope = (
                f"{host}:grant-details"
                if path.startswith("/ayudas-y-financiacion/")
                else ""
            )
        if block_scope and block_scope in self._blocked_scopes:
            return ""

        page = self.context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded")
            if response and response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
            # Para extraer HTML basta con que el nodo exista. Algunas vistas de
            # impresión mantienen body/html ocultos aunque el DOM esté completo.
            page.wait_for_selector(wait_selector, state="attached")
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except PlaywrightTimeoutError:
                # Varias webs públicas mantienen conexiones de analítica abiertas.
                pass
            html = page.content()
            page_title = page.title().casefold()
            visible_text = page.locator("body").inner_text(timeout=3_000).casefold()
            block_markers = (
                "the url you requested has been blocked",
                "access denied",
                "request rejected",
                "solicitud bloqueada",
            )
            if any(
                marker in page_title or marker in visible_text
                for marker in block_markers
            ):
                if block_scope:
                    self._blocked_scopes.add(block_scope)
                raise RuntimeError("respuesta de bloqueo/WAF")
            return html
        except Exception as exc:
            log.warning(f"Playwright no pudo cargar {url}: {exc}")
            return ""
        finally:
            page.close()


class VerifyingDocumentBrowser:
    """Chromium que **verifica** el TLS, y que solo arranca si hace falta.

    Existe por un caso concreto y medido el 02/09/2026 (punto 38 del backlog):
    `boletin.dpz.es` —el Boletín Oficial de la provincia de Zaragoza, la de la
    propia empresa— era el único host que fallaba de toda la recopilación, con
    `CERTIFICATE_VERIFY_FAILED` en dos edictos.

    **Qué se midió, y por qué el matiz importa más que el arreglo.** El
    servidor envía **un solo certificado**: el suyo, sin el intermedio que
    completa la cadena. `requests` —OpenSSL— no puede verificarlo y descarta el
    documento. Chromium sí puede, porque va a buscar el intermedio que falta
    por su cuenta. Comprobado con las dos configuraciones:

        ignore_https_errors=False  ->  HTTP 200
        ignore_https_errors=True   ->  HTTP 200

    Que la primera línea diga 200 es todo el argumento. **No se está ignorando
    un error de certificado: se está verificando bien uno que OpenSSL no sabe
    verificar.** Si solo funcionara con `True`, esto sería la misma relajación
    de TLS que el backlog descarta —y que contradice
    `_is_safe_public_https_url()`— con otro nombre, y no debería existir.

    Por eso esta clase **no reutiliza `PlaywrightBrowser`**, que arranca su
    contexto con `ignore_https_errors=True` para las fuentes que scrapea: usar
    aquel dejaría el código relajando la verificación aunque no le hiciera
    falta, y la frase de arriba dejaría de ser cierta. Aquí se verifica, y un
    certificado que de verdad no sea de fiar sigue cerrando la puerta.

    Arranca **perezosamente**: si ningún documento falla —lo normal—, Chromium
    no se inicia y no se paga nada. Si arrancar falla, se anota y no se
    reintenta en toda la ejecución.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None
        self.context: BrowserContext | None = None
        self._startup_failed = False
        self.rescued = 0

    def _ensure_started(self) -> bool:
        if self.context is not None:
            return True
        if self._startup_failed:
            return False
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self.context = self._browser.new_context(
                locale="es-ES",
                timezone_id="Europe/Madrid",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                # Deliberado, y es el punto entero de esta clase.
                ignore_https_errors=False,
            )
            self.context.set_default_timeout(15_000)
            self.context.set_default_navigation_timeout(30_000)
            log.info(
                "  Chromium arrancado para un segundo intento de descarga "
                "(cadena de certificados incompleta en el origen)"
            )
            return True
        except Exception as exc:
            log.warning(f"  No se pudo arrancar el navegador de respaldo: {exc}")
            self._startup_failed = True
            self.close()
            return False

    def status(self, url: str) -> int | None:
        if not self._ensure_started():
            return None
        page = self.context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded")
            return response.status if response else None
        except Exception as exc:
            log.debug(f"Respaldo: no se pudo comprobar {url}: {exc}")
            return None
        finally:
            page.close()

    def html(self, url: str) -> str:
        if not self._ensure_started():
            return ""
        page = self.context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded")
            html = page.content()
            self.rescued += 1
            return html
        except Exception as exc:
            log.debug(f"Respaldo: no se pudo cargar {url}: {exc}")
            return ""
        finally:
            page.close()

    def close(self) -> None:
        for recurso, cerrar in (
            (self.context, "close"), (self._browser, "close"), (self._playwright, "stop")
        ):
            if recurso is None:
                continue
            try:
                getattr(recurso, cerrar)()
            except Exception:
                pass
        self.context = None
        self._browser = None
        self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
