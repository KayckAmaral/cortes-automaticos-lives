"""Mesmo teste do botão Baixar, mas no motor do Safari (WebKit) simulando um iPhone.
Compara a página como estava (encaixe ligado) com a correção (encaixe desligado no celular)."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
with urllib.request.urlopen("http://127.0.0.1:8000/api/cortes", timeout=30) as r:
    lista = json.load(r)[:n]
ENCAIXE_ANTIGO = "html { scroll-snap-type: y mandatory !important; } .corte { scroll-snap-align: start !important; scroll-snap-stop: always !important; }"

with sync_playwright() as p:
    iphone = p.devices["iPhone 13"]
    b = p.webkit.launch(headless=True)
    for rotulo, css in (("COMO ESTAVA (com encaixe)", ENCAIXE_ANTIGO), ("CORRIGIDO (sem encaixe)", "")):
        ctx = b.new_context(**iphone)
        pg = ctx.new_page()
        pg.route("**/api/cortes", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(lista)))
        pg.goto("http://127.0.0.1:8000/videos", wait_until="networkidle", timeout=30000)
        if css:
            pg.add_style_tag(content=css)
        pg.wait_for_timeout(1200)
        alvo = pg.evaluate("document.querySelector('.btn.baixar').getBoundingClientRect().bottom + scrollY - innerHeight + 20")
        pg.evaluate(f"scrollTo(0, {alvo})")
        pg.wait_for_timeout(1500)
        y = pg.evaluate("scrollY")
        vis = pg.evaluate("(() => { const r = document.querySelector('.btn.baixar').getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })()")
        print(f"[iPhone/Safari] {rotulo:26s} rolei até {alvo:.0f}px → ficou em {y:.0f}px | Baixar visível: {'SIM ✅' if vis else 'NÃO ❌ (puxou de volta)'}")
        ctx.close()
    b.close()
