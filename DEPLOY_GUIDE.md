# Guia de Deploy — Monitor de Desinformação

**Autor:** Reinaldo Chaves (reichaves@gmail.com)

Este guia cobre todos os passos para colocar o pipeline em produção no GitHub Actions
com publicação automática no GitHub Pages e armazenamento no Google Drive.

---

## Sumário

1. [Pré-requisitos](#1-pré-requisitos)
2. [Estrutura do repositório](#2-estrutura-do-repositório)
3. [Criar repositório no GitHub](#3-criar-repositório-no-github)
4. [Configurar secrets e variáveis](#4-configurar-secrets-e-variáveis)
5. [Configurar GitHub Pages](#5-configurar-github-pages)
6. [Configurar Google Drive (opcional)](#6-configurar-google-drive-opcional)
7. [Testar localmente](#7-testar-localmente)
8. [Verificar o pipeline no Actions](#8-verificar-o-pipeline-no-actions)
9. [Monitorar e manter](#9-monitorar-e-manter)
10. [Referência de variáveis de ambiente](#10-referência-de-variáveis-de-ambiente)

---

## 1. Pré-requisitos

| Ferramenta | Versão mínima | Como obter |
|---|---|---|
| Python | 3.11+ | python.org |
| ffmpeg | qualquer | `apt install ffmpeg` / `brew install ffmpeg` / ffmpeg.org |
| Git | 2.x | git-scm.com |
| Conta GitHub | — | github.com |
| Chave de API Gemini | — | aistudio.google.com (grátis) |

---

## 2. Estrutura do repositório

```
desinformacao-monitor/
├── .github/workflows/daily_monitor.yml  ← GitHub Actions (roda 7h BRT)
├── src/                                 ← Código-fonte modular
│   ├── collector/   youtube + tiktok
│   ├── processor/   screenshots, transcrição, análise visual e de conteúdo
│   ├── storage/     local + Google Drive
│   └── reporter/    gerador HTML
├── config/keywords.json                 ← Hashtags e termos monitorados
├── docs/index.html                      ← Relatório interativo (GitHub Pages)
├── pipeline.py                          ← Entry point principal
├── requirements.txt
├── .env.example                         ← Template de variáveis
└── DEPLOY_GUIDE.md                      ← Este arquivo
```

---

## 3. Criar repositório no GitHub

```bash
# 1. Crie um repositório público chamado "desinformacao-monitor" em github.com/reichaves
# 2. Clone ou inicialize localmente:

cd /caminho/para/desinformacao
git init
git remote add origin https://github.com/reichaves/desinformacao-monitor.git
git add .
git commit -m "feat: initial pipeline setup"
git push -u origin main
```

> **Repositório deve ser público** para que o GitHub Pages funcione no plano gratuito.

---

## 4. Configurar Secrets e Variáveis

### Via GitHub Web (Settings → Secrets and variables → Actions)

#### Secrets (valores sensíveis — nunca aparecem em logs):

| Nome | Valor | Obrigatório |
|---|---|---|
| `GEMINI_API_KEY` | Sua chave em aistudio.google.com | ✅ |
| `YOUTUBE_COOKIES` | Conteúdo do cookies.txt do YouTube (formato Netscape) | Recomendado |
| `TIKTOK_COOKIES` | Conteúdo do cookies.txt do TikTok (formato Netscape) | Recomendado |
| `GOOGLE_DRIVE_CLIENT_ID` | Client ID do OAuth 2.0 (Google Cloud Console) | Apenas se usar Drive |
| `GOOGLE_DRIVE_CLIENT_SECRET` | Client Secret do OAuth 2.0 | Apenas se usar Drive |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | Refresh token gerado pelo `setup_drive_auth.py` | Apenas se usar Drive |
| `GOOGLE_DRIVE_FOLDER_ID` | ID da pasta no Drive | Apenas se usar Drive |

#### Variables (valores não-sensíveis):

| Nome | Valor padrão | Descrição |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.5-flash-preview-05-20` | Modelo Gemini |
| `MAX_VIDEOS_PER_RUN` | `20` | Máx. vídeos por execução |
| `ENABLE_GOOGLE_DRIVE` | `false` | `true` para ativar upload Drive |

### Como adicionar um secret via `gh` CLI:

```bash
# Instale: https://cli.github.com/
gh secret set GEMINI_API_KEY --body "sua_chave_aqui" --repo reichaves/desinformacao-monitor
gh secret set YOUTUBE_COOKIES --body "$(cat youtube_cookies.txt)" --repo reichaves/desinformacao-monitor
gh secret set TIKTOK_COOKIES --body "$(cat tiktok_cookies.txt)" --repo reichaves/desinformacao-monitor
```

---

## 5. Configurar GitHub Pages

1. No repositório, vá em **Settings → Pages**.
2. Em **Source**, selecione **Deploy from a branch**.
3. Selecione branch: `main`, pasta: `/docs`.
4. Clique **Save**.
5. Aguarde ~2 minutos. O site estará em: `https://reichaves.github.io/desinformacao-monitor/`

---

## 6. Configurar Google Drive (opcional)

O pipeline usa **OAuth 2.0 com refresh token** (não service account) para garantir quota de armazenamento.

### 6a. Criar projeto e credenciais no Google Cloud

```
1. Acesse console.cloud.google.com
2. Crie um projeto (ex: "desinformacao-monitor")
3. Ative: APIs & Services → Enable APIs → "Google Drive API"
4. Crie credenciais: APIs & Services → Credentials → Create credentials
   → OAuth client ID → Desktop app
5. Baixe o JSON das credenciais
```

### 6b. Gerar o refresh token

Execute localmente (apenas uma vez):

```bash
python setup_drive_auth.py
```

O script abrirá o browser, você fará login com sua conta Google e o script imprimirá os comandos `gh secret set` com os três valores necessários: `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET` e `GOOGLE_DRIVE_REFRESH_TOKEN`.

### 6c. Criar pasta no Drive e obter o FOLDER_ID

```
1. Crie uma pasta no Google Drive (ex: "Monitor Desinformação")
2. Abra a pasta; copie o ID da URL:
   drive.google.com/drive/folders/<FOLDER_ID>
3. gh secret set GOOGLE_DRIVE_FOLDER_ID --body "<FOLDER_ID>" --repo reichaves/desinformacao-monitor
```

### 6d. Ativar upload

```
GitHub → Settings → Variables → New variable:
Nome: ENABLE_GOOGLE_DRIVE
Valor: true
```

---

## 7. Testar localmente

```bash
# 1. Clone o repositório
git clone https://github.com/reichaves/desinformacao-monitor.git
cd desinformacao-monitor

# 2. Crie o ambiente virtual
python -m venv .venv
source .venv/bin/activate         # Linux/Mac
.venv\Scripts\activate            # Windows

# 3. Instale dependências
pip install -r requirements.txt

# 4. Configure as variáveis
cp .env.example .env
# Edite .env e preencha GEMINI_API_KEY

# 5. Carregue as variáveis e execute
# Linux/Mac:
export $(grep -v '^#' .env | xargs)
python pipeline.py

# Windows (PowerShell):
Get-Content .env | Where-Object { $_ -notmatch '^#' -and $_ -ne '' } | ForEach-Object {
    $parts = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($parts[0], $parts[1])
}
python pipeline.py

# 6. Abra o relatório gerado
start docs/index.html   # Windows
open docs/index.html    # Mac
```

### Executar testes

```bash
python -m pytest tests/ -v
```

---

## 8. Verificar o pipeline no Actions

1. Após o push inicial, vá em **Actions** no repositório.
2. Você verá o workflow **Daily Disinformation Monitor**.
3. Para testar imediatamente sem esperar 7h, clique em **Run workflow** → **Run workflow**.
4. Acompanhe os logs em tempo real.
5. Ao fim, o `docs/index.html` será commitado automaticamente e o GitHub Pages atualizado.

---

## 9. Monitorar e Manter

### Verificar custos Gemini

- Acesse: aistudio.google.com → API Keys → Usage
- Com 20 vídeos/dia e `gemini-2.5-flash-preview`, o custo estimado é **< USD 2/mês** (sujeito a preços vigentes).

### Atualizar palavras-chave

Edite `config/keywords.json` e faça commit. As mudanças entram na próxima execução.

### Ajustar frequência

Edite `cron: "0 10 * * *"` em `.github/workflows/daily_monitor.yml`.
Referência: crontab.guru

### Ver artefatos de cada execução

No GitHub → Actions → [execução] → Artifacts → `run-data-N`
Contém o `run_summary.json` com todos os dados coletados e analisados.

---

## 10. Referência de variáveis de ambiente

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `GEMINI_API_KEY` | ✅ | — | Chave da API Gemini |
| `GEMINI_MODEL` | | `gemini-2.5-flash-preview-05-20` | Modelo Gemini |
| `MAX_VIDEOS_PER_RUN` | | `20` | Máx. vídeos por ciclo |
| `HOURS_BACK` | | `24` | Janela de busca em horas |
| `SCREENSHOT_INTERVAL_SECONDS` | | `3` | Intervalo entre frames |
| `ENABLE_GOOGLE_DRIVE` | | `false` | Ativar upload Drive |
| `YOUTUBE_COOKIES` | | — | Conteúdo Netscape cookies.txt do YouTube |
| `TIKTOK_COOKIES` | | — | Conteúdo Netscape cookies.txt do TikTok |
| `GOOGLE_DRIVE_CLIENT_ID` | Se Drive ativo | — | OAuth Client ID |
| `GOOGLE_DRIVE_CLIENT_SECRET` | Se Drive ativo | — | OAuth Client Secret |
| `GOOGLE_DRIVE_REFRESH_TOKEN` | Se Drive ativo | — | OAuth Refresh Token |
| `GOOGLE_DRIVE_FOLDER_ID` | Se Drive ativo | — | ID da pasta no Drive |
| `DATA_DIR` | | `data` | Diretório de dados temporários |
| `DOCS_DIR` | | `docs` | Diretório do relatório HTML |
| `KEYWORDS_PATH` | | `config/keywords.json` | Caminho do arquivo de keywords |
