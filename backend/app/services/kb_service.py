"""Knowledge Base Service for incident validation"""
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import json
import re

logger = logging.getLogger(__name__)


class KBService:
    """
    Knowledge Base Service for validating incidents against
    True Incident KB and False Incident KB
    Supports tenant-specific and global KB entries.
    Persists to MongoDB; falls back to in-memory defaults if DB unavailable.
    """

    def __init__(self):
        self.true_incidents_kb: List[Dict[str, Any]] = []
        self.false_incidents_kb: List[Dict[str, Any]] = []
        self.incident_patterns: List[Dict[str, Any]] = []
        self._db = None
        self._initialize_default_kb()

    # ── MongoDB persistence helpers ──────────────────────────────────────

    def _get_db(self):
        """Lazy-load MongoDB connection."""
        if self._db is None:
            try:
                from app.core.mongodb import get_database
                self._db = get_database()
            except Exception:
                self._db = None
        return self._db

    def _entry_for_storage(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Return a shallow copy safe for Mongo writes.

        PyMongo mutates inserted dictionaries by adding `_id`; never pass the
        in-memory KB entries directly or those ObjectIds leak into API results.
        """
        return {k: v for k, v in entry.items() if k != "_id"}

    def _entry_for_response(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Return a JSON-safe KB entry for API responses."""
        return self._json_safe(self._entry_for_storage(entry))

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._json_safe(v) for k, v in value.items() if k != "_id"}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, datetime):
            return value.isoformat()
        try:
            from bson import ObjectId
            if isinstance(value, ObjectId):
                return str(value)
        except Exception:
            pass
        return value

    async def load_from_db(self):
        """Load KB entries from MongoDB. If DB has entries, use them
        instead of hard-coded defaults so manual/auto entries survive restarts."""
        db = self._get_db()
        if db is None:
            logger.warning("MongoDB unavailable — using in-memory KB only")
            return

        try:
            true_count = await db.kb_true_incidents.count_documents({})
            false_count = await db.kb_false_incidents.count_documents({})

            if true_count > 0 or false_count > 0:
                true_docs = await db.kb_true_incidents.find({}, {"_id": 0}).to_list(None)
                false_docs = await db.kb_false_incidents.find({}, {"_id": 0}).to_list(None)
                pattern_docs = await db.kb_incident_patterns.find({}, {"_id": 0}).to_list(None)
                self.true_incidents_kb = self._merge_seed_entries(self.true_incidents_kb, true_docs)
                self.false_incidents_kb = self._merge_seed_entries(self.false_incidents_kb, false_docs)
                self.incident_patterns = pattern_docs
                logger.info(
                    f"Loaded KB from MongoDB: {len(true_docs)} true, {len(false_docs)} false, {len(pattern_docs)} patterns"
                )
                await self._persist_missing_seed_entries(true_docs, false_docs)
            else:
                # First run — seed defaults into MongoDB
                await self._seed_db()
        except Exception as e:
            logger.error(f"Failed to load KB from MongoDB: {e} — using in-memory defaults")

    async def _seed_db(self):
        """Persist the default in-memory KB entries to MongoDB."""
        db = self._get_db()
        if db is None:
            return
        try:
            if self.true_incidents_kb:
                await db.kb_true_incidents.insert_many(
                    [self._entry_for_storage(entry) for entry in self.true_incidents_kb]
                )
            if self.false_incidents_kb:
                await db.kb_false_incidents.insert_many(
                    [self._entry_for_storage(entry) for entry in self.false_incidents_kb]
                )
            logger.info(
                f"Seeded KB to MongoDB: {len(self.true_incidents_kb)} true, "
                f"{len(self.false_incidents_kb)} false"
            )
        except Exception as e:
            logger.error(f"Failed to seed KB to MongoDB: {e}")

    async def _persist_entry(self, kb_type: str, entry: Dict[str, Any]):
        """Persist a single KB entry to MongoDB."""
        db = self._get_db()
        if db is None:
            return
        try:
            col = db.kb_true_incidents if kb_type == "true" else db.kb_false_incidents
            await col.replace_one(
                {"kb_id": entry["kb_id"]}, self._entry_for_storage(entry), upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to persist KB entry {entry.get('kb_id')}: {e}")

    async def _delete_from_db(self, kb_type: str, kb_id: str):
        """Delete a KB entry from MongoDB."""
        db = self._get_db()
        if db is None:
            return
        try:
            col = db.kb_true_incidents if kb_type == "true" else db.kb_false_incidents
            await col.delete_one({"kb_id": kb_id})
        except Exception as e:
            logger.error(f"Failed to delete KB entry {kb_id} from MongoDB: {e}")

    async def _persist_incident_pattern(self, pattern: Dict[str, Any]):
        """Persist a pending incident pattern to MongoDB."""
        db = self._get_db()
        if db is None:
            return
        try:
            await db.kb_incident_patterns.replace_one(
                {"incident_id": pattern.get("incident_id")},
                pattern,
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Failed to persist incident pattern {pattern.get('incident_id')}: {e}")

    def _merge_seed_entries(
        self,
        seed_entries: List[Dict[str, Any]],
        db_entries: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged = {str(entry.get("kb_id")): entry for entry in db_entries if entry.get("kb_id")}
        for entry in seed_entries:
            kb_id = str(entry.get("kb_id", ""))
            if kb_id and kb_id not in merged:
                merged[kb_id] = entry
        return list(merged.values())

    async def _persist_missing_seed_entries(
        self,
        existing_true_docs: List[Dict[str, Any]],
        existing_false_docs: List[Dict[str, Any]],
    ):
        db = self._get_db()
        if db is None:
            return

        existing_true_ids = {str(entry.get("kb_id")) for entry in existing_true_docs if entry.get("kb_id")}
        existing_false_ids = {str(entry.get("kb_id")) for entry in existing_false_docs if entry.get("kb_id")}

        missing_true = [entry for entry in self.true_incidents_kb if str(entry.get("kb_id")) not in existing_true_ids]
        missing_false = [entry for entry in self.false_incidents_kb if str(entry.get("kb_id")) not in existing_false_ids]

        try:
            if missing_true:
                await db.kb_true_incidents.insert_many(
                    [self._entry_for_storage(entry) for entry in missing_true]
                )
            if missing_false:
                await db.kb_false_incidents.insert_many(
                    [self._entry_for_storage(entry) for entry in missing_false]
                )
        except Exception as e:
            logger.error(f"Failed to persist missing KB seed entries: {e}")

    def _initialize_default_kb(self):
        """Initialize with default knowledge base entries"""

        # True Incidents - Real gas emergencies (Global KB - tenant_id=None)
        self.true_incidents_kb = [
            {
                "kb_id": "true_001",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "Occupant reported strong rotten egg smell in kitchen area. Two residents experienced headaches and nausea. Smell was strongest near the gas cooker connection.",
                "key_indicators": {
                    "strong_mercaptan_odour": True,
                    "health_symptoms_headache": True,
                    "health_symptoms_nausea": True,
                    "smell_near_appliance": True
                },
                "risk_factors": {
                    "safety_symptoms": 1.0,
                    "strong_gas_smell": 1.0,
                    "enclosed_space": 0.8
                },
                "outcome": "emergency_dispatch",
                "tags": ["domestic", "cooker", "health_symptoms", "gas_escape"],
                "root_cause": "Deteriorated flexible connector on gas cooker had developed a crack at the bayonet fitting, allowing gas to escape during use.",
                "actions_taken": "National Gas Emergency Service attended. Gas supply isolated at ECV. Faulty connector replaced by Gas Safe Registered engineer. Tightness test passed. Property ventilated and declared safe.",
                "resolution_summary": "This was a confirmed incident of type 'gas_smell'. Root cause: cracked flexible connector at cooker bayonet fitting. Resolution: connector replaced, tightness test passed, supply restored.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_002",
                "tenant_id": None,
                "use_case": "suspected_co_leak",
                "description": "Family in rented property experiencing recurring flu-like symptoms — dizziness, fatigue, and confusion. CO alarm activated at 2 AM. Gas Safe engineer found CO being emitted from a poorly installed boiler flue.",
                "key_indicators": {
                    "co_alarm_triggered": True,
                    "recurring_flu_symptoms": True,
                    "multiple_occupants_affected": True,
                    "symptoms_improve_outdoors": True
                },
                "risk_factors": {
                    "co_alarm_triggered": 1.0,
                    "safety_symptoms": 1.0,
                    "enclosed_space": 0.9,
                    "faulty_flue": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["co_poisoning", "boiler", "flue", "rented_property", "RIDDOR_reportable"],
                "root_cause": "Boiler flue was not properly sealed and was incorrectly positioned, allowing CO to leak into the living space. Installation was performed by an unregistered individual without Gas Safe qualifications.",
                "actions_taken": "Emergency services attended. Property evacuated. Boiler classified as 'Immediately Dangerous' (ID). Gas supply capped. Landlord served improvement notice. New boiler installed. Incident reported under RIDDOR.",
                "resolution_summary": "This was a confirmed incident of type 'suspected_co_leak'. Root cause: illegally installed boiler with unsealed flue. Resolution: boiler condemned as ID, property evacuated, new compliant installation fitted.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_003",
                "tenant_id": None,
                "use_case": "hissing_sound",
                "description": "Homeowner heard persistent hissing/whistling sound from external meter box. Mercaptan smell detected in the immediate area. No appliances running at the time.",
                "key_indicators": {
                    "hissing_sound_near_meter": True,
                    "gas_smell_outdoor": True,
                    "no_appliance_running": True
                },
                "risk_factors": {
                    "hissing_sound_detected": 1.0,
                    "strong_gas_smell": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["service_pipe", "meter_box", "external_leak", "gas_escape"],
                "root_cause": "Corroded joint on the service pipe connection at the meter inlet. Pipe material was ageing steel, typical of pre-1970s installations.",
                "actions_taken": "National Gas Emergency Service attended within 1 hour. Area cordoned off. Gas network isolated upstream. Cadent engineers replaced the corroded service pipe section. Pressure test confirmed integrity.",
                "resolution_summary": "This was a confirmed incident of type 'hissing_sound'. Root cause: corroded steel service pipe joint at meter connection. Resolution: service pipe section replaced, tightness tested, supply restored.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_004",
                "tenant_id": None,
                "use_case": "underground_gas_leak",
                "description": "Construction workers excavating for a car park extension struck a high-pressure gas main. Pipeline marker posts had been removed by the groundwork contractors.",
                "key_indicators": {
                    "excavation_activity_nearby": True,
                    "pipeline_damage": True,
                    "gas_smell_outdoor": True,
                    "bubbling_ground": True
                },
                "risk_factors": {
                    "hissing_sound_detected": 1.0,
                    "strong_gas_smell": 1.0,
                    "commercial_area": 0.8
                },
                "outcome": "emergency_dispatch",
                "tags": ["third_party_damage", "construction", "MAH_pipeline", "HSE_investigation"],
                "root_cause": "Groundwork contractors had no prior experience working near Major Accident Hazard Pipelines. They did not obtain underground services plans and removed pipeline marker posts.",
                "actions_taken": "Work stopped immediately. Area evacuated. Pipeline operator emergency team isolated damaged section. HSE investigation launched.",
                "resolution_summary": "This was a confirmed incident of type 'underground_gas_leak'. Root cause: unauthorised excavation without utility mapping. Resolution: pipeline section repaired, HSE enforcement action taken.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_005",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "At 2:40 AM, emergency services responded to an explosion on Mallowdale Avenue, Heysham. Two houses destroyed, a third severely damaged. A 2-year-old child died in the incident.",
                "key_indicators": {
                    "explosion_occurred": True,
                    "structural_damage": True,
                    "casualty_reported": True,
                    "multiple_properties_affected": True
                },
                "risk_factors": {
                    "safety_symptoms": 1.0,
                    "strong_gas_smell": 1.0,
                    "meter_tampering": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["explosion", "fatality", "meter_tampering", "pipe_cutting", "criminal", "GSMR_investigation"],
                "root_cause": "Occupant used an angle grinder to cut copper gas installation pipes to sell as scrap. Gas meter had been previously sabotaged. Gas accumulated on the upper floor and ignited.",
                "actions_taken": "Cadent attended. DNV and HSE launched joint investigation under GSMR. Police led investigation. Occupant sentenced to 15 years imprisonment.",
                "resolution_summary": "This was a confirmed incident caused by criminal gas pipe cutting and meter tampering. Root cause: deliberate cutting of gas pipes for copper theft. Resolution: criminal prosecution, 15-year sentence.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_006",
                "tenant_id": None,
                "use_case": "weak_flame",
                "description": "Resident reported weak yellow/orange flames on all burners of their gas hob. Cooking times had significantly increased. Soot deposits observed on cookware.",
                "key_indicators": {
                    "yellow_orange_flame": True,
                    "all_burners_affected": True,
                    "soot_on_cookware": True,
                    "increased_cooking_time": True
                },
                "risk_factors": {
                    "strong_gas_smell": 0.5
                },
                "outcome": "schedule_engineer",
                "tags": ["weak_flame", "incomplete_combustion", "CO_risk", "burner_maintenance"],
                "root_cause": "Combination of clogged burner ports from grease and food debris, and a faulty pressure regulator delivering insufficient gas pressure to the appliance.",
                "actions_taken": "Gas Safe Registered engineer attended. Burner ports cleaned. Air shutters adjusted. Pressure regulator tested and found faulty — replaced. Post-repair flame confirmed as steady blue.",
                "resolution_summary": "This was a confirmed incident of type 'weak_flame'. Root cause: clogged burner ports and faulty pressure regulator. Resolution: burners cleaned, regulator replaced, blue flame restored.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_007",
                "tenant_id": None,
                "use_case": "suspected_co_leak",
                "description": "Multiple restaurant workers experienced nausea, headache, and dizziness during a shift. Symptoms worsened in the kitchen area. One worker lost consciousness. CO detector had not been installed.",
                "key_indicators": {
                    "multiple_persons_affected": True,
                    "symptoms_in_workplace": True,
                    "loss_of_consciousness": True,
                    "no_co_detector": True
                },
                "risk_factors": {
                    "co_alarm_triggered": 0.8,
                    "safety_symptoms": 1.0,
                    "commercial_property": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["co_poisoning", "commercial", "restaurant", "kitchen", "ventilation"],
                "root_cause": "Malfunctioning commercial gas burner combined with inadequate kitchen ventilation caused CO accumulation. Extraction fan had failed.",
                "actions_taken": "Emergency services attended. Building evacuated. Affected workers treated at hospital. Gas supply isolated. Extraction system repaired. CO detectors installed.",
                "resolution_summary": "This was a confirmed incident of type 'suspected_co_leak'. Root cause: failed extraction fan and malfunctioning gas burner in commercial kitchen. Resolution: ventilation repaired, CO detectors installed.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_008",
                "tenant_id": None,
                "use_case": "meter_tampering",
                "description": "Gas network detected erratic consumption patterns from a commercial premises. On-site inspection revealed gas meter had been tampered with — dials not moving despite active gas use.",
                "key_indicators": {
                    "erratic_consumption_pattern": True,
                    "dials_not_moving": True,
                    "rubber_piping_present": True,
                    "smell_near_meter": True
                },
                "risk_factors": {
                    "meter_running_fast": 1.0,
                    "strong_gas_smell": 0.7
                },
                "outcome": "emergency_dispatch",
                "tags": ["meter_tampering", "theft_of_gas", "commercial", "safety_risk", "Ofgem"],
                "root_cause": "Premises owner installed a rubber bypass pipe around the gas meter to avoid paying for gas usage, creating a significant gas leak risk.",
                "actions_taken": "Gas supply immediately disconnected. Police and Stay Energy Safe notified. Meter bypass removed. New tamper-resistant smart meter installed. Premises owner prosecuted.",
                "resolution_summary": "This was a confirmed incident of type 'meter_tampering'. Root cause: deliberate meter bypass using rubber tubing. Resolution: supply disconnected, bypass removed, smart meter installed, criminal prosecution.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_009",
                "tenant_id": None,
                "use_case": "post_earthquake_gas_check",
                "description": "Following seismic activity, resident noticed rotten egg smell near the water heater. Gas appliances had shifted from original positions.",
                "key_indicators": {
                    "recent_seismic_activity": True,
                    "gas_smell_near_appliance": True,
                    "appliance_displaced": True,
                    "visible_pipe_movement": True
                },
                "risk_factors": {
                    "strong_gas_smell": 1.0,
                    "safety_symptoms": 0.8
                },
                "outcome": "emergency_dispatch",
                "tags": ["earthquake", "gas_check", "flexible_connector", "water_heater"],
                "root_cause": "Seismic shaking caused the water heater to shift, pulling the rigid copper gas connection loose at the fitting.",
                "actions_taken": "Gas supply shut off at meter. Property evacuated. Gas Safe engineer inspected all appliances. Damaged rigid connection replaced with approved flexible connector. Full tightness test performed.",
                "resolution_summary": "This was a confirmed incident of type 'post_earthquake_gas_check'. Root cause: rigid gas connection failed under seismic movement. Resolution: replaced with flexible connector, appliances re-anchored.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_010",
                "tenant_id": None,
                "use_case": "frozen_pipe_gas_interruption",
                "description": "During sub-zero temperatures, a residential condensing boiler stopped operating and displayed error code F4. White plastic condensate pipe running externally was solid with ice.",
                "key_indicators": {
                    "boiler_error_code": True,
                    "sub_zero_temperatures": True,
                    "frozen_external_pipe": True,
                    "no_heating_or_hot_water": True
                },
                "risk_factors": {},
                "outcome": "schedule_engineer",
                "tags": ["frozen_pipe", "condensate", "winter", "boiler_shutdown", "BS6798"],
                "root_cause": "External condensate pipe lacked UV-resistant waterproof insulation. The exposed section froze in overnight temperatures of -5C, blocking condensate drainage.",
                "actions_taken": "Homeowner attempted to thaw using lukewarm water. Boiler reset cleared the fault. Gas Safe engineer subsequently insulated the condensate pipe with proper 13mm lagging.",
                "resolution_summary": "This was a confirmed incident of type 'frozen_pipe_gas_interruption'. Root cause: uninsulated external condensate pipe froze in sub-zero conditions. Resolution: pipe thawed, insulated to BS 6798:2014 standard.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_012",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "Tenant in a rented property noticed a faint gas smell near the boiler that worsened over several days. Landlord's Gas Safety Certificate had expired. Investigating engineer found the boiler flue was dirty and producing elevated CO readings.",
                "key_indicators": {
                    "gas_smell_near_boiler": True,
                    "expired_gas_safety_cert": True,
                    "rented_property": True,
                    "gradual_worsening": True
                },
                "risk_factors": {
                    "strong_gas_smell": 0.8,
                    "safety_symptoms": 0.9
                },
                "outcome": "schedule_engineer",
                "tags": ["boiler", "gas_safety_certificate", "rented", "landlord_duty", "CO_risk"],
                "root_cause": "Gas boiler flueways were clogged. When cleaned, CO levels dropped from lethal levels to 2 ppm.",
                "actions_taken": "Boiler classified as Immediately Dangerous. Gas supply capped. Boiler fully serviced and flue cleaned. New Gas Safety Certificate issued.",
                "resolution_summary": "This was a confirmed incident of type 'gas_smell'. Root cause: unserviced boiler with clogged flueways producing lethal CO. Resolution: boiler cleaned, CO levels reduced, new safety certificate issued.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_013",
                "tenant_id": None,
                "use_case": "hissing_sound",
                "description": "Loud roaring/hissing sound heard from outdoor area near a gas distribution main. Bubbling observed in nearby standing water. Dead grass visible in a concentrated area along the pipeline route.",
                "key_indicators": {
                    "loud_roaring_sound": True,
                    "bubbling_in_water": True,
                    "dead_vegetation_pattern": True,
                    "outdoor_smell": True
                },
                "risk_factors": {
                    "hissing_sound_detected": 1.0,
                    "strong_gas_smell": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["distribution_main", "pipeline_leak", "outdoor", "corrosion"],
                "root_cause": "Corrosion on ageing cast-iron distribution main caused a fracture. The leak was significant enough to displace oxygen in the soil.",
                "actions_taken": "Area evacuated. Gas distribution network operator isolated the affected main section. Temporary bypass installed. Corroded cast-iron section replaced with modern polyethylene pipe.",
                "resolution_summary": "This was a confirmed incident of type 'hissing_sound'. Root cause: fractured ageing cast-iron distribution main. Resolution: section replaced with polyethylene pipe.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_016",
                "tenant_id": None,
                "use_case": "meter_running_fast",
                "description": "Homeowner noticed gas bills had doubled over two billing periods despite no change in usage patterns. Gas meter dials appeared to spin faster than normal.",
                "key_indicators": {
                    "abnormal_billing_increase": True,
                    "meter_spinning_fast": True,
                    "no_usage_change": True,
                    "consumption_anomaly": True
                },
                "risk_factors": {
                    "meter_running_fast": 1.0,
                    "consumption_anomaly": 0.9
                },
                "outcome": "schedule_engineer",
                "tags": ["meter_fault", "consumption_anomaly", "billing_dispute"],
                "root_cause": "Internal meter diaphragm had degraded, causing the meter to over-register gas consumption. A small undetected leak was also found on the downstream pipework.",
                "actions_taken": "Gas network engineer tested meter accuracy. Meter found to be over-registering by 18%. Faulty meter replaced. Gas Safe engineer located and repaired the downstream leak. Billing adjusted.",
                "resolution_summary": "This was a confirmed incident of type 'meter_running_fast'. Root cause: degraded meter diaphragm over-registering and a small downstream leak. Resolution: meter replaced, leak repaired, billing corrected.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_017",
                "tenant_id": None,
                "use_case": "smart_home_alert",
                "description": "Smart home methane detector triggered an alert showing methane concentration above safe threshold (>1% LEL). Alert received on homeowner's mobile app at 3 AM. No occupants at home. Smart valve automatically shut off gas.",
                "key_indicators": {
                    "smart_detector_alert": True,
                    "methane_above_threshold": True,
                    "automatic_shutoff": True,
                    "unoccupied_property": True
                },
                "risk_factors": {
                    "strong_gas_smell": 0.8
                },
                "outcome": "emergency_dispatch",
                "tags": ["smart_home", "IoT", "methane_detector", "auto_shutoff"],
                "root_cause": "Slow leak developed at the gas hob connection fitting due to thermal cycling loosening the compression joint over time.",
                "actions_taken": "Homeowner called National Gas Emergency Service remotely. Smart valve confirmed to have isolated supply correctly. Leak located at hob connection. Joint re-made. Full tightness test performed. Smart detector recalibrated.",
                "resolution_summary": "This was a confirmed incident of type 'smart_home_alert'. Root cause: loose compression joint at gas hob from thermal cycling. Resolution: joint re-made, tightness tested, smart detector recalibrated.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_018",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "Intermittent gas smell reported in upstairs bedroom of a 1960s semi-detached house. Smell came and went unpredictably. No gas appliances located upstairs.",
                "key_indicators": {
                    "intermittent_smell": True,
                    "no_nearby_appliance": True,
                    "upstairs_location": True,
                    "older_property": True
                },
                "risk_factors": {
                    "strong_gas_smell": 0.7
                },
                "outcome": "schedule_engineer",
                "tags": ["hidden_leak", "cavity_wall", "intermittent", "1960s_property"],
                "root_cause": "Gas supply pipe running through the cavity wall had corroded due to moisture ingress. Gas was escaping into the cavity and migrating upwards.",
                "actions_taken": "Cadent engineer attended with gas sniffer equipment. Elevated methane readings detected in cavity wall. Internal gas pipework rerouted to avoid cavity. New surface-mounted copper pipes installed.",
                "resolution_summary": "This was a confirmed incident of type 'gas_smell'. Root cause: corroded gas pipe in cavity wall leaking intermittently. Resolution: internal pipework rerouted surface-mounted.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_019",
                "tenant_id": None,
                "use_case": "suspected_co_leak",
                "description": "A 52-year-old man died of carbon monoxide poisoning in a hotel room. Two contractors had improperly designed and fitted the boiler flue near a hotel window.",
                "key_indicators": {
                    "fatality": True,
                    "hotel_room": True,
                    "flue_near_window": True,
                    "symptoms_mistaken_for_flu": True
                },
                "risk_factors": {
                    "co_alarm_triggered": 0.9,
                    "safety_symptoms": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["co_fatality", "hotel", "flue_defect", "prosecution", "RIDDOR"],
                "root_cause": "Two contractors positioned the flue near a hotel window, allowing CO from the boiler to enter the guest's room. No CO alarm was present.",
                "actions_taken": "Police investigation launched. HSE investigated under RIDDOR/GSMR. Both contractors found guilty. Hotel required to install CO alarms in all rooms.",
                "resolution_summary": "This was a confirmed fatal incident of type 'suspected_co_leak'. Root cause: improperly designed boiler flue near hotel window. Resolution: criminal prosecution, CO alarms mandated.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_020",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "Strong gas smell reported by neighbours. Investigation revealed gas pipes in an adjacent property had been cut using an angle grinder by occupants stripping copper for scrap.",
                "key_indicators": {
                    "strong_smell_reported_by_neighbours": True,
                    "multiple_cut_pipes": True,
                    "meter_tampered": True,
                    "angle_grinder_found": True
                },
                "risk_factors": {
                    "strong_gas_smell": 1.0,
                    "meter_tampering": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["copper_theft", "pipe_cutting", "meter_tampering", "criminal"],
                "root_cause": "Occupant deliberately cut gas installation copper pipes to sell as scrap. Gas meter was sabotaged to prevent consumption recording.",
                "actions_taken": "National Gas Emergency Service isolated supply. Police investigation under GSMR. DNV appointed as competent investigator. Criminal charges brought.",
                "resolution_summary": "This was a confirmed incident involving criminal gas pipe cutting. Root cause: deliberate copper theft. Resolution: supply isolated, criminal prosecution.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_021",
                "tenant_id": None,
                "use_case": "weak_flame",
                "description": "After a kitchen deep-clean, resident noticed gas cooker producing an orange/yellow flame instead of the usual blue. Flames were uneven and flickering. Black soot depositing on pan bottoms.",
                "key_indicators": {
                    "yellow_flame_post_cleaning": True,
                    "soot_on_pans": True,
                    "uneven_flame": True,
                    "recent_appliance_disturbance": True
                },
                "risk_factors": {
                    "strong_gas_smell": 0.3
                },
                "outcome": "close_with_guidance",
                "tags": ["air_shutter", "burner_cap", "incomplete_combustion", "self_fix"],
                "root_cause": "Burner caps were misaligned after being removed and replaced during cleaning. Air shutters were partially blocked.",
                "actions_taken": "Guidance provided: remove burner caps, clean thoroughly, realign centrally. Adjust air shutters. Confirmed steady blue flame after correction. No engineer visit required.",
                "resolution_summary": "This was a confirmed incident of type 'weak_flame'. Root cause: misaligned burner caps and blocked air shutters after cleaning. Resolution: self-fix — caps realigned, blue flame restored.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_022",
                "tenant_id": None,
                "use_case": "suspected_co_leak",
                "description": "London Fire Brigade attended a food court in Kensington High Street after raised CO levels were detected. Premises evacuated.",
                "key_indicators": {
                    "commercial_premises": True,
                    "raised_co_levels": True,
                    "multiple_persons_present": True,
                    "food_service": True
                },
                "risk_factors": {
                    "co_alarm_triggered": 1.0,
                    "safety_symptoms": 0.9,
                    "commercial_property": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["London", "commercial", "food_court", "LFB", "co_increase"],
                "root_cause": "Faulty commercial gas appliance producing CO due to incomplete combustion. Contributing factor: reduced maintenance frequency.",
                "actions_taken": "LFB crews evacuated premises. Ventilated using PPV fans. CO levels monitored until safe. Gas supply isolated to faulty appliance.",
                "resolution_summary": "This was a confirmed incident of type 'suspected_co_leak'. Root cause: faulty commercial gas appliance with incomplete combustion. Resolution: premises evacuated, ventilated, faulty appliance isolated.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_023",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "Resident detected persistent gas smell outside near garden wall. White mist visible on cold morning emanating from ground near external gas pipe entry point.",
                "key_indicators": {
                    "outdoor_smell": True,
                    "visible_mist": True,
                    "near_pipe_entry": True,
                    "persistent": True
                },
                "risk_factors": {
                    "strong_gas_smell": 1.0,
                    "hissing_sound_detected": 0.6
                },
                "outcome": "emergency_dispatch",
                "tags": ["external_pipe", "corrosion", "ground_entry"],
                "root_cause": "Service pipe entering the property had corroded at the point where it passed through the external wall, creating a pin-hole leak.",
                "actions_taken": "National Gas Emergency Service attended. Leak confirmed. ECV turned off. Gas network replaced the corroded service pipe section. Tightness test passed.",
                "resolution_summary": "This was a confirmed incident of type 'gas_smell'. Root cause: corroded service pipe at wall entry. Resolution: service pipe section replaced, tightness tested.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_024",
                "tenant_id": None,
                "use_case": "frozen_pipe_gas_interruption",
                "description": "During the 'Beast from the East' cold snap, hundreds of thousands of UK boilers stopped working due to frozen condensate pipes. British Gas dealt with over 1.2 million callouts in a single season.",
                "key_indicators": {
                    "mass_boiler_failures": True,
                    "extreme_cold_snap": True,
                    "condensate_pipe_frozen": True,
                    "error_codes_displayed": True
                },
                "risk_factors": {},
                "outcome": "schedule_engineer",
                "tags": ["beast_from_the_east", "mass_event", "condensate", "2018", "British_Gas"],
                "root_cause": "Prolonged sub-zero temperatures caused mass freezing of external condensate pipes. Over 10 million UK homes had unprotected external condensate pipes.",
                "actions_taken": "Public guidance issued for DIY thawing with lukewarm water. Emergency engineer teams deployed. HHIC issued updated guidance requiring 13mm UV-resistant insulation.",
                "resolution_summary": "This was a confirmed mass incident of type 'frozen_pipe_gas_interruption'. Root cause: millions of inadequately insulated condensate pipes froze. Resolution: DIY thawing guidance, updated HHIC insulation standards.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_025",
                "tenant_id": None,
                "use_case": "suspected_co_leak",
                "description": "An 18-year-old died from CO poisoning while staying in a rented holiday cottage in Scotland. A portable butane gas cabinet heater was found to be at fault. A CO alarm sounded but its warning was not acted upon.",
                "key_indicators": {
                    "fatality": True,
                    "holiday_accommodation": True,
                    "portable_heater": True,
                    "co_alarm_sounded_and_ignored": True
                },
                "risk_factors": {
                    "co_alarm_triggered": 1.0,
                    "safety_symptoms": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["co_fatality", "portable_heater", "butane", "holiday_cottage", "alarm_ignored"],
                "root_cause": "Portable butane gas cabinet heater produced dangerous levels of CO in an enclosed room. CO alarm sounded but occupants did not recognise the significance.",
                "actions_taken": "Emergency services attended. Heater tested and found to be producing lethal CO levels. Recommendations for clearer public education on CO alarm response.",
                "resolution_summary": "This was a confirmed fatal incident of type 'suspected_co_leak'. Root cause: portable butane heater producing lethal CO, alarm ignored. Resolution: heater removed, public awareness campaign.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_026",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "During planned pipe replacement work, a field engineer's construction plans failed to account for regulator-sensing lines. Regulators opened fully, flooding the network with high-pressure gas (75 psi into a 0.5 psi system).",
                "key_indicators": {
                    "maintenance_in_progress": True,
                    "pressure_spike": True,
                    "multiple_fires": True,
                    "mass_evacuations": True
                },
                "risk_factors": {
                    "strong_gas_smell": 1.0,
                    "safety_symptoms": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["pressure_spike", "regulator_failure", "mass_incident", "NTSB"],
                "root_cause": "Field engineer failed to transfer pressure sensors from old cast-iron main to new polyethylene replacement, causing 75 psi to flood into 0.5 psi domestic network.",
                "actions_taken": "Multiple fire departments responded. 30,000+ residents evacuated. Company paid $143M class-action settlement, $53M federal fine, and $56M regulatory settlement. Company forced to leave the state.",
                "resolution_summary": "This was a confirmed mass incident caused by a maintenance engineering error. Root cause: regulator sensing lines not transferred. Resolution: company paid $252M+ in settlements and fines.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_027",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "Resident noticed faint gas smell in garden area near a crack in the driveway. Recent dry weather had caused ground subsidence. Gas supply pipe running beneath the driveway had cracked.",
                "key_indicators": {
                    "outdoor_smell": True,
                    "ground_subsidence": True,
                    "driveway_crack": True,
                    "dry_weather": True
                },
                "risk_factors": {
                    "strong_gas_smell": 0.6
                },
                "outcome": "schedule_engineer",
                "tags": ["subsidence", "supply_pipe", "ground_movement", "external"],
                "root_cause": "Ground subsidence caused by prolonged dry weather cracked the cast-iron service pipe beneath the driveway.",
                "actions_taken": "Gas distribution network attended. Leak confirmed via bar-hole survey. Supply pipe replaced with modern PE pipe. Driveway surface reinstated.",
                "resolution_summary": "This was a confirmed incident of type 'gas_smell'. Root cause: ground subsidence cracked the cast-iron service pipe. Resolution: pipe replaced with PE.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_028",
                "tenant_id": None,
                "use_case": "hissing_sound",
                "description": "Householder heard a faint hissing sound behind kitchen wall units, accompanied by a mild gas smell. Sound only noticeable at night when the house was quiet.",
                "key_indicators": {
                    "faint_hissing": True,
                    "behind_wall_units": True,
                    "mild_smell": True,
                    "noticeable_when_quiet": True
                },
                "risk_factors": {
                    "hissing_sound_detected": 0.8,
                    "strong_gas_smell": 0.6
                },
                "outcome": "schedule_engineer",
                "tags": ["internal_pipe", "kitchen", "hidden_leak", "compression_fitting"],
                "root_cause": "A compression fitting on the gas pipe running behind the kitchen units had loosened over time due to thermal expansion/contraction cycles.",
                "actions_taken": "Gas Safe engineer attended. Tightness test failed. Leak pinpointed using leak detection fluid. Fitting re-made and tightened. Full tightness test passed.",
                "resolution_summary": "This was a confirmed incident of type 'hissing_sound'. Root cause: loosened compression fitting behind kitchen units. Resolution: fitting re-made, tightness tested.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_029",
                "tenant_id": None,
                "use_case": "smart_home_alert",
                "description": "Smart methane detector triggered at 11 PM. Homeowner had left a gas hob burner on without ignition after cleaning. Gas had been flowing for approximately 30 minutes.",
                "key_indicators": {
                    "smart_detector_alert": True,
                    "hob_left_on": True,
                    "no_ignition": True,
                    "unattended": True
                },
                "risk_factors": {
                    "strong_gas_smell": 1.0
                },
                "outcome": "emergency_dispatch",
                "tags": ["smart_home", "gas_hob", "left_on", "unignited"],
                "root_cause": "Gas hob control knob accidentally turned to 'on' during cleaning without flame ignition. Gas accumulated until smart detector alarm threshold reached.",
                "actions_taken": "Homeowner opened all windows and doors. Gas hob turned off. National Gas Emergency Service verified property was safe. Homeowner advised to install FFD hob.",
                "resolution_summary": "This was a confirmed incident of type 'smart_home_alert'. Root cause: gas hob accidentally left on without ignition. Resolution: property ventilated, FFD hob recommended.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "true_030",
                "tenant_id": None,
                "use_case": "gas_smell",
                "description": "Following a property flood from burst water pipes, resident noticed gas smell near the gas fire in the living room. Water damage had affected the area around the gas fire connection.",
                "key_indicators": {
                    "post_flood": True,
                    "gas_smell_near_appliance": True,
                    "water_damage_visible": True,
                    "fire_connection": True
                },
                "risk_factors": {
                    "strong_gas_smell": 0.8,
                    "safety_symptoms": 0.5
                },
                "outcome": "schedule_engineer",
                "tags": ["flood_damage", "gas_fire", "connector", "water_ingress"],
                "root_cause": "Flood water had saturated the area around the gas fire connection, accelerating corrosion of the steel connector.",
                "actions_taken": "Gas supply isolated. Gas Safe engineer inspected all gas appliances affected by flooding. Corroded connector replaced. All fittings tightness tested. Insurance claim raised.",
                "resolution_summary": "This was a confirmed incident of type 'gas_smell'. Root cause: flood water accelerated corrosion of gas fire connector. Resolution: connector replaced, all flood-affected fittings inspected and tested.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
        ]

        # False Incidents - Common false positives (Global KB)
        self.false_incidents_kb = [
            {
                "kb_id": "false_001",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Hydrogen sulphide (H2S) from dry P-trap in unused bathroom",
                "false_positive_reason": "Sewer gas (H2S) smells like rotten eggs, similar to mercaptan added to natural gas. However, natural gas mercaptan smells more like skunk, while sewer gas is more like rotten eggs.",
                "key_indicators": {
                    "rotten_egg_smell": True,
                    "unused_bathroom": True,
                    "no_gas_appliance_nearby": True,
                    "smell_from_drain": True
                },
                "tags": ["sewer_gas", "dry_trap", "false_alarm", "plumbing"],
                "resolution": "Gas engineer attended, tested with gas sniffer — no methane detected. Smell traced to dry P-trap in guest bathroom. Pouring water into the drain eliminated the odour immediately.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_002",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Skunk spray near the property",
                "false_positive_reason": "Thiols (chemicals in skunk spray) are the same class of compounds as mercaptan added to natural gas, making them virtually indistinguishable to the average person.",
                "key_indicators": {
                    "skunk_like_smell": True,
                    "outdoor_only": True,
                    "no_hissing_sound": True,
                    "no_meter_readings_abnormal": True
                },
                "tags": ["skunk", "mercaptan_confusion", "false_alarm", "outdoor"],
                "resolution": "Fire service attended and confirmed no gas leak. Gas company engineer found no elevated methane readings. Skunk identified as source.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_003",
                "tenant_id": None,
                "reported_as": "smart_home_alert",
                "actual_issue": "Cooking fumes (ethanol from cooking wine, acetic acid from vinegar) triggered household methane detector",
                "false_positive_reason": "Household methane detectors can cross-react with ethanol vapours from cooking wine and acetic acid from vinegar, especially during high-heat cooking.",
                "key_indicators": {
                    "alarm_during_cooking": True,
                    "no_gas_smell": True,
                    "stir_frying": True,
                    "cooking_wine_in_use": True
                },
                "tags": ["false_alarm", "cooking", "sensor_cross_reaction", "methane_detector"],
                "resolution": "Gas engineer confirmed no leak. Detector identified as catalytic-bead type susceptible to cooking vapour interference. Homeowner advised to relocate detector and upgrade to NDIR type sensor.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_004",
                "tenant_id": None,
                "reported_as": "smart_home_alert",
                "actual_issue": "Butane propellant in aerosol cleaning spray triggered hydrocarbon gas detector",
                "false_positive_reason": "Canned aerosol sprays commonly use butane or propane as propellants. Hydrocarbon gas detectors cannot distinguish between these propellants and natural gas.",
                "key_indicators": {
                    "alarm_after_spraying": True,
                    "aerosol_can_in_use": True,
                    "no_gas_smell": True,
                    "detector_near_spray_area": True
                },
                "tags": ["false_alarm", "aerosol", "butane_propellant", "detector"],
                "resolution": "No gas leak found. Detector was functioning correctly — it detected hydrocarbons from the aerosol propellant. Homeowner advised to avoid spraying aerosols near gas detectors.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_005",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "VOCs (volatile organic compounds) from fresh interior paint",
                "false_positive_reason": "Some solvent-based paints and primers emit strong chemical odours that can be mistaken for gas, particularly by residents unfamiliar with paint fumes.",
                "key_indicators": {
                    "chemical_smell": True,
                    "recent_painting": True,
                    "paint_cans_present": True,
                    "no_gas_readings": True
                },
                "tags": ["false_alarm", "paint_fumes", "VOC", "decorating"],
                "resolution": "Gas engineer attended, confirmed zero methane readings throughout property. Smell identified as VOC off-gassing from recently applied oil-based paint.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_006",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Chloramine gas produced by mixing bleach with ammonia-based cleaning products",
                "false_positive_reason": "Mixing bleach with ammonia-based products creates chloramine gas, which produces a sharp, pungent chemical odour. Occupants may believe it is a gas leak.",
                "key_indicators": {
                    "chemical_smell": True,
                    "cleaning_in_progress": True,
                    "burning_eyes": True,
                    "coughing": True
                },
                "tags": ["false_alarm", "cleaning_products", "chloramine", "chemical_reaction"],
                "resolution": "Fire service attended. No methane detected. Source identified as chloramine gas from mixed cleaning products. Property ventilated. Occupant treated for chemical irritation.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_007",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Gas fire pilot light had blown out, releasing a tiny amount of gas before the thermocouple safety device shut off supply",
                "false_positive_reason": "When a pilot light blows out, a small amount of unburned gas is released before the thermocouple shuts off the supply (typically 30-60 seconds).",
                "key_indicators": {
                    "gas_fire_not_working": True,
                    "faint_smell_near_fire": True,
                    "pilot_light_out": True,
                    "thermocouple_clicked": True
                },
                "tags": ["false_alarm", "pilot_light", "gas_fire", "thermocouple"],
                "resolution": "Gas engineer confirmed thermocouple had correctly shut off supply. Pilot light re-ignited. No ongoing leak detected.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_008",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Freshly laid asphalt/tarmac on the road outside the property",
                "false_positive_reason": "Hot asphalt produces hydrocarbon vapours with a strong chemical odour that can be confused with gas, particularly when road works are nearby.",
                "key_indicators": {
                    "chemical_smell_outdoor": True,
                    "road_works_nearby": True,
                    "no_indoor_smell": True,
                    "hot_weather": True
                },
                "tags": ["false_alarm", "asphalt", "road_works", "hydrocarbon_odour"],
                "resolution": "Gas emergency engineer attended. No methane readings detected. Road surfacing works confirmed as the odour source.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_009",
                "tenant_id": None,
                "reported_as": "suspected_co_leak",
                "actual_issue": "Excessive steam/humidity from shower triggered an electrochemical CO detector",
                "false_positive_reason": "Electrochemical CO sensors can be affected by extreme humidity. Steam from hot showers in poorly ventilated bathrooms can cause moisture ingress into the sensor.",
                "key_indicators": {
                    "co_alarm_after_shower": True,
                    "steam_filled_bathroom": True,
                    "no_gas_smell": True,
                    "alarm_stops_after_ventilation": True
                },
                "tags": ["false_alarm", "steam", "humidity", "co_detector", "bathroom"],
                "resolution": "Fire service attended. CO readings normal throughout property. CO detector relocated to outside the bathroom. Occupant advised to use extraction fan.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_010",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Refrigerant leak from old fridge-freezer",
                "false_positive_reason": "Older refrigerant compounds can produce a sweet chemical odour when leaking, which some residents mistake for gas.",
                "key_indicators": {
                    "chemical_smell_in_kitchen": True,
                    "near_fridge": True,
                    "no_gas_smell_at_meter": True,
                    "appliance_not_cooling": True
                },
                "tags": ["false_alarm", "refrigerant", "fridge", "chemical_odour"],
                "resolution": "Gas engineer confirmed no gas leak. Smell traced to refrigerant from old fridge-freezer. Appliance decommissioned.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_011",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Charcoal lighter fluid and BBQ smoke drifting from neighbour's garden",
                "false_positive_reason": "Lighter fluid vapours combined with charcoal smoke can produce a hydrocarbon-like smell confused with gas.",
                "key_indicators": {
                    "outdoor_smell_only": True,
                    "warm_weather": True,
                    "weekend_afternoon": True,
                    "no_indoor_readings": True
                },
                "tags": ["false_alarm", "BBQ", "lighter_fluid", "neighbour"],
                "resolution": "Fire service investigated. No gas readings detected. Source identified as neighbour's BBQ with lighter fluid.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_012",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Decomposing rodent under floorboards producing hydrogen sulphide and other foul gases",
                "false_positive_reason": "Decomposing organic matter produces hydrogen sulphide (rotten egg smell) and mercaptans — the same chemical family added to natural gas.",
                "key_indicators": {
                    "persistent_rotten_egg_smell": True,
                    "smell_from_floor_area": True,
                    "no_gas_readings": True,
                    "no_appliance_nearby": True
                },
                "tags": ["false_alarm", "decomposition", "rodent", "hydrogen_sulphide"],
                "resolution": "Gas engineer confirmed zero methane readings. Pest control identified a dead rodent under the floorboards. Remains removed and area sanitised.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_013",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Acidic condensate water from condensing boiler backing up and producing a sour/chemical smell",
                "false_positive_reason": "Condensing boiler condensate is mildly acidic (pH 3-5) and when it backs up due to a blocked drain, it can produce a sharp chemical odour mistaken for gas.",
                "key_indicators": {
                    "smell_near_boiler": True,
                    "boiler_recently_running": True,
                    "no_hissing": True,
                    "water_visible_under_boiler": True
                },
                "tags": ["false_alarm", "condensate", "boiler", "blocked_drain"],
                "resolution": "Gas engineer confirmed no gas leak. Tightness test passed. Condensate drain found blocked. Drain cleared and flushed. Smell eliminated.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_014",
                "tenant_id": None,
                "reported_as": "smart_home_alert",
                "actual_issue": "Sudden temperature and humidity change caused false reading on catalytic-bead methane sensor",
                "false_positive_reason": "Catalytic-bead sensors are affected by rapid changes in ambient temperature and humidity. Condensation on the sensor element can produce a false methane reading.",
                "key_indicators": {
                    "alarm_during_weather_change": True,
                    "no_gas_smell": True,
                    "sensor_near_window": True,
                    "condensation_visible": True
                },
                "tags": ["false_alarm", "sensor_drift", "humidity", "weather_change"],
                "resolution": "Engineer confirmed no leak. Sensor recalibrated. Homeowner advised to relocate sensor away from windows. Infrared (NDIR) sensor recommended.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_015",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Fertiliser/manure spread on garden producing strong odour",
                "false_positive_reason": "Organic fertiliser and manure produce sulphur compounds when freshly applied, creating a strong rotten-egg-like smell.",
                "key_indicators": {
                    "outdoor_smell": True,
                    "garden_area": True,
                    "spring_season": True,
                    "no_gas_readings": True
                },
                "tags": ["false_alarm", "fertiliser", "garden", "neighbour_report"],
                "resolution": "Fire service attended — confirmed as 'good intent' false alarm. No gas readings. Neighbour had spread manure on garden beds.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_016",
                "tenant_id": None,
                "reported_as": "smart_home_alert",
                "actual_issue": "Construction dust contaminated gas detector sensor surface",
                "false_positive_reason": "During renovation, fine particulate dust can coat the sensor element of methane detectors, interfering with accurate readings.",
                "key_indicators": {
                    "alarm_during_renovation": True,
                    "visible_dust": True,
                    "no_gas_smell": True,
                    "builder_on_site": True
                },
                "tags": ["false_alarm", "dust", "construction", "sensor_contamination"],
                "resolution": "No gas leak. Detector sensor cleaned with compressed air. Detector covered during remaining building work. Normal readings restored.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_017",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Chemical off-gassing from newly fitted synthetic carpet",
                "false_positive_reason": "New synthetic carpets release volatile organic compounds including formaldehyde that produce a strong chemical odour.",
                "key_indicators": {
                    "chemical_smell": True,
                    "new_carpet_installed": True,
                    "smell_strongest_at_floor_level": True,
                    "no_gas_readings": True
                },
                "tags": ["false_alarm", "carpet", "VOC", "off_gassing", "new_furnishings"],
                "resolution": "Gas engineer confirmed no leak. Tightness test passed. Homeowner advised to ventilate rooms for 48-72 hours.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_018",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Storm water overwhelmed drains, pushing sewer gases back through floor drains and broken seals",
                "false_positive_reason": "Heavy rainfall can cause sewer backup, pushing hydrogen sulphide-rich gases through floor drains. The rotten egg smell is easily confused with gas.",
                "key_indicators": {
                    "smell_after_heavy_rain": True,
                    "ground_floor_smell": True,
                    "near_floor_drain": True,
                    "no_gas_readings": True
                },
                "tags": ["false_alarm", "sewer_backup", "heavy_rain", "drain_smell"],
                "resolution": "Gas engineer confirmed no methane present. Smell traced to sewer gases through unsealed floor drain gully. Plumber installed anti-syphon trap.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_019",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Overheating electrical connection in the consumer unit located in the same cupboard as the gas meter",
                "false_positive_reason": "Burning plastic/electrical insulation produces an acrid chemical smell. When co-located with the gas meter, occupants associate the smell with gas.",
                "key_indicators": {
                    "smell_near_meter_cupboard": True,
                    "acrid_smell": True,
                    "warm_to_touch_electrical": True,
                    "no_gas_readings": True
                },
                "tags": ["false_alarm", "electrical", "burning_smell", "meter_cupboard"],
                "resolution": "Gas engineer confirmed no gas leak. Smell identified as overheating electrical connection. Electrician attended urgently. Faulty connection replaced.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            },
            {
                "kb_id": "false_020",
                "tenant_id": None,
                "reported_as": "gas_smell",
                "actual_issue": "Resident panicked after seeing a gas network van in the street, assumed there was a gas emergency",
                "false_positive_reason": "Seeing gas network vehicles conducting routine maintenance can cause concerned residents to believe there is an active gas emergency.",
                "key_indicators": {
                    "no_actual_smell": True,
                    "gas_van_visible": True,
                    "routine_works_in_area": True,
                    "anxiety_driven_report": True
                },
                "tags": ["false_alarm", "good_intent", "routine_maintenance", "public_concern"],
                "resolution": "National Gas Emergency Service confirmed the van was conducting planned routine surveys. No gas escape in the area. Call recorded as 'good intent false alarm'.",
                "source": "research",
                "verified_by": "system",
                "verified_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
        ]

        # Add CO-specific KB entries from real Cadent CO Data 2024-25
        from app.services.kb_seeder_co import (
            get_co_true_incidents_kb,
            get_co_false_incidents_kb,
            get_co_workflow_seed_true_kb,
            get_co_workflow_seed_false_kb,
        )
        self.true_incidents_kb.extend(get_co_true_incidents_kb())
        self.false_incidents_kb.extend(get_co_false_incidents_kb())
        self.true_incidents_kb.extend(get_co_workflow_seed_true_kb())
        self.false_incidents_kb.extend(get_co_workflow_seed_false_kb())

        logger.info(f"Initialized KB with {len(self.true_incidents_kb)} true incidents "
                   f"and {len(self.false_incidents_kb)} false incidents")

    def verify_incident(
        self,
        incident_data: Dict[str, Any],
        use_case: str,
        workflow_outcome: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify incident against KB and return similarity scores

        Args:
            incident_data: Structured incident data with key indicators
            use_case: Incident type/use case

        Returns:
            {
                "true_kb_match": float (0-1),
                "false_kb_match": float (0-1),
                "best_match_type": "true" | "false",
                "best_match_id": str,
                "confidence_adjustment": float (-0.3 to +0.3),
                "explanation": str,
                "all_matches": list of all matching entries with scores
            }
        """
        incident_pattern = self.build_incident_pattern(
            incident_data,
            use_case=use_case,
            workflow_outcome=workflow_outcome,
            incident_id=incident_data.get("incident_id"),
        )
        return self.verify_incident_pattern(incident_pattern)

    def verify_incident_pattern(self, incident_pattern: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verify a prebuilt incident pattern against KB and return similarity scores.

        This is used to keep re-validation consistent with the original workflow
        snapshot instead of rebuilding a slightly different pattern later.
        """
        incident_pattern = dict(incident_pattern or {})
        incident_pattern.setdefault(
            "use_case",
            self._normalize_use_case_key(incident_pattern.get("use_case", "")),
        )

        # Find all strong pattern matches from both sides
        all_true_matches = self._find_all_pattern_matches(
            incident_pattern, self.true_incidents_kb, "true", threshold=0.28
        )
        all_false_matches = self._find_all_pattern_matches(
            incident_pattern, self.false_incidents_kb, "false", threshold=0.28
        )

        # Combine the strongest matches on each side into overall similarity
        # scores. This makes the verdict depend on the full support of the
        # true/false buckets, not just one single best match.
        true_score = self._combine_match_scores(all_true_matches)
        false_score = self._combine_match_scores(all_false_matches)
        true_match = all_true_matches[0] if all_true_matches else None
        false_match = all_false_matches[0] if all_false_matches else None

        winning_confidence = 0.0

        # Determine best match type.
        # We always produce a binary verdict using the stronger side. If the
        # best scores tie, use broader support first and specificity second.
        matched_entry = None
        true_support = self._support_score(all_true_matches)
        false_support = self._support_score(all_false_matches)
        true_specificity = len((true_match or {}).get("matched_tags", [])) + len(((true_match or {}).get("pattern_fields")) or {})
        false_specificity = len((false_match or {}).get("matched_tags", [])) + len(((false_match or {}).get("pattern_fields")) or {})

        if true_score > false_score:
            choose_true = True
        elif false_score > true_score:
            choose_true = False
        elif true_support > false_support:
            choose_true = True
        elif false_support > true_support:
            choose_true = False
        elif true_specificity > false_specificity:
            choose_true = True
        else:
            # Exact or unresolved tie: default to false so ambiguous cases do not
            # drift into a true incident classification.
            choose_true = False

        if choose_true:
            match_type = "true"
            best_match_id = true_match["kb_id"] if true_match else None
            winning_confidence = true_score
            confidence_adj = min(0.3, max(0.0, (true_score - 0.5) * 0.6))  # +0 to +0.3
            if true_score == false_score and true_support != false_support:
                explanation = (
                    f"Overall true and false similarity tied at {true_score:.2f}; "
                    f"classified as true because true-side support ({true_support:.2f}) "
                    f"exceeded false support ({false_support:.2f})"
                )
            elif true_score == false_score:
                explanation = (
                    f"Overall true and false similarity tied at {true_score:.2f}; "
                    f"classified as true because the top true-side pattern was at least as specific as the false side"
                )
            else:
                explanation = (
                    f"Classified as true incident because combined true similarity "
                    f"({true_score:.2f}) exceeded combined false similarity ({false_score:.2f})"
                )
            # Include matched entry details
            if true_match:
                matched_entry = {
                    "incident_type": true_match.get("incident_type", ""),
                    "description": true_match.get("description", ""),
                    "outcome": true_match.get("outcome", ""),
                    "resolution_summary": true_match.get("resolution_summary", ""),
                    "tags": true_match.get("matched_tags", []),
                    "reason": true_match.get("reason", ""),
                    "score": true_match.get("score", 0),
                }
        else:
            match_type = "false"
            best_match_id = false_match["kb_id"] if false_match else None
            winning_confidence = false_score
            confidence_adj = -min(0.3, max(0.0, (false_score - 0.5) * 0.6))  # -0.3 to -0
            if true_score == false_score and false_support == true_support and false_specificity >= true_specificity:
                explanation = (
                    f"Overall true and false similarity tied at {false_score:.2f}; "
                    f"classified as false because support and specificity did not clearly exceed the false side"
                )
            elif true_score == false_score:
                explanation = (
                    f"Overall true and false similarity tied at {false_score:.2f}; "
                    f"classified as false because false-side support ({false_support:.2f}) "
                    f"exceeded true support ({true_support:.2f})"
                )
            else:
                explanation = (
                    f"Classified as false incident because combined false similarity "
                    f"({false_score:.2f}) exceeded combined true similarity ({true_score:.2f})"
                )
            # Include matched entry details for false incidents
            if false_match:
                matched_entry = {
                    "incident_type": false_match.get("incident_type", ""),
                    "description": false_match.get("description", ""),
                    "outcome": false_match.get("outcome", "false_positive"),
                    "resolution_summary": false_match.get("resolution_summary", ""),
                    "tags": false_match.get("matched_tags", []),
                    "reason": false_match.get("reason", ""),
                    "score": false_match.get("score", 0),
                }
        result = {
            "true_kb_match": true_score,
            "false_kb_match": false_score,
            "best_match_type": match_type,
            "best_match_id": best_match_id,
            "confidence": winning_confidence,
            "match_confidence": winning_confidence,
            "explicit_split": False,
            "confidence_adjustment": confidence_adj,
            "explanation": explanation,
            "all_matches": all_true_matches + all_false_matches  # Combine all matches
        }
        
        # Add matched entry details if available
        if matched_entry:
            result["matched_entry"] = matched_entry
        result["incident_pattern"] = incident_pattern
        result["top_true_matches"] = all_true_matches[:3]
        result["top_false_matches"] = all_false_matches[:3]
        
        return result

    def _combine_match_scores(
        self,
        matches: List[Dict[str, Any]],
        top_n: int = 5,
    ) -> float:
        if not matches:
            return 0.0

        top_matches = matches[:top_n]
        weights = [1.0, 0.75, 0.55, 0.4, 0.3]
        weighted_total = 0.0
        weight_sum = 0.0

        for index, match in enumerate(top_matches):
            weight = weights[index] if index < len(weights) else max(0.15, weights[-1] - (index - len(weights) + 1) * 0.05)
            weighted_total += float(match.get("score", 0.0)) * weight
            weight_sum += weight

        return round((weighted_total / weight_sum) if weight_sum else 0.0, 3)

    def _find_best_pattern_match(
        self,
        incident_pattern: Dict[str, Any],
        kb_list: List[Dict[str, Any]],
        kb_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], float]:
        best_match = None
        best_score = 0.0

        for kb_entry in kb_list:
            kb_pattern = self._build_kb_pattern(kb_entry, kb_type)
            if not self._pattern_use_case_compatible(incident_pattern, kb_pattern):
                continue
            score = self._calculate_pattern_similarity(incident_pattern, kb_entry, kb_type)
            if score > best_score:
                best_score = score
                best_match = kb_entry

        return best_match, best_score

    def _find_all_pattern_matches(
        self,
        incident_pattern: Dict[str, Any],
        kb_list: List[Dict[str, Any]],
        kb_type: str,
        threshold: float = 0.28,
    ) -> List[Dict[str, Any]]:
        matches = []
        current_incident_id = str(incident_pattern.get("incident_id") or "").strip()

        for kb_entry in kb_list:
            kb_incident_id = str(kb_entry.get("incident_id") or "").strip()
            if current_incident_id and kb_incident_id and kb_incident_id == current_incident_id:
                continue
            kb_pattern = self._build_kb_pattern(kb_entry, kb_type)
            if not self._pattern_use_case_compatible(incident_pattern, kb_pattern):
                continue
            score = self._calculate_pattern_similarity(incident_pattern, kb_entry, kb_type)
            if score < threshold:
                continue

            match_data = {
                "kb_id": kb_entry.get("kb_id"),
                "kb_type": kb_type,
                "score": round(score, 3),
                "incident_type": kb_entry.get("use_case") if kb_type == "true" else kb_entry.get("reported_as"),
                "description": kb_entry.get("description") if kb_type == "true" else kb_entry.get("actual_issue"),
                "outcome": kb_entry.get("outcome", "false_positive" if kb_type == "false" else ""),
                "resolution_summary": kb_entry.get("resolution_summary") or kb_entry.get("resolution", ""),
                "reason": kb_entry.get("root_cause") if kb_type == "true" else kb_entry.get("false_positive_reason", ""),
                "manufacturer": kb_pattern.get("manufacturer"),
                "model": kb_pattern.get("model"),
                "matched_tags": sorted(set(incident_pattern.get("derived_tags", [])) & set(kb_pattern.get("derived_tags", []))),
                "pattern_fields": kb_pattern.get("pattern_fields", {}),
            }
            matches.append(match_data)

        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches

    def _pattern_use_case_compatible(
        self,
        incident_pattern: Dict[str, Any],
        kb_pattern: Dict[str, Any],
    ) -> bool:
        incident_use_case = self._normalize_use_case_key(incident_pattern.get("use_case", ""))
        kb_use_case = self._normalize_use_case_key(kb_pattern.get("use_case", ""))
        if not incident_use_case or not kb_use_case:
            return True
        if incident_use_case == kb_use_case:
            return True
        return incident_use_case in kb_use_case or kb_use_case in incident_use_case

    def _calculate_pattern_similarity(
        self,
        incident_pattern: Dict[str, Any],
        kb_entry: Dict[str, Any],
        kb_type: str,
    ) -> float:
        kb_pattern = self._build_kb_pattern(kb_entry, kb_type)
        if not kb_pattern:
            return 0.0

        score = 0.0
        max_score = 0.0

        def norm(value: Any) -> str:
            return str(value or "").strip().lower()

        # Use case alignment
        max_score += 1.5
        incident_use_case = norm(incident_pattern.get("use_case"))
        kb_use_case = norm(kb_pattern.get("use_case"))
        if incident_use_case and kb_use_case:
            if incident_use_case == kb_use_case:
                score += 1.5
            elif incident_use_case in kb_use_case or kb_use_case in incident_use_case:
                score += 1.0

        # Manufacturer / model are high-signal when present
        for field, weight in (("manufacturer", 1.8), ("model", 2.2)):
            max_score += weight
            incident_value = norm(incident_pattern.get(field))
            kb_value = norm(kb_pattern.get(field))
            if not incident_value or not kb_value:
                continue
            if incident_value == kb_value:
                score += weight
            elif incident_value in kb_value or kb_value in incident_value:
                score += weight * 0.65

        # Pattern fields
        incident_fields = incident_pattern.get("pattern_fields", {}) or {}
        kb_fields = kb_pattern.get("pattern_fields", {}) or {}
        field_weights = {
            "light_pattern": 1.4,
            "sound_pattern": 1.8,
            "state_now": 1.2,
            "repeat_pattern": 1.5,
            "likely_meaning": 1.8,
            "symptom_level": 1.0,
            "safety_state": 0.9,
            "alarm_type": 0.8,
        }
        for field, weight in field_weights.items():
            max_score += weight
            incident_value = norm(incident_fields.get(field))
            kb_value = norm(kb_fields.get(field))
            if not incident_value or not kb_value:
                continue
            if incident_value == kb_value:
                score += weight
            elif incident_value in kb_value or kb_value in incident_value:
                score += weight * 0.6

        # Tag overlap
        incident_tags = set(incident_pattern.get("derived_tags", []) or [])
        kb_tags = set(kb_pattern.get("derived_tags", []) or [])
        max_score += 2.2
        if incident_tags and kb_tags:
            overlap = len(incident_tags & kb_tags)
            union = len(incident_tags | kb_tags)
            if union:
                score += 2.2 * (overlap / union)

        # Workflow outcome is informative but not truth
        max_score += 0.6
        incident_outcome = norm(incident_pattern.get("workflow_outcome"))
        kb_outcome = norm(kb_pattern.get("workflow_outcome"))
        if incident_outcome and kb_outcome and incident_outcome == kb_outcome:
            score += 0.6

        return max(0.0, min(1.0, score / max_score if max_score else 0.0))

    def _build_kb_pattern(self, kb_entry: Dict[str, Any], kb_type: str) -> Dict[str, Any]:
        if kb_entry.get("incident_pattern"):
            pattern = dict(kb_entry.get("incident_pattern") or {})
            pattern.setdefault("use_case", self._normalize_use_case_key(pattern.get("use_case", "")))
            return pattern

        use_case = kb_entry.get("use_case") if kb_type == "true" else kb_entry.get("reported_as")
        manufacturer = kb_entry.get("manufacturer")
        model = kb_entry.get("model")
        pattern_fields: Dict[str, Any] = {}
        derived_tags = set()

        indicators = self._canonicalize_indicator_map(kb_entry.get("key_indicators", {}))
        tags = [str(tag).strip().lower() for tag in kb_entry.get("tags", []) if tag]
        blob = " ".join(
            str(part).lower()
            for part in (
                kb_entry.get("description"),
                kb_entry.get("actual_issue"),
                kb_entry.get("false_positive_reason"),
                kb_entry.get("resolution_summary"),
                kb_entry.get("resolution"),
                kb_entry.get("root_cause"),
            )
            if part
        )

        if indicators.get("red_light_flashing"):
            pattern_fields["light_pattern"] = "Red"
            derived_tags.add("red_light")
        if indicators.get("intermittent_chirp"):
            pattern_fields["sound_pattern"] = "Single chirp"
            derived_tags.add("chirping")
        if indicators.get("four_beep_pattern") or indicators.get("continuous_beeping"):
            pattern_fields["sound_pattern"] = "4 quick beeps"
            derived_tags.add("repeating_four_beep_pattern")
        if indicators.get("battery_low"):
            pattern_fields["likely_meaning"] = "Low battery"
            derived_tags.add("battery_issue")
        if indicators.get("alarm_out_of_date"):
            pattern_fields["likely_meaning"] = "End of life"
            derived_tags.add("end_of_life")
        if indicators.get("faulty_alarm"):
            pattern_fields["likely_meaning"] = "Fault"
            derived_tags.add("fault")
        if indicators.get("symptoms_present"):
            pattern_fields["symptom_level"] = "Yes - one person feels unwell"
            derived_tags.add("symptoms_present")
        if indicators.get("multiple_symptoms"):
            pattern_fields["symptom_level"] = "Yes - multiple people feel unwell"
            derived_tags.add("multiple_people_unwell")
        if indicators.get("is_safe_evacuated"):
            pattern_fields["safety_state"] = "Yes, we are outside/in fresh air"
            derived_tags.add("evacuated")
        if indicators.get("not_evacuated"):
            pattern_fields["safety_state"] = "No, still inside the property"
            derived_tags.add("not_evacuated")
        if indicators.get("co_alarm_type"):
            pattern_fields["alarm_type"] = "CO (Carbon Monoxide) alarm"
        if indicators.get("smoke_alarm_type"):
            pattern_fields["alarm_type"] = "Smoke alarm"
            derived_tags.add("smoke_alarm")
        if indicators.get("no_co_readings") or indicators.get("all_checks_clear") or indicators.get("no_gas_fault"):
            derived_tags.add("normal_pattern")
        if indicators.get("co_readings_detected"):
            derived_tags.add("possible_co_alarm")
            pattern_fields.setdefault("likely_meaning", "Possible CO alarm")

        if "charcoal" in blob:
            derived_tags.add("charcoal_trigger")
        if "paint" in blob or "voc" in blob:
            derived_tags.add("paint_voc_trigger")
        if "steam" in blob or "humidity" in blob:
            derived_tags.add("steam_humidity_trigger")
        if "electrical" in blob or "hard wired" in blob or "hard-wired" in blob:
            derived_tags.add("electrical_issue")
        if "smoke alarm" in blob:
            derived_tags.add("smoke_alarm")
        if "faulty" in blob and "alarm" in blob:
            derived_tags.add("fault")
        if "battery" in blob:
            derived_tags.add("battery_issue")
        if "expired" in blob or "out of date" in blob or "end of life" in blob:
            derived_tags.add("end_of_life")

        workflow_outcome = kb_entry.get("outcome")
        if not workflow_outcome and kb_type == "false":
            workflow_outcome = "close_with_guidance"

        return {
            "use_case": self._normalize_use_case_key(use_case or ""),
            "manufacturer": manufacturer,
            "model": model,
            "workflow_outcome": workflow_outcome,
            "pattern_fields": pattern_fields,
            "derived_tags": sorted(derived_tags | set(tags)),
        }

    def _find_best_match(
        self,
        incident_data: Dict[str, Any],
        use_case: str,
        kb_list: List[Dict[str, Any]],
        kb_type: str
    ) -> Tuple[Optional[Dict[str, Any]], float]:
        """
        Find best matching KB entry

        Returns:
            (best_match_entry, similarity_score)
        """
        best_match = None
        best_score = 0.0
        normalized_use_case = self._normalize_use_case_key(use_case)

        for kb_entry in kb_list:
            # Filter by use case if applicable (with normalization)
            if kb_type == "true":
                kb_uc = self._normalize_use_case_key(kb_entry.get("use_case") or "")
                if normalized_use_case and kb_uc and kb_uc != normalized_use_case:
                    # Allow partial matching (e.g. "gas smell" matches "gas smell detected")
                    if normalized_use_case not in kb_uc and kb_uc not in normalized_use_case:
                        continue

            # Calculate similarity score
            score = self._calculate_similarity(incident_data, kb_entry)

            if score > best_score:
                best_score = score
                best_match = kb_entry

        return best_match, best_score

    def _find_all_matches(
        self,
        incident_data: Dict[str, Any],
        use_case: str,
        kb_list: List[Dict[str, Any]],
        kb_type: str,
        threshold: float = 0.4
    ) -> List[Dict[str, Any]]:
        """
        Find all matching KB entries above threshold

        Returns:
            List of matches with scores and details
        """
        matches = []
        normalized_use_case = self._normalize_use_case_key(use_case)

        for kb_entry in kb_list:
            # Filter by use case if applicable (with normalization)
            if kb_type == "true":
                kb_uc = self._normalize_use_case_key(kb_entry.get("use_case") or "")
                if normalized_use_case and kb_uc and kb_uc != normalized_use_case:
                    # Allow partial matching
                    if normalized_use_case not in kb_uc and kb_uc not in normalized_use_case:
                        continue

            # Calculate similarity score
            score = self._calculate_similarity(incident_data, kb_entry)

            if score >= threshold:
                # Format entry based on type
                if kb_type == "true":
                    match_data = {
                        "kb_id": kb_entry.get("kb_id"),
                        "kb_type": "true",
                        "score": round(score, 3),
                        "incident_type": kb_entry.get("use_case", ""),
                        "description": kb_entry.get("description", ""),
                        "outcome": kb_entry.get("outcome", ""),
                        "resolution_summary": kb_entry.get("resolution_summary", ""),
                        "reason": kb_entry.get("root_cause", "")
                    }
                else:  # false
                    match_data = {
                        "kb_id": kb_entry.get("kb_id"),
                        "kb_type": "false",
                        "score": round(score, 3),
                        "incident_type": kb_entry.get("reported_as", ""),
                        "description": kb_entry.get("actual_issue", ""),
                        "outcome": "false_positive",
                        "resolution_summary": kb_entry.get("resolution", ""),
                        "reason": kb_entry.get("false_positive_reason", "")
                    }
                matches.append(match_data)

        # Sort by score descending
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches

    # Maps workflow variable values → KB indicator booleans so the matching
    # algorithm can bridge the gap between workflow structured_data (e.g.
    # "alarm_sound_pattern": "Single beep/chirp every 30-60 seconds") and
    # KB key_indicators (e.g. "intermittent_chirp": True).
    _WORKFLOW_TO_KB_MAP = {
        # CO alarm workflow fields → KB indicator keys
        "intermittent_chirp": lambda d: any(
            token in (d.get("alarm_sound_pattern") or "").lower()
            for token in ("chirp", "every 30", "every 48", "every minute", "every 60", "single beep")
        ) or any(
            token in d.get("_text_blob", "")
            for token in ("low battery", "single beep every", "chirp every", "intermittent beep", "intermittent beeping")
        ),
        "every_30_60_seconds": lambda d: "30-60" in (d.get("alarm_sound_pattern") or "") or "every 30" in (d.get("alarm_sound_pattern") or "").lower() or "every 60" in (d.get("alarm_sound_pattern") or "").lower(),
        "continuous_beeping": lambda d: "continuous" in (d.get("alarm_sound_pattern") or "").lower() or "non-stop" in (d.get("alarm_sound_pattern") or "").lower(),
        "four_beep_pattern": lambda d: any(
            token in (d.get("alarm_sound_pattern") or "").lower()
            for token in ("4 loud beeps", "4 beeps", "4 quick beeps", "loud pulses", "loud alarm pulses", "co alarm pattern")
        ) or any(
            token in d.get("_text_blob", "")
            for token in ("4 quick beeps", "loud pulses", "loud alarm pulses", "co alarm pattern")
        ),
        "alarm_memory": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("alarm memory", "red blink every 60", "red | 1 blink every 60", "red led blinks once every 60", "red led blinks 1 time every 60")
        ),
        "memory_fault": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("memory fault", "amber 3 blinks", "amber | 3 blinks", "amber led blinks 3 times every 30", "3 times every 30")
        ),
        "co_fault": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("co fault", "amber 5 blinks", "amber | 5 blinks", "amber led blinks 5 times every 30", "5 times every 30")
        ),
        "mcu_failure": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("mcu failure", "constant tone")
        ),
        "stuck_button": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("stuck button", "every 5 sec")
        ),
        "test_mode": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("test beep pattern", "green and amber", "test lights and beeps")
        ),
        "alarm_stopped": lambda d: "stopped" in (d.get("alarm_sound_pattern") or "").lower(),
        "no_symptoms": lambda d: "no symptom" in (d.get("co_symptoms") or "").lower(),
        "symptoms_present": lambda d: "feel unwell" in (d.get("co_symptoms") or "").lower() or "headache" in (d.get("co_symptoms") or "").lower(),
        "multiple_symptoms": lambda d: "multiple" in (d.get("co_symptoms") or "").lower(),
        "battery_low": lambda d: (
            "chirp" in (d.get("alarm_sound_pattern") or "").lower()
            and "no symptom" in (d.get("co_symptoms") or "").lower()
        ) or any(
            token in d.get("_text_blob", "")
            for token in ("battery", "low battery", "replace batteries", "battery / power issue", "amber blink + chirp every 60", "amber blink every 60", "amber | 1 blink every 60")
        ),
        "alarm_over_7_years": lambda d: "over 7" in (d.get("alarm_age") or "").lower() or "expired" in (d.get("alarm_age") or "").lower() or "end of life" in d.get("_text_blob", "") or "2 chirps every 60" in d.get("_text_blob", "") or "amber 2 blinks every 60" in d.get("_text_blob", "") or "amber | 2 blinks every 60" in d.get("_text_blob", ""),
        "alarm_out_of_date": lambda d: "over 7" in (d.get("alarm_age") or "").lower() or "expired" in (d.get("alarm_age") or "").lower() or "out of date" in d.get("_text_blob", "") or "end of life" in d.get("_text_blob", "") or "2 chirps every 60" in d.get("_text_blob", "") or "amber 2 blinks every 60" in d.get("_text_blob", "") or "amber | 2 blinks every 60" in d.get("_text_blob", ""),
        "alarm_5_to_7_years": lambda d: "5-7" in (d.get("alarm_age") or ""),
        "no_co_readings": lambda d: (
            "no symptom" in (d.get("co_symptoms") or "").lower()
            and ("stopped" in (d.get("alarm_sound_pattern") or "").lower() or "chirp" in (d.get("alarm_sound_pattern") or "").lower())
        ) or any(
            token in d.get("_text_blob", "")
            for token in ("no co readings", "no readings", "no co found", "no trace", "all checks clear")
        ),
        "co_readings_detected": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("co detected", "co reading", "ppm", "dangerous co", "rising co")
        ) and not any(
            token in d.get("_text_blob", "")
            for token in ("no co", "no readings", "no trace", "no co found")
        ),
        "is_safe_evacuated": lambda d: "outside" in (d.get("is_safe") or "").lower() or "fresh air" in (d.get("is_safe") or "").lower(),
        "not_evacuated": lambda d: "still inside" in (d.get("is_safe") or "").lower() or "still inside" in (d.get("is_evacuated") or "").lower(),
        "red_light_flashing": lambda d: "red" in (d.get("alarm_light_colour") or "").lower(),
        "no_light": lambda d: "no light" in (d.get("alarm_light_colour") or "").lower(),
        "co_alarm_type": lambda d: str(d.get("alarm_type", "")).lower().startswith("co"),
        "smoke_alarm_type": lambda d: "smoke" in str(d.get("alarm_type") or "").lower(),
        "faulty_alarm": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("faulty alarm", "sensor fault", "device issue", "product issue", "alarm fault", "defective alarm", "amber 3 blinks", "amber 5 blinks", "amber | 3 blinks", "amber | 5 blinks", "constant tone")
        ),
        "tightness_test_passed": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("tightness test passed", "tt pass", "tt passed")
        ),
        "tt_passed": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("tightness test passed", "tt pass", "tt passed")
        ),
        "all_checks_clear": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("all checks clear", "appliances checked clear", "all clear")
        ),
        "no_gas_fault": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("no gas fault", "appliances checked clear", "no fault found", "no signs evident", "all checks clear")
        ),
        "portable_alarm_not_activated": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("portable alarm not activated", "portable co alarm did not", "second alarm not activated", "other alarm not active", "newer alarm not active")
        ),
        "other_alarm_not_active": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("portable alarm not activated", "second alarm not activated", "other alarm not active", "newer alarm not active")
        ),
        "hard_wired_alarm": lambda d: "hard wired" in d.get("_text_blob", "") or "hard-wired" in d.get("_text_blob", ""),
        "all_alarms_activated": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("all alarms activated", "all went off", "same circuit")
        ),
        "electrical_fault_suspected": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("electrical fault", "shared fuse", "electrics checked")
        ),
        "paint_smell_present": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("paint smell", "paint fumes", "varnish", "voc", "cleaning chemical")
        ),
        "recent_decorating": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("decorating", "painted", "fresh paint", "varnish")
        ),
        "alarm_triggered_by_voc": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("voc", "paint fumes", "cleaning chemical")
        ),
        "charcoal_burning": lambda d: "charcoal" in d.get("_text_blob", ""),
        "near_co_alarm": lambda d: "near co alarm" in d.get("_text_blob", "") or "near alarm" in d.get("_text_blob", ""),
        "appliances_checked_clear": lambda d: any(
            token in d.get("_text_blob", "")
            for token in ("appliances checked clear", "all checks clear")
        ),
        "high_humidity": lambda d: "humidity" in d.get("_text_blob", ""),
        "steam_present": lambda d: "steam" in d.get("_text_blob", ""),
        "alarm_near_bathroom": lambda d: "bathroom" in d.get("_text_blob", ""),
        "alarm_fell": lambda d: any(token in d.get("_text_blob", "") for token in ("fell from ceiling", "alarm fell", "dropped alarm")),
        "impact_triggered": lambda d: any(token in d.get("_text_blob", "") for token in ("impact", "fell from ceiling", "dropped")),
        "heat_alarm_activated": lambda d: "heat alarm" in d.get("_text_blob", "") or "heat element" in d.get("_text_blob", ""),
        "combined_heat_co": lambda d: "combined heat" in d.get("_text_blob", "") or "heat/co" in d.get("_text_blob", ""),
        # Gas smell workflow fields
        "strong_mercaptan_odour": lambda d: "strong" in (d.get("smell_intensity") or "").lower() or "overwhelming" in (d.get("smell_intensity") or "").lower(),
        "health_symptoms_headache": lambda d: "headache" in (d.get("symptoms") or "").lower() or "feel unwell" in (d.get("symptoms") or "").lower(),
        "health_symptoms_nausea": lambda d: "nausea" in (d.get("symptoms") or "").lower() or "feel unwell" in (d.get("symptoms") or "").lower(),
        "hissing_sound": lambda d: "yes" in str(d.get("hissing_sound") or "").lower() or str(d.get("hissing_sound") or "").lower() == "true",
        "near_meter": lambda d: "meter" in (d.get("smell_location") or "").lower(),
        "smell_near_appliance": lambda d: "appliance" in (d.get("smell_location") or "").lower() or "boiler" in (d.get("smell_location") or "").lower(),
        # CO condensation/flames
        "flue_blocked": lambda d: "blocked" in (d.get("flue_condition") or "").lower(),
        "co_alarm_sounding": lambda d: "sounding" in (d.get("co_alarm") or "").lower(),
        "soot_visible": lambda d: "soot" in (d.get("soot_visible") or "").lower() or "black" in (d.get("soot_visible") or "").lower(),
    }

    _USE_CASE_ALIASES = {
        "co2_alarm": "co_alarm",
        "co_fumes": "co_visible_fumes",
        "gas_escape": "gas_smell",
    }

    _INDICATOR_ALIASES = {
        "intermittent_beep": "intermittent_chirp",
        "intermittent_beeping": "intermittent_chirp",
        "tt_passed": "tightness_test_passed",
        "second_alarm_not_activated": "other_alarm_not_active",
        "portable_alarm_not_activated": "other_alarm_not_active",
        "newer_alarm_not_active": "other_alarm_not_active",
        "appliances_checked_clear": "all_checks_clear",
        "alarm_5_years_expired": "alarm_out_of_date",
        "alarm_over_7_years": "alarm_out_of_date",
    }

    _INDICATOR_WEIGHTS = {
        "co_readings_detected": 1.7,
        "no_co_readings": 1.7,
        "no_gas_fault": 1.6,
        "four_beep_pattern": 1.5,
        "continuous_beeping": 1.4,
        "strong_mercaptan_odour": 1.5,
        "hissing_sound": 1.5,
        "flue_blocked": 1.4,
        "soot_visible": 1.4,
        "red_light_flashing": 1.3,
        "co_alarm_type": 0.8,
        "symptoms_present": 1.1,
        "multiple_symptoms": 1.2,
        "not_evacuated": 1.1,
        "is_safe_evacuated": 1.0,
        "intermittent_chirp": 1.2,
        "battery_low": 1.3,
        "alarm_memory": 1.4,
        "memory_fault": 1.3,
        "co_fault": 1.3,
        "mcu_failure": 1.3,
        "stuck_button": 1.2,
        "test_mode": 1.1,
        "alarm_out_of_date": 1.2,
        "alarm_over_7_years": 1.2,
        "smoke_alarm_type": 1.2,
    }

    def _normalize_use_case_key(self, use_case: str) -> str:
        raw = (use_case or "").lower().strip()
        aliased = self._USE_CASE_ALIASES.get(raw, raw)
        return aliased.replace("_", " ").strip()

    def _indicator_weight(self, indicator_name: str) -> float:
        """Return the weight for a KB indicator."""
        return float(self._INDICATOR_WEIGHTS.get(self._canonicalize_indicator_name(indicator_name), 1.0))

    def _canonicalize_indicator_name(self, indicator_name: str) -> str:
        return self._INDICATOR_ALIASES.get(indicator_name, indicator_name)

    def _canonicalize_indicator_map(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        canonical: Dict[str, Any] = {}
        for key, value in (indicators or {}).items():
            canonical_key = self._canonicalize_indicator_name(key)
            if canonical_key not in canonical:
                canonical[canonical_key] = value
                continue

            existing = canonical[canonical_key]
            if isinstance(existing, bool) and isinstance(value, bool):
                canonical[canonical_key] = existing or value
            elif existing in (None, "", False) and value not in (None, "", False):
                canonical[canonical_key] = value
        return canonical

    def _specificity_factor(self, kb_indicators: Dict[str, Any]) -> float:
        """Penalize sparse KB entries so generic 2-indicator entries don't max out."""
        kb_indicators = self._canonicalize_indicator_map(kb_indicators)
        if not kb_indicators:
            return 1.0

        total_weight = sum(self._indicator_weight(key) for key in kb_indicators)
        indicator_count = len(kb_indicators)
        count_factor = min(1.0, indicator_count / 4.0)
        weight_factor = min(1.0, total_weight / 4.5)
        return 0.55 + (0.45 * max(count_factor, weight_factor))

    def _support_score(self, matches: List[Dict[str, Any]], top_n: int = 3) -> float:
        """Average score of the strongest matches, used as a binary tie-breaker."""
        if not matches:
            return 0.0
        top_matches = matches[:top_n]
        return sum(match.get("score", 0.0) for match in top_matches) / len(top_matches)

    def _normalize_incident_data(self, incident_data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(incident_data or {})

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
        kidde_indicator_pattern = next(
            (
                str(value)
                for key, value in normalized.items()
                if key.lower().startswith("kidde")
                and key.lower().endswith("_indicator_pattern")
                and value not in (None, "")
            ),
            "",
        )
        kidde_visual_pattern = next(
            (
                str(value)
                for key, value in normalized.items()
                if key.lower().startswith("kidde")
                and key.lower().endswith("_visual_pattern")
                and value not in (None, "")
            ),
            "",
        )
        kidde_visual_colour = next(
            (
                str(value)
                for key, value in normalized.items()
                if key.lower().startswith("kidde")
                and key.lower().endswith("_visual_colour")
                and value not in (None, "")
            ),
            "",
        )
        kidde_visual_cadence = next(
            (
                str(value)
                for key, value in normalized.items()
                if key.lower().startswith("kidde")
                and key.lower().endswith("_visual_cadence")
                and value not in (None, "")
            ),
            "",
        )
        kidde_sound_pattern = next(
            (
                str(value)
                for key, value in normalized.items()
                if key.lower().startswith("kidde")
                and key.lower().endswith("_sound_pattern")
                and value not in (None, "")
            ),
            "",
        )
        kidde_observed_pattern = " | ".join(
            part
            for part in (
                kidde_visual_colour,
                kidde_visual_cadence,
                kidde_visual_pattern,
                kidde_sound_pattern,
                kidde_indicator_pattern,
            )
            if part
        )
        if not normalized.get("alarm_light_colour") and kidde_observed_pattern:
            pattern_lower = kidde_observed_pattern.lower()
            if "red" in pattern_lower:
                normalized["alarm_light_colour"] = "Red"
            elif "amber" in pattern_lower:
                normalized["alarm_light_colour"] = "Amber"
            elif "green" in pattern_lower:
                normalized["alarm_light_colour"] = "Green"
            elif "no led" in pattern_lower or "no light" in pattern_lower:
                normalized["alarm_light_colour"] = "No light"
        if not normalized.get("alarm_light_colour"):
            value = self._find_dynamic_answer_value(normalized, suffixes=("light", "led"))
            if value:
                normalized["alarm_light_colour"] = value

        if not normalized.get("alarm_sound_pattern"):
            if normalized.get("fa_red_sound"):
                normalized["alarm_sound_pattern"] = str(normalized["fa_red_sound"])
            elif normalized.get("fh_beeps"):
                normalized["alarm_sound_pattern"] = str(normalized["fh_beeps"])
            elif normalized.get("kidde_red_sound"):
                normalized["alarm_sound_pattern"] = str(normalized["kidde_red_sound"])
            elif kidde_sound_pattern:
                normalized["alarm_sound_pattern"] = kidde_sound_pattern
            elif kidde_indicator_pattern:
                normalized["alarm_sound_pattern"] = kidde_indicator_pattern
            elif normalized.get("gen_sound"):
                normalized["alarm_sound_pattern"] = str(normalized["gen_sound"])
            elif normalized.get("co_alarm_status"):
                normalized["alarm_sound_pattern"] = str(normalized["co_alarm_status"])
            elif normalized.get("kidde_amber_count") == "1 flash":
                normalized["alarm_sound_pattern"] = "chirp every minute"
            elif normalized.get("aico_flashes") == "1 flash":
                normalized["alarm_sound_pattern"] = "chirp every 48 seconds"
            elif normalized.get("xs_flashes") == "1 flash":
                normalized["alarm_sound_pattern"] = "chirp every minute"
            elif normalized.get("xs_led") == "Red (steady, not flashing)":
                normalized["alarm_sound_pattern"] = "alarm silenced / stopped"
        if not normalized.get("alarm_sound_pattern"):
            value = self._find_dynamic_answer_value(
                normalized,
                suffixes=("sound", "voice", "alert", "beeps"),
            )
            if value:
                normalized["alarm_sound_pattern"] = value

        if not normalized.get("co_alarm"):
            co_alarm_status = str(normalized.get("co_alarm_status", "")).lower()
            if "sounding" in co_alarm_status:
                normalized["co_alarm"] = "sounding"

        if not normalized.get("hissing_sound") and normalized.get("has_hissing"):
            normalized["hissing_sound"] = normalized.get("has_hissing")

        text_parts = [
            normalized.get("description"),
            normalized.get("incident_type"),
            normalized.get("location"),
            normalized.get("alarm_type"),
            normalized.get("alarm_sound_pattern"),
            normalized.get("alarm_light_colour"),
            normalized.get("co_symptoms"),
            normalized.get("is_safe"),
            normalized.get("co_alarm_status"),
            normalized.get("manufacturer"),
            normalized.get("model_number"),
            normalized.get("manufacturer_triage_message"),
            normalized.get("manufacturer_triage_outcome"),
            normalized.get("last_subworkflow_message"),
            normalized.get("last_subworkflow_outcome"),
            kidde_observed_pattern,
            normalized.get("kidde1_reset_result"),
            normalized.get("kidde1_state"),
            normalized.get("resolution_summary"),
            normalized.get("notes"),
        ]
        normalized["_text_blob"] = " | ".join(
            str(part).lower() for part in text_parts if part not in (None, "")
        )

        return normalized

    def _find_dynamic_answer_value(
        self,
        incident_data: Dict[str, Any],
        suffixes: Tuple[str, ...],
    ) -> Optional[str]:
        candidates: List[Tuple[str, str]] = []
        blocked_suffixes = (
            "_score",
            "_normalized_score",
            "_calculate_score",
            "_risk_switch",
            "_model",
            "_switch",
        )

        for key, value in incident_data.items():
            if value in (None, "", [], {}):
                continue
            if not isinstance(value, str):
                continue
            if any(key.endswith(blocked) for blocked in blocked_suffixes):
                continue
            lowered = key.lower()
            if not any(lowered.endswith(f"_{suffix}") or lowered == suffix for suffix in suffixes):
                continue
            candidates.append((key, value))

        if not candidates:
            return None

        preferred_prefixes = (
            "kidde",
            "fa",
            "fh",
            "xc",
            "xs",
            "hw",
            "nest",
            "net",
            "cav",
            "other",
            "aico",
            "gen",
        )
        candidates.sort(
            key=lambda item: (
                0 if any(item[0].lower().startswith(prefix) for prefix in preferred_prefixes) else 1,
                len(item[0]),
            )
        )
        return candidates[0][1]

    def build_incident_pattern(
        self,
        incident_data: Dict[str, Any],
        use_case: str,
        workflow_outcome: Optional[str] = None,
        incident_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a normalized workflow-answer pattern for the incident.

        This is stored separately from verified true/false KB so new incidents
        can be matched and reviewed later without polluting the curated KB.
        """
        normalized = self._normalize_incident_data(incident_data)
        manufacturer, model = self._extract_manufacturer_model(normalized)

        pattern = {
            "incident_id": incident_id,
            "use_case": self._normalize_use_case_key(use_case),
            "manufacturer": manufacturer,
            "model": model,
            "workflow_outcome": workflow_outcome,
            "pattern_fields": self._extract_pattern_fields(normalized),
            "derived_tags": sorted(self._derive_incident_tags(normalized)),
            "created_at": datetime.utcnow().isoformat(),
            "verification_status": "pending",
        }

        return pattern

    def add_incident_pattern(self, pattern: Dict[str, Any]) -> Optional[str]:
        """Store a newly created incident pattern separately from verified KB."""
        if not pattern or not pattern.get("incident_id"):
            return None

        incident_id = str(pattern["incident_id"])
        existing_idx = next(
            (idx for idx, entry in enumerate(self.incident_patterns) if str(entry.get("incident_id")) == incident_id),
            None,
        )
        if existing_idx is not None:
            self.incident_patterns[existing_idx] = pattern
        else:
            self.incident_patterns.append(pattern)

        logger.info("Stored incident pattern: %s", incident_id)

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            loop.create_task(self._persist_incident_pattern(pattern))
        except RuntimeError:
            pass

        return incident_id

    def promote_incident_to_verified_kb(
        self,
        incident: Any,
        target_type: str,
        reviewed_by: str = "system",
        review_notes: Optional[str] = None,
    ) -> Optional[str]:
        """
        Add or move an incident into the verified true/false KB bucket.

        If the incident already exists in the opposite bucket, it is removed and
        recreated in the requested target bucket.
        """
        if target_type not in ("true", "false") or not incident:
            return None

        use_case_label = incident.incident_type or getattr(incident, "classified_use_case", None) or "Unknown"
        incident_pattern = incident.incident_pattern or self.build_incident_pattern(
            incident.structured_data or {},
            use_case=use_case_label,
            workflow_outcome=getattr(incident.outcome, "value", incident.outcome),
            incident_id=incident.incident_id,
        )

        # Remove from the opposite side if present
        opposite_type = "false" if target_type == "true" else "true"
        opposite_entry = self._find_verified_entry_by_incident_id(incident.incident_id, opposite_type)
        if opposite_entry:
            self.delete_kb_entry(opposite_entry.get("kb_id"), opposite_type)

        existing_entry = self._find_verified_entry_by_incident_id(incident.incident_id, target_type)
        entry = self._build_verified_kb_entry(
            incident=incident,
            incident_pattern=incident_pattern,
            kb_type=target_type,
            reviewed_by=reviewed_by,
            review_notes=review_notes,
            existing_kb_id=existing_entry.get("kb_id") if existing_entry else None,
        )

        if existing_entry:
            self.update_kb_entry(existing_entry["kb_id"], target_type, entry)
            return existing_entry["kb_id"]

        if target_type == "true":
            return self.add_true_incident(entry)
        return self.add_false_incident(entry)

    def _find_verified_entry_by_incident_id(self, incident_id: str, kb_type: str) -> Optional[Dict[str, Any]]:
        kb_list = self.true_incidents_kb if kb_type == "true" else self.false_incidents_kb
        for entry in kb_list:
            if str(entry.get("incident_id")) == str(incident_id):
                return entry
        return None

    def _build_verified_kb_entry(
        self,
        incident: Any,
        incident_pattern: Dict[str, Any],
        kb_type: str,
        reviewed_by: str,
        review_notes: Optional[str],
        existing_kb_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        use_case_label = incident.incident_type or getattr(incident, "classified_use_case", None) or "Unknown"
        description = getattr(incident, "description", "") or ""
        pattern_fields = incident_pattern.get("pattern_fields", {}) or {}
        likely_meaning = pattern_fields.get("likely_meaning") or "Pattern-derived incident classification"
        resolution_summary = review_notes or getattr(incident, "resolution_notes", "") or ""
        workflow_outcome = getattr(incident.outcome, "value", incident.outcome)
        base = {
            "kb_id": existing_kb_id,
            "tenant_id": getattr(incident, "tenant_id", None),
            "incident_id": incident.incident_id,
            "source": "incident_review",
            "verified_by": reviewed_by,
            "verified_at": now,
            "created_at": now if not existing_kb_id else None,
            "incident_pattern": incident_pattern,
            "tags": sorted(set((incident_pattern.get("derived_tags", []) or []) + ["incident_review", use_case_label.lower().replace(" ", "_")])),
            "review_notes": review_notes,
        }

        if kb_type == "true":
            base.update({
                "use_case": use_case_label,
                "description": description or f"Verified true incident for {use_case_label}",
                "key_indicators": {},
                "risk_factors": {},
                "outcome": workflow_outcome or "monitor",
                "root_cause": likely_meaning,
                "actions_taken": [],
                "resolution_summary": resolution_summary or "Reviewed and confirmed as true incident.",
            })
        else:
            base.update({
                "reported_as": use_case_label,
                "actual_issue": likely_meaning,
                "false_positive_reason": resolution_summary or "Reviewed and confirmed as false report.",
                "key_indicators": {},
                "resolution": resolution_summary or "Reviewed and confirmed as false report.",
            })

        return {k: v for k, v in base.items() if v is not None}

    def _extract_manufacturer_model(self, incident_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        manufacturer = None
        model = None

        manufacturer_field = incident_data.get("alarm_manufacturer") or incident_data.get("manufacturer")
        if manufacturer_field and str(manufacturer_field).strip():
            manufacturer = str(manufacturer_field).strip()

        model_fields = (
            "aico_model", "cav_model", "fa_model", "fh_model", "hw_model",
            "kidde_model", "net_model", "nest_model", "other_model", "xs_model",
            "model_number", "manufacturer_model", "model",
        )
        for key in model_fields:
            value = incident_data.get(key)
            if value not in (None, ""):
                model = str(value).strip()
                break

        return manufacturer, model

    def _extract_pattern_fields(self, incident_data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_incident_data(incident_data)
        fields = {
            "safety_state": normalized.get("is_safe"),
            "symptom_level": normalized.get("co_symptoms"),
            "alarm_type": normalized.get("alarm_type"),
            "light_pattern": normalized.get("alarm_light_colour"),
            "sound_pattern": normalized.get("alarm_sound_pattern"),
            "state_now": self._pick_first_value(
                normalized,
                (
                    "fa_now", "fh_now", "aico3030_now", "aico3018_now", "aico3028_now",
                    "aico208_now", "aicogen_now", "kidde_now", "xs_now", "hw_now",
                    "net_now", "nest_now", "cav_now", "other_now", "co_alarm_status",
                ),
            ),
            "repeat_pattern": self._pick_first_value(
                normalized,
                (
                    "fa_repeat", "fh_repeat", "aico3030_timing", "aico3018_timing",
                    "aico3028_timing", "aico208_timing", "aicogen_timing",
                    "kidde_repeat", "xs_repeat", "hw_repeat", "net_repeat",
                    "nest_repeat", "cav_repeat", "other_repeat",
                ),
            ),
            "likely_meaning": self._pick_first_value(
                normalized,
                (
                    "fa_summary", "fh_summary", "aico3030_summary", "aico3018_summary",
                    "aico3028_summary", "aico208_summary", "aicogen_summary",
                    "kidde_summary", "xs_summary", "hw_summary", "net_summary",
                    "nest_summary", "cav_summary", "other_summary",
                ),
            ),
        }

        if not fields["state_now"]:
            fields["state_now"] = self._find_dynamic_answer_value(normalized, suffixes=("now",))
        if not fields["repeat_pattern"]:
            fields["repeat_pattern"] = self._find_dynamic_answer_value(
                normalized,
                suffixes=("repeat", "pattern", "timing"),
            )
        if not fields["likely_meaning"]:
            fields["likely_meaning"] = self._find_dynamic_answer_value(
                normalized,
                suffixes=("issue", "summary", "hint", "app"),
            )

        return {key: value for key, value in fields.items() if value not in (None, "")}

    def _pick_first_value(self, incident_data: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[Any]:
        for key in keys:
            value = incident_data.get(key)
            if value not in (None, ""):
                return value
        return None

    def _derive_incident_tags(self, incident_data: Dict[str, Any]) -> List[str]:
        normalized = self._normalize_incident_data(incident_data)
        tags = set()

        light = str(normalized.get("alarm_light_colour", "")).lower()
        sound = str(normalized.get("alarm_sound_pattern", "")).lower()
        symptoms = str(normalized.get("co_symptoms", "")).lower()
        safety = str(normalized.get("is_safe", "")).lower()
        likely = str(self._extract_pattern_fields(normalized).get("likely_meaning", "")).lower()

        if "red" in light:
            tags.add("red_light")
        if "amber" in light or "yellow" in light:
            tags.add("amber_or_yellow_light")
        if "green" in light:
            tags.add("green_light")

        if "4" in sound and ("beep" in sound or "chirp" in sound):
            tags.add("repeating_four_beep_pattern")
        if "chirp" in sound:
            tags.add("chirping")
        if "silent" in sound:
            tags.add("silent")

        if "outside" in safety or "fresh air" in safety:
            tags.add("evacuated")
        if "inside" in safety:
            tags.add("not_evacuated")
        if "cannot move" in safety:
            tags.add("immobile_occupant")

        if "multiple" in symptoms:
            tags.add("multiple_people_unwell")
        elif symptoms and "no symptoms" not in symptoms:
            tags.add("symptoms_present")

        if "possible co alarm" in likely or "co alarm" in likely:
            tags.add("possible_co_alarm")
        if "battery" in likely:
            tags.add("battery_issue")
        if "end of life" in likely:
            tags.add("end_of_life")
        if "fault" in likely:
            tags.add("fault")
        if "normal" in likely:
            tags.add("normal_pattern")

        return list(tags)

    def _derive_kb_indicators(self, incident_data: Dict[str, Any]) -> Dict[str, bool]:
        """Derive KB-style boolean indicators from workflow structured data."""
        incident_data = self._normalize_incident_data(incident_data)
        derived = {}
        for indicator, check_fn in self._WORKFLOW_TO_KB_MAP.items():
            try:
                result = check_fn(incident_data)
                if result:
                    derived[self._canonicalize_indicator_name(indicator)] = True
            except Exception:
                pass
        return derived

    def _calculate_similarity(
        self,
        incident_data: Dict[str, Any],
        kb_entry: Dict[str, Any]
    ) -> float:
        """
        Calculate similarity score between incident and KB entry.

        Uses key indicators matching when available, falls back to
        text-based description matching for external/backfilled incidents
        that lack structured indicators.
        """
        kb_indicators = self._canonicalize_indicator_map(kb_entry.get("key_indicators", {}))
        incident_data = self._normalize_incident_data(incident_data)

        # Derive KB-style indicators from workflow structured data
        derived_indicators = self._derive_kb_indicators(incident_data)
        # Merge: original incident_data fields + derived boolean indicators
        merged_data = {**incident_data, **derived_indicators}
        merged_data = {
            **merged_data,
            **{
                self._canonicalize_indicator_name(key): value
                for key, value in merged_data.items()
            },
        }

        # --- Indicator-based matching ---
        matched_weight = 0.0
        checked_weight = 0.0
        contradicted_weight = 0.0
        total_weight = sum(self._indicator_weight(key) for key in kb_indicators) if kb_indicators else 0.0

        if kb_indicators:
            for key, expected_value in kb_indicators.items():
                actual_value = merged_data.get(key)
                weight = self._indicator_weight(key)

                if actual_value is None:
                    continue  # Skip indicators not present in incident data

                checked_weight += weight
                if self._values_match(actual_value, expected_value):
                    matched_weight += weight
                else:
                    contradicted_weight += weight

        if checked_weight > 0 and total_weight > 0:
            precision = matched_weight / checked_weight if checked_weight else 0.0
            coverage = checked_weight / total_weight
            contradiction_ratio = contradicted_weight / checked_weight if checked_weight else 0.0
            specificity = self._specificity_factor(kb_indicators)

            # Sparse/generic entries should not reach 1.0 too easily.
            coverage_factor = 0.35 + (0.65 * coverage)
            contradiction_factor = max(0.25, 1.0 - (0.7 * contradiction_ratio))
            similarity = precision * coverage_factor * specificity * contradiction_factor
            return max(0.0, min(1.0, similarity))

        # --- Text-based fallback for incidents without key_indicators ---
        incident_desc = (incident_data.get("description") or "").lower()
        # True KB entries have "description"; false KB entries have
        # "actual_issue" + "false_positive_reason" instead.
        kb_desc = (
            kb_entry.get("description")
            or " ".join(filter(None, [
                kb_entry.get("actual_issue", ""),
                kb_entry.get("false_positive_reason", ""),
            ]))
        ).lower()
        if not incident_desc or not kb_desc:
            return 0.0

        return self._text_similarity(incident_desc, kb_desc)

    def _text_similarity(self, text_a: str, text_b: str) -> float:
        """Compute word-overlap similarity between two text strings.

        Uses a simple Jaccard-like metric on meaningful words (length >= 3),
        weighted toward important domain terms.  Returns 0.0 – 1.0.
        """
        # Domain-important terms get extra weight
        DOMAIN_TERMS = {
            "gas", "leak", "smell", "odour", "odor", "hissing", "meter",
            "boiler", "flue", "flame", "explosion", "carbon", "monoxide",
            "co", "mercaptan", "pipe", "pressure", "headache", "nausea",
            "dizziness", "soot", "corrosion", "corroded", "excavation",
            "alarm", "detector", "methane", "emergency", "evacuate",
            "isolated", "rotten", "egg", "poisoning", "fatality",
            "condensate", "frozen", "tampering", "bypass", "cooking",
            "ventilation", "appliance", "burner", "kitchen", "fire",
        }
        STOP_WORDS = {
            "the", "and", "was", "were", "has", "had", "for", "with",
            "that", "this", "from", "are", "been", "have", "not",
            "but", "they", "which", "their", "into", "also", "than",
            "its", "can", "all", "will", "one", "two", "being",
        }

        def tokenize(text: str) -> List[str]:
            return [w for w in re.findall(r"[a-z]+", text)
                    if len(w) >= 3 and w not in STOP_WORDS]

        words_a = tokenize(text_a)
        words_b = tokenize(text_b)
        if not words_a or not words_b:
            return 0.0

        set_a = set(words_a)
        set_b = set(words_b)
        common = set_a & set_b
        if not common:
            return 0.0

        # Weight domain terms 2x
        weighted_common = sum(2.0 if w in DOMAIN_TERMS else 1.0 for w in common)
        weighted_union = sum(2.0 if w in DOMAIN_TERMS else 1.0 for w in (set_a | set_b))

        raw_score = weighted_common / weighted_union if weighted_union else 0.0

        # Scale into a useful range: raw Jaccard on long texts is typically low,
        # so we apply a gentle boost to push meaningful matches above the 0.6 threshold.
        # A raw score of 0.25+ (strong overlap) → ~0.75 after scaling.
        scaled = min(1.0, raw_score * 3.0)
        return scaled

    def _values_match(self, actual: Any, expected: Any) -> bool:
        """Check if two values match (with fuzzy matching for strings)"""
        if type(actual) != type(expected):
            # Try string comparison
            return str(actual).lower() == str(expected).lower()

        if isinstance(actual, bool):
            return actual == expected

        if isinstance(actual, (int, float)):
            # Numeric tolerance
            return abs(actual - expected) < 0.1

        if isinstance(actual, str):
            # Fuzzy string matching
            return actual.lower() == expected.lower()

        return actual == expected

    def add_true_incident(self, incident_data: Dict[str, Any]) -> str:
        """Add a verified true incident to KB"""
        import asyncio
        kb_id = self._next_verified_kb_id("true")
        now = datetime.utcnow().isoformat()
        entry = {
            "kb_id": kb_id,
            "verified_at": now,
            "created_at": now,
            "source": incident_data.get("source", "manual"),
            **incident_data
        }
        self.true_incidents_kb.append(entry)
        logger.info(f"Added true incident to KB: {kb_id}")
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._persist_entry("true", entry))
        except RuntimeError:
            pass
        return kb_id

    def add_false_incident(self, incident_data: Dict[str, Any]) -> str:
        """Add a verified false incident to KB"""
        import asyncio
        kb_id = self._next_verified_kb_id("false")
        now = datetime.utcnow().isoformat()
        entry = {
            "kb_id": kb_id,
            "verified_at": now,
            "created_at": now,
            "source": incident_data.get("source", "manual"),
            **incident_data
        }
        self.false_incidents_kb.append(entry)
        logger.info(f"Added false incident to KB: {kb_id}")
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._persist_entry("false", entry))
        except RuntimeError:
            pass
        return kb_id

    def _next_verified_kb_id(self, kb_type: str) -> str:
        kb_list = self.true_incidents_kb if kb_type == "true" else self.false_incidents_kb
        prefix = "true" if kb_type == "true" else "false"
        max_num = 0

        for entry in kb_list:
            raw_id = str(entry.get("kb_id") or "").strip().lower()
            if not raw_id.startswith(f"{prefix}_"):
                continue
            suffix = raw_id.split("_", 1)[1].strip()
            if suffix.isdigit():
                max_num = max(max_num, int(suffix))

        return f"{prefix}_{max_num + 1:03d}"

    def get_true_incidents(self) -> List[Dict[str, Any]]:
        """Get all true incidents from KB"""
        return self.true_incidents_kb

    def get_false_incidents(self) -> List[Dict[str, Any]]:
        """Get all false incidents from KB"""
        return self.false_incidents_kb

    def search_kb(
        self,
        query: str,
        kb_type: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search KB entries by text query

        Args:
            query: Search text
            kb_type: "true" or "false" or None for both
            limit: Max results
            offset: Zero-based offset for pagination
            tenant_id: Optional tenant filter (includes global entries)

        Returns:
            Paginated matching KB entries
        """
        results = []
        query_lower = query.lower()

        def matches_tenant(entry: Dict[str, Any]) -> bool:
            if not tenant_id:
                return True
            return entry.get("tenant_id") in (None, tenant_id)

        def entry_matches(entry: Dict[str, Any], text_fields: List[str]) -> bool:
            haystacks = []
            for field in text_fields:
                value = entry.get(field, "")
                if value:
                    haystacks.append(str(value).lower())

            incident_pattern = entry.get("incident_pattern") or {}
            manufacturer = entry.get("manufacturer") or incident_pattern.get("manufacturer")
            model = entry.get("model") or incident_pattern.get("model")
            if manufacturer:
                haystacks.append(str(manufacturer).lower())
            if model:
                haystacks.append(str(model).lower())

            tags = " ".join(entry.get("tags", [])).lower()
            if tags:
                haystacks.append(tags)
            use_case = entry.get("use_case") or entry.get("reported_as")
            if use_case:
                haystacks.append(str(use_case).replace("_", " ").lower())
            return any(query_lower in haystack for haystack in haystacks)

        # Search true incidents
        if kb_type in [None, "true"]:
            for entry in self.true_incidents_kb:
                if matches_tenant(entry) and entry_matches(
                    entry,
                    ["description", "outcome"],
                ):
                    results.append({**self._entry_for_response(entry), "kb_type": "true"})

        # Search false incidents
        if kb_type in [None, "false"]:
            for entry in self.false_incidents_kb:
                if matches_tenant(entry) and entry_matches(
                    entry,
                    ["false_positive_reason", "actual_issue"],
                ):
                    results.append({**self._entry_for_response(entry), "kb_type": "false"})

        results.sort(
            key=lambda entry: str(entry.get("verified_at") or entry.get("created_at") or ""),
            reverse=True,
        )
        total = len(results)
        paged_results = results[offset:offset + limit]
        pages = max((total + limit - 1) // limit, 1) if limit else 1

        return {
            "items": paged_results,
            "total": total,
            "page": (offset // limit) + 1 if limit else 1,
            "pages": pages,
            "limit": limit,
        }


    def add_from_incident(
        self,
        incident: Any,
        outcome: str,
        verified_by: str,
        risk_score: float
    ) -> Optional[str]:
        """
        Store a resolved incident as a pending pattern for later KB review.

        Args:
            incident: Incident object
            outcome: Incident outcome
            verified_by: User who verified/resolved
            risk_score: Calculated risk score

        Returns:
            Incident ID if pattern stored
        """
        use_case_label = incident.incident_type or getattr(incident, "classified_use_case", None) or "Unknown"
        incident_pattern = self.build_incident_pattern(
            incident.structured_data or {},
            use_case=use_case_label,
            workflow_outcome=outcome,
            incident_id=incident.incident_id,
        )
        incident_pattern["resolved_by"] = verified_by
        incident_pattern["resolution_risk_score"] = risk_score
        incident_pattern["resolution_notes"] = getattr(incident, "resolution_notes", "") or ""
        incident_pattern["verification_status"] = "pending_review"
        self.add_incident_pattern(incident_pattern)
        logger.info(
            "Stored resolved incident %s as pending incident_pattern for later KB review",
            incident.incident_id,
        )
        return incident.incident_id

    def _update_existing_kb_entry(
        self,
        kb_list: List[Dict[str, Any]],
        use_case: str,
        new_entry: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        If a KB entry with matching use_case (from incident source) already exists
        for the same tenant, update it with the latest resolution data.

        Returns the updated entry, or None if no existing entry was found.
        """
        use_case_lower = use_case.lower()
        for existing in kb_list:
            existing_use_case = (
                existing.get("use_case") or existing.get("reported_as") or ""
            ).lower()
            if (
                existing.get("source") == "incident"
                and existing_use_case == use_case_lower
                and existing.get("tenant_id") == new_entry.get("tenant_id")
            ):
                # Update with latest resolution data
                existing["resolution_summary"] = new_entry.get("resolution_summary", "")
                existing["resolution_notes"] = new_entry.get("resolution_notes", "")
                existing["root_cause"] = new_entry.get("root_cause", "")
                existing["actions_taken"] = new_entry.get("actions_taken", [])
                existing["verification_result"] = new_entry.get("verification_result", "")
                existing["incident_verified_as"] = new_entry.get("incident_verified_as", "")
                existing["updated_at"] = datetime.utcnow().isoformat()
                existing["updated_by"] = new_entry.get("verified_by", "system")
                # Merge tags
                existing_tags = set(existing.get("tags", []))
                new_tags = set(new_entry.get("tags", []))
                existing["tags"] = list(existing_tags | new_tags)
                logger.info(
                    f"Updated existing KB entry {existing['kb_id']} "
                    f"with resolution from incident {new_entry.get('incident_id')}"
                )
                return existing
        return None

    def _persist_entry_sync(self, kb_type: str, entry: Dict[str, Any]):
        """Fire-and-forget async persist from sync context."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._persist_entry(kb_type, entry))
        except RuntimeError:
            pass

    def get_kb_stats(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get KB statistics

        Args:
            tenant_id: Optional tenant filter (None for global + all tenants)

        Returns:
            {
                "total_true": int,
                "total_false": int,
                "tenant_true": int,
                "tenant_false": int,
                "global_true": int,
                "global_false": int,
                "recent_additions": int
            }
        """
        if tenant_id:
            # Tenant-specific + global
            tenant_true = sum(1 for e in self.true_incidents_kb
                            if e.get("tenant_id") == tenant_id or e.get("tenant_id") is None)
            tenant_false = sum(1 for e in self.false_incidents_kb
                             if e.get("tenant_id") == tenant_id or e.get("tenant_id") is None)
            global_true = sum(1 for e in self.true_incidents_kb if e.get("tenant_id") is None)
            global_false = sum(1 for e in self.false_incidents_kb if e.get("tenant_id") is None)
        else:
            # All entries
            tenant_true = len(self.true_incidents_kb)
            tenant_false = len(self.false_incidents_kb)
            global_true = sum(1 for e in self.true_incidents_kb if e.get("tenant_id") is None)
            global_false = sum(1 for e in self.false_incidents_kb if e.get("tenant_id") is None)

        # Recent additions (last 7 days)
        from datetime import timedelta
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        recent_true = sum(1 for e in self.true_incidents_kb
                         if e.get("created_at", "") >= week_ago)
        recent_false = sum(1 for e in self.false_incidents_kb
                          if e.get("created_at", "") >= week_ago)

        return {
            "total_true": len(self.true_incidents_kb),
            "total_false": len(self.false_incidents_kb),
            "tenant_true": tenant_true,
            "tenant_false": tenant_false,
            "global_true": global_true,
            "global_false": global_false,
            "recent_additions": recent_true + recent_false
        }

    def get_paginated_true_incidents(
        self,
        page: int = 1,
        limit: int = 20,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get paginated true incidents

        Args:
            page: Page number (1-indexed)
            limit: Items per page
            tenant_id: Optional tenant filter (None includes global)

        Returns:
            {
                "items": List[Dict],
                "total": int,
                "page": int,
                "pages": int
            }
        """
        # Filter by tenant
        if tenant_id:
            filtered = [e for e in self.true_incidents_kb
                       if e.get("tenant_id") == tenant_id or e.get("tenant_id") is None]
        else:
            filtered = self.true_incidents_kb

        # Sort by created_at descending
        sorted_items = sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True)

        # Paginate
        total = len(sorted_items)
        pages = (total + limit - 1) // limit if limit > 0 else 1
        start = (page - 1) * limit
        end = start + limit
        items = [self._entry_for_response(entry) for entry in sorted_items[start:end]]

        return {
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
            "limit": limit
        }

    def get_paginated_false_incidents(
        self,
        page: int = 1,
        limit: int = 20,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get paginated false incidents

        Args:
            page: Page number (1-indexed)
            limit: Items per page
            tenant_id: Optional tenant filter (None includes global)

        Returns:
            {
                "items": List[Dict],
                "total": int,
                "page": int,
                "pages": int
            }
        """
        # Filter by tenant
        if tenant_id:
            filtered = [e for e in self.false_incidents_kb
                       if e.get("tenant_id") == tenant_id or e.get("tenant_id") is None]
        else:
            filtered = self.false_incidents_kb

        # Sort by created_at descending
        sorted_items = sorted(filtered, key=lambda x: x.get("created_at", ""), reverse=True)

        # Paginate
        total = len(sorted_items)
        pages = (total + limit - 1) // limit if limit > 0 else 1
        start = (page - 1) * limit
        end = start + limit
        items = [self._entry_for_response(entry) for entry in sorted_items[start:end]]

        return {
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
            "limit": limit
        }

    def delete_kb_entry(self, kb_id: str, kb_type: str) -> bool:
        """
        Delete KB entry

        Args:
            kb_id: KB entry ID
            kb_type: "true" or "false"

        Returns:
            True if deleted, False if not found
        """
        import asyncio
        if kb_type == "true":
            original_len = len(self.true_incidents_kb)
            self.true_incidents_kb = [e for e in self.true_incidents_kb if e.get("kb_id") != kb_id]
            deleted = len(self.true_incidents_kb) < original_len
        elif kb_type == "false":
            original_len = len(self.false_incidents_kb)
            self.false_incidents_kb = [e for e in self.false_incidents_kb if e.get("kb_id") != kb_id]
            deleted = len(self.false_incidents_kb) < original_len
        else:
            return False

        if deleted:
            logger.info(f"Deleted KB entry: {kb_type}/{kb_id}")
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self._delete_from_db(kb_type, kb_id))
            except RuntimeError:
                pass
        return deleted

    def update_kb_entry(
        self,
        kb_id: str,
        kb_type: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Update KB entry

        Args:
            kb_id: KB entry ID
            kb_type: "true" or "false"
            updates: Fields to update

        Returns:
            Updated entry or None if not found
        """
        import asyncio
        kb_list = self.true_incidents_kb if kb_type == "true" else self.false_incidents_kb

        for entry in kb_list:
            if entry.get("kb_id") == kb_id:
                # Update fields
                for key, value in updates.items():
                    if key not in ["kb_id", "created_at"]:  # Don't allow changing these
                        entry[key] = value
                entry["updated_at"] = datetime.utcnow().isoformat()
                logger.info(f"Updated KB entry: {kb_type}/{kb_id}")
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(self._persist_entry(kb_type, entry))
                except RuntimeError:
                    pass
                return entry

        return None

    def get_recent_kb_entries(
        self,
        limit: int = 10,
        tenant_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent KB entries (both true and false)

        Args:
            limit: Max number of entries
            tenant_id: Optional tenant filter

        Returns:
            List of recent KB entries with kb_type field
        """
        # Combine both lists with type indicator
        all_entries = []

        for entry in self.true_incidents_kb:
            if tenant_id is None or entry.get("tenant_id") == tenant_id or entry.get("tenant_id") is None:
                all_entries.append({**self._entry_for_response(entry), "kb_type": "true"})

        for entry in self.false_incidents_kb:
            if tenant_id is None or entry.get("tenant_id") == tenant_id or entry.get("tenant_id") is None:
                all_entries.append({**self._entry_for_response(entry), "kb_type": "false"})

        # Sort by created_at descending
        sorted_entries = sorted(all_entries, key=lambda x: x.get("created_at", ""), reverse=True)

        return sorted_entries[:limit]
