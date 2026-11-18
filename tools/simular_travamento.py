"""Congela o streamlink (como quando a rede cai) para testar o vigia da gravação.

Uso: python tools/simular_travamento.py
Congela o streamlink.exe E o python.exe filho dele (quem realmente baixa a live) e observa
por até 90 s se o sistema derruba a gravação travada e abre uma nova.
"""
import ctypes
import subprocess
import time

PROCESS_SUSPEND_RESUME = 0x0800


def processos():
    """[(pid, pai, nome)] via WMIC/PowerShell."""
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId);$($_.ParentProcessId);$($_.Name)\" }"],
                         capture_output=True, text=True).stdout
    res = []
    for l in out.strip().splitlines():
        try:
            pid, pai, nome = l.split(";", 2)
            res.append((int(pid), int(pai), nome.lower()))
        except ValueError:
            pass
    return res


def arvore_streamlink():
    ps = processos()
    raizes = [p for p, _, n in ps if n == "streamlink.exe"]
    alvo = set(raizes)
    for p, pai, _ in ps:
        if pai in raizes:
            alvo.add(p)
    return raizes, alvo


raizes = []
for _ in range(30):
    raizes, alvo = arvore_streamlink()
    if raizes:
        break
    time.sleep(2)
if not raizes:
    raise SystemExit("streamlink não encontrado")

time.sleep(20)  # deixa gravar uns segmentos antes
raizes, alvo = arvore_streamlink()
handles = []
for pid in alvo:
    h = ctypes.windll.kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
    ctypes.windll.ntdll.NtSuspendProcess(h)
    handles.append(h)
print(f"{time.strftime('%H:%M:%S')} CONGELADOS: {sorted(alvo)}")
t = time.time()
reagiu = False
while time.time() - t < 90:
    novos, _ = arvore_streamlink()
    if novos and not set(novos) & alvo:
        print(f"{time.strftime('%H:%M:%S')} vigia reagiu: travados encerrados, novo streamlink {novos} "
              f"({time.time() - t:.0f}s depois)")
        reagiu = True
        break
    time.sleep(2)
if not reagiu:
    print("o vigia NÃO reagiu em 90 s")
for h in handles:
    ctypes.windll.ntdll.NtResumeProcess(h)
    ctypes.windll.kernel32.CloseHandle(h)
