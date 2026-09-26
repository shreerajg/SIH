"""Gemini-powered grounded answer generation from retrieved evidence."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from app.llm.service import LLMService, get_llm
from app.retrieval.bis_retriever import BISRetriever, RetrievedSource

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "bn": "Bengali",
    "gu": "Gujarati",
    "mr": "Marathi",
    "pa": "Punjabi",
    "or": "Odia",
    "as": "Assamese",
}


class BISIntent(str, Enum):
    PRODUCT_STANDARD = "product_standard"
    CERTIFICATION = "certification"
    LICENSING = "licensing"
    TESTING_LAB = "testing_lab"
    HALLMARKING = "hallmarking"
    CONSUMER_QUERY = "consumer_query"
    STANDARD_DETAILS = "standard_details"
    COMPLIANCE = "compliance"
    GENERAL_BIS = "general_bis"
    UNKNOWN = "unknown"


@dataclass
class QueryUnderstanding:
    intent: BISIntent
    product: Optional[str] = None
    is_number: Optional[str] = None
    category: Optional[str] = None
    confidence: float = 0.0


def _build_system_prompt(language: str) -> str:
    lang_name = LANGUAGE_NAMES.get(language, "English")

    # Language-specific instructions
    if language == "hi":
        lang_instruction = "हिंदी में पूरी तरह उत्तर दें। अंग्रेजी शब्दों का मिश्रण न करें।"
        structure_guide = """
उत्तर की संरचना:
- प्रश्न का सीधा उत्तर दें
- विशिष्ट मानक संख्या और आवश्यकताएं बताएं
- महत्वपूर्ण शर्तें या अपवाद शामिल करें
- मुख्य बात का सारांश दें"""
    elif language == "mr":
        lang_instruction = "मराठीत संपूर्ण उत्तर द्या. इंग्रजी शब्दांचे मिश्रण करू नका."
        structure_guide = """
उत्तराची रचना:
- प्रश्नाचे थेट उत्तर द्या
- विशिष्ट मानक संख्या आणि आवश्यकता सांगा
- महत्वाच्या अटी किंवा अपवाद समाविष्ट करा
- मुख्य मुद्द्याचा सारांश द्या"""
    else:
        lang_instruction = f"RESPOND ENTIRELY IN {lang_name.upper()}. Every word of your answer must be in {lang_name}. Do NOT mix languages."
        structure_guide = """
STRUCTURE YOUR ANSWER:
- Start with the direct answer to the question
- List specific standards, requirements, or steps
- Include any important conditions or exceptions
- End with a brief summary or key takeaway"""

    return f"""You are a BIS (Bureau of Indian Standards) expert assistant. Your job is to provide comprehensive, direct answers like ChatGPT — synthesizing information from sources into a clear, helpful response.

CRITICAL RULES:
1. {lang_instruction}
2. Give a DIRECT, COMPLETE answer immediately. Do not say "please refer to" or "you can visit" — answer the question yourself.
3. Synthesize all source information into one coherent answer with specific details.
4. Include actual standard numbers, requirements, and procedures from the sources.
5. Cite sources naturally: [S1], [S2], etc.
6. If sources have enough info, provide a full answer. Only say "insufficient information" if sources truly have nothing relevant.
7. Write conversationally — like a knowledgeable friend explaining, not redirecting.

{structure_guide}
- Keep source citations [S1] inline throughout"""


def _build_user_prompt(question: str, sources_text: str) -> str:
    return f"""QUESTION: {question}

EVIDENCE FROM OFFICIAL BIS SOURCES:
{sources_text}

Answer the question completely and directly using the evidence above. Give a full, helpful answer — do NOT redirect the user to open documents themselves."""


class GeminiGroundedService:
    """Gemini-powered grounded answer generation."""

    def __init__(self, llm: Optional[LLMService] = None, retriever: Optional[BISRetriever] = None):
        self.llm = llm or get_llm()
        self.retriever = retriever

    def answer(
        self,
        question: str,
        *,
        language: str = "en",
        max_sources: int = 8,
    ) -> Dict[str, Any]:
        understanding = self._understand_query(question)

        if self.retriever is None:
            return self._error_response(understanding, language, "Search not configured.")

        sources = self.retriever.retrieve(
            question,
            max_results=max_sources,
            prefer_official=True,
            language=language,
        )

        if not sources:
            msg = {
                "en": "I couldn't find specific BIS information for your question. Could you provide more details about the product or standard you're asking about? For example, mention the specific product name, its intended use, or any BIS standard number you might know.",
                "hi": "मुझे आपके प्रश्न के लिए विशिष्ट BIS जानकारी नहीं मिली। क्या आप उत्पाद या मानक के बारे में अधिक विवरण दे सकते हैं? उदाहरण के लिए, विशिष्ट उत्पाद का नाम, इसका उपयोग, या कोई BIS मानक संख्या बताएं।",
                "mr": "मला तुमच्या प्रश्नासाठी विशिष्ट BIS माहिती मिळाली नाही. तुम्ही उत्पाद किंवा मानकांबद्दल अधिक तपशील देऊ शकता का? उदाहरणार्थ, विशिष्ट उत्पादाचे नाव, त्याचा वापर, किंवा तुम्हाला माहीत असलेली BIS मानक संख्या सांगा.",
                "ta": "உங்கள் கேள்விக்கு குறிப்பிட்ட BIS தகவல் கிடைக்கவில்லை. தயவுசெய்து தயாரிப்பு அல்லது தரநிலையைப் பற்றி மேலும் விவரங்கள் வழங்க முடியுமா? உதாரணமாக, குறிப்பிட்ட தயாரிப்பு பெயர், அதன் பயன்பாடு அல்லது உங்களுக்குத் தெரிந்த BIS தரநிலை எண்ணைக் குறிப்பிடுங்கள்.",
                "te": "మీ ప్రశ్నకు నిర్దిష్ట BIS సమాచారం దొరకలేదు. దయచేసి ఉత్పత్తి లేదా ప్రమాణం గురించి మరిన్ని వివరాలు అందించగలరా? ఉదాహరణకు, నిర్దిష్ట ఉత్పత్తి పేరు, దాని ఉపయోగం లేదా మీకు తెలిసిన BIS ప్రమాణ సంఖ్యను పేర్కొనండి.",
                "kn": "ನಿಮ್ಮ ಪ್ರಶ್ನೆಗೆ ನಿರ್ದಿಷ್ಟ BIS ಮಾಹಿತಿ ದೊರೆಯಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಉತ್ಪಾದನೆ ಅಥವಾ ಮಾನದಂಡದ ಬಗ್ಗೆ ಹೆಚ್ಚಿನ ವಿವರಗಳನ್ನು ಒದಗಿಸಬಹುದೇ? ಉದಾಹರಣೆಗೆ, ನಿರ್ದಿಷ್ಟ ಉತ್ಪಾದನೆಯ ಹೆಸರು, ಅದರ ಬಳಕೆ ಅಥವಾ ನಿಮಗೆ ತಿಳಿದಿರುವ BIS ಮಾನದಂಡದ ಸಂಖ್ಯೆಯನ್ನು ನಮೂದಿಸಿ.",
                "ml": "നിങ്ങളുടെ ചോദ്യത്തിന് നിർദ്ദിഷ്ട BIS വിവരങ്ങൾ കണ്ടെത്താനായില്ല. ഉൽപ്പന്നത്തെക്കുറിച്ചോ നിലവാരത്തെക്കുറിച്ചോ കൂടുതൽ വിവരങ്ങൾ നൽകാമോ? ഉദാഹരണത്തിന്, നിർദ്ദിഷ്ട ഉൽപ്പന്ന നാമം, അതിന്റെ ഉപയോഗം അല്ലെങ്കിൽ നിങ്ങൾക്കറിയാവുന്ന BIS നിലവാര നമ്പർ പരാമർശിക്കുക.",
                "bn": "আপনার প্রশ্নের জন্য নির্দিষ্ট BIS তথ্য খুঁজে পাইনি। আপনি কি পণ্য বা মানদণ্ড সম্পর্কে আরো বিবরণ দিতে পারেন? উদাহরণস্বরূপ, নির্দিষ্ট পণ্যের নাম, এর ব্যবহার, বা আপনার জানা কোনো BIS মানদণ্ড নম্বর উল্লেখ করুন।",
                "gu": "તમારા પ્રશ્ન માટે વિશિષ્ટ BIS માહિતી મળી નથી. શું તમે ઉત્પાદન અથવા ધોરણ વિશે વધુ વિગતો આપી શકો છો? ઉદાહરણ તરીકે, વિશિષ્ટ ઉત્પાદનનું નામ, તેનો ઉપયોગ અથવા તમને ખબર હોય તેવો BIS ધોરણ નંબર ઉલ્લેખ કરો.",
                "pa": "ਮੈਨੂੰ ਤੁਹਾਡੇ ਸਵਾਲ ਲਈ ਖਾਸ BIS ਜਾਣਕਾਰੀ ਨਹੀਂ ਮਿਲੀ। ਕੀ ਤੁਸੀਂ ਉਤਪਾਦ ਜਾਂ ਮਾਪਦੰਡ ਬਾਰੇ ਹੋਰ ਵੇਰਵੇ ਦੇ ਸਕਦੇ ਹੋ? ਉਦਾਹਰਨ ਲਈ, ਖਾਸ ਉਤਪਾਦ ਦਾ ਨਾਮ, ਇਸਦੀ ਵਰਤੋਂ, ਜਾਂ ਕੋਈ BIS ਮਾਪਦੰਡ ਨੰਬਰ ਦਿਓ।",
                "or": "ଆପଣଙ୍କ ପ୍ରଶ୍ନ ପାଇଁ ନିର୍ଦ୍ଦିଷ୍ଟ BIS ସୂଚନା ମିଳିଲା ନାହିଁ। ଆପଣ ଉତ୍ପାଦ କିମ୍ବା ମାନଦଣ୍ଡ ବିଷୟରେ ଅଧିକ ବିବରଣୀ ଦେଇ ପାରିବେ କି? ଉଦାହରଣ ସ୍ୱରୂପ, ନିର୍ଦ୍ଦିଷ୍ଟ ଉତ୍ପାଦର ନାମ, ଏହାର ବ୍ୟବହାର, କିମ୍ବା ଆପଣ ଜାଣିଥିବା କୌଣସି BIS ମାନଦଣ୍ଡ ସଂଖ୍ୟା ଉଲ୍ଲେଖ କରନ୍ତୁ।",
                "as": "আপোনাৰ প্ৰশ্নৰ বাবে নিৰ্দিষ্ট BIS তথ্য পোৱা নগ'ল। আপুনি উৎপাদন বা মানদণ্ডৰ বিষয়ে অধিক বিৱৰণ দিব পাৰেনে? উদাহৰণস্বৰূপে, নিৰ্দিষ্ট উৎপাদনৰ নাম, ইয়াৰ ব্যৱহাৰ, বা আপোনাৰ জনা কোনো BIS মানদণ্ড সংখ্যা উল্লেখ কৰক।",
            }.get(language, "I couldn't find specific BIS information for your question. Could you provide more details about the product or standard you're asking about? For example, mention the specific product name, its intended use, or any BIS standard number you might know.")
            return {
                "answer": msg,
                "sources": [],
                "intent": understanding.intent.value,
                "answerable": False,
                "llm_used": False,
            }

        if not self.llm.available:
            return self._extractive_response(question, sources, understanding, language)

        answer_text = self._call_gemini(question, sources, language)
        if answer_text is None:
            return self._extractive_response(question, sources, understanding, language)

        return {
            "answer": answer_text,
            "sources": [self._source_to_dict(s) for s in sources],
            "intent": understanding.intent.value,
            "query_understanding": {
                "product": understanding.product,
                "is_number": understanding.is_number,
                "category": understanding.category,
            },
            "answerable": True,
            "confidence": "High",
            "llm_used": True,
            "search_queries": self.retriever._generate_search_queries(question, language),
        }

    def _call_gemini(self, question: str, sources: List[RetrievedSource], language: str) -> Optional[str]:
        """Call Gemini using the correct LLMService.text() interface."""
        system = _build_system_prompt(language)
        sources_text = self._format_sources(sources)
        prompt = _build_user_prompt(question, sources_text)

        try:
            result = self.llm.text(system, prompt, temperature=0.2, max_tokens=2000)
            if result and result.strip():
                return result.strip()
            return None
        except Exception as exc:
            logger.warning("Gemini call failed: %s", exc)
            return None

    def _understand_query(self, question: str) -> QueryUnderstanding:
        lowered = question.lower()

        if any(kw in lowered for kw in ["which standard", "what standard", "applicable standard", "standards for", "standard for", "मानक", "தரநிலை", "ప్రమాణం"]):
            intent = BISIntent.PRODUCT_STANDARD
        elif any(kw in lowered for kw in ["certification", "certified", "licence", "license", "bis mark", "प्रमाणीकरण"]):
            intent = BISIntent.CERTIFICATION
        elif any(kw in lowered for kw in ["test", "testing", "laboratory", "lab"]):
            intent = BISIntent.TESTING_LAB
        elif any(kw in lowered for kw in ["hallmark", "gold", "jewel", "purity"]):
            intent = BISIntent.HALLMARKING
        elif any(kw in lowered for kw in ["how to", "process", "procedure", "apply", "steps"]):
            intent = BISIntent.LICENSING
        elif any(kw in lowered for kw in ["comply", "compliance", "mandatory", "compulsory"]):
            intent = BISIntent.COMPLIANCE
        else:
            intent = BISIntent.GENERAL_BIS

        is_match = re.search(r'\bIS[\s/-]?\d{1,5}(?:[\s:-]\d{4})?\b', question, re.IGNORECASE)

        return QueryUnderstanding(
            intent=intent,
            is_number=is_match.group(0) if is_match else None,
            confidence=0.8,
        )

    def _format_sources(self, sources: List[RetrievedSource]) -> str:
        lines = []
        for source in sources:
            tag = "OFFICIAL BIS" if source.official else "Supporting"
            title = source.title.replace("[PDF]", "").strip()
            lines.append(f"[{source.id}] ({tag}) {title}")
            lines.append(f"Content: {source.snippet}")
            lines.append("")
        return "\n".join(lines)

    def _source_to_dict(self, source: RetrievedSource) -> Dict[str, Any]:
        url = source.url
        # Strip encrypted/ugly URLs to base
        if "encryptedId=" in url:
            base = url.split("?")[0]
            import urllib.parse
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            std = qs.get("standardNumber", [""])[0]
            url = f"{base}?standard={std}" if std else base

        return {
            "id": source.id,
            "title": source.title.replace("[PDF]", "").strip(),
            "url": url,
            "snippet": source.snippet,
            "domain": source.domain,
            "official": source.official,
            "trust_level": source.trust_level,
        }

    def _extractive_response(
        self,
        question: str,
        sources: List[RetrievedSource],
        understanding: QueryUnderstanding,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Structured fallback when Gemini is unavailable."""
        official = [s for s in sources if s.official]
        all_src = official or sources

        # Create conversational response based on intent and language
        answer = self._build_conversational_answer(question, all_src[:5], understanding.intent, language)

        return {
            "answer": answer,
            "sources": [self._source_to_dict(s) for s in sources],
            "intent": understanding.intent.value,
            "answerable": True,
            "llm_used": False,
        }

    def _build_conversational_answer(
        self,
        question: str,
        sources: List[RetrievedSource],
        intent: BISIntent,
        language: str = "en"
    ) -> str:
        """Build a conversational answer from sources without LLM."""

        # Language-specific response templates
        templates = {
            "en": {
                "intro": "Based on official BIS sources, here's what I found:",
                "certification": "For BIS certification of {product}:",
                "standard": "The applicable BIS standard for {product} is:",
                "general": "According to BIS documentation:",
                "source_prefix": "According to",
                "see_more": "For more details, refer to the sources below."
            },
            "hi": {
                "intro": "आधिकारिक BIS स्रोतों के आधार पर, यहाँ जानकारी है:",
                "certification": "{product} के BIS प्रमाणीकरण के लिए:",
                "standard": "{product} के लिए लागू BIS मानक है:",
                "general": "BIS दस्तावेजों के अनुसार:",
                "source_prefix": "के अनुसार",
                "see_more": "अधिक विवरण के लिए, नीचे दिए गए स्रोत देखें।"
            },
            "mr": {
                "intro": "अधिकृत BIS स्रोतांच्या आधारे, येथे माहिती आहे:",
                "certification": "{product} च्या BIS प्रमाणीकरणासाठी:",
                "standard": "{product} साठी लागू BIS मानक आहे:",
                "general": "BIS दस्तऐवजांनुसार:",
                "source_prefix": "नुसार",
                "see_more": "अधिक तपशीलांसाठी, खालील स्रोत पहा।"
            }
        }

        lang_template = templates.get(language, templates["en"])

        # Extract product/subject from question
        product = self._extract_product_from_question(question)

        # Build conversational response
        parts = []

        # Add contextual intro based on intent
        if intent == BISIntent.CERTIFICATION and product:
            intro = lang_template["certification"].format(product=product)
        elif intent == BISIntent.PRODUCT_STANDARD and product:
            intro = lang_template["standard"].format(product=product)
        else:
            intro = lang_template["general"]

        parts.append(intro)
        parts.append("")  # Empty line

        # Add key information from sources
        key_points = []
        for i, source in enumerate(sources[:3]):  # Limit to top 3 sources
            clean_snippet = source.snippet.replace("[PDF]", "").strip()
            clean_title = source.title.replace("[PDF]", "").strip()

            # Extract the most relevant sentence or key point
            sentences = clean_snippet.split('. ')
            relevant_sentence = sentences[0] if sentences else clean_snippet

            if len(relevant_sentence) > 200:
                relevant_sentence = relevant_sentence[:200] + "..."

            if language in ["hi", "mr"]:
                point = f"• {relevant_sentence} ({lang_template['source_prefix']} {clean_title} [S{i+1}])"
            else:
                point = f"• {relevant_sentence} ({lang_template['source_prefix']} {clean_title} [S{i+1}])"

            key_points.append(point)

        parts.extend(key_points)
        parts.append("")  # Empty line
        parts.append(lang_template["see_more"])

        return "\n".join(parts)

    def _extract_product_from_question(self, question: str) -> str:
        """Extract product name from question for better templating."""
        # Common product patterns
        import re

        # Look for "for X", "of X", "X certification", etc.
        patterns = [
            r'(?:for|of)\s+([a-z\s]+?)(?:\s+(?:certification|standard|testing|bis))',
            r'([a-z\s]+?)\s+(?:certification|standard|testing|bis)',
            r'bis\s+(?:certification|standard|testing)\s+(?:for|of)\s+([a-z\s]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, question.lower())
            if match:
                product = match.group(1).strip()
                # Clean up common words
                words = product.split()
                filtered = [w for w in words if w not in ['the', 'a', 'an', 'is', 'are', 'what', 'which']]
                if filtered:
                    return ' '.join(filtered)

        return ""

    def _error_response(self, understanding: QueryUnderstanding, language: str, msg: str) -> Dict[str, Any]:
        return {
            "answer": msg,
            "sources": [],
            "intent": understanding.intent.value,
            "answerable": False,
            "llm_used": False,
        }


_service: Optional[GeminiGroundedService] = None


def get_gemini_grounded_service(retriever: Optional[BISRetriever] = None) -> GeminiGroundedService:
    global _service
    if _service is None:
        _service = GeminiGroundedService(retriever=retriever)
    return _service
