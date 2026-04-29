"""
Comprehensive content analysis combining audio transcript + visual data.

Sends transcription and visual summary to Gemini for a final structured
analysis with disinformation classification and severity scoring.

Author: Reinaldo Chaves (reichaves@gmail.com)
Date: 2026-04-28
Dependencies: google-genai, json, os
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

from google import genai
from google.genai import types

from .visual_analyzer import VisualAnalysisResult

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash-preview-05-20"


@dataclass
class ContentAnalysis:
    """Structured result of the full content analysis for one video."""

    video_id: str
    platform: str
    title: str
    url: str
    channel: str

    # Core analysis
    summary_pt: str = ""
    disinformation_type: str = ""         # e.g. "saúde", "eleitoral", "institucional", "mídia"
    severity: int = 0                     # 0-5 (0=none, 5=extreme)
    confidence: int = 0                   # 0-100 — model confidence in the classification
    severity_justification: str = ""
    target_journalist_or_institution: str = ""
    claims: list[str] = field(default_factory=list)      # False/misleading claims found
    counter_narrative: str = ""           # Brief factual counter-narrative
    keywords_found: list[str] = field(default_factory=list)

    # Source data
    transcript: str = ""
    visual_signals: list[str] = field(default_factory=list)
    ocr_texts: list[str] = field(default_factory=list)

    # Metadata
    view_count: int = 0
    like_count: int = 0
    duration_seconds: int = 0
    published_at: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary suitable for JSON output."""
        return {
            "video_id": self.video_id,
            "platform": self.platform,
            "title": self.title,
            "url": self.url,
            "channel": self.channel,
            "summary_pt": self.summary_pt,
            "disinformation_type": self.disinformation_type,
            "severity": self.severity,
            "confidence": self.confidence,
            "severity_justification": self.severity_justification,
            "target": self.target_journalist_or_institution,
            "claims": self.claims,
            "counter_narrative": self.counter_narrative,
            "keywords_found": self.keywords_found,
            "transcript_excerpt": self.transcript[:1000] if self.transcript else "",
            "visual_signals": self.visual_signals,
            "ocr_texts": self.ocr_texts[:10],
            "view_count": self.view_count,
            "like_count": self.like_count,
            "duration_seconds": self.duration_seconds,
            "published_at": self.published_at,
        }


_ANALYSIS_PROMPT_TEMPLATE = """Você é um pesquisador sênior de desinformação. Sua tarefa é analisar um vídeo coletado por monitoramento de palavras-chave e determinar SE ele realmente contém desinformação — ou se apenas menciona esses temas sem propagá-los.

ATENÇÃO: A maioria dos vídeos coletados por monitoramento de palavras-chave NÃO é desinformação. Eles aparecem porque mencionam os temas monitorados, não porque os desinformam. Seja rigoroso: só classifique como desinformação se houver evidência clara e direta no conteúdo fornecido.

=== TÍTULO DO VÍDEO ===
{title}

=== CANAL / AUTOR ===
{channel}

=== TRANSCRIÇÃO / TEXTO ===
{transcript}

=== TEXTOS VISÍVEIS NAS IMAGENS ===
{ocr_texts}

=== SINAIS VISUAIS DETECTADOS ===
{visual_signals}

=== PALAVRAS-CHAVE QUE MOTIVARAM A COLETA ===
{keywords}

---

DEFINIÇÕES DE SEVERIDADE (use com rigor):
- 0 = Sem desinformação detectável. Conteúdo informativo, opinativo legítimo, humor, ou simplesmente menciona os temas sem desinformar.
- 1 = Conteúdo levemente enganoso, framing distorcido, omissão relevante — mas sem afirmação falsa direta.
- 2 = Afirmações questionáveis com alguma base, mas apresentadas de forma enganosa ou fora de contexto.
- 3 = Afirmações claramente falsas ou manipuladas sobre temas de saúde pública, eleições, instituições ou jornalistas.
- 4 = Desinformação deliberada com potencial de causar dano real (incitação, pânico, desconfiança institucional grave).
- 5 = Desinformação extrema: ameaça direta a jornalistas, chamado à violência, negação de resultados eleitorais comprovados.

CATEGORIAS:
- "saude": Desinformação sobre vacinas, medicamentos, pandemia, tratamentos.
- "eleitoral": Ataques ao sistema eleitoral, urnas, fraudes eleitorais sem evidência.
- "institucional": Ataques ao STF, democracia, poderes da República.
- "midia": Ataques a jornalistas, veículos ou liberdade de imprensa.
- "outro": Desinformação confirmada que não se encaixa acima.
- "nenhum": Sem desinformação — conteúdo legítimo que apenas menciona os temas.

CRITÉRIOS OBRIGATÓRIOS para severidade > 0:
1. Deve haver uma afirmação específica e verificável que seja falsa ou enganosa.
2. A afirmação deve ser apresentada como verdade, não como opinião ou humor.
3. Se a transcrição estiver vazia ou incompleta, use apenas o título e metadados — e seja ainda mais conservador.

Responda em JSON com EXATAMENTE esta estrutura:

{{
  "resumo": "Resumo objetivo em 2-3 frases do que o vídeo aborda",
  "tipo_desinformacao": "nenhum | saude | eleitoral | institucional | midia | outro",
  "severidade": <inteiro 0-5>,
  "confianca": <inteiro 0-100 — sua confiança nessa classificação, baseada na completude do conteúdo disponível>,
  "justificativa_severidade": "Por que essa severidade específica (1 frase concisa)",
  "alvo": "Nome de jornalista, veículo ou instituição atacada — ou 'nenhum'",
  "afirmacoes_falsas": ["Afirmação falsa específica encontrada — lista vazia se nenhuma"],
  "contra_narrativa": "Resposta factual à desinformação — ou 'N/A' se nenhuma",
  "palavras_chave_encontradas": ["Palavras-chave do monitoramento efetivamente presentes no conteúdo"]
}}

REGRAS ANTI-ALUCINAÇÃO:
- Baseie-se EXCLUSIVAMENTE no conteúdo acima. Nunca invente afirmações, nomes ou fatos.
- Em caso de dúvida, prefira severidade mais baixa. Falso negativo é menos prejudicial que falso positivo.
- Se o conteúdo disponível for insuficiente para análise (transcrição vazia, sem imagens), indique confianca < 40 e severidade=0.
- Responda APENAS com JSON válido. Sem markdown, sem texto fora do JSON."""


class ContentAnalyzer:
    """
    Performs final structured content analysis using Gemini.

    Combines transcript, visual analysis, and metadata into a single
    ContentAnalysis object with disinformation classification.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
    ):
        """
        Initialize the content analyzer.

        Args:
            api_key: Gemini API key. Falls back to GEMINI_API_KEY env var.
            model: Gemini model ID.
        """
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise EnvironmentError(
                "Gemini API key not found. Set GEMINI_API_KEY environment variable."
            )
        self.client = genai.Client(api_key=key)
        self.model_name = model
        logger.info("ContentAnalyzer initialized with model: %s", model)

    def analyze(
        self,
        video_id: str,
        platform: str,
        title: str,
        url: str,
        channel: str,
        transcript: str,
        visual_result: VisualAnalysisResult,
        keywords_matched: list[str],
        view_count: int = 0,
        like_count: int = 0,
        duration_seconds: int = 0,
        published_at: Optional[str] = None,
    ) -> ContentAnalysis:
        """
        Run full content analysis for a single video.

        Args:
            video_id: Platform video ID.
            platform: 'youtube' or 'tiktok'.
            title: Video title.
            url: Video URL.
            channel: Channel / uploader name.
            transcript: Full audio transcript.
            visual_result: Output of VisualAnalyzer.analyze_frames().
            keywords_matched: List of monitoring keywords that matched this video.
            view_count: Number of views.
            like_count: Number of likes.
            duration_seconds: Video duration.
            published_at: ISO 8601 publish timestamp string or None.

        Returns:
            ContentAnalysis with all fields populated.
        """
        base = ContentAnalysis(
            video_id=video_id,
            platform=platform,
            title=title,
            url=url,
            channel=channel,
            transcript=transcript,
            visual_signals=visual_result.disinformation_signals,
            ocr_texts=visual_result.key_texts_on_screen,
            keywords_found=keywords_matched,
            view_count=view_count,
            like_count=like_count,
            duration_seconds=duration_seconds,
            published_at=published_at,
        )

        prompt = _ANALYSIS_PROMPT_TEMPLATE.format(
            title=title,
            channel=channel,
            transcript=transcript[:6000] if transcript else "[sem transcrição]",
            ocr_texts="\n".join(visual_result.key_texts_on_screen[:20]) or "[nenhum]",
            visual_signals="\n".join(visual_result.disinformation_signals[:20]) or "[nenhum]",
            keywords=", ".join(keywords_matched) or "[nenhum]",
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
                ),
            )
            raw = response.text.strip()

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            parsed = json.loads(raw)
            base.summary_pt = parsed.get("resumo", "")
            base.disinformation_type = parsed.get("tipo_desinformacao", "nenhum")
            base.severity = int(parsed.get("severidade", 0))
            base.confidence = int(parsed.get("confianca", 50))
            base.severity_justification = parsed.get("justificativa_severidade", "")
            base.target_journalist_or_institution = parsed.get("alvo", "nenhum")
            base.claims = parsed.get("afirmacoes_falsas", [])
            base.counter_narrative = parsed.get("contra_narrativa", "N/A")
            # Merge keywords from analysis with original matched keywords
            extra_kws = parsed.get("palavras_chave_encontradas", [])
            base.keywords_found = list(dict.fromkeys(keywords_matched + extra_kws))

            logger.info(
                "Content analysis done for %s: type=%s, severity=%d",
                video_id,
                base.disinformation_type,
                base.severity,
            )

        except Exception as exc:
            logger.error(
                "Content analysis failed for %s: %s", video_id, exc, exc_info=True
            )
            base.summary_pt = "Análise automática indisponível."

        return base
