"""Separa fala do streamer (português) de fala do jogo (inglês/espanhol) pelo idioma do texto.

Por quê: a voz do streamer e o som do jogo vêm misturados num único áudio, e o reconhecimento
de voz por 'impressão digital' errou muito nos testes (o som do jogo está sempre por baixo).
Já o idioma é um sinal forte: o GTA é dublado em inglês (com falas em espanhol em Vice City),
e o streamer BR fala português. O Whisper, mesmo com language="pt", transcreve as falas em
inglês em inglês, então dá para classificar pelo próprio texto.
"""
from __future__ import annotations

import re

RE_PALAVRA = re.compile(r"[a-záàâãéêíóôõúüç']+", re.IGNORECASE)
RE_ACENTO_PT = re.compile(r"[ãõçâêô]|ção|ções", re.IGNORECASE)

PT = set("""
não nao é eh que de do da dos das eu você voce vc ele ela eles isso isto esse essa aqui ali lá
irmão irmao mano meu minha meus pra pro para com uma um uns no na nos nas vai vou vamo vamos tem
tô to tá ta tava mas se já ja então entao cara porra caralho nossa deus mds véi vei velho mermão
também tambem muito muita nada tudo agora ainda quando onde como porque por quê pq gente tipo
fazer faz fez foi era ser estou está esta estão nem só so mesmo assim aí ai olha calma bora
cadê cade rapaz moleque filho mãe mae pai óh oxe uai né ne kkk kkkk sim obrigado valeu
""".split())

EN = set("""
the you i i'm im it it's is are was were to and of that this what don't dont didn't can't cant
we me my your you're youre get got go going gonna let's lets here there right just know think
come want need with for from they them their he she his her him our us have has had do does did
will would should could be been being if then than but not all out up down over now okay well
fucking fuck shit man hey yeah yes oh god damn where who why how when about into on in at by
""".split())

# espanhol (Vice City) — conta como "jogo"
ES = set("""
el los las qué pero hombre está estás usted ustedes señor señora vámonos vamos hermano
chico mira oye ahora aquí nada muy bueno gracias por favor cabrón pinche
""".split())

AMBIGUAS = {"no", "a", "o", "e", "de", "se", "me", "te", "la", "man", "ok", "okay", "yeah", "sim", "vamos"}


def classificar_texto(texto: str) -> str:
    """'streamer' (português), 'jogo' (inglês/espanhol) ou 'incerto'."""
    palavras = [p.lower() for p in RE_PALAVRA.findall(texto)]
    if not palavras:
        return "incerto"
    pt = sum(1 for p in palavras if p in PT and p not in AMBIGUAS)
    en = sum(1 for p in palavras if p in EN and p not in AMBIGUAS)
    es = sum(1 for p in palavras if p in ES and p not in PT)
    pt += 2 * len(RE_ACENTO_PT.findall(texto))
    estrangeiro = en + es
    if estrangeiro > pt and estrangeiro >= 1:
        return "jogo"
    if pt > estrangeiro and pt >= 1:
        return "streamer"
    return "incerto"
