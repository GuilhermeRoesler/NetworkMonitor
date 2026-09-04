---
name: ci-cd
description: >-
  Pipelines GitHub Actions do Network Monitor: CI (ruff, pytest, CMake/CTest,
  layout) e CD (PyInstaller + C++ em tags v*). Use ao editar
  .github/workflows, pyproject.toml, requirements-dev ou o processo de release.
---

# CI/CD

## CI — `.github/workflows/ci.yml`

Triggers: push/PR em `main`/`master`, `workflow_dispatch`.  
Runner: `windows-latest`.

| Job | O quê |
|-----|--------|
| `python` | matrix 3.10/3.12/3.13 · ruff check/format · compileall · pytest (`--cov-fail-under=35`) |
| `cpp` | CMake Release · build · CTest · smoke `--status` |
| `validate` | arquivos obrigatórios (inclui `README.md`) · runtime JSON/log **não** versionados |
| Pages | `pages.yml` — copia `python/ui/` para GitHub Pages (demo visual) |

## CD — `.github/workflows/cd.yml`

Triggers: tags `v*`, ou `workflow_dispatch` com input `tag`.

1. `build-python` — `python/build.py` → zip `NetworkMonitor-python-win-x64-v*` + Inno Setup `NetworkMonitor-Setup-v*.exe`
2. `build-cpp` — Release → zip `NetworkMonitorCpp-win-x64-v*`
3. `release` — GitHub Release com Setup.exe e ambos os zips; prerelease se tag contém `-`/`rc`/`beta`/`alpha`

Instalador: `installer/NetworkMonitor.iss` (Program Files; dados em `%LOCALAPPDATA%\NetworkMonitor`). CI instala Inno via Chocolatey (`innosetup`).

## Dev local alinhado ao CI

```bash
pip install -r python/requirements-dev.txt
ruff check python
ruff format --check python
pytest
cmake -S cpp -B cpp/build && cmake --build cpp/build --config Release
ctest --test-dir cpp/build -C Release --output-on-failure
```

## Ao alterar pipelines

- Manter PowerShell (`pwsh`) nos jobs Windows
- Paths do exe C++: checar as mesmas candidatas do CI (`bin/`, `bin/Release/`, …)
- Não exigir `peers.json` commitado — validate falha se estiver tracked
- `README.md` é obrigatório no job `validate`
