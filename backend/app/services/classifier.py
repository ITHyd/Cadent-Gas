"""Incident classification service"""
import logging
from typing import Dict, Any, Optional
from app.core.config import settings
from app.constants.use_cases import USE_CASE_DESCRIPTIONS, GAS_SMELL

logger = logging.getLogger(__name__)


class IncidentClassifier:
    """Classifies incidents into use cases using LLM"""

    def __init__(self):
        self.use_cases = USE_CASE_DESCRIPTIONS

    async def classify(
        self,
        description: str,
        media_types: Optional[list] = None,
        sensor_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Classify incident into closest use case

        Returns:
            {
                "use_case": str,
                "confidence": float,
                "reasoning": str
            }
        """
        try:
            # Build classification prompt
            prompt = self._build_classification_prompt(
                description, media_types, sensor_data
            )

            # Call LLM for classification
            # Pass original description separately for keyword fallback
            response = await self._call_llm(prompt, description=description)

            # Parse response
            classification = self._parse_classification(response)

            logger.info(f"Classified incident as: {classification['use_case']} "
                       f"(confidence: {classification['confidence']})")

            return classification

        except Exception as e:
            logger.error(f"Classification error: {str(e)}")
            # Fallback - use low confidence so the orchestrator asks
            # the user to clarify rather than guessing wrong
            return {
                "use_case": GAS_SMELL,
                "confidence": 0.1,
                "reasoning": "Fallback classification due to error"
            }

    def _build_classification_prompt(
        self,
        description: str,
        media_types: Optional[list],
        sensor_data: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for LLM classification"""
        use_case_list = "\n".join([
            f"- {key}: {value}"
            for key, value in self.use_cases.items()
        ])

        prompt = f"""You are a gas incident classification expert working for Cadent (UK gas distribution network).
Classify the following incident into the most appropriate use case.

Available Use Cases:
{use_case_list}

Incident Description: {description}
"""

        if media_types:
            prompt += f"\nMedia Provided: {', '.join(media_types)}"

        if sensor_data:
            prompt += f"\nSensor Data: {sensor_data}"

        prompt += """

Respond in JSON format:
{
    "use_case": "exact_use_case_key",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}"""

        return prompt

    async def _call_llm(self, prompt: str, description: str = "") -> str:
        """Keyword-based classification (no external LLM)."""
        return self._keyword_classify(description or prompt)

    def _keyword_classify(self, text_input: str) -> str:
        """
        Rule-based keyword classifier - works without any LLM API key.
        Updated for CO Process Improvement workflows based on real Cadent data.
        """
        import json as _json
        text = text_input.lower()

        rules = [
            # (keywords, use_case, confidence)
            # --- CO Fatality (highest priority) ---
            (["fatality", "death", "died", "deceased", "fatal", "dead body"],
             "co_fatality", 0.95),

            # --- CO Blood Test ---
            (["blood test", "carboxyhemoglobin", "cohb", "co blood", "blood result co"],
             "co_blood_test", 0.93),

            # --- CO Alarm (primary workflow - 55.9% of visits) ---
            (["co alarm", "co2 alarm", "co detector", "carbon monoxide alarm",
              "carbon monoxide detector", "co beeping", "co chirping",
              "alarm sounding co", "alarm beeping"],
             "co_alarm", 0.92),

            # --- Suspected CO Leak (symptom-based) ---
            (["carbon monoxide symptom", "co symptom", "co poisoning",
              "headache dizzy gas", "feel unwell gas", "flu like gas",
              "suspected co", "co leak"],
             "suspected_co_leak", 0.90),

            # --- CO Signs ---
            (["orange flame", "yellow flame", "lazy flame", "flame orange",
              "flame yellow", "flame colour", "flame color"],
             "co_orange_flames", 0.88),

            (["sooting", "soot", "scarring", "black marks appliance",
              "black stain boiler", "soot on wall"],
             "co_sooting_scarring", 0.88),

            (["excessive condensation", "condensation window", "condensation boiler",
              "moisture gas", "dripping window gas", "condensation near",
              "condensation on window"],
             "co_excessive_condensation", 0.85),

            (["visible fume", "fumes from", "smoke from boiler", "smoke from gas",
              "fumes gas fire", "visible smoke appliance", "smoke coming from",
              "fumes coming from", "smoke from my gas"],
             "co_visible_fumes", 0.88),

            # --- Smoke Alarm differentiation ---
            (["smoke alarm", "smoke detector", "fire alarm", "fire detector"],
             "co_smoke_alarm", 0.85),

            # --- Core gas emergencies ---
            (["hissing", "whistling", "hiss sound", "pipe noise", "gas hiss"],
             "hissing_sound", 0.88),

            (["smell gas outside", "gas smell outside", "outside meter", "outdoor gas"],
             "gas_smell", 0.86),

            (["smell gas", "gas smell", "odor", "odour", "rotten egg", "mercaptan",
              "smell of gas", "gas leak"],
             "gas_smell", 0.85),
        ]

        for keywords, use_case, confidence in rules:
            for kw in keywords:
                if kw in text:
                    return _json.dumps({
                        "use_case": use_case,
                        "confidence": confidence,
                        "reasoning": f"Keyword match: '{kw}'"
                    })

        symptom_keywords = [
            "headache", "dizziness", "dizzy", "nausea", "vomiting",
            "tiredness", "flu like", "flu-like", "confusion",
            "shortness of breath", "breathless", "collapse",
            "loss of consciousness", "feel unwell",
        ]
        location_keywords = [
            "inside", "at home", "in my home", "in the house",
            "in the property", "when i am home", "when i'm home",
            "when inside", "outside", "fresh air", "boiler",
            "gas fire", "cooker", "hob",
        ]
        if any(kw in text for kw in symptom_keywords) and any(
            kw in text for kw in location_keywords
        ):
            return _json.dumps({
                "use_case": "suspected_co_leak",
                "confidence": 0.82,
                "reasoning": "Symptom-led CO pattern with indoor/property context",
            })

        # Small-talk / off-topic heuristic
        greetings = ["hello", "hi", "hey", "thanks", "thank you", "ok", "okay", "bye", "good"]
        if any(text.startswith(g) for g in greetings):
            return _json.dumps({
                "use_case": "gas_smell",
                "confidence": 0.15,
                "reasoning": "Appears to be small talk / greeting"
            })

        # Check for any gas-related keywords
        gas_related_hints = [
            "gas", "smell", "leak", "meter", "flame", "hiss", "pressure",
            "boiler", "stove", "appliance", "pipe", "supply", "alarm",
            "co", "carbon", "valve", "burner", "fume", "soot",
            "condensation", "symptom", "headache", "dizzy", "nausea",
        ]
        has_gas_hint = any(hint in text for hint in gas_related_hints)

        if not has_gas_hint:
            return _json.dumps({
                "use_case": "gas_smell",
                "confidence": 0.20,
                "reasoning": "No gas-related keywords found - likely off-topic"
            })

        # Default fallback
        return _json.dumps({
            "use_case": "gas_smell",
            "confidence": 0.50,
            "reasoning": "No strong keyword match - default fallback"
        })

    def _parse_classification(self, response: str) -> Dict[str, Any]:
        """Parse LLM response"""
        import json
        try:
            return json.loads(response)
        except:
            return {
                "use_case": GAS_SMELL,
                "confidence": 0.1,
                "reasoning": "Failed to parse classification"
            }
