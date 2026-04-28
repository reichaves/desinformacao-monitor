# Monitor de Desinformação

Pipeline automatizado de monitoramento de vídeos de desinformação e ataques à imprensa e à democracia no Brasil, via YouTube e TikTok.

**Site ao vivo:** https://reichaves.github.io/desinformacao-monitor/

## O que faz

- Busca vídeos no YouTube e TikTok usando +100 hashtags e termos ligados à desinformação brasileira
- Faz download automático de até 20 vídeos por dia
- Extrai um screenshot a cada 3 segundos de cada vídeo
- Transcreve palavra por palavra o áudio de cada vídeo (Gemini)
- Analisa visualmente os screenshots detectando textos, legendas e indicadores de desinformação (Gemini)
- Classifica cada vídeo por tipo de desinformação e severidade (0–5)
- Publica um relatório interativo e filtrável no GitHub Pages
- Envia os resultados para o Google Drive (opcional)
- Roda automaticamente todo dia às 7h (horário de Brasília) via GitHub Actions

## Início rápido

```bash
git clone https://github.com/reichaves/desinformacao-monitor.git
cd desinformacao-monitor
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edite e preencha GEMINI_API_KEY
python pipeline.py
```

Veja o [Guia de Deploy](DEPLOY_GUIDE.md) para instruções completas de configuração no GitHub.

## Estrutura

```
pipeline.py           ← Orquestrador principal
src/
  collector/          ← YouTube + TikTok (yt-dlp, youtubesearchpython)
  processor/          ← Screenshots (ffmpeg), transcrição + análise (Gemini)
  storage/            ← Armazenamento local + Google Drive
  reporter/           ← Gerador de relatório HTML interativo
config/keywords.json  ← Hashtags e termos monitorados (editável)
docs/index.html       ← Relatório publicado no GitHub Pages
.github/workflows/    ← Automação diária via GitHub Actions
tests/                ← Testes unitários
```

## Modelo de IA

- **Gemini 2.5 Flash Preview** para transcrição de áudio, análise visual e classificação de conteúdo
- Sem alucinações: o modelo analisa apenas o conteúdo real dos vídeos coletados

## Palavras-chave monitoradas

Mais de 100 hashtags e termos relacionados a desinformação eleitoral, ataques à imprensa, teorias conspiratórias e discurso antidemocrático no Brasil. Veja e edite `config/keywords.json`.

## Requisitos

- Python 3.11+
- ffmpeg (sistema)
- Chave de API Gemini (google.ai/studio — grátis)
- Conta GitHub (para Actions + Pages)
- Conta Google Drive com service account (opcional)

## Aviso legal

Este projeto coleta e analisa conteúdo público para fins de pesquisa jornalística e monitoramento de desinformação, em conformidade com a Lei de Acesso à Informação e os Termos de Uso das plataformas. A severidade atribuída pelo modelo de IA é uma estimativa automatizada e **requer verificação humana antes de qualquer publicação**. Abraji, 2026.
