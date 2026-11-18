"""Testa 'assistido/novo': servidor com corte FALSO; tela com o POST interceptado (cortes reais não mudam)."""
import json
import shutil
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.util import RAIZ  # noqa: E402

API = "http://127.0.0.1:8000"
CORTES = RAIZ / "cortes"


def post(p, d):
    req = urllib.request.Request(API + p, data=json.dumps(d).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ---- 1) servidor, com corte falso
FAKE = CORTES / "teste_visto"
FAKE.mkdir(exist_ok=True)
origem = next(p for p in CORTES.glob("*/*.mp4") if p.with_suffix(".json").exists() and p.parent.name != "teste_visto")
shutil.copy(origem, FAKE / "20000101_000000_x1.0.mp4")
(FAKE / "20000101_000000_x1.0.json").write_text(json.dumps({"canal": "teste_visto", "inicio": time.time()}), encoding="utf-8")
print("marcar:", post("/api/assistido", {"id": "teste_visto/20000101_000000_x1.0", "assistido": True}),
      "→ json:", json.loads((FAKE / "20000101_000000_x1.0.json").read_text())["assistido"])
print("desmarcar:", post("/api/assistido", {"id": "teste_visto/20000101_000000_x1.0", "assistido": False}),
      "→ json:", json.loads((FAKE / "20000101_000000_x1.0.json").read_text())["assistido"])
try:
    post("/api/assistido", {"id": "../config", "assistido": True})
    print("id malicioso ACEITO (ruim)")
except urllib.error.HTTPError as e:
    print("id malicioso recusado:", json.load(e)["erro"])
shutil.rmtree(FAKE)

# ---- 2) tela (POST interceptado)
enviados, erros = [], []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    pg = b.new_page(viewport={"width": 1366, "height": 768})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))

    def interceptar(route):
        enviados.append(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body='{"ok": true}')

    pg.route("**/api/assistido", interceptar)
    pg.goto(API + "/galeria", wait_until="networkidle")
    pg.wait_for_timeout(2500)
    print("lateral:", pg.locator("#filtros .chip").all_inner_texts()[:2])
    pg.locator('#filtros .chip[data-f="novos"]').click()
    pg.wait_for_timeout(1200)
    primeiro = pg.locator("#feed .corte").first
    print("1º em Novos:", primeiro.get_attribute("data-id"), "| rótulo:", primeiro.locator("[data-visto]").inner_text())
    # leva o vídeo para perto do fim → deve marcar sozinho
    primeiro.locator("video").evaluate("v => { v.muted = true; v.currentTime = Math.max(0, v.duration - 2); v.play(); }")
    pg.wait_for_timeout(3500)
    print("após chegar ao fim → rótulo:", primeiro.locator("[data-visto]").inner_text(), "| enviado:", enviados[-1:] )
    print("continua na lista de Novos (até trocar de filtro)?", pg.locator(f'#feed .corte[data-id="{primeiro.get_attribute("data-id")}"]').count() == 1)
    print("contador Novos:", pg.locator('#filtros .chip[data-f="novos"] span').inner_text())
    pg.screenshot(path="tmp/galeria_novos.png")
    # clique no rótulo desmarca
    primeiro.locator("[data-visto]").click()
    pg.wait_for_timeout(600)
    print("após clique → rótulo:", primeiro.locator("[data-visto]").inner_text(), "| enviado:", enviados[-1:])
    b.close()
print("\n".join(erros) or "sem erros de JS")
