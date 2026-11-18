"""Testa a galeria vazia: (1) abrir com zero cortes; (2) 'Apagar todos' do último streamer.
O navegador só 'enxerga' um streamer FALSO (a resposta de /api/cortes é filtrada): cortes reais não mudam."""
import json
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.util import RAIZ  # noqa: E402

CORTES = RAIZ / "cortes"
FAKE = CORTES / "teste_vazio"
erros = []


def estado(pg):
    return {"lateral": pg.locator("#filtros .chip").all_inner_texts(),
            "info": pg.locator("#info").inner_text(),
            "feed": pg.locator("#feed").inner_text()[:60]}


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)

    # (1) zero cortes desde o início
    pg = b.new_page(viewport={"width": 1366, "height": 768})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pg.route("**/api/cortes", lambda r: r.fulfill(status=200, content_type="application/json", body="[]"))
    pg.goto("http://127.0.0.1:8000/galeria", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    print("(1) abrir vazio:", estado(pg))
    pg.close()

    # (2) apagar todos do único streamer visível
    FAKE.mkdir(exist_ok=True)
    origem = next(p for p in CORTES.glob("*/*.mp4") if p.with_suffix(".json").exists() and p.parent.name != "teste_vazio")
    for i in range(2):
        base = f"20000101_00000{i}_x2.0"
        shutil.copy(origem, FAKE / f"{base}.mp4")
        (FAKE / f"{base}.json").write_text(json.dumps({"canal": "teste_vazio", "inicio": time.time() - i}), encoding="utf-8")

    def so_falso(route):
        resp = route.fetch()
        dados = [c for c in resp.json() if c["canal"] == "teste_vazio"]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(dados))

    pg = b.new_page(viewport={"width": 1366, "height": 768})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pg.route("**/api/cortes", so_falso)
    pg.goto("http://127.0.0.1:8000/galeria#teste_vazio", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    print("(2) antes:", estado(pg))
    pg.locator("#apagar-todos").click()
    pg.locator("#at-confirmar").click()
    pg.wait_for_function("!document.querySelector('#at-fundo').classList.contains('aberto')", timeout=60000)
    pg.wait_for_timeout(1500)
    print("(2) depois:", estado(pg))
    pg.screenshot(path="tmp/galeria_vazia.png")
    b.close()

print("pasta falsa removida pelo 'apagar todos'?", not FAKE.exists())
shutil.rmtree(FAKE, ignore_errors=True)
print("\n".join(erros) or "sem erros de JS")
