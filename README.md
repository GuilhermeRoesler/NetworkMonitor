# Network Monitor

Monitor de peers **Radmin VPN** e **LAN** no Windows. Faz ping periódico, descobre dispositivos na sub-rede `/24` e notifica quando alguém fica online ou offline.

## Requisitos

- Windows
- Python 3.10+ (versão principal)
- CMake + compilador C++17 (versão CLI opcional)

## Início rápido

```powershell
pip install -r python/requirements.txt
.\run.bat
```

Isso abre o ícone na bandeja e inicia o monitor. Clique duas vezes no ícone para o painel.

## Comandos

| Comando | Descrição |
|---------|-----------|
| `.\run.bat` | Bandeja + monitor (Python) |
| `.\python\run.bat --status` | Status atual |
| `.\python\run.bat --scan-all` | Escaneia Radmin e LAN |
| `.\python\run.bat --gui` | Monitor + painel |
| `.\python\run.bat --install` | Atalho na pasta Startup |
| `.\cpp\run.bat --status` | Mesmo status via C++ (compila se preciso) |

## O que cada versão faz

| Recurso | Python | C++ |
|---------|--------|-----|
| Ping / descoberta / loop | sim | sim |
| `peers.json` / `state.json` | sim | sim |
| Toast / bandeja / painel | sim | não |
| Startup do Windows | sim | não |

Config e estado ficam na **raiz do repositório** e são compartilhados.

## Configuração

Na primeira execução é gerado `peers.json`. Campos principais:

- `interval_seconds` — intervalo entre pings (padrão 15)
- `scan_interval_seconds` — intervalo de auto-descoberta (padrão 300)
- `notifications_enabled` — toasts globais
- `networks[]` — redes `radmin` e/ou `lan`, cada uma com `peers`

Por peer: `hidden` (não monitora) e `muted` (monitora sem notificar).

`peers.json`, `state.json` e `monitor.log` são locais — não vão para o git.

## Build

**Python (PyInstaller):**

```powershell
cd python
pip install -r requirements.txt pyinstaller
python build.py
```

Saída: `python/dist/NetworkMonitor/`.

**C++:**

```powershell
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build --config Release
```

## Desenvolvimento

```powershell
pip install -r python/requirements-dev.txt
ruff check python
ruff format --check python
pytest
```

CI em `.github/workflows/ci.yml`. Releases em tags `v*` via `cd.yml`.

## Specs para agentes

Convenções do projeto em `.cursor/rules/` (rules curtas) e `.cursor/skills/` (detalhe por área).
