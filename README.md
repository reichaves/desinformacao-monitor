# Monitor de Desinformação

> **Status: 🚧 Versão Beta**

[![GitHub Pages](https://img.shields.io/badge/Relatório%20ao%20vivo-GitHub%20Pages-red)](https://reichaves.github.io/desinformacao-monitor/)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue)](https://github.com/reichaves/desinformacao-monitor)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Gemini](https://img.shields.io/badge/IA-Gemini%202.5%20Flash-orange)](https://aistudio.google.com)
[![Actions](https://img.shields.io/badge/Automação-GitHub%20Actions%2019h%20BRT-lightgrey)](https://github.com/reichaves/desinformacao-monitor/actions)

Pipeline automatizado que monitora vídeos de **desinformação, ataques à imprensa e discursos antidemocráticos no Brasil** no YouTube e TikTok — com análise por IA (Gemini), relatório interativo publicado no GitHub Pages e execução diária via GitHub Actions.

**Autor:** Reinaldo Chaves ([reichaves@gmail.com](mailto:reichaves@gmail.com)) · [@reichaves](https://github.com/reichaves)

**Relatório ao vivo:** https://reichaves.github.io/desinformacao-monitor/

---

## Como funciona

```
┌─────────────────────────────────────────────────────────┐
│  config/keywords.json  (100+ hashtags e termos)         │
└─────────────────────┬───────────────────────────────────┘
                      │
          ┌───────────▼────────────┐
          │   Coletores            │
          │  YouTube (yt-dlp)      │  → busca por ytsearchN:query
          │  TikTok  (Playwright)  │  → navega hashtag pages
          └───────────┬────────────┘
                      │ VideoMetadata
          ┌───────────▼────────────┐
          │   Download / Fallback  │
          │  yt-dlp + ffmpeg       │  → vídeo + MP3
          │  Fallback sem download:│
          │    YouTube Transcript  │  → legendas via API
          │    API + thumbnail     │
          │    TikTok: Playwright  │  → texto da página +
          │    page screenshot     │    screenshot
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │   Processadores        │
          │  Transcrição (Gemini)  │  → áudio → texto
          │  Análise visual        │  → frames → sinais
          │  Análise de conteúdo   │  → classificação + severidade
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │   Armazenamento        │
          │  Local (data/)         │  → JSON por vídeo + sumário
          │  Google Drive          │  → opcional
          └───────────┬────────────┘
                      │
          ┌───────────▼────────────┐
          │   Relatório HTML       │
          │  docs/index.html       │  → GitHub Pages
          └────────────────────────┘
```

### O que o pipeline faz a cada execução

1. **Coleta** até 20 vídeos no YouTube e TikTok usando 100+ hashtags e termos de desinformação brasileira
2. **Download + extração** de áudio (MP3) via yt-dlp + ffmpeg
   - *Fallback automático:* se o download for bloqueado (IPs de datacenter), usa a API de legendas do YouTube (sem download) e scraping Playwright do TikTok
3. **Transcrição** palavra a palavra via Gemini File API (ou legendas pré-capturadas no fallback)
4. **Análise visual** de frames/thumbnails — Gemini detecta textos em tela, indicadores visuais de desinformação, personalidades e símbolos
5. **Classificação por IA**: tipo de desinformação (`saúde`, `eleitoral`, `institucional`, `mídia`, `outro`, `nenhum`), severidade 0–5, alegações falsas, contra-narrativa factual
6. **Relatório HTML** interativo com filtros, gráficos e alertas de alta severidade
7. **Commit automático** do relatório atualizado no GitHub Pages

---

## Estrutura do projeto

```
desinformacao-monitor/
├── pipeline.py                          ← Orquestrador principal (entry point)
├── setup_drive_auth.py                  ← Gerador de OAuth refresh token (uso único)
├── requirements.txt
├── config/
│   └── keywords.json                    ← Hashtags e termos monitorados (editável)
├── src/
│   ├── collector/
│   │   ├── base_collector.py            ← Classe abstrata + VideoMetadata dataclass
│   │   ├── youtube_collector.py         ← Busca + download + fallback transcript/thumb
│   │   └── tiktok_collector.py          ← Playwright scraping + download + fallback
│   ├── processor/
│   │   ├── screenshot_extractor.py      ← ffmpeg: 1 frame a cada N segundos
│   │   ├── audio_transcriber.py         ← Gemini File API: áudio → texto
│   │   ├── visual_analyzer.py           ← Gemini vision: frames → sinais de disinfo
│   │   └── content_analyzer.py          ← Gemini text: classificação estruturada
│   ├── storage/
│   │   ├── local_storage.py             ← Diretórios por execução + JSON
│   │   └── drive_uploader.py            ← Upload OAuth 2.0 para Google Drive
│   └── reporter/
│       ├── html_generator.py            ← Renderiza Jinja2 → HTML
│       └── templates/
│           └── index_template.html      ← Chart.js + Tailwind (zero build)
├── docs/
│   └── index.html                       ← Relatório publicado (GitHub Pages)
├── tests/                               ← Testes unitários (pytest)
└── .github/
    └── workflows/
        └── daily_monitor.yml            ← Cron 10:00 UTC = 07:00 BRT
```

---

## Início rápido (local)

### Pré-requisitos

| Ferramenta | Versão | Instalação |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| ffmpeg | qualquer | `apt install ffmpeg` / `brew install ffmpeg` / [ffmpeg.org](https://ffmpeg.org) |
| Git | 2.x+ | [git-scm.com](https://git-scm.com) |
| Chave Gemini API | — | [aistudio.google.com](https://aistudio.google.com) (grátis) |

### Instalação

```bash
# Clone o repositório
git clone https://github.com/reichaves/desinformacao-monitor.git
cd desinformacao-monitor

# Crie e ative o ambiente virtual
python -m venv .venv
source .venv/bin/activate         # Linux/Mac
.venv\Scripts\activate            # Windows

# Instale as dependências Python
pip install -r requirements.txt

# Instale o browser do Playwright (necessário para TikTok)
playwright install chromium
```

### Configuração

Crie um arquivo `.env` na raiz do projeto:

```env
# Obrigatório
GEMINI_API_KEY=sua_chave_aqui

# Opcional — modelo Gemini (padrão: gemini-2.5-flash-preview-05-20)
GEMINI_MODEL=gemini-2.5-flash-preview-05-20

# Opcional — controle de volume
MAX_VIDEOS_PER_RUN=20
HOURS_BACK=24

# Opcional — cookies para evitar bloqueio por bot detection
YOUTUBE_COOKIES_FILE=/caminho/para/youtube_cookies.txt
TIKTOK_COOKIES_FILE=/caminho/para/tiktok_cookies.txt

# Opcional — Google Drive
ENABLE_GOOGLE_DRIVE=false
GOOGLE_DRIVE_CLIENT_ID=
GOOGLE_DRIVE_CLIENT_SECRET=
GOOGLE_DRIVE_REFRESH_TOKEN=
GOOGLE_DRIVE_FOLDER_ID=
```

### Executar

```bash
# Linux/Mac — carregar .env e executar
export $(grep -v '^#' .env | xargs) && python pipeline.py

# Windows (PowerShell)
Get-Content .env | Where-Object { $_ -notmatch '^#' -and $_ -ne '' } | ForEach-Object {
    $parts = $_ -split '=', 2
    [Environment]::SetEnvironmentVariable($parts[0], $parts[1])
}
python pipeline.py
```

O relatório será gerado em `docs/index.html`. Abra no browser para visualizar.

### Testes

```bash
python -m pytest tests/ -v
```

---

## Deploy no GitHub Actions (automação diária)

Veja o [Guia de Deploy completo](DEPLOY_GUIDE.md) para instruções passo a passo.

### Resumo dos Secrets necessários no GitHub

| Secret | Descrição |
|---|---|
| `GEMINI_API_KEY` | Chave da API Gemini — obrigatório |
| `YOUTUBE_COOKIES` | Conteúdo do `cookies.txt` do YouTube (Netscape format) |
| `TIKTOK_COOKIES` | Conteúdo do `cookies.txt` do TikTok (Netscape format) |
| `GOOGLE_DRIVE_CLIENT_ID` | OAuth Client ID — apenas se usar Drive |
| `GOOGLE_DRIVE_CLIENT_SECRET` | OAuth Client Secret — apenas se usar Drive |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | OAuth Refresh Token (gerado por `setup_drive_auth.py`) |
| `GOOGLE_DRIVE_FOLDER_ID` | ID da pasta no Drive |

O workflow roda todos os dias às **19h00 (horário de Brasília)** e:
- Coleta vídeos
- Analisa com Gemini
- Commita o `docs/index.html` atualizado no repositório
- O GitHub Pages publica automaticamente

---

## Adaptar para outro contexto

### Mudar as palavras-chave monitoradas

Edite `config/keywords.json`. A estrutura é:

```json
{
  "search_queries_youtube": ["busca específica", "outra busca"],
  "search_queries_tiktok": ["hashtag1", "hashtag2"],
  "hashtags": ["#exemplo", "#outro"],
  "terms": ["termo livre", "outro termo"]
}
```

As mudanças entram em vigor na próxima execução.

### Mudar o idioma ou contexto da análise

O prompt de análise está em `src/processor/content_analyzer.py`, na variável `_ANALYSIS_PROMPT_TEMPLATE`. Reescreva o prompt para adaptar ao seu contexto (outro país, outro tipo de conteúdo, outro idioma).

### Mudar o modelo Gemini

Defina `GEMINI_MODEL` como variável de ambiente ou GitHub Variable. Modelos compatíveis: `gemini-2.5-flash-preview-05-20`, `gemini-2.0-flash`, `gemini-1.5-pro`, etc.

### Adicionar uma nova plataforma

1. Crie `src/collector/nova_plataforma_collector.py` herdando de `BaseCollector`
2. Implemente `search()` e `download()`
3. Instancie e adicione ao loop em `pipeline.py`

---

## Limitações conhecidas (Versão Beta)

- **Downloads bloqueados no GitHub Actions:** IPs de datacenter são bloqueados pelo YouTube e TikTok. O pipeline usa um fallback automático (API de legendas + thumbnails para YouTube; scraping de texto + screenshot para TikTok), mas a análise fica menos completa do que com o vídeo completo.
- **TikTok timestamps via snowflake ID:** Os IDs de vídeo do TikTok são snowflake IDs — o timestamp de criação é decodificado dos primeiros 32 bits do ID numérico. Funciona na prática mas pode ter pequenas imprecisões dependendo do formato do ID.
- **Severidade requer verificação humana:** A classificação de severidade (0–5) é uma estimativa do modelo de IA e pode conter erros. Não publique resultados sem revisão editorial.
- **Quota Gemini:** Com 20 vídeos/dia e `gemini-2.5-flash-preview`, o custo estimado é < USD 2/mês no plano pago. No plano gratuito, o rate limit pode ser atingido.

---

## Aviso legal

Este projeto coleta e analisa conteúdo público disponível no YouTube e TikTok exclusivamente para fins de **pesquisa jornalística e monitoramento de desinformação**. A severidade atribuída pelo modelo de IA é uma estimativa automatizada e **requer verificação humana antes de qualquer publicação**. O autor não se responsabiliza pelo uso indevido deste software.

---

**Autor:** Reinaldo Chaves · [reichaves@gmail.com](mailto:reichaves@gmail.com) · [github.com/reichaves](https://github.com/reichaves)
