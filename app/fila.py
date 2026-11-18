"""Fila única de processamento: pico → juntar segmentos → Whisper → legenda → render → aviso.

Também cuida da EDIÇÃO de cortes prontos (ajustar início/fim):
- depois de cada corte, guarda em segundo plano uma "sobra" do vídeo original
  (geral.sobra_edicao_seg antes e depois) em cortes/<canal>/_fontes/<base>.mp4 (cópia, sem recodificar);
- um ajuste refaz o corte a partir dessa sobra e SUBSTITUI o vídeo, guardando o original
  em cortes/<canal>/_originais/ para poder reverter;
- cortes novos têm prioridade sobre ajustes.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from . import notificador, webcam
from .cortador import juntar_trecho
from .editor import renderizar
from .legenda_ass import gerar_ass, texto_credito
from .transcricao import extrair_audio, transcrever, traduzir_falas_jogo
from .util import FFMPEG, FFPROBE, RAIZ, config_canal, rodar

log = logging.getLogger("fila")


def duracao_video(caminho) -> float:
    try:
        r = rodar([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(caminho)],
                  timeout=30)
        return float(r.stdout.decode().strip() or 0)
    except (RuntimeError, ValueError):
        return 0.0


def silencio_inicial(audio, sr: int = 16000) -> float:
    """Segundos de silêncio ABSOLUTO no começo (live sem som: ex. streamer cortou o áudio por direitos
    autorais). Silêncio digital fica abaixo de −60 dB; fala baixa/pausa normal fica bem acima."""
    import numpy as np
    n = int(sr * 0.25)
    for k in range(len(audio) // n):
        bloco = audio[k * n:(k + 1) * n]
        if 20 * np.log10(float(np.sqrt(np.mean(bloco ** 2))) + 1e-9) > -60:
            return round(k * 0.25, 1)
    return round(len(audio) / sr, 1)


def marcar_transcricao(palavras: list[dict]) -> str:
    """"fala do streamer [jogo: fala do personagem] ..." """
    partes, quem_atual = [], "streamer"
    for p in palavras:
        q = p.get("quem", "streamer")
        if q != quem_atual:
            partes.append("[jogo:" if q == "jogo" else "]")
            quem_atual = q
        partes.append(p["palavra"])
    if quem_atual == "jogo":
        partes.append("]")
    return " ".join(partes).replace(" ]", "]")


def salvar_json(caminho: Path, dados: dict):
    tmp = caminho.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


class Fila(threading.Thread):
    def __init__(self, cfg: dict, canais: dict[str, dict], estado):
        super().__init__(daemon=True, name="fila")
        self.cfg = cfg
        self.canais = canais
        self.estado = estado
        self.cond = threading.Condition()
        self.itens: list[dict] = []
        self.parar = threading.Event()
        self._seq = 0
        self.lock_arquivos = threading.Lock()   # json/mp4 dos cortes (fila x sobra x painel)
        # chamado quando a webcam de um canal mudou de lugar (o gerenciador salva e mostra no painel)
        self.ao_mudar_webcam = None

    @property
    def pasta_cortes(self) -> Path:
        return RAIZ / self.cfg["geral"]["pasta_cortes"]

    # ------------------------------------------------------------------ entrada
    def adicionar(self, pico: dict):
        with self.cond:
            self._seq += 1
            item = {"id": self._seq, "tipo": "corte", "canal": pico["canal"], "hora_txt": pico["hora_txt"],
                    "relativo": pico["relativo"], "status": "aguardando", "etapas": {}, "pico": pico}
            self.itens.append(item)
            # descarta os piores se lotar (manuais têm prioridade; ajustes nunca são descartados)
            maximo = self.cfg["geral"]["max_fila"]
            pendentes = [i for i in self.itens if i["status"] == "aguardando" and i["tipo"] == "corte"]
            if len(pendentes) > maximo:
                pior = min(pendentes, key=lambda i: (i["pico"]["manual"], i["relativo"]))
                self.itens.remove(pior)
                log.warning("fila cheia: descartado pico de %s às %s", pior["canal"], pior["hora_txt"])
            self._publicar()
            self.cond.notify()

    def adicionar_edicao(self, corte_id: str, s: float, e: float):
        """Pede para refazer o corte usando o trecho [s, e] (segundos dentro da sobra)."""
        canal, base = corte_id.split("/")
        with self.cond:
            if any(i.get("corte_id") == corte_id and i["status"] not in ("pronto", "erro") for i in self.itens):
                raise ValueError("esse corte já está sendo ajustado; aguarde terminar")
            self._seq += 1
            self.itens.append({"id": self._seq, "tipo": "edicao", "canal": canal, "corte_id": corte_id,
                               "hora_txt": "ajuste", "relativo": 0, "status": "aguardando", "etapas": {},
                               "s": float(s), "e": float(e), "pico": {"manual": False}})
            self._publicar()
            self.cond.notify()

    def em_edicao(self) -> set[str]:
        with self.cond:
            return {i["corte_id"] for i in self.itens if i.get("tipo") == "edicao" and i["status"] not in ("pronto", "erro")}

    def _publicar(self):
        with self.estado.lock:
            self.estado.fila = [{k: v for k, v in i.items() if k != "pico"} for i in self.itens]

    def _status(self, item: dict, status: str):
        with self.cond:
            item["status"] = status
            self._publicar()

    def retomar_sobras(self):
        """Ao iniciar: cortes recentes cuja sobra não chegou a ser guardada (sistema reiniciado no meio)
        ganham a sobra de novo, enquanto o vídeo ainda está no buffer."""
        margem = float(self.cfg["geral"].get("sobra_edicao_seg", 60))
        limite_buffer = float(self.cfg["geral"]["buffer_minutos"]) * 60 - 30
        for js in self.pasta_cortes.glob("*/*.json"):
            try:
                meta = json.loads(js.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if meta.get("fonte") or not meta.get("sobra_pronta_em") or not meta.get("inicio"):
                continue
            a = meta["inicio"] - margem
            b = meta["inicio"] + meta.get("duracao", 30) + margem
            if time.time() - a > limite_buffer:
                continue  # o começo da sobra já saiu do buffer
            video = js.with_suffix(".mp4")
            buffer = RAIZ / self.cfg["geral"]["pasta_buffer"] / js.parent.name
            log.info("retomando sobra de %s/%s", js.parent.name, js.stem)
            threading.Thread(target=self._guardar_sobra, args=(buffer, video, a, b), daemon=True).start()

    # ------------------------------------------------------------------ loop
    def limpar_temporarios(self):
        """Ao iniciar: apaga pastas temporárias com mais de 30 min (cortes que falharam/foram interrompidos)."""
        pasta = RAIZ / "tmp"
        if not pasta.exists():
            return
        for p in pasta.iterdir():
            try:
                if p.is_dir() and time.time() - p.stat().st_mtime > 1800:
                    shutil.rmtree(p, ignore_errors=True)
                    log.info("temporário antigo removido: %s", p.name)
            except OSError:
                pass

    def run(self):
        try:
            self.limpar_temporarios()
            self.retomar_sobras()
        except Exception:  # noqa: BLE001
            log.exception("erro ao retomar sobras")
        while not self.parar.is_set():
            with self.cond:
                pend = [i for i in self.itens if i["status"] == "aguardando"]
                if not pend:
                    self.cond.wait(1.0)
                    continue
                # cortes novos antes de ajustes; entre cortes, manuais primeiro; depois o mais antigo
                item = min(pend, key=lambda i: (i["tipo"] == "edicao", not i["pico"]["manual"], i["id"]))
            try:
                if item["tipo"] == "edicao":
                    self._processar_edicao(item)
                else:
                    self._processar(item)
            except Exception as e:  # noqa: BLE001
                log.exception("erro processando %s de %s", item["tipo"], item["canal"])
                item["erro"] = str(e)[:300]
                self._status(item, "erro")
            finally:
                # mantém o item visível alguns segundos e remove
                threading.Timer(20, self._remover, args=(item,)).start()

    def _remover(self, item):
        with self.cond:
            if item in self.itens and item["status"] in ("pronto", "erro"):
                self.itens.remove(item)
                self._publicar()

    def _etapa(self, item, nome, t0):
        item["etapas"][nome] = round(time.time() - t0, 1)

    def _grafico(self, canal_nome: str, a: float, b: float) -> list[list[float]]:
        """Pedaço do gráfico do chat [(t, pontuação, limite)] entre a e b (1 ponto por segundo)."""
        with self.estado.lock:
            ch = self.estado.canais.get(canal_nome)
            hist = list(ch["historico"]) if ch else []
        return [[round(t, 1), round(p, 1), round(l, 1)] for t, p, l in hist if a <= t <= b]

    # ------------------------------------------------------------------ webcam automática
    def _ajustar_webcam(self, item, fonte: Path, inicio: float, dur: float, canal: dict, salvar: bool) -> dict:
        """Procura a webcam nos frames do PRÓPRIO trecho do corte. Se ela estiver em outro lugar (o streamer
        mudou a câmera de posição) ou o canal não tiver calibração, usa a posição detectada neste corte.
        Com salvar=True (corte novo), a nova posição também vira a calibração do canal."""
        c_cam = self.cfg.get("webcam") or {}
        if not c_cam.get("auto", True) or canal.get("webcam_auto") is False:
            return canal
        t = time.time()
        self._status(item, "achando webcam")
        try:
            r = webcam.detectar(webcam.frames_de_video(fonte, inicio, dur, int(c_cam.get("frames", 8))))
        except Exception as e:  # noqa: BLE001  (nunca impede o corte de sair)
            log.warning("detecção da webcam falhou (%s): %s", canal["nome"], e)
            return canal
        finally:
            self._etapa(item, "webcam", t)
        atual = canal.get("camera") if canal.get("layout") == "camera_gameplay" else None
        minimo = float(c_cam.get("confianca_minima", 0.62))
        if not atual:
            minimo = max(minimo, float(c_cam.get("confianca_sem_calibracao", 0.72)))
        if not r or r["confianca"] < minimo:
            if r:
                log.info("webcam de %s: detecção incerta (%.2f), mantendo a configuração", canal["nome"], r["confianca"])
            return canal
        novo = r["camera"]
        if atual and webcam.iou(atual, novo) >= 0.6:
            return canal   # mesma posição: mantém a calibração atual
        log.info("📷 webcam de %s %s: %s (confiança %.2f)", canal["nome"],
                 "MUDOU de lugar" if atual else "detectada", novo, r["confianca"])
        item["webcam_auto"] = novo
        if salvar and self.ao_mudar_webcam:
            try:
                self.ao_mudar_webcam(canal["nome"], novo)
            except Exception as e:  # noqa: BLE001
                log.warning("não consegui salvar a nova webcam de %s: %s", canal["nome"], e)
        return {**canal, "layout": "camera_gameplay", "camera": novo}

    # ------------------------------------------------------------------ legenda + render (comum)
    def _legendar_e_renderizar(self, item, fonte: Path, inicio: float, dur: float, canal: dict,
                               trabalho: Path, destino: Path, salvar_webcam: bool = False) -> tuple[list, dict]:
        c_leg = config_canal(self.cfg, canal, "legenda")
        c_saida = config_canal(self.cfg, canal, "saida")
        palavras, traducoes = [], {}
        item["mudo_inicio"] = 0.0
        trabalho.mkdir(parents=True, exist_ok=True)
        if c_leg.get("ativa", True):
            t = time.time()
            self._status(item, "transcrevendo")
            audio = extrair_audio(fonte, inicio, dur)
            item["mudo_inicio"] = silencio_inicial(audio)
            palavras = transcrever(audio, c_leg)
            if c_leg.get("traduzir_jogo", True) and c_leg.get("falas_jogo", "silencio") == "silencio":
                traducoes = traduzir_falas_jogo(palavras)
            self._etapa(item, "whisper", t)
        canal = self._ajustar_webcam(item, fonte, inicio, dur, canal, salvar_webcam)
        item["canal_render"] = canal
        credito = texto_credito(canal, self.cfg)
        tem_ass = bool(palavras or credito)
        if tem_ass:
            gerar_ass(palavras, trabalho / "legenda.ass", c_leg, traducoes=traducoes, credito=credito, duracao=dur)
        t = time.time()
        self._status(item, "montando vídeo")
        destino.parent.mkdir(parents=True, exist_ok=True)   # a pasta pode ter sido apagada no meio
        renderizar(fonte, inicio, dur, canal, c_saida, trabalho, destino, com_legenda=tem_ass)
        self._etapa(item, "render", t)
        return palavras, traducoes

    # ------------------------------------------------------------------ corte novo
    def _processar(self, item: dict):
        pico = item["pico"]
        canal = self.canais[pico["canal"]]
        c_corte = config_canal(self.cfg, canal, "corte")
        off = float(canal.get("offset_seg", 0))
        ini = pico["hora"] - c_corte["antes_seg"] + off
        fim = pico["hora"] + c_corte["depois_seg"] + off
        dur = fim - ini

        carimbo = datetime.fromtimestamp(ini).strftime("%Y%m%d_%H%M%S")
        rotulo = "manual" if pico["manual"] else f"x{pico['relativo']}"
        base_nome = f"{carimbo}_{rotulo}"
        pasta_saida = self.pasta_cortes / canal["nome"]
        pasta_saida.mkdir(parents=True, exist_ok=True)
        trabalho = RAIZ / "tmp" / f"{canal['nome']}_{base_nome}"
        pasta_buffer = RAIZ / self.cfg["geral"]["pasta_buffer"] / canal["nome"]

        try:
            self._processar_corte(item, pico, canal, c_corte, ini, fim, dur, base_nome, pasta_saida, trabalho, pasta_buffer)
        except Exception:
            shutil.rmtree(trabalho, ignore_errors=True)   # não deixa temporário abandonado
            raise

    def _processar_corte(self, item, pico, canal, c_corte, ini, fim, dur, base_nome, pasta_saida, trabalho, pasta_buffer):
        t = time.time()
        self._status(item, "aguardando segmentos")
        bruto, offset, t0 = juntar_trecho(pasta_buffer, ini, fim, trabalho, c_corte.get("max_espera_segmento_seg", 45))
        self._etapa(item, "juntar", t)
        # trava de segurança: se a gravação parou, não gera um "corte" vazio
        disponivel = duracao_video(bruto) - offset
        if disponivel < dur * 0.5:
            shutil.rmtree(trabalho, ignore_errors=True)
            raise RuntimeError(f"gravação sem dados nesse trecho (só {max(disponivel, 0):.1f}s de {dur:.0f}s). "
                               "A gravação travou ou a live caiu?")

        video = pasta_saida / f"{base_nome}.mp4"
        palavras, traducoes = self._legendar_e_renderizar(item, bruto, offset, dur, canal, trabalho, video,
                                                          salvar_webcam=True)
        canal = item.get("canal_render", canal)   # com a webcam que foi usada de fato

        texto = marcar_transcricao(palavras)
        margem = float(self.cfg["geral"].get("sobra_edicao_seg", 60))
        total = round(time.time() - pico["hora"], 1)
        meta = {**pico, "arquivo": str(video.relative_to(RAIZ)), "inicio": t0 + offset, "duracao": dur,
                "transcricao": texto, "falas_jogo": list(traducoes.values()), "etapas": item["etapas"],
                "pronto_em_seg": total, "sobra_pronta_em": fim + margem + 15,
                "mudo_inicio": item.get("mudo_inicio", 0.0),
                "webcam_auto": item.get("webcam_auto"),
                # gráfico do chat em volta do corte (completado depois, quando a sobra for guardada)
                "grafico": self._grafico(canal["nome"], ini - 90, fim + 60),
                "canal_cfg": {k: canal.get(k) for k in ("nome", "plataforma", "url", "layout", "camera",
                                                         "gameplay_offset_x", "legenda", "saida",
                                                         "credito_texto", "credito_ativo")}}
        with self.lock_arquivos:
            video.parent.mkdir(parents=True, exist_ok=True)
            salvar_json(video.with_suffix(".json"), meta)
        shutil.rmtree(trabalho, ignore_errors=True)
        log.info("✅ corte pronto: %s (%.0fs após o pico; etapas %s)", video.name, total, item["etapas"])
        self._status(item, "pronto")
        with self.estado.lock:
            self.estado.cortes.append({
                "canal": canal["nome"], "hora_txt": pico["hora_txt"], "relativo": pico["relativo"],
                "manual": pico["manual"], "titulo": pico["sugestao_titulo"], "transcricao": texto[:200],
                "url": "/" + str(video.relative_to(RAIZ)).replace("\\", "/"), "pronto_em_seg": total,
            })
        # sobra para edição: em segundo plano, sem atrasar a fila
        if margem > 0:
            threading.Thread(target=self._guardar_sobra, daemon=True, name=f"sobra-{base_nome}",
                             args=(pasta_buffer, video, ini - margem, fim + margem)).start()
        notificador.avisar(self.cfg.get("discord", {}).get("webhook_url", ""), meta, video)

    # ------------------------------------------------------------------ sobra para edição
    def _guardar_sobra(self, pasta_buffer: Path, video: Path, a: float, b: float):
        """Espera o fim da margem ser gravado e copia [a, b] para _fontes/<base>.mp4 (sem recodificar)."""
        espera = b + 12 - time.time()
        if espera > 0 and self.parar.wait(espera):
            return
        base = video.stem
        if not video.with_suffix(".json").exists():   # corte apagado enquanto esperava: nada a fazer
            return
        trabalho = RAIZ / "tmp" / f"sobra_{video.parent.name}_{base}"
        destino = video.parent / "_fontes" / f"{base}.mp4"
        try:
            bruto, _offset, t0 = juntar_trecho(pasta_buffer, a, b, trabalho, max_espera=30)
            destino.parent.mkdir(parents=True, exist_ok=True)
            rodar([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(bruto), "-map", "0:v:0",
                   "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", str(destino)], timeout=180)
            dur = duracao_video(destino)
            js = video.with_suffix(".json")
            with self.lock_arquivos:
                if not js.exists():   # corte apagado enquanto esperava
                    destino.unlink(missing_ok=True)
                    return
                meta = json.loads(js.read_text(encoding="utf-8"))
                meta["fonte"] = {"arquivo": str(destino.relative_to(RAIZ)), "inicio": t0, "duracao": dur}
                meta.pop("sobra_pronta_em", None)
                # agora o chat depois do corte já aconteceu: completa o gráfico
                graf = self._grafico(video.parent.name, a - 30, b)
                if len(graf) > len(meta.get("grafico") or []):
                    meta["grafico"] = graf
                salvar_json(js, meta)
            log.info("sobra para edição guardada: %s (%.0fs)", destino.name, dur)
        except Exception as e:  # noqa: BLE001
            log.warning("não consegui guardar a sobra de %s: %s", base, e)
        finally:
            shutil.rmtree(trabalho, ignore_errors=True)

    # ------------------------------------------------------------------ ajuste de tempo
    def _processar_edicao(self, item: dict):
        canal_nome, base = item["corte_id"].split("/")
        pasta = self.pasta_cortes / canal_nome
        video, js = pasta / f"{base}.mp4", pasta / f"{base}.json"
        meta = json.loads(js.read_text(encoding="utf-8"))
        fonte_info = meta.get("fonte")
        if not fonte_info:
            raise RuntimeError("esse corte não tem sobra guardada para edição")
        fonte = RAIZ / fonte_info["arquivo"]
        s, e = item["s"], item["e"]
        dur = e - s
        # usa a config atual do canal (ex.: webcam recalibrada); se o canal foi removido, a do momento do corte
        canal = self.canais.get(canal_nome) or meta.get("canal_cfg") or {"nome": canal_nome, "layout": "so_gameplay"}

        trabalho = RAIZ / "tmp" / f"edicao_{canal_nome}_{base}"
        novo = trabalho / "novo.mp4"
        palavras, traducoes = self._legendar_e_renderizar(item, fonte, s, dur, canal, trabalho, novo)

        with self.lock_arquivos:
            # guarda o ORIGINAL só na primeira edição (reverter volta sempre ao corte automático)
            orig = pasta / "_originais"
            if not (orig / f"{base}.mp4").exists():
                orig.mkdir(exist_ok=True)
                shutil.copy2(video, orig / f"{base}.mp4")
                shutil.copy2(js, orig / f"{base}.json")
            os.replace(novo, video)
            # relê: o .json pode ter mudado durante o ajuste (ex.: marcado como assistido)
            meta = json.loads(js.read_text(encoding="utf-8"))
            meta.update({
                "inicio": fonte_info["inicio"] + s, "duracao": dur,
                "transcricao": marcar_transcricao(palavras), "falas_jogo": list(traducoes.values()),
                "editado": True, "edicoes": int(meta.get("edicoes", 0)) + 1,
                "mudo_inicio": item.get("mudo_inicio", 0.0),
                "canal_cfg": {**(meta.get("canal_cfg") or {}),
                              **{k: item.get("canal_render", canal).get(k) for k in ("layout", "camera")}},
                "webcam_auto": item.get("webcam_auto"),
            })
            salvar_json(js, meta)
        shutil.rmtree(trabalho, ignore_errors=True)
        log.info("✂ corte ajustado: %s/%s (%.0fs, etapas %s)", canal_nome, base, dur, item["etapas"])
        self._status(item, "pronto")

    def reverter(self, corte_id: str):
        canal_nome, base = corte_id.split("/")
        pasta = self.pasta_cortes / canal_nome
        orig = pasta / "_originais"
        if not (orig / f"{base}.mp4").exists():
            raise ValueError("não há versão original guardada para esse corte")
        if corte_id in self.em_edicao():
            raise ValueError("esse corte está sendo ajustado agora; aguarde terminar")
        with self.lock_arquivos:
            atual = json.loads((pasta / f"{base}.json").read_text(encoding="utf-8"))
            original = json.loads((orig / f"{base}.json").read_text(encoding="utf-8"))
            if atual.get("fonte"):  # a sobra pode ter sido registrada depois do backup
                original["fonte"] = atual["fonte"]
            for k in ("assistido", "assistido_em", "postar", "postar_em", "grafico", "capa_texto"):  # valem para as duas versões
                if k in atual:
                    original[k] = atual[k]
            os.replace(orig / f"{base}.mp4", pasta / f"{base}.mp4")
            salvar_json(pasta / f"{base}.json", original)
            (orig / f"{base}.json").unlink(missing_ok=True)
        log.info("↩ corte revertido ao original: %s", corte_id)
