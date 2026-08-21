# browser.py — sesión Chromium única compartida por las fuentes sin API
#
# Cuatro conectores (CDTI, IDAE, BOE/MITECO y BOA Aragón) necesitan JavaScript
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
