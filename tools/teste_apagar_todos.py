"""Testa a barra lateral e o 'Apagar todos' com um streamer FALSO (teste_apagar), sem tocar nos cortes reais."""
import json
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.util import RAIZ  # noqa: E402

CORTES = RAIZ / "cortes"
FAKE = CORTES / "teste_apagar"

# cria 3 cortes falsos copiando um real
origem = next(p for p in CORTES.glob("*/*.mp4") if p.with_suffix(".json").exists() and p.parent.name != "teste_apagar")
FAKE.mkdir(exist_ok=True)
meta = json.loads(origem.with_suffix(".json").read_text(encoding="utf-8"))
for i in range(3):
    base = f"20000101_00000{i}_x9.9"
    shutil.copy(origem, FAKE / f"{base}.mp4")
    m = {**meta, "canal": "teste_apagar", "arquivo": f"cortes/teste_apagar/{base}.mp4", "inicio": time.time() - 10 - i}
    m.pop("fonte", None)
    (FAKE / f"{base}.json").write_text(json.dumps(m), encoding="utf-8")
reais_antes = sorted(p.name for p in CORTES.glob("*/*.mp4") if p.parent.name != "teste_apagar")
print("cortes reais antes:", len(reais_antes))

erros = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1366, "height": 768})   # tela de notebook
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pg.goto("http://127.0.0.1:8000/galeria", wait_until="networkidle")
    pg.wait_for_timeout(2500)
    print("filtros na lateral:", pg.locator("#filtros .chip").all_inner_texts())
    print("botão 'apagar todos' em Todos?", pg.locator("#apagar-todos").count())
    # verifica se os botões do 1º corte cabem na tela
    pg.locator("#feed .corte").first.scroll_into_view_if_needed()
    pg.wait_for_timeout(800)
    bb = pg.locator("#feed .corte").first.locator(".btn.apagar").bounding_box()
    print(f"botão Apagar do 1º corte: y={bb['y']:.0f}..{bb['y'] + bb['height']:.0f} (altura da tela 768) →",
          "visível" if bb["y"] + bb["height"] <= 768 else "CORTADO")
    pg.screenshot(path="tmp/galeria_lateral.png")
    pg.locator('#filtros .chip[data-f="teste_apagar"]').click()
    pg.wait_for_timeout(800)
    print("botão:", pg.locator("#apagar-todos").inner_text())
    pg.locator("#apagar-todos").click()
    pg.wait_for_timeout(500)
    print("modal:", pg.locator("#at-desc").inner_text(), "|", pg.locator("#at-confirmar").inner_text())
    pg.screenshot(path="tmp/galeria_apagar_todos.png")
    pg.locator("#at-confirmar").click()
    pg.wait_for_function("!document.querySelector('#at-fundo').classList.contains('aberto') || "
                         "document.querySelector('#at-erro').textContent", timeout=60000)
    pg.wait_for_timeout(1500)
    print("erro no modal:", pg.locator("#at-erro").inner_text() or "-")
    print("aviso:", pg.locator("#aviso").inner_text())
    print("filtros depois:", pg.locator("#filtros .chip").all_inner_texts())
    b.close()

reais_depois = sorted(p.name for p in CORTES.glob("*/*.mp4") if p.parent.name != "teste_apagar")
print("pasta falsa ainda existe?", FAKE.exists(), "| cortes reais intactos?", reais_antes == reais_depois)
print("\n".join(erros) or "sem erros de JS")
