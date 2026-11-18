"""Abre o painel num Chrome invisível, clica em Ajustes do 1º canal e mostra erros de JS + screenshot."""
import sys

from playwright.sync_api import sync_playwright

saida = sys.argv[1] if len(sys.argv) > 1 else "tmp/painel.png"
erros = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1400, "height": 1800})
    pg.on("pageerror", lambda e: erros.append(f"pageerror: {e}"))
    pg.on("console", lambda m: m.type == "error" and erros.append(f"console: {m.text}"))
    pg.goto("http://127.0.0.1:8000/", wait_until="networkidle")
    pg.wait_for_timeout(2500)
    botao = pg.locator('[data-a="ajustes"]').first
    botao.click()
    pg.wait_for_timeout(2500)
    aberto = pg.locator(".ajustes.aberto").count()
    filhos = pg.locator(".ajustes.aberto *").count()
    print("ajustes abertos:", aberto, "| elementos dentro:", filhos)
    if aberto:
        print("status preset:", pg.locator('[data-v="preset-status"]').first.inner_text())
        pg.locator('[data-acao="calibrar"]').first.click()
        pg.wait_for_timeout(2500)
        print("botões fechar visíveis:", pg.locator('[data-a="fechar"]').count())
    pg.screenshot(path=saida, full_page=False)
    b.close()
print("\n".join(erros) or "sem erros de JS")
