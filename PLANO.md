# PLANO: cortes automáticos de lives (lançamento do GTA 6)

> Arquivo de referência do projeto. Sempre que retomar o trabalho, comece por aqui.
> Última atualização: 17/11/2026

---

## 0. Status (atualize conforme avança)

| # | Etapa | Status |
|---|-------|--------|
| 1 | Ambiente: FFmpeg 9.0.2, Streamlink 8.6.3, venv com faster-whisper/opencv, QuickSync testado, benchmark do Whisper feito | ✅ pronto |
| 2 | Gravador em segmentos (buffer de 10 min) | ✅ testado no kick.com/dona (720p60) |
| 3a | Chat Twitch (IRC) + detector de picos | 🟨 código pronto, não testado ao vivo |
| 3b | Chat Kick (Chrome invisível via Playwright) | ✅ funcionando no kick.com/dona (ver 5.0: a Kick abandonou o Pusher) |
| 3c | Chat YouTube (chat-downloader) | 🟨 código pronto, não testado |
| 4 | Cortador (junta segmentos do pico) | ✅ |
| 5 | Calibração da webcam por streamer | ✅ **automática** desde 18/11 (`app/webcam.py`): detecta em cada corte e acompanha mudanças de posição; calibração manual continua disponível |
| 6 | Editor vertical + legenda (Whisper) | ✅ corte manual em **32 s** (juntar 6,6 s + whisper 11,7 s + render QSV 8,1 s) |
| 7 | Fila de processamento + aviso no Discord | 🟨 fila ✅; Discord sem webhook ainda |
| 7b | Painel ao vivo em `http://localhost:8000` | ✅ no ar (gráfico, fila, cortes com player, botão "Cortar agora") |
| 7c | Painel: adicionar live por URL, parar/iniciar/remover, ajustes de sensibilidade ao vivo (com atalhos), calibração da webcam arrastando um retângulo | ✅ canais agora ficam em `canais.yaml` (gerenciado pelo painel) |
| 8 | Teste de estabilidade de madrugada | 🟨 o usuário deixou o `INICIAR.bat` rodando no Gabepeixe ao sair (17/11 ~16h30) |
| 9 | **Onda 1: acesso pela NZ (18/11, 08:00 de Brasília)** | ⬜ pendente |
| 10 | Onda 2: lançamento oficial BR (19/11, 00:00 de Brasília) | ⬜ pendente |

### ▶ Retomar em 18/11 de manhã (checklist)
1. Ver o log da noite (`logs\2026-11-17.log` e `2026-11-18.log`): quedas/reinícios, "gravação travada", erros na fila.
2. Conferir os cortes da noite em Vídeos: legenda sincronizada, crédito até o fim, aviso "⚠ live sem som".
3. ~07:30: o usuário fecha as abas do Chrome e o VS Code (a RAM chegou a 91%), liga Coringa/Gabepeixe/Yuri22 e calibra as webcams.
4. Confirmar o **chat do Yuri22 no YouTube** quando ele entrar ao vivo (o leitor novo só foi testado na Lofi Girl).
5. Ideia que ficou para depois: acesso ao painel **fora do Wi-Fi de casa** (ex.: Tailscale), que o usuário achou útil para quando sair.

> **18/11 ~08:40: projeto migrado para outra máquina** (`C:\GTA6\cortes-automaticos-lives`): AMD Ryzen 5 4600G (6 núcleos/12 threads), Radeon integrada, 12 GB de RAM, ~40 GB livres no C:. Python 3.12.10, FFmpeg 9.0.2 e Streamlink 8.6.3 reinstalados via winget, `.venv` recriado. Sem QuickSync: o encoder agora testa `h264_qsv` e depois **`h264_amf`** (AMD), com fallback `libx264` (escolhido aqui: `amf`). Whisper com até 6 threads. O botão 📱 Celular passa a usar o IP do **Tailscale** (100.x) quando ele estiver instalado, para funcionar fora do Wi-Fi de casa. **Tailscale instalado e logado (PC `100.127.41.6` + celular)**; a janela do QR mostra se está em modo Tailscale ou Wi-Fi. Firewall: regra "Painel de cortes (Tailscale)" (TCP 8000, só de 100.64.0.0/10) precisa ser criada como administrador, se o celular não abrir.
> **18/11 ~09:20, bug na galeria pelo celular:** com ~25 cortes, os mais antigos ficavam "indisponíveis" (o celular tem limite de players de vídeo ao mesmo tempo, e cada card criava um). Agora o vídeo só recebe o `src` quando está a até ~2 telas de distância (`ligarPlayer`/`soltarPlayer` em `galeria.html`); os outros soltam o player. Testado em emulação do Pixel 7: 2–3 players ativos, o último corte toca. Também: `Range` além do fim do arquivo agora responde 416.
> **18/11 ~09:30:** (1) Galeria: o feed era refeito com `innerHTML = ""` a cada mudança na lista, o que pausava o vídeo e perdia a rolagem. Agora atualiza **no lugar** (só insere/remove cards), compensa a rolagem pelo card visível e, se um vídeo estiver tocando, cortes novos só entram pelo botão "▲ N cortes novos". (2) **Vigia de disco** (`app/disco.py`, `geral.disco_minimo_gb: 8`): a cada 30 s mede o espaço livre; abaixo do limite, **pausa todos os canais** (sem mudar `ativo` no canais.yaml) e o painel e a galeria mostram uma faixa vermelha + título "⛔ DISCO CHEIO". Ao liberar espaço, a faixa fica verde com o botão **Retomar monitoramento** (`POST /api/disco/retomar`). Iniciar canal com o disco cheio dá erro. Disco livre também aparece no topo do painel.
>
> **18/11 ~12:15: Capa para o TikTok** (`app/capa.py`, seção `capa:` do config). Todo vídeo marcado ⭐ Postar ganha na hora, na pasta `postar/`: `<canal>_<base>.jpg` (quadro mais nítido antes do pico, desfocado atrás do texto + frase em Impact + selo com a reação do chat + "CANAL • GTA 6") e `<canal>_<base>.mp4`, o corte com a capa nos **3 primeiros quadros** (0,1 s; recodificado a 8 Mbps, ~5 s por vídeo com AMF). No TikTok: Capa → arrastar até o início. O texto sai de uma heurística local, gratuita e offline (frase com !/? perto do pico, sem enchimentos tipo "mano"), e pode ser trocado no card (↻ Refazer, `POST /api/capa`). Uma thread confere a lista a cada 10 s: refaz a capa se o corte for ajustado ou revertido, e apaga quando ele sai da lista ou é apagado. Texto melhor que a heurística: dá para usar IA (ex.: API gratuita do Gemini), mas depende de o usuário criar uma chave.

> **18/11 ~14:25: Detecção automática da webcam** (`app/webcam.py`, seção `webcam:` do config). Motivo: o alanzoka mudou a câmera de lugar no meio da live e vários cortes saíram com o crop errado. Em **cada corte**, 8 frames do próprio trecho passam por: (1) detector de rosto YuNet (`modelos/rosto/`, OpenCV): o rosto que fica parado no mesmo lugar na maioria dos frames é o do streamer (rostos do jogo mudam de lugar); (2) mapa de **linhas paradas** (a moldura da webcam não se mexe, a gameplay sim) + contraste de movimento (quarto parado dentro, gameplay mudando fora); (3) testa os retângulos formados por essas linhas/borda da tela em volta do rosto. Se a posição detectada diferir da calibração (IoU < 0,6) com confiança ≥ 0,62 (≥ 0,72 se o canal estava "só gameplay"), o corte usa a nova posição e ela vira a calibração do canal. Custo ~2,7 s por corte. Ajustes/refazer de cortes antigos também detectam (no trecho deles), sem mexer na calibração atual. Painel: botão **🎯 Detectar automaticamente** na calibração (últimos ~3 min do buffer) e caixa "detectar sozinho em cada corte" por canal ("Streamer sem webcam" desliga). Testes: alanzoka/davyjones/gabepeixe ao vivo, IoU 0,96–1,00 com a calibração manual; webcam espelhada para o outro lado: 0,98–0,99; tela sem webcam: nada detectado (correto); fim a fim no alanzoka com calibração errada de propósito: corte saiu certo e `canais.yaml` foi corrigido.

Legenda: ⬜ pendente · 🟨 em andamento · ✅ pronto · ❌ bloqueado

---

## 1. Objetivo

Acompanhar lives da **Twitch, Kick e YouTube** em tempo real e, quando o chat explodir, gerar sozinho um corte de ~30 s com:
- formato vertical 1080×1920 (Reels / TikTok / Shorts);
- rosto do streamer em cima e gameplay embaixo;
- legenda grande, palavra por palavra, em português;
- aviso no Discord a cada corte novo.

A ideia é postar em **minutos** depois do lance, e não horas depois da live acabar.

---

## 2. Correções sobre o vídeo do Instagram

- É **GTA 6**, não GTA V. Lançamento em **19/11/2026** (PS5 e Xbox Series X|S), liberado à meia-noite no horário de Brasília. Os streamers grandes vão entrar ao vivo nesse horário.
- "Clador" é "clipador". "Bota oar" é "bota a IA". Foi erro de transcrição.
- "Numa noite" é otimista. Dá pra ter uma versão funcionando numa noite. Deixar confiável leva mais um dia de ajustes.

### ⚠️ Prazo antecipado: acesso pela Nova Zelândia
Alguns streamers brasileiros trocam a região do console para a **Nova Zelândia**. Lá o jogo libera à meia-noite do dia 19 no horário local (NZDT, UTC+13), o que dá **quarta-feira, 18/11, às 08:00 de Brasília**. A conta bate: 00:00 NZDT = 11:00 UTC = 08:00 BRT.

Consequências:
- **O primeiro prazo real é 18/11 às 08:00**, e não 19/11 à meia-noite. Isso dá uma noite de trabalho, não dois dias.
- São **duas ondas**: (1) 18/11 às 08:00, com poucos streamers jogando antes de todo mundo, o que deixa os cortes muito valiosos; (2) 19/11 às 00:00, no lançamento oficial no Brasil, com todo mundo.
- A onda 1 vira o **ensaio geral de verdade**. O que der errado de manhã é corrigido durante o dia para a onda 2.
- Risco: a Rockstar ou as lojas podem bloquear o truque da região, ou o streamer pode atrasar. Ter canais reserva.

---

## 3. Sua máquina e o que isso muda

| Item | Valor | Consequência |
|------|-------|--------------|
| CPU | Intel i5-8265U (notebook, 4 núcleos / 8 threads) | Whisper e encode de vídeo são o gargalo. |
| GPU | Intel UHD 620 (sem NVIDIA) | Sem CUDA. **Mas tem Intel QuickSync** (`h264_qsv`), que codifica vídeo pelo chip gráfico, bem mais rápido que pela CPU. |
| RAM | 8 GB | Usar modelo Whisper `small` (ou `base`) em `int8`. Nada de `medium`/`large`. |
| Disco D: | ~970 GB livres | Sem problema. Mesmo assim o buffer é apagado continuamente. |
| Python | 3.12.10 ✅ | OK |
| FFmpeg | ❌ não instalado | Instalar (etapa 1). |
| Streamlink | ❌ não instalado | Instalar (etapa 1). |

**Decisões tomadas por causa do hardware:**
1. **No máximo 2 streamers ao mesmo tempo.** Gravar é barato, mas cada corte precisa de Whisper + encode. Os cortes entram numa **fila única** e são processados um de cada vez, para o notebook não travar.
2. **Whisper `small` int8 na CPU**, com `beam_size=1` e VAD (pula silêncio). Para 30 s de áudio, a estimativa é de 15 a 40 s. Se ficar lento, cair para `base`.
3. **Encode por QuickSync (`h264_qsv`)**, com fallback automático para `libx264 -preset veryfast`.
4. **Saída em 30 fps** (metade do trabalho de 60 fps, e as redes sociais comprimem pra isso de qualquer jeito).
5. **Gravar em 720p60** em vez de 1080p60. O rosto e a gameplay ficam bons no vertical, e o consumo de internet cai (≈3–4 GB/h por streamer em vez de ≈6). Configurável.
6. Notebook **na tomada, sem suspender e sem hibernar** durante a live.

**Tempo estimado por corte:** ~1 min do pico até o arquivo pronto (espera o segmento fechar, depois Whisper, depois render). O Whisper `small` levou ~10 s para 40 s de áudio, então o gargalo deve ser o render.

---

## 4. Arquitetura

```
                ┌──────────────┐   segmentos .ts de 10 s (nome = hora real)
 Twitch ──────► │  GRAVADOR    │ ─────────────► buffer/<canal>/seg_20261119_001230.ts
 (vídeo)        │ streamlink → │                (apaga o que tem mais de 10 min)
                │ ffmpeg -c copy│
                └──────────────┘
                ┌──────────────┐   pico às 00:12:47
 Twitch ──────► │ CHAT + DETEC.│ ──────────────┐
 (IRC anônimo)  │ conta msgs/5s│               ▼
                └──────────────┘        ┌──────────────┐
                                        │  FILA (1 por │
                                        │   vez)       │
                                        └──────┬───────┘
                                               ▼
                 ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐
                 │ CORTADOR│→ │ WHISPER  │→ │ EDITOR    │→ │ DISCORD  │
                 │ junta   │  │ palavras │  │ vertical +│  │ webhook  │
                 │ segmen. │  │ + tempos │  │ legenda   │  │          │
                 └─────────┘  └──────────┘  └───────────┘  └──────────┘
                                                  ▼
                                    cortes/<canal>/20261119_001222_score87.mp4
                                    cortes/<canal>/20261119_001222_score87.json
```

Um único comando sobe tudo: `python main.py` (lê `config.yaml`, abre uma thread de gravador + uma de chat por canal e um worker da fila).

### Estrutura de pastas

```
D:\GTA6\
├── PLANO.md              ← este arquivo
├── CLAUDE.md             ← instruções pro Claude Code
├── config.yaml           ← canais, sensibilidade, layout, webhook
├── requirements.txt
├── main.py               ← orquestra tudo
├── calibrar.py           ← tira print da live pra marcar a webcam
├── testar_corte.py       ← gera um corte manual (pra testar layout/legenda)
├── app\
│   ├── gravador.py
│   ├── chat.py
│   ├── detector.py
│   ├── cortador.py
│   ├── transcricao.py
│   ├── legenda_ass.py
│   ├── editor.py
│   ├── notificador.py
│   └── fila.py
├── buffer\<canal>\       ← segmentos temporários (auto-limpeza)
├── cortes\<canal>\       ← RESULTADO FINAL
├── calibracao\           ← prints usados para marcar a webcam
└── logs\
```

---

## 5. Detalhes técnicos por módulo

### 5.0 Multiplataforma (Twitch, Kick, YouTube)

O sistema é o mesmo para as três plataformas. Só mudam **de onde vem o vídeo** e **como ler o chat**. Cada canal no `config.yaml` tem um campo `plataforma`.

| | Twitch | Kick | YouTube |
|---|---|---|---|
| **Vídeo** | Streamlink, plugin `twitch` ✅ | Streamlink, plugin `kick` ✅ (testado em 17/11: encontra os canais) | Streamlink, plugin `youtube` ✅ (URL `youtube.com/@canal/live` ou `/channel/<ID>/live`) |
| **Chat** | IRC anônimo (`justinfan`) | WebSocket do Pusher que o próprio site usa: pega o `chatroom.id` em `kick.com/api/v2/channels/<canal>` e assina `chatrooms.<id>.v2`, evento `App\Events\ChatMessageEvent` | Biblioteca `chat-downloader` (lê o chat ao vivo sem login nem chave de API) |
| **Hora da mensagem** | hora de chegada | `created_at` da mensagem | `timestamp` da mensagem (chega em lotes a cada 1–5 s, então a hora da chegada não serve) |
| **Emotes** | texto puro (`KEKW`) | vêm como `[emote:37226:KEKW]`, então converter para o nome | emojis (😂, `:face-with-tears-of-joy:`) contam como reação |
| **Atraso típico da live** | 2–6 s (low latency) | 3–8 s | 5–30 s (depende do modo de latência do streamer) |
| **Risco** | baixo, é estável | médio: API não oficial, protegida por Cloudflare, e a chave do Pusher já mudou antes | médio: o YouTube muda coisas com frequência; manter `chat-downloader` e `streamlink` atualizados |

> ⚠️ **ATUALIZAÇÃO 17/11, sobre o chat da Kick:** a Kick **abandonou o Pusher**. Agora o chat usa um servidor **Centrifugo** em `wss://realtime.us-east-1.platform.kick.com/connection/websocket`, com um token JWT de visitante (`guest:<uuid>`, que expira em 45 min) gerado pelo JavaScript do site. Não existe nenhuma requisição visível que entregue esse token. Os canais assinados continuam iguais: `chatrooms.<id>.v2`, evento `App\Events\ChatMessageEvent`.
> **Solução adotada:** `app/chat/kick.py` abre `kick.com/<canal>` num **Chrome headless** (Playwright, `channel="chrome"`, usando o Chrome já instalado), bloqueia vídeo, imagens, fontes e CSS, e escuta os frames do WebSocket `realtime`. Não precisa de `chatroom_id` nem de chave. Reabre a página se ficar 5 min sem mensagens, e a cada 3 h por manutenção.
> Custo: um processo do Chrome por canal da Kick (~150–300 MB de RAM).

**Pontos de atenção:**
- **Sincronia por plataforma:** como o atraso varia, cada canal tem um `offset_seg` no config para empurrar a janela do corte. Começa em 0 e é ajustado olhando os primeiros cortes.
- **Sensibilidade por plataforma:** o chat do YouTube costuma ser mais lento, e o da Kick tem muito spam de emote. Cada canal pode sobrescrever `multiplicador`, `minimo_absoluto` e `min_usuarios_unicos`.
- **Kick sem acesso à API:** se a Cloudflare bloquear a consulta do `chatroom.id`, o plano B é colocar o ID manualmente no config. Você abre `https://kick.com/api/v2/channels/<canal>` no navegador e me passa o número em `"chatroom":{"id": ...}`. Plano C: a lib `curl_cffi`, que imita um navegador.
- **Código:** `app/chat/twitch.py`, `app/chat/kick.py`, `app/chat/youtube.py`. Os três entregam `(hora, usuario, texto_normalizado)` para o mesmo detector.
- **Hardware:** com 3 plataformas aumenta a vontade de monitorar mais canais. O limite continua sendo **~3 canais gravando ao mesmo tempo** (internet ~15–20 Mbps em 720p) e **uma fila única** de processamento. Na fila, um corte com pico relativo maior (pontuação ÷ base) passa na frente.

**Canais citados (17/11):**
| Streamer | Plataforma | URL | Situação |
|---|---|---|---|
| Gabepeixe | Kick | `kick.com/gabepeixe` | canal existe, estava offline |
| LOUD Coringa | Kick | `kick.com/coringa` ou `kick.com/loud_coringa`? | os dois existem; **confirmar qual é o certo** |
| Yuri22 | YouTube | `youtube.com/@yuri22` deu 404 | **precisa do link certo do canal** |

### 5.1 Gravador
```
streamlink --twitch-disable-ads --twitch-low-latency --stdout twitch.tv/<canal> 720p60,720p,best
  | ffmpeg -i pipe:0 -c copy -f segment -segment_time 10 -reset_timestamps 1
           -strftime 1 buffer/<canal>/seg_%Y%m%d_%H%M%S.ts
```
- `-c copy`: não recodifica, então quase não usa CPU.
- O **nome do arquivo é a hora real** em que o segmento começou. Isso deixa o casamento com o horário do chat trivial.
- Os segmentos cortam em keyframes (a Twitch manda um a cada ~2 s), então duram ~10–12 s.
- **Reconexão:** se o streamlink cair ou a live estiver offline, tenta de novo a cada 30–60 s, para sempre.
- **Limpeza:** uma thread apaga segmentos com mais de `buffer_minutos` (padrão 10), **exceto** os que estão reservados por um corte na fila.
- `--twitch-disable-ads` pula os intervalos comerciais (vira um "buraco" no vídeo, e não o anúncio).
- **Vigia de travamento (17/11):** a rede mudou (`ERR_NETWORK_CHANGED`), o streamlink ficou vivo mas mudo, e 4 cortes saíram com 0,1 s. Agora, se não chegar dado novo em `geral.gravacao_travada_seg` (40 s), a gravação é derrubada e reaberta. Testado congelando o processo (`tools/simular_travamento.py`): reagiu em 40 s e reconectou 5 s depois.
- **Árvore de processos:** no Windows, `streamlink.exe` é só um lançador, e o trabalho é feito por um `python.exe` filho. Encerrar só o lançador deixava o filho órfão. Agora usa `taskkill /T /F` (`matar_arvore`).
- **Trava no corte:** se o trecho juntado tiver menos de 50% da duração esperada, o corte vira **erro** na fila ("gravação sem dados nesse trecho") em vez de gerar um vídeo vazio.

### 5.2 Chat (IRC anônimo, sem login, sem biblioteca extra)
- Conecta em `irc.chat.twitch.tv:6667`, `NICK justinfan<numero>`, `JOIN #<canal>`.
- Responde `PING` com `PONG` (senão a Twitch derruba).
- Cada mensagem vira `(hora_local, usuario, texto)`.
- Reconexão automática.

### 5.3 Detector de picos (melhorado em relação ao vídeo)
Contar só mensagens erra muito. O detector usa:
1. **Pontuação ponderada por mensagem:**
   - normal = 1;
   - reação forte (`KKKK`, `KEKW`, `LUL`, `OMEGALUL`, `MDS`, `PQP`, `CLIPA`, `CLIP`, `NOOO`, `??????`, `CARALHO`, `WTF`, `POG`) = 2–3 (lista no config);
   - **ignorar** comandos (`!sorteio`, `!pix`...) e bots (`nightbot`, `streamelements`, `moobot`...);
   - mensagens repetidas do mesmo usuário na janela contam 1 vez só (anti-spam).
2. **Usuários únicos** na janela de 5 s. Um pico exige pelo menos `min_usuarios_unicos` (ex.: 15). Isso mata spam de poucas pessoas.
3. **Linha de base = mediana** da pontuação das janelas dos últimos 5 min (a mediana resiste a picos antigos melhor que a média).
4. **Dispara** quando `pontuação ≥ multiplicador × base` (padrão 3×) **e** `pontuação ≥ minimo_absoluto`.
5. **Espera o pico parar de subir** (até 10 s) e usa o **momento máximo** como referência.
6. **Pausa de 60 s** entre cortes do mesmo canal.
6b. **Saudações e pedidos** (SALVE, OI, BOA NOITE, "MANDA UM SALVE", "LÊ MEU NOME"...; lista editável no painel) **valem 0** e não contam como pessoa reagindo. Se a mensagem também tiver reação ("SALVE KKKK"), conta normalmente. Se ≥ 50% das mensagens da janela forem saudação, o pico é **ignorado**, e o painel mostra "🚫 pico ignorado" com o motivo. Pedidos de música ("COLOCA...") **contam**, por decisão do usuário: a reação do streamer à música pode render corte.
7. **Filtro de sorteio:** se mais de 60% das mensagens da janela forem idênticas (ex.: todo mundo digitando `!participar`), não corta.

Cada corte salva um `.json` com pontuação, base, as 20 mensagens mais repetidas e uma **sugestão de título** (palavras mais frequentes do chat). Ajuda na hora de postar.

### 5.4 Cortador
- Janela: de **25 s antes até 5 s depois** do pico (configurável). O chat reage atrasado, então o lance aconteceu antes do pico.
- Espera o último segmento necessário fechar (~10–15 s depois do pico).
- Junta os segmentos com o concat demuxer do FFmpeg (`-c copy`) e depois apara exato no render final.
- Sobre a sincronia: a nossa gravação e os espectadores veem a live com atraso parecido, e o chat chega praticamente na hora. Por isso pico do chat menos 25 s cobre o lance. Se na prática os cortes começarem tarde ou cedo, ajustar `antes_seg` / `offset_seg` no config.

### 5.5 Calibração da webcam (a parte mais manual)
Cada streamer põe a câmera num lugar. Fluxo:
1. `python calibrar.py <canal>` grava 1 frame da live atual em `calibracao/<canal>.png`.
2. Abre uma janela onde **você arrasta um retângulo sobre a webcam** e aperta Enter (OpenCV `selectROI`).
   - Alternativa: **eu (Claude) abro o PNG, identifico a webcam e preencho as coordenadas**. Depois você confere numa prévia.
3. As coordenadas são salvas em **proporção** (0–1) no `config.yaml`, então funcionam em 720p ou 1080p.
4. Gera `calibracao/<canal>_preview.png` com o layout vertical final, pra conferir.

Se o streamer **não tiver webcam** ou ela sumir, use o layout `so_gameplay`: gameplay no centro e um fundo desfocado da própria gameplay em cima e embaixo.

### 5.6 Layout vertical (1080×1920)
```
┌────────────────┐
│  WEBCAM        │  1080×608  (crop da webcam, escala 16:9)
├────────────────┤ ← legenda fica perto daqui (ou no meio da gameplay)
│                │
│  GAMEPLAY      │  1080×1312 (crop central da tela, deslocamento X ajustável)
│                │
└────────────────┘
```
Filtro (exemplo com valores proporcionais já convertidos):
```
[0:v]crop=W_cam:H_cam:X_cam:Y_cam,scale=1080:608,setsar=1[cam];
[0:v]crop=ih*1080/1312:ih:X_game:0,scale=1080:1312,setsar=1[game];
[cam][game]vstack,fps=30,ass=legenda.ass[out]
```
- Se a webcam não for 16:9, aplica crop/pad para não distorcer o rosto.
- Pegadinha do Windows: o filtro `ass=` odeia caminhos com `C:\`. **Rodar o ffmpeg com a pasta de trabalho no diretório do corte e passar só o nome do arquivo.**

### 5.7 Transcrição e legenda
1. Extrai o áudio do corte (wav mono 16 kHz).
2. `faster-whisper` modelo `small`, `device="cpu"`, `compute_type="int8"`, `language="pt"`, `word_timestamps=True`, `vad_filter=True`, `beam_size=1`.
   - `initial_prompt` com vocabulário do contexto: "GTA 6, Vice City, Lucia, Jason, Rockstar..." para melhorar os nomes.
3. Gera `.ass`:
   - 2–3 palavras por vez, em **MAIÚSCULAS**, fonte grande (Arial Black, ~80 px), branca com contorno preto grosso;
   - a **palavra falada no momento fica amarela** (estilo dos cortes virais);
   - posição configurável: na divisa câmera/gameplay ou a ~70% da altura.
4. Primeira execução baixa o modelo (~500 MB), uma vez só.

**Benchmark real nesta máquina (17/11, 40 s de fala em PT-BR, CPU int8, beam 1):**
| Modelo | Carregar | Transcrever 40 s | Qualidade |
|---|---|---|---|
| `base` | 1,3 s | 7,4 s | errou "Caio", "Visse cítita", "clica" |
| `small` | ~3 s (36 s na 1ª vez, por causa do download) | **9,8 s** | melhor: "Caiu", "Vici City", "Tô" |

➡️ **Decisão: `small`**, carregado **uma vez** no início e mantido em memória pelo worker da fila.
⚠️ **Bug encontrado:** o PyAV instalado é incompatível com o `faster-whisper` 1.2.1 (`open() got an unexpected keyword argument 'metadata_errors'`). **Solução:** decodificar o áudio com o FFmpeg para um array numpy (float32, 16 kHz) e passar o array para o Whisper. Exemplo em `tools/benchmark_whisper.py`.
💡 O `initial_prompt` deve incluir "Vice City, chat, clipa, GTA 6" para corrigir "Vici City" e "clipe a".

### 5.7b Fala do streamer x fala do jogo (17/11)
- **Problema:** o áudio da live é um só (voz + jogo), e o Whisper legendava os personagens do GTA.
- **Tentativa descartada:** reconhecimento de voz por "impressão digital" (sherpa-onnx CAM++). No teste com o áudio real do Dona, falas do jogo ("Incoming!") ficaram com 0,95 de similaridade com o streamer, e falas do streamer com som do jogo por baixo ficaram com 0,04. Não é confiável. Desinstalado.
- **Solução adotada: idioma** (`app/idioma.py`). O GTA é dublado em inglês (com espanhol em Vice City), e o streamer BR fala português. Classifica cada trecho do Whisper por palavras típicas de PT/EN/ES e acentos. Frases curtas sem pista → `detect_language` pelo som (máx. 5 por corte). Na dúvida → streamer.
- **Bug encontrado:** com `language="pt"`, o Whisper às vezes **pula** falas em inglês. Solução: depois da transcrição, o VAD acha trechos com voz que ficaram sem palavras e eles são transcritos de novo com idioma automático (máx. 4 por corte).
- **Modos** (`legenda.falas_jogo`, por canal, no painel): `silencio` (padrão: fala do jogo menor, itálico, azul-claro, um pouco abaixo), `nunca` (só o streamer), `desligado` (tudo igual, como era antes).
- A transcrição salva no `.json` marca as falas do jogo como `[jogo: ...]`.
- Limitação: se o streamer falar inglês, aquilo vira "jogo"; se um personagem falar português, vira "streamer".
- **Orçamento de tempo:** as checagens extras (idioma pelo som + lacunas) têm limite de 10 s por corte (`legenda.tempo_max_extra_seg`), e só trechos de até 8 s são retranscritos. Motivo: com música tocando (Beyoncé), a transcrição subiu de ~10 s para 147 s antes desse limite.
- **Tradução das falas do jogo (inglês → português BR), offline:** modelo Argos Translate en→pb 1.9 (CTranslate2, ~78 MB) em `modelos/traducao_en_pb/`, usado direto com `ctranslate2` + `sentencepiece`, sem PyTorch (`app/traducao.py`). Traduz frase a frase (o modelo descartava a 2ª frase de "Hands up! Nobody move!"). Teste: 11 frases em 0,45 s. A fala do jogo é agrupada por frase inteira e trocada pela tradução; frases longas são divididas em partes de ~7 palavras com o tempo proporcional. Opção `legenda.traduzir_jogo` (checkbox no painel; só vale no modo "silencio"). O `.json` do corte guarda `falas_jogo: [{original, traducao}]`.

### 5.8 Render final
- `h264_qsv` (QuickSync) com bitrate ~4–5 Mbps. Se falhar, `libx264 -preset veryfast -crf 23`.
- Áudio AAC 128 kbps. `-movflags +faststart`.
- 30 s × ~4,5 Mbps ≈ 17 MB.

### 5.8b Corte exato (bug corrigido em 17/11, ~16h)
- **1ª tentativa (errada):** só `-ss` antes do `-i` em .ts de live cai segundos DEPOIS do ponto (sem índice; quadro-chave da Kick a cada ~4 s): a imagem começava 1,6–3,3 s depois do som.
- **2ª tentativa (introduziu outro bug):** `-ss` depois do `-i` corta na SAÍDA, mas os filtros (legenda `ass` + crédito) já tinham visto o relógio antigo. A legenda ficava adiantada em até 15 s e o crédito sumia antes do fim. Afetou 2 cortes (refeitos com `tools/refazer_cortes.py`).
- **Solução final (`editor.renderizar`):** `-ss (início − 15 s)` antes do `-i` (rápido), depois `trim=start=…:duration=…,setpts=PTS-STARTPTS` no vídeo e `atrim/asetpts` no áudio **dentro do filtro**. Vídeo, áudio, legenda e crédito começam juntos no 0 do corte. Testado com uma legenda-marcador em 10,0–11,0 s (`tools/teste_sincronia_legenda.py`) e o crédito do 1º ao último segundo, com início perto e longe do começo do arquivo.
- A legenda (Whisper) lê o áudio com `args_trecho` (`-ss` na saída, só áudio, sem filtros): defasagem medida 0,00 s em relação ao vídeo final (`tools/diagnostico_sincronia.py`).

### 5.9 Aviso no Discord
- Webhook: mensagem com canal, horário, pontuação, sugestão de título e caminho do arquivo.
- Upload do vídeo junto **só se couber no limite do Discord (~10 MB)**. Senão, opcionalmente gera uma versão leve de prévia (480p) só pra assistir no celular.

### 5.9b Ajustar o tempo de um corte pronto (17/11)
Decisões do usuário: sobra de **60 s**, o ajuste **substitui** o corte (com opção de **reverter**), edição numa **linha do tempo com prévia**, e **cortes novos têm prioridade** sobre ajustes.
- **Sobra:** depois de cada corte, uma thread espera `fim + 60 s + 12 s` e copia `[início − 60 s, fim + 60 s]` do buffer para `cortes/<canal>/_fontes/<base>.mp4` (remux com `-c copy`, quase sem CPU, ~70 MB). O `.json` ganha `fonte: {arquivo, inicio (epoch), duracao}`. Até lá, `sobra_pronta_em` alimenta a contagem regressiva na Galeria. **Não atrasa o corte.**
- **Ajuste:** `POST /api/editar {id, inicio, fim}` (segundos dentro da sobra; 3 s a 3 min) cria um item `tipo: "edicao"` na fila, processado depois dos cortes novos. Refaz legenda e tradução a partir da sobra e substitui o `.mp4`. Na **1ª** edição, guarda o original em `_originais/`. Usa a config atual do canal (ou `canal_cfg` salva no corte, se o canal foi removido).
- **Reverter:** `POST /api/reverter {id}` devolve o vídeo e o `.json` originais. Mantém a `fonte`, então dá para ajustar de novo.
- **Apagar** remove também a sobra e o original guardado.
- **Galeria:** botão "✂ Ajustar tempo" abre um editor com o vídeo original (horizontal), uma trilha com o trecho atual (tracejado), o pico (amarelo), o novo trecho (azul, com bordas arrastáveis), botões ±1 s/±5 s e "▶ Assistir trecho". A URL do vídeo leva `?v=<mtime>` para o navegador não mostrar a versão antiga do cache.
- Cortes feitos antes dessa função não têm sobra e não podem ser ajustados.

### 5.10b Painel ao vivo (`http://localhost:8000`)
Página leve, servida pelo próprio `main.py` (servidor HTTP embutido do Python, sem dependência extra), atualizada a cada ~2 s, **sem vídeo ao vivo**:
- **Cartão por canal:** plataforma, se está online ou offline, gravando ou não, msgs/5 s agora, linha de base e status do chat (conectado ou com erro).
- **Gráfico do ritmo do chat** (últimos 10 min) com a linha do limite de pico e marcadores nos picos que viraram corte.
- **Lista de picos:** horário, pontuação, mensagens mais repetidas e sugestão de título.
- **Fila:** cada corte com o status atual (aguardando segmento → cortando → transcrevendo → montando → pronto/erro) e o tempo de cada etapa.
- **Últimos cortes:** player para assistir no painel, e botão para abrir a pasta.
- **Botão "Cortar agora"** por canal: corte manual dos últimos 30 s.
- Código em `app/painel.py` + `app/painel.html`. A API é `/api/estado` (JSON). Os vídeos são servidos de `cortes/`.
- Só abre em `127.0.0.1` (não fica exposto na rede).

### 5.10 Fila
- Um worker só, processando um corte por vez (protege o notebook).
- Se a fila passar de N itens (ex.: 5), descarta os de menor pontuação, porque corte velho não serve pra nada.
- Logs em `logs/AAAA-MM-DD.log` com tudo: picos, cortes, erros, tempo de cada etapa.

---

## 6. `config.yaml` (modelo)

```yaml
geral:
  buffer_minutos: 10
  qualidade: "720p60,720p,best"
  max_fila: 5
  pasta_cortes: "cortes"

detector:
  janela_seg: 5
  base_minutos: 5
  multiplicador: 3.0
  minimo_absoluto: 25
  min_usuarios_unicos: 15
  pausa_entre_cortes_seg: 60
  palavras_peso:
    3: ["KKKK", "KEKW", "OMEGALUL", "CLIPA", "CLIP", "MDS", "PQP", "WTF", "CARALHO"]
    2: ["LUL", "NOOO", "POG", "???", "SOCORRO"]
  ignorar_usuarios: ["nightbot", "streamelements", "moobot", "wizebot"]

corte:
  antes_seg: 25
  depois_seg: 5

legenda:
  modelo: "small"        # base = mais rápido, small = melhor
  fonte: "Arial Black"
  tamanho: 80
  posicao_y: 0.40        # fração da altura (0.32 ≈ divisa câmera/gameplay)
  palavras_por_vez: 3

saida:
  fps: 30
  encoder: "auto"        # auto | qsv | x264

discord:
  webhook_url: ""        # VOCÊ precisa preencher (ver seção 8)

canais:
  - nome: "gabepeixe"
    plataforma: "kick"          # twitch | kick | youtube
    url: "https://kick.com/gabepeixe"
    ativo: true
    offset_seg: 0               # empurra a janela do corte (atraso da plataforma)
    detector: {multiplicador: 3.5}   # opcional: sobrescreve o padrão
    layout: "camera_gameplay"
    camera: {x: 0.74, y: 0.73, w: 0.25, h: 0.25}
    gameplay_offset_x: 0.5
  - nome: "yuri22"
    plataforma: "youtube"
    url: "https://www.youtube.com/<LINK_CORRETO>/live"
    ativo: true
    layout: "so_gameplay"
  - nome: "exemplo_twitch"
    plataforma: "twitch"
    url: "https://twitch.tv/exemplo_twitch"
    ativo: false
    layout: "camera_gameplay"   # ou "so_gameplay"
    camera: {x: 0.74, y: 0.73, w: 0.25, h: 0.25}   # proporções, vêm do calibrar.py
    gameplay_offset_x: 0.5      # 0 = esquerda, 0.5 = centro, 1 = direita
```

---

## 7. Cronograma

> Cronograma comprimido por causa do acesso antecipado pela Nova Zelândia (seção 2).
> **Prioridade é o MVP:** gravar, detectar, cortar, layout e legenda. Discord e enfeites só se sobrar tempo; sem eles, os cortes simplesmente caem em `cortes\`.

### 17/11, hoje (dia todo e noite): construir o MVP inteiro (etapas 1 a 6)
- Ordem do chat: **Kick primeiro** (Gabepeixe e Coringa são os principais), depois YouTube, depois Twitch.
- [ ] Instalar FFmpeg e Streamlink via `winget`; criar `.venv` e instalar `faster-whisper`, `pyyaml`, `requests`, `opencv-python`.
- [ ] Testar QuickSync e fazer o **benchmark do Whisper** (`small` e `base`) para decidir o modelo.
- [ ] Gravador + chat + detector + cortador funcionando numa live grande qualquer que esteja no ar.
- [ ] Editor vertical + legenda. Testar com `testar_corte.py` (corte manual) para não depender de pico.
- [ ] **Painel em localhost:8000** (depois que o MVP gerar o primeiro corte).
- [ ] Deixar **rodando de madrugada** em 1–2 lives grandes como teste de estabilidade (travou? vazou disco? reconectou?).
- **Pronto quando:** sai um `.mp4` vertical com legenda a partir de um pico real.

### 18/11, 06:30 a 07:45: preparação da onda 1 (Nova Zelândia)
- [ ] Ver o log da madrugada e corrigir o que quebrou.
- [ ] Confirmar quais streamers vão entrar às 08:00 (anúncios no Twitter/Instagram deles).
- [ ] Calibrar a webcam de quem já estiver ao vivo (eu calibro pelo print em ~2 min por canal).
- [ ] Quem ainda não tiver calibração começa com `so_gameplay` e é calibrado assim que entrar.
- [ ] Notebook na tomada, suspensão desligada, `main.py` rodando **antes das 07:45**.

### 18/11, 08:00 em diante: onda 1 = operação + ajuste ao vivo
- Revisar cada corte, postar os bons e descartar os ruins.
- Ajustar sensibilidade (`multiplicador`, `min_usuarios_unicos`) e janela (`antes_seg`) com base nos cortes reais.
- Recalibrar se o streamer mudar de cena.

### 18/11, tarde: consolidar (etapas 7 e 8)
- [ ] Corrigir os problemas vistos de manhã.
- [ ] Fila com descarte + aviso no Discord.
- [ ] Escolher os canais da onda 2 e calibrar.

### 18/11, 23:00 a 23:30: preparação da onda 2 (lançamento oficial BR)
- [ ] Reiniciar o notebook, fechar outros programas, conferir calibrações.
- [ ] `main.py` rodando antes da meia-noite.

### 19/11, 00:00 em diante: onda 2
- Mesma rotina: revisar e postar. A concorrência de clipadores vai ser bem maior, então velocidade importa.

---

## 8. O que só VOCÊ pode fazer

| # | Tarefa | Quando | Como |
|---|--------|--------|------|
| 1 | **Aprovar as instalações** | Etapa 1 | O `winget` pode abrir uma janela do Windows (UAC) pedindo permissão. Clique em "Sim". |
| 2 | **Escolher os streamers** (1 ou 2 principais + 1 reserva), de preferência **quem vai jogar pela Nova Zelândia às 08:00 de 18/11**. Já citados: Gabepeixe e Coringa (Kick), Yuri22 (YouTube). **Confirmar as URLs exatas** (ver 5.0). | Hoje, o quanto antes |
| 2b | **Liberar o acesso à API da Kick** quando o Claude Code pedir (ele consulta `kick.com/api/v2/channels/...` para achar a sala do chat). Se não liberar, abrir esse link no navegador e passar o `chatroom.id`. | Etapa 3b | Mande os nomes dos canais da Twitch. Prefira quem **autoriza cortes** (muitos têm programa oficial de clipadores). |
| 3 | **Criar o webhook do Discord** | Antes da etapa 7 | Num servidor seu: Configurações do servidor → Integrações → Webhooks → Novo webhook → escolha o canal → "Copiar URL do webhook". Cole a URL pra mim (ou direto no `config.yaml`). |
| 4 | **Conferir a calibração** da webcam | Etapa 5 | Olhar o `*_preview.png` e dizer se o rosto ficou certo. Se usar o modo manual, arrastar o retângulo. |
| 5 | **Desativar a suspensão** do notebook | 18/11 à noite | Eu posso fazer via `powercfg` com a sua permissão, ou você vai em Configurações → Sistema → Energia → "Nunca". |
| 6 | **Testar a internet** | Hoje | Em fast.com. Cada streamer em 720p60 consome ~5–8 Mbps contínuos. |
| 7 | **Revisar e postar** os cortes | Dia 19 | A IA erra às vezes. Nunca poste sem assistir. |
| 8 | **Contas nas redes** (TikTok / Reels / Shorts) prontas e logadas | Antes do dia 19 | Postagem automática fica fora do escopo por enquanto (risco de banimento e APIs burocráticas). |

---

## 9. Riscos e cuidados

- **Direitos autorais / permissão:** o conteúdo é do streamer. Corte de quem não autoriza pode levar strike ou derrubada de conta. A Rockstar também pode bloquear spoilers da história. Prefira momentos de reação e engraçados aos de spoiler pesado.
- **Notebook fraco:** se a fila crescer, desative um canal ou troque o Whisper para `base`.
- **Streamer muda a cena / esconde a câmera:** o corte sai com o crop errado. Recalibrar ou usar `so_gameplay`.
- **Twitch muda algo / streamlink quebra:** manter o streamlink atualizado (`winget upgrade streamlink`).
- **Picos falsos:** sorteios, raids, hosts e "spam de emote" combinado. O detector filtra parte; o resto você descarta na revisão.
- **Atraso real:** do lance ao arquivo pronto, ~1–2 min. Isso ainda é muito mais rápido que quem espera a live acabar.
- **Kick / YouTube:** o chat usa métodos não oficiais e pode quebrar sem aviso. Se o chat de um canal cair, o sistema continua gravando e registra o erro no log. Ainda dá pra tirar corte manual com `testar_corte.py`.

---

## 10. Ideias para depois (não fazer agora)
- Detecção automática do rosto (sem calibrar).
- Título e descrição gerados por IA a partir da transcrição.

---

## 10a. Feito em 17/11 à tarde (decisão do usuário: itens vermelhos menos Discord + grito/risada)
- **P1 Chat do YouTube:** o `chat-downloader` QUEBROU ("Unable to parse initial video data"). Reescrito em `app/chat/youtube.py` usando a API interna do YouTube (innertube: `/live_chat` → `get_live_chat` com `continuation`), só HTTP, sem navegador (um Chrome gastaria ~250 MB, e a RAM já estava em 85%). Testado na live da Lofi Girl: conecta e recebe mensagens.
- **P2 `INICIAR.bat`:** loop que reinicia o `main.py` 10 s após qualquer queda. `main.py` chama `SetThreadExecutionState` (o notebook não suspende enquanto roda; volta ao normal ao fechar) e mata streamlink/ffmpeg **órfãos** de execuções anteriores (psutil). Testado derrubando o processo: voltou sozinho e limpou os órfãos.
- **P3 Crédito:** estilo `Credito` no .ass (34 px, branco semitransparente, embaixo, o vídeo todo). Padrão = endereço do canal (`kick.com/coringa`); texto e liga/desliga por canal nos Ajustes (com prévia). `saida.credito` liga/desliga geral.
- **P4 Celular (sem Discord):** `painel.acesso_celular: true` → o servidor escuta em 0.0.0.0, mas **pedidos que não vêm do próprio notebook exigem a chave** (`painel_chave.txt`, no link/QR do botão 📱 Celular → vira cookie de 30 dias). Testado: sem chave/chave errada = 403; com a chave = 200. ⚠ O firewall do Windows pede permissão na 1ª vez.
- **P5 CPU/RAM no painel** (topo, verde/amarelo/vermelho). Diagnóstico: a RAM chegou a 91% com 1 canal, mas o **Chrome do usuário (abas) usava 2,6 GB**; o sistema de cortes usa ~0,7 GB (Whisper ~400 MB, Chrome invisível da Kick ~230 MB, streamlink ~70 MB).
- **Q1 Grito/risada (`app/audio.py`):** volume na faixa da voz (300–3500 Hz) a cada 0,25 s em cada segmento fechado. Base = mediana de 5 min. Média de 1 s ≥ base + 12 dB = candidato, que só vira corte se o chat reagir ≥ 1,5× o normal nos 15 s seguintes (evita cortar tiro/explosão). Corte centrado no grito (−15 s/+15 s), `gatilho: "audio"` (🔊 no painel e em Vídeos). Ajustável por canal.

## 10b. Propostas de melhorias (análise de 17/11, ~14h30)

### 🔴 Prioridade 1: antes das 08:00 de amanhã (risco de falhar no lançamento)
| # | Proposta | Por quê | Esforço |
|---|---|---|---|
| P1 | **Testar o chat do YouTube** (Yuri22) | É a única plataforma **nunca testada ao vivo**. Twitch (Coreano) e Kick (Dona) já foram testados. Se quebrar amanhã, o canal do Yuri22 grava mas não corta sozinho. | ~20 min com qualquer live do YouTube no ar |
| P2 | **Arquivo `INICIAR.bat`** (duplo clique): abre o sistema, **impede o notebook de suspender** enquanto roda e **reinicia sozinho se o programa fechar por erro** | Hoje o sistema roda dentro do Claude Code; se ele fechar, tudo para. Uma queda de madrugada passaria despercebida. | ~20 min |
| P3 | **Crédito do streamer no vídeo** (ex.: "kick.com/coringa" pequeno num canto) | Muitos streamers só aceitam cortes com crédito. Reduz risco de derrubada e ajuda a ser aceito como clipador. | ~20 min |
| P4 | **Aviso no celular** (Discord, já pronto: só falta a URL do webhook) **ou** abrir o painel no celular pela mesma rede Wi-Fi | Você não precisa ficar na frente do notebook para saber que saiu corte. | 5 min (Discord) / 20 min (celular) |
| P5 | **Medir o notebook com 3 canais ao mesmo tempo** (Coringa + Gabepeixe + Yuri22) e mostrar CPU/RAM no painel | Com 2 canais, a legenda já levou 35 s (antes 10 s). Cada canal da Kick abre um Chrome invisível (~250 MB). Melhor descobrir o limite hoje do que às 08:00. | ~30 min |

### 🟡 Prioridade 2: qualidade dos cortes (dá para fazer durante o dia 18)
| # | Proposta | Por quê |
|---|---|---|
| Q1 | **Segundo sinal de pico: o áudio do streamer** (grito/risada = volume que dispara) | Chats pequenos (ou o YouTube, que chega em lotes) perdem lances. Juntar "chat explodiu" + "streamer gritou" dá picos mais certeiros. |
| Q2 | **Juntar picos colados** num corte só (dois picos a 40 s de distância viram 1 corte maior, em vez de 1 corte + 1 descartado pela pausa) | Hoje a pausa de 60 s descarta o 2º pico. |
| Q3 | **Títulos melhores**: usar a frase mais repetida do chat + o trecho mais forte da fala, em vez de palavras soltas ("Laion Fazer Joga Amo") | Economiza tempo na hora de postar. |
| Q4 | **Aprender com as suas escolhas**: a proporção de vídeos que você marca "Postar" ou apaga, por streamer, vira uma sugestão de sensibilidade ("Dona: você apagou 80% → aumentar o limite?") | O sistema fica cada vez mais certeiro sem você mexer em números. |
| Q5 | ✅ **Webcam que acompanha o rosto** (detecção automática) — feito em 18/11, ver nota "Detecção automática da webcam" na seção 0 | |
| Q6 | **Gancho nos 2 primeiros segundos**: o título em letra grande no começo do vídeo | Melhora a retenção em Reels/TikTok/Shorts. |

### 🟢 Prioridade 3: fluxo de postagem (conforto)
| # | Proposta |
|---|---|
| F1 | Na lista **Postar**: botão **"Baixar todos"** (um .zip), **legenda pronta para copiar** (título + #hashtags + crédito) e status **"✓ Postado"** (com a rede: TikTok/Reels/Shorts) para separar o que já foi publicado. |
| F2 | **Atalhos de teclado** na página Vídeos: `P` = postar, `Del` = apagar, `E` = ajustar tempo, `N` = próximo novo. |
| F3 | **Limpeza automática** das "sobras" de ajuste com mais de 24 h (~70 MB cada; com 300 cortes são ~21 GB). |
| F4 | **Relatório do dia**: cortes por streamer, quantos foram postados ou apagados, horários de pico. |

### Observações técnicas (sem ação imediata)
- A sincronia entre chat e vídeo na Kick tem uma imprecisão de alguns segundos (a gravação chega em rajadas de ~6 s). O "−25 s antes do pico" absorve isso, e a função de **ajustar tempo** corrige casos pontuais.
- O tabela de status (seção 0) está desatualizada nas etapas 8–10. Atualizar depois da decisão sobre as propostas.

## 11. Comandos úteis

```powershell
# rodar tudo
.\.venv\Scripts\python main.py

# calibrar webcam de um canal
.\.venv\Scripts\python calibrar.py <canal>

# gerar corte manual dos últimos 30 s (teste)
.\.venv\Scripts\python testar_corte.py <canal>

# ver o log ao vivo
Get-Content logs\$(Get-Date -Format yyyy-MM-dd).log -Wait

# atualizar streamlink
winget upgrade streamlink
```
