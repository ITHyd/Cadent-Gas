"""Risk score calculation service with KB verification"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class RiskCalculator:
    """
    Calculates risk scores based on workflow data and KB verification
    
    Enhanced with:
    - Multi-factor risk scoring
    - KB similarity adjustment
    - Confidence reconciliation
    """
    
    def calculate_enhanced_risk(
        self,
        structured_data: Dict[str, Any],
        kb_verification: Optional[Dict[str, Any]] = None,
        property_type: str = "residential"
    ) -> Dict[str, Any]:
        """
        Calculate enhanced risk score with KB verification
        
        USE CASE 15: Commercial Property Logic
        - Risk score weighted ×1.5 for commercial properties
        - Faster escalation path
        - Higher consumption baseline
        - More severe safety rules
        
        Args:
            structured_data: Extracted structured variables from workflow
            kb_verification: KB verification result from KBService
            property_type: "residential" or "commercial"
        
        Returns:
            {
                "preliminary_risk_score": float,
                "kb_adjusted_risk_score": float,
                "final_risk_score": float,
                "confidence_score": float,
                "risk_factors": dict,
                "decision": str,
                "is_commercial": bool,
                "commercial_multiplier": float
            }
        """
        # Determine if commercial property
        is_commercial = property_type.lower() == "commercial"
        commercial_multiplier = 1.5 if is_commercial else 1.0
        normalized_data = self._normalize_structured_data(structured_data)
        
        # Calculate preliminary risk score
        risk_factors = self._extract_risk_factors(normalized_data, is_commercial)
        preliminary_score = self._calculate_preliminary_score(risk_factors)
        
        # Apply commercial multiplier
        if is_commercial:
            preliminary_score = min(1.0, preliminary_score * commercial_multiplier)
            logger.info(f"Commercial property detected - risk score multiplied by {commercial_multiplier}")
        
        # Apply KB adjustment if available
        kb_adjusted_score = preliminary_score
        if kb_verification:
            kb_adjustment = kb_verification.get("confidence_adjustment", 0.0)
            kb_adjusted_score = max(0.0, min(1.0, preliminary_score + kb_adjustment))
            logger.info(f"KB adjustment: {kb_adjustment:+.2f}, "
                       f"score: {preliminary_score:.2f} -> {kb_adjusted_score:.2f}")
        
        # Calculate confidence
        confidence_factors = self._calculate_confidence_factors(
            normalized_data, kb_verification
        )
        avg_confidence = sum(confidence_factors.values()) / len(confidence_factors)
        
        # Final reconciliation
        final_score = self._reconcile_score(kb_adjusted_score, avg_confidence)
        
        # Determine decision (with commercial escalation path)
        decision = self._determine_decision(final_score, risk_factors, is_commercial)
        
        return {
            "preliminary_risk_score": preliminary_score,
            "kb_adjusted_risk_score": kb_adjusted_score,
            "final_risk_score": final_score,
            "confidence_score": avg_confidence,
            "risk_factors": risk_factors,
            "confidence_factors": confidence_factors,
            "decision": decision,
            "kb_verification": kb_verification,
            "is_commercial": is_commercial,
            "commercial_multiplier": commercial_multiplier
        }

    def _normalize_structured_data(self, structured_data: Dict[str, Any]) -> Dict[str, Any]:
        """Derive generic safety fields from manufacturer-specific workflow answers."""
        normalized = dict(structured_data or {})

        if not normalized.get("is_safe") and normalized.get("is_evacuated"):
            evac = str(normalized.get("is_evacuated", "")).lower()
            normalized["is_safe"] = (
                "Yes, we are outside/in fresh air"
                if "outside" in evac
                else "No, still inside the property"
            )

        if not normalized.get("co_symptoms"):
            symptom_parts = [
                normalized.get("symptom_type"),
                normalized.get("flame_symptoms"),
                normalized.get("symptoms"),
            ]
            normalized["co_symptoms"] = " | ".join(
                str(part) for part in symptom_parts if part
            )

        if not normalized.get("alarm_light_colour"):
            for key in ("fa_led", "fh_led", "aico_led", "kidde_led", "xs_led", "gen_led"):
                value = normalized.get(key)
                if value:
                    normalized["alarm_light_colour"] = value
                    break

        if not normalized.get("alarm_sound_pattern"):
            normalized["alarm_sound_pattern"] = self._derive_alarm_sound_pattern(normalized)

        if not normalized.get("hissing_sound"):
            hissing = str(normalized.get("has_hissing", "")).lower()
            normalized["hissing_sound"] = "yes" in hissing

        if not normalized.get("co_alarm"):
            co_alarm_status = str(normalized.get("co_alarm_status", "")).lower()
            if "sounding" in co_alarm_status:
                normalized["co_alarm"] = "sounding"
            elif "not sounding" in co_alarm_status:
                normalized["co_alarm"] = "not sounding"

        return normalized

    def _derive_alarm_sound_pattern(self, structured_data: Dict[str, Any]) -> str:
        sound_fields = (
            "fa_red_sound",
            "fh_beeps",
            "kidde_red_sound",
            "gen_sound",
            "co_alarm_status",
        )
        for key in sound_fields:
            value = structured_data.get(key)
            if value:
                return str(value)

        amber_count = structured_data.get("kidde_amber_count")
        if amber_count:
            return f"Kidde amber pattern: {amber_count}"

        aico_flashes = structured_data.get("aico_flashes")
        if aico_flashes:
            return f"Aico yellow pattern: {aico_flashes}"

        xs_flashes = structured_data.get("xs_flashes")
        if xs_flashes:
            return f"X-Sense yellow pattern: {xs_flashes}"

        xs_led = structured_data.get("xs_led")
        if xs_led:
            return str(xs_led)

        return ""
    
    def _extract_risk_factors(self, structured_data: Dict[str, Any], is_commercial: bool = False) -> Dict[str, float]:
        """
        Extract and normalize risk factors from structured data.

        Supports both gas-smell workflow fields (symptoms, smell_intensity)
        and CO alarm workflow fields (co_symptoms, is_safe, alarm_type, etc.)
        """
        factors = {}

        # ── Safety symptoms (highest priority) ──
        # Gas smell workflows use "symptoms", CO workflows use "co_symptoms"
        symptoms = structured_data.get("symptoms", "")
        co_symptoms = structured_data.get("co_symptoms", "")
        co_sym_lower = str(co_symptoms).lower()
        sym_lower = str(symptoms).lower()

        has_symptoms = False
        if "yes" in sym_lower or "feel unwell" in sym_lower or "present" in sym_lower:
            has_symptoms = True
        if any(
            token in co_sym_lower
            for token in (
                "feel unwell", "headache", "dizziness", "nausea",
                "vomiting", "confusion", "collapse", "loss of consciousness",
                "shortness of breath", "breathless", "flu-like", "flu like",
            )
        ):
            has_symptoms = True
        if "multiple" in co_sym_lower:
            has_symptoms = True  # Multiple people unwell = critical
        factors["safety_symptoms"] = 1.0 if has_symptoms else 0.0

        # ── CO alarm (critical) ──
        # Gas smell workflows: co_alarm field (boolean-ish)
        # CO alarm workflows: alarm_type field + alarm_sound_pattern
        co_alarm_val = structured_data.get("co_alarm", "")
        alarm_type = str(structured_data.get("alarm_type", "")).lower()
        alarm_sound = str(structured_data.get("alarm_sound_pattern", "")).lower()
        alarm_light = str(structured_data.get("alarm_light_colour", "")).lower()

        has_co_alarm = False
        if co_alarm_val and "sounding" in str(co_alarm_val).lower():
            has_co_alarm = True
        if alarm_type.startswith("co") or "carbon monoxide" in alarm_type:
            # CO alarm type selected — check if it's actively sounding
            if "continuous" in alarm_sound or "4 loud beeps" in alarm_sound or "non-stop" in alarm_sound:
                has_co_alarm = True
            elif "loud repeated beeps" in alarm_sound or "4 quick beeps" in alarm_sound:
                has_co_alarm = True
            elif "red (flashing)" in alarm_sound:
                has_co_alarm = True
            elif "chirp" in alarm_sound or "every 30" in alarm_sound or "every few" in alarm_sound:
                has_co_alarm = False  # Chirping = likely battery, not real CO
            elif "stopped" in alarm_sound:
                has_co_alarm = False  # Stopped = no active alarm
            elif "yes - co alarm is sounding" in str(structured_data.get("co_alarm_status", "")).lower():
                has_co_alarm = True
            elif alarm_light == "red":
                has_co_alarm = True
            elif "red (flashing)" in alarm_light:
                has_co_alarm = True
        factors["co_alarm"] = 1.0 if has_co_alarm else 0.0

        # ── Not evacuated (risk multiplier for CO) ──
        is_safe = str(structured_data.get("is_safe", "")).lower()
        if "still inside" in is_safe or "cannot move" in is_safe:
            factors["safety_symptoms"] = max(factors["safety_symptoms"], 0.5)

        # ── Smell intensity ──
        smell = structured_data.get("smell_intensity", "none")
        smell_map = {
            "none": 0.0, "faint": 0.25, "moderate": 0.5,
            "strong": 0.75, "overwhelming": 1.0
        }
        factors["strong_smell"] = smell_map.get(str(smell).lower(), 0.0)

        if is_commercial and factors["strong_smell"] >= 0.5:
            factors["strong_smell"] = min(1.0, factors["strong_smell"] * 1.3)

        # ── Meter movement ──
        meter_moving = structured_data.get("meter_moving", False)
        appliances_off = structured_data.get("appliances_off", False)
        factors["meter_motion"] = 1.0 if (meter_moving and appliances_off) else 0.0

        # ── Audio/Visual/OCR ──
        factors["audio_leak_conf"] = structured_data.get("audio_leak_confidence", 0.0)
        factors["cv_damage_conf"] = structured_data.get("visual_damage_confidence", 0.0)
        ocr_delta = structured_data.get("consumption_delta_pct", 0.0)
        factors["ocr_delta_pct"] = min(1.0, abs(ocr_delta) / 100.0)

        # ── Nearby reports ──
        nearby_count = structured_data.get("nearby_reports_count", 0)
        factors["nearby_reports"] = min(1.0, nearby_count / 5.0)

        # ── Hissing sound ──
        hissing_value = structured_data.get("hissing_sound", False)
        if isinstance(hissing_value, str):
            hissing_detected = "yes" in hissing_value.lower()
        else:
            hissing_detected = bool(hissing_value)
        factors["hissing_sound"] = 1.0 if hissing_detected else 0.0

        # ── CO-specific: flue/soot/condensation indicators ──
        flue = str(structured_data.get("flue_condition", "")).lower()
        if "blocked" in flue or "obstructed" in flue:
            factors["safety_symptoms"] = max(factors["safety_symptoms"], 0.7)

        soot = str(structured_data.get("soot_visible", "")).lower()
        if "yes" in soot or "soot" in soot or "black" in soot:
            factors["cv_damage_conf"] = max(factors["cv_damage_conf"], 0.6)

        return factors
    
    def _calculate_preliminary_score(self, risk_factors: Dict[str, float]) -> float:
        """
        Calculate preliminary risk score using weighted formula
        
        Formula based on UK gas safety priorities:
        - Safety symptoms: 30 points (critical)
        - CO alarm: 30 points (critical)
        - Strong smell: 20 points (high)
        - Meter motion: 15 points (high)
        - Hissing sound: 15 points (high)
        - Audio leak: 10 points (medium)
        - Visual damage: 10 points (medium)
        - Consumption delta: 10 points (medium)
        - Nearby reports: 5 points (low)
        """
        score = 0.0
        
        # Critical factors
        score += 30 * risk_factors.get("safety_symptoms", 0.0)
        score += 30 * risk_factors.get("co_alarm", 0.0)
        
        # High priority factors
        score += 20 * risk_factors.get("strong_smell", 0.0)
        score += 15 * risk_factors.get("meter_motion", 0.0)
        score += 15 * risk_factors.get("hissing_sound", 0.0)
        
        # Medium priority factors
        score += 10 * risk_factors.get("audio_leak_conf", 0.0)
        score += 10 * risk_factors.get("cv_damage_conf", 0.0)
        score += 10 * risk_factors.get("ocr_delta_pct", 0.0)
        
        # Low priority factors
        score += 5 * risk_factors.get("nearby_reports", 0.0)
        
        # Normalize to 0-1 range (max possible score is ~145)
        normalized_score = min(1.0, score / 100.0)
        
        return normalized_score
    
    def _calculate_confidence_factors(
        self,
        structured_data: Dict[str, Any],
        kb_verification: Optional[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Calculate confidence factors based on data quality and KB match."""
        factors = {}

        # Data completeness — check fields relevant to ANY workflow type
        all_fields = [
            # Gas smell fields
            "incident_type", "smell_intensity", "appliances_off",
            # CO alarm fields
            "is_safe", "co_symptoms", "alarm_type", "alarm_sound_pattern",
            "alarm_light_colour", "alarm_age",
            "fa_led", "fh_beeps", "aico_flashes", "kidde_red_sound",
            "xs_led", "gen_sound", "co_alarm_status", "symptom_type",
            # CO other fields
            "flame_location", "condensation_location", "flue_condition",
        ]
        filled = sum(1 for f in all_fields if structured_data.get(f))
        # At least 3 fields filled = good data; normalize to 0-1
        completeness = min(1.0, filled / 4.0)
        factors["data_completeness"] = completeness

        # KB match confidence — strong KB match = high confidence
        if kb_verification:
            kb_match = max(
                kb_verification.get("true_kb_match", 0.0),
                kb_verification.get("false_kb_match", 0.0)
            )
            factors["kb_match_confidence"] = kb_match
        else:
            factors["kb_match_confidence"] = 0.5

        # User trust score
        factors["user_trust"] = structured_data.get("user_trust_score", 0.8)

        # Evidence quality — bonus if provided, but don't penalize absence
        has_audio = structured_data.get("audio_provided", False)
        has_image = structured_data.get("image_provided", False)
        has_video = structured_data.get("video_provided", False)
        evidence_count = sum([has_audio, has_image, has_video])
        # Base 0.5 (neutral) + bonus for media evidence
        factors["evidence_quality"] = min(1.0, 0.5 + evidence_count * 0.25)

        return factors
    
    def _reconcile_score(self, risk_score: float, confidence: float) -> float:
        """
        Reconcile risk score with confidence
        
        Low confidence -> move toward moderate risk (0.5)
        High confidence -> keep original score
        """
        adjustment_factor = confidence
        reconciled = (
            risk_score * adjustment_factor +
            0.5 * (1 - adjustment_factor)
        )
        return max(0.0, min(1.0, reconciled))
    
    def _determine_decision(
        self,
        risk_score: float,
        risk_factors: Dict[str, float],
        is_commercial: bool = False
    ) -> str:
        """
        Determine final decision based on risk score and factors
        
        Commercial properties have faster escalation path:
        - >= 0.70: Emergency dispatch (vs 0.80 for residential)
        - 0.40-0.69: Schedule engineer (vs 0.50-0.79)
        - 0.25-0.39: Monitor (vs 0.30-0.49)
        - < 0.25: Guidance (vs < 0.30)
        """
        # Override for critical safety factors
        if risk_factors.get("co_alarm", 0.0) >= 0.9:
            return "emergency_dispatch"
        
        if risk_factors.get("safety_symptoms", 0.0) >= 0.9:
            return "emergency_dispatch"
        
        # Commercial property thresholds (more aggressive)
        if is_commercial:
            if risk_score >= 0.70:
                return "emergency_dispatch"
            elif risk_score >= 0.40:
                return "schedule_engineer"
            elif risk_score >= 0.25:
                return "monitor"
            else:
                return "close_with_guidance"
        
        # Residential thresholds (standard)
        if risk_score >= 0.80:
            return "emergency_dispatch"
        elif risk_score >= 0.50:
            return "schedule_engineer"
        elif risk_score >= 0.30:
            return "monitor"
        else:
            return "close_with_guidance"
    
    def calculate(
        self,
        formula: str,
        inputs: Dict[str, str],
        variables: Dict[str, Any]
    ) -> float:
        """
        Calculate risk score using formula and inputs
        
        Args:
            formula: Mathematical formula string
            inputs: Mapping of formula variables to workflow variables
            variables: Current workflow variables
        
        Returns:
            Calculated risk score (0.0 - 1.0)
        """
        try:
            # Resolve input variables
            resolved_inputs = {}
            for key, var_ref in inputs.items():
                value = self._resolve_variable(var_ref, variables)
                resolved_inputs[key] = self._normalize_value(value)
            
            # Replace variables in formula
            eval_formula = formula
            for key, value in resolved_inputs.items():
                eval_formula = eval_formula.replace(key, str(value))
            
            # Evaluate formula
            result = eval(eval_formula)
            
            # Clamp to 0-1 range
            result = max(0.0, min(1.0, result))
            
            logger.info(f"Risk score calculated: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Risk calculation error: {e}")
            return 0.5  # Default moderate risk
    
    def reconcile(
        self,
        preliminary_score: float,
        confidence_factors: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Reconciliation layer - adjust score based on confidence
        
        Args:
            preliminary_score: Initial risk score
            confidence_factors: Various confidence metrics
        
        Returns:
            {
                "final_risk_score": float,
                "confidence_score": float
            }
        """
        # Calculate overall confidence
        avg_confidence = sum(confidence_factors.values()) / len(confidence_factors)
        
        # Adjust risk score based on confidence
        # Low confidence -> move toward moderate risk (0.5)
        adjustment_factor = avg_confidence
        final_score = (
            preliminary_score * adjustment_factor +
            0.5 * (1 - adjustment_factor)
        )
        
        return {
            "final_risk_score": max(0.0, min(1.0, final_score)),
            "confidence_score": avg_confidence
        }
    
    def _resolve_variable(self, var_ref: str, variables: Dict[str, Any]) -> Any:
        """Resolve variable reference"""
        if var_ref.startswith("{{") and var_ref.endswith("}}"):
            var_name = var_ref[2:-2]
            return variables.get(var_name, 0)
        return var_ref
    
    def _normalize_value(self, value: Any) -> float:
        """Normalize value to 0-1 range"""
        if isinstance(value, (int, float)):
            return float(value)
        
        # Map text values to scores
        value_map = {
            "yes": 1.0,
            "no": 0.0,
            "faint": 0.25,
            "moderate": 0.5,
            "strong": 0.75,
            "overwhelming": 1.0,
            "low": 0.25,
            "medium": 0.5,
            "high": 0.75,
            "critical": 1.0
        }
        
        if isinstance(value, str):
            return value_map.get(value.lower(), 0.5)
        
        return 0.5
