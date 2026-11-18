"""Celular simulado: rola a página até o botão Baixar e confere se o navegador puxa de volta.
Compara a página como estava (encaixe ligado no celular) com a correção (encaixe desligado no celular).
Uso: python tools/teste_celular_toque.py [n_videos]"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
with urllib.request.urlopen("http://127.0.0.1:8000/api/cortes", timeout=30) as r:
    lista = json.load(r)[:n]
ENCAIXE_ANTIGO = "html { scroll-snap-type: y mandatory !important; } .corte { scroll-snap-align: start !important; scroll-snap-stop: always !important; }"

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    for rotulo, css in (("COMO ESTAVA (com encaixe)", ENCAIXE_ANTIGO), ("CORRIGIDO (sem encaixe no celular)", "")):
        ctx = b.new_context(viewport={"width": 390, "height": 760}, device_scale_factor=2, is_mobile=True, has_touch=True)
        pg = ctx.new_page()
        pg.route("**/api/cortes", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(lista)))
        pg.goto("http://127.0.0.1:8000/videos", wait_until="networkidle")
        if css:
            pg.add_style_tag(content=css)
        pg.wait_for_timeout(1200)
        alvo = pg.evaluate("document.querySelector('.btn.baixar').getBoundingClientRect().bottom + scrollY - innerHeight + 20")
        pg.evaluate(f"scrollTo(0, {alvo})")
        pg.wait_for_timeout(1500)
        y = pg.evaluate("scrollY")
        vis = pg.evaluate("(() => { const r = document.querySelector('.btn.baixar').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()")
        print(f"{rotulo:36s} rolei até {alvo:.0f}px → ficou em {y:.0f}px | botão Baixar visível: {'SIM ✅' if vis else 'NÃO ❌ (puxou de volta)'}")
        ctx.close()
    b.close()
