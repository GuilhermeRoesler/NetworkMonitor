# Network Monitor

Monitor de peers **Radmin VPN** e **rede local (LAN)** para Windows. Verifica periodicamente quem está online ou offline via ping, descobre dispositivos na sub-rede e envia notificações toast quando o status muda.

## Estrutura

```
NetworkMonitor/
├── run.bat / run.sh   # atalho → versão Python
├── python/            # versão primária (tkinter + pystray + winotify)
├── cpp/               # versão secundária — core CLI (ICMP / Win32)
├── peers.json         # config compartilhada (gerada na 1ª execução)
├── state.json         # estado online/offline (compartilhado)
└── monitor.log
```

As duas versões leem/escrevem os **mesmos** `peers.json` e `state.json` na raiz do repositório.

## Executar

Na raiz (Python por padrão):

```powershell
.\run.bat
```

Direto em cada versão:

```powershell
.\python\run.bat
.\python\run.bat --status
.\cpp\run.bat --status      # compila se o .exe não existir
.\cpp\run.bat --scan-all
```

## Funcionalidades

| Recurso | Python | C++ (Fase 1) |
|---------|--------|--------------|
| Ping / descoberta / loop | Sim | Sim |
| `peers.json` / `state.json` | Sim | Sim |
| CLI (`--status`, `--scan*`, `--run`) | Sim | Sim |
| Notificações toast | Sim | Não (log no console) |
| Bandeja + painel tkinter | Sim | Não |
| Startup do Windows | Sim | Não |

## Python (primária)

Requisitos: Windows · Python 3.10+

```powershell
cd python
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Build do executável

```powershell
cd python
pip install pyinstaller
python build.py
```

O pacote sai em `python/dist/NetworkMonitor/`. Copie `peers.json` para a pasta do `.exe` se quiser reutilizar a config.

## C++ (secundária — core)

C++17 · CMake · Win32 (ICMP via `IcmpSendEcho`). Sem tray/GUI nesta fase.

```powershell
cmake -S cpp -B cpp/build
cmake --build cpp/build --config Release
.\cpp\build\bin\NetworkMonitorCpp.exe --status
```

Ou simplesmente `.\cpp\run.bat --status`.

## Comandos CLI (ambas as versões)

| Comando | Descrição |
|---------|-----------|
| *(sem flag)* / `--run` | Loop de monitoramento |
| `--scan` | Escaneia a sub-rede Radmin |
| `--scan-lan` | Escaneia a sub-rede LAN |
| `--scan-all` | Escaneia Radmin e LAN |
| `--status` | Mostra IPs locais e status dos peers |

Só na versão Python:

| Comando | Descrição |
|---------|-----------|
| *(sem flag)* | Ícone na bandeja + monitor |
| `--gui` | Monitor + painel gráfico |
| `--install` / `--uninstall` | Atalho na pasta Startup |

## Configuração (`peers.json`)

Arquivo na **raiz do repo** (compartilhado). Exemplo:

```json
{
  "interval_seconds": 15,
  "auto_discover": true,
  "scan_interval_seconds": 300,
  "notifications_enabled": true,
  "peer_order": ["26.0.0.2"],
  "networks": [
    {
      "name": "Radmin VPN",
      "type": "radmin",
      "enabled": true,
      "auto_discover": true,
      "peers": [
        { "name": "PC-Amigo", "ip": "26.0.0.2" }
      ]
    },
    {
      "name": "Rede Local (LAN)",
      "type": "lan",
      "enabled": true,
      "auto_discover": true,
      "peers": []
    }
  ]
}
```

## Stack

- **Primária:** Python · tkinter · pystray · winotify · Pillow · (opcional) PyInstaller
- **Secundária:** C++17 · CMake · Win32 / ICMP · nlohmann/json (header vendored)

## Licença

Uso pessoal. Consulte o repositório para detalhes de distribuição.
