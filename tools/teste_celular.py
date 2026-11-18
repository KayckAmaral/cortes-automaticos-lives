"""Simula um celular na página Vídeos, filtro Postar com UM vídeo, rola até o botão Baixar e então
chega um corte NOVO de outro streamer (atualização automática a cada 8 s). A página não pode pular."""
import json
import urllib.request

from playwright.sync_api import sync_playwright

with urllib.request.urlopen("http://127.0.0.1:8000/api/cortes", timeout=30) as r:
    todos = json.load(r)
um = dict(todos[0], postar=True)
outro = dict(todos[1] if len(todos) > 1 else todos[0], id="fake/novo_corte", canal="outro", postar=False, versao=1)
estado = {"lista": [um]}

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(viewport={"width": 390, "height": 760}, device_scale_factor=2, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.route("**/api/cortes", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(estado["lista"])))
    pg.goto("http://127.0.0.1:8000/videos#postar", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    pg.evaluate("document.querySelector('.btn.baixar').scrollIntoView({block: 'center'})")
    pg.wait_for_timeout(1200)
    y0 = pg.evaluate("scrollY")
    print(f"rolei até o Baixar: scrollY={y0:.0f}")
    estado["lista"] = [outro, um]          # chega um corte novo de outro streamer
    pg.wait_for_timeout(9500)              # espera a atualização automática (8 s)
    y1 = pg.evaluate("scrollY")
    vis = pg.evaluate("(() => { const r = document.querySelector('.btn.baixar').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()")
    print(f"depois da atualização automática: scrollY={y1:.0f} | {'PULOU PARA O TOPO ❌' if y1 < y0 - 50 else 'ficou no lugar ✅'} | Baixar visível: {vis}")
    pg.screenshot(path="tmp/celular.png")
    b.close()
