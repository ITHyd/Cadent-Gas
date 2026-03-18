"""
CO Process Improvement Workflow Definitions
Based on Cadent CO Data 2024-25 (50,957 workorders) and CO Process Improvement PPT.

Key insight: 78.3% of CO callouts are false alarms. These workflows implement
manufacturer-specific alarm triage to reduce unnecessary visits.

Manufacturer triage data sourced from CO ALarms-Mac.xlsx.
"""
import logging
from app.constants.use_cases import (
    CO_ALARM, SUSPECTED_CO_LEAK,
    CO_ORANGE_FLAMES, CO_SOOTING_SCARRING, CO_EXCESSIVE_CONDENSATION,
    CO_VISIBLE_FUMES, CO_BLOOD_TEST, CO_FATALITY, CO_SMOKE_ALARM,
    GAS_SMELL, HISSING_SOUND,
)
from app.schemas.workflow_definition import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    WorkflowNodeType,
)

logger = logging.getLogger(__name__)


# ============================================================
# WORKFLOW 1: CO ALARM - Enhanced with Manufacturer Triage
# Targets 55.9% of all visits (battery failures + active alarm no CO)
# ============================================================

def _create_co_alarm_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    Enhanced CO Alarm workflow with manufacturer-specific triage.

    Flow:
    1. Safety & evacuation check
    2. Immediate symptom assessment (fast-track to emergency if severe)
    3. Alarm type identification (CO alarm vs smoke alarm vs other)
    4. Alarm behaviour: sound pattern + light colour
    5. Manufacturer identification
    6. Manufacturer-specific triage to determine: Battery Fault vs CO Detected
    7. Decision: Advise (battery) / Dispatch (CO detected) / Schedule (uncertain)

    Manufacturer beep/light patterns from CO ALarms-Mac.xlsx:
    - Continuous beep = CO detected (all manufacturers)
    - Intermittent beep every 30-60s = low battery (most manufacturers)
    - Continuous red light = CO alarm active
    - Intermittent yellow light = fault/end-of-life
    """
    workflow_id = f"{tenant_id}_{CO_ALARM}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_ALARM,
        version=1,
        start_node="safety_check",
        nodes=[
            # === PHASE 1: Immediate Safety ===
            WorkflowNode(
                id="safety_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are you and everyone in the property safe? Have you evacuated or moved to fresh air?",
                    "variable": "is_safe",
                    "options": [
                        {"label": "Yes, we are outside/in fresh air", "score": 0},
                        {"label": "No, still inside the property", "score": 15},
                        {"label": "Someone is feeling unwell and cannot move", "score": 30},
                    ]
                },
            ),
            WorkflowNode(
                id="co_symptoms",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is anyone experiencing any of these symptoms: headache, dizziness, nausea, breathlessness, or confusion?",
                    "variable": "co_symptoms",
                    "options": [
                        {"label": "Yes - multiple people feel unwell", "score": 30},
                        {"label": "Yes - one person feels unwell", "score": 20},
                        {"label": "Mild headache only", "score": 10},
                        {"label": "No symptoms at all", "score": 0},
                    ]
                },
            ),
            # Fast-track emergency check for severe symptoms
            WorkflowNode(
                id="check_severe_symptoms",
                type=WorkflowNodeType.CONDITION,
                data={"expression": "total_score >= 45"},
            ),
            WorkflowNode(
                id="emergency_symptoms_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "EMERGENCY: CO symptoms detected. Stay outside, do NOT re-enter. Emergency engineer being dispatched. Call 999 if anyone loses consciousness."
                },
            ),

            # === PHASE 2: Alarm Identification ===
            WorkflowNode(
                id="alarm_type",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What type of alarm is sounding?",
                    "variable": "alarm_type",
                    "options": [
                        {"label": "CO (Carbon Monoxide) alarm", "score": 10},
                        {"label": "Smoke alarm", "score": 0},
                        {"label": "Combined smoke and CO alarm", "score": 10},
                        {"label": "Not sure / Don't know", "score": 5},
                    ]
                },
            ),
            # Redirect smoke-only alarms
            WorkflowNode(
                id="check_smoke_alarm",
                type=WorkflowNodeType.CONDITION,
                data={"expression": "alarm_type == 'Smoke alarm'"},
            ),
            WorkflowNode(
                id="smoke_alarm_guidance",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": "This appears to be a smoke alarm, not a CO alarm. Smoke alarms detect fire/smoke, not carbon monoxide. Please check for any source of smoke. If you smell gas, call us back. If there is a fire, call 999."
                },
            ),

            # === PHASE 3: Manufacturer Selection ===
            WorkflowNode(
                id="alarm_manufacturer",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you see the brand name on the alarm?",
                    "variable": "manufacturer",
                    "options": [
                        {"label": "Kidde", "score": 0},
                        {"label": "FireAngel", "score": 0},
                        {"label": "Aico", "score": 0},
                        {"label": "Firehawk", "score": 0},
                        {"label": "X-Sense", "score": 0},
                        {"label": "Honeywell", "score": 0},
                        {"label": "Google Nest", "score": 0},
                        {"label": "Netatmo", "score": 0},
                        {"label": "Cavius", "score": 0},
                        {"label": "Other / Cannot see", "score": 5},
                    ]
                },
            ),

            # === SWITCH: Route to manufacturer-specific branch ===
            WorkflowNode(
                id="manufacturer_switch",
                type=WorkflowNodeType.SWITCH,
                data={
                    "variable": "manufacturer",
                    "label": "Manufacturer Triage",
                    "cases": ["FireAngel", "Firehawk", "Aico", "Kidde", "X-Sense"],
                    "default": "Other",
                },
            ),

            # ─── FireAngel branch ─────────────────────────────
            WorkflowNode(id="fa_q1", type=WorkflowNodeType.QUESTION, data={
                "group": "FireAngel",
                "question": "What colour light is flashing on your FireAngel alarm?",
                "variable": "fa_led", "options": [
                    {"label": "Red", "score": 20}, {"label": "Amber / Yellow", "score": 0},
                    {"label": "Green", "score": 0}, {"label": "No light", "score": 3},
                ]}),
            WorkflowNode(id="fa_check_red", type=WorkflowNodeType.CONDITION, data={"group": "FireAngel", "expression": "fa_led == 'Red'"}),
            WorkflowNode(id="fa_q2_red", type=WorkflowNodeType.QUESTION, data={
                "group": "FireAngel",
                "question": "Is your FireAngel alarm beeping loudly?",
                "variable": "fa_red_sound", "options": [
                    {"label": "Yes - loud repeated beeps", "score": 25},
                    {"label": "Single chirp every minute", "score": 5},
                    {"label": "No sound (red light only)", "score": 10},
                ]}),
            WorkflowNode(id="fa_check_co", type=WorkflowNodeType.CONDITION, data={"group": "FireAngel", "expression": "fa_red_sound == 'Yes - loud repeated beeps'"}),
            WorkflowNode(id="fa_co_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "emergency_dispatch", "message": "CO DETECTED by your FireAngel alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched. FireAngel Support: 0330 094 5830"}),
            WorkflowNode(id="fa_memory_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "schedule_engineer", "message": "Your FireAngel alarm detected CO while you were away.\n\n1. Ventilate the property\n2. Don't use gas appliances\n3. Press test button to clear memory\n\nEngineer will investigate."}),
            WorkflowNode(id="fa_check_amber", type=WorkflowNodeType.CONDITION, data={"group": "FireAngel", "expression": "fa_led == 'Amber / Yellow'"}),
            WorkflowNode(id="fa_q2_amber", type=WorkflowNodeType.QUESTION, data={
                "group": "FireAngel",
                "question": "Does the chirp happen at the same time as the amber flash?",
                "variable": "fa_chirp_sync", "options": [
                    {"label": "Yes - chirp and flash together", "score": 0},
                    {"label": "No - chirp and flash at different times", "score": 0},
                ]}),
            WorkflowNode(id="fa_check_sync", type=WorkflowNodeType.CONDITION, data={"group": "FireAngel", "expression": "fa_chirp_sync == 'Yes - chirp and flash together'"}),
            WorkflowNode(id="fa_battery_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "close_with_guidance", "message": "LOW BATTERY / END OF LIFE (not CO).\n\nReplace batteries (FA6813) or the entire alarm (sealed models).\nPress test button to silence for 8 hours.\nNo engineer visit needed."}),
            WorkflowNode(id="fa_fault_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "close_with_guidance", "message": "SENSOR FAULT - alarm cannot detect CO.\n\nReplace the alarm immediately.\nNo engineer visit needed."}),
            WorkflowNode(id="fa_normal_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."}),

            # ─── Firehawk branch ──────────────────────────────
            WorkflowNode(id="fh_q1", type=WorkflowNodeType.QUESTION, data={
                "group": "Firehawk",
                "question": "What colour light is flashing on your Firehawk alarm?",
                "variable": "fh_led", "options": [
                    {"label": "Red", "score": 20}, {"label": "Red + Yellow together", "score": 0},
                    {"label": "Green", "score": 0}, {"label": "No light", "score": 3},
                ]}),
            WorkflowNode(id="fh_check_red", type=WorkflowNodeType.CONDITION, data={"group": "Firehawk", "expression": "fh_led == 'Red'"}),
            WorkflowNode(id="fh_q2", type=WorkflowNodeType.QUESTION, data={
                "group": "Firehawk",
                "question": "How many beeps between pauses?",
                "variable": "fh_beeps", "options": [
                    {"label": "4 beeps repeating (loud)", "score": 25},
                    {"label": "1 beep every minute", "score": 0},
                    {"label": "3 beeps every minute", "score": 0},
                ]}),
            WorkflowNode(id="fh_check_co", type=WorkflowNodeType.CONDITION, data={"group": "Firehawk", "expression": "fh_beeps == '4 beeps repeating (loud)'"}),
            WorkflowNode(id="fh_co_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "emergency_dispatch", "message": "CO DETECTED by your Firehawk alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched."}),
            WorkflowNode(id="fh_check_eol", type=WorkflowNodeType.CONDITION, data={"group": "Firehawk", "expression": "fh_beeps == '3 beeps every minute'"}),
            WorkflowNode(id="fh_eol_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": "END OF ALARM LIFE.\n\nReplace the entire alarm. No engineer visit needed."}),
            WorkflowNode(id="fh_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": "LOW BATTERY (not CO). Replace the alarm (sealed battery).\nNo engineer visit needed."}),
            WorkflowNode(id="fh_check_fault", type=WorkflowNodeType.CONDITION, data={"group": "Firehawk", "expression": "fh_led == 'Red + Yellow together'"}),
            WorkflowNode(id="fh_fault_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": "ALARM FAULT. Red + Yellow LEDs = hardware/sensor fault.\nReplace the alarm immediately. No engineer visit needed."}),
            WorkflowNode(id="fh_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."}),

            # ─── Aico branch ─────────────────────────────────
            WorkflowNode(id="aico_q1", type=WorkflowNodeType.QUESTION, data={
                "group": "Aico",
                "question": "What colour light is flashing on your Aico alarm?",
                "variable": "aico_led", "options": [
                    {"label": "Red", "score": 20}, {"label": "Yellow", "score": 0},
                    {"label": "Green", "score": 0}, {"label": "No light", "score": 3},
                ]}),
            WorkflowNode(id="aico_check_red", type=WorkflowNodeType.CONDITION, data={"group": "Aico", "expression": "aico_led == 'Red'"}),
            WorkflowNode(id="aico_co_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "emergency_dispatch", "message": "CO DETECTED by your Aico alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched."}),
            WorkflowNode(id="aico_check_yellow", type=WorkflowNodeType.CONDITION, data={"group": "Aico", "expression": "aico_led == 'Yellow'"}),
            WorkflowNode(id="aico_q2", type=WorkflowNodeType.QUESTION, data={
                "group": "Aico",
                "question": "How many yellow flashes before a pause?",
                "variable": "aico_flashes", "options": [
                    {"label": "1 flash", "score": 0}, {"label": "2 flashes", "score": 0},
                    {"label": "3 flashes", "score": 0},
                ]}),
            WorkflowNode(id="aico_check_1f", type=WorkflowNodeType.CONDITION, data={"group": "Aico", "expression": "aico_flashes == '1 flash'"}),
            WorkflowNode(id="aico_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": "LOW BATTERY (not CO).\n\nEi207: replace AAA batteries. Ei208 (sealed): replace alarm.\nPress test button to silence for 12 hours.\nNo engineer visit needed."}),
            WorkflowNode(id="aico_check_2f", type=WorkflowNodeType.CONDITION, data={"group": "Aico", "expression": "aico_flashes == '2 flashes'"}),
            WorkflowNode(id="aico_fault_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": "SENSOR FAULT - alarm cannot detect CO.\nReplace immediately. No engineer visit needed."}),
            WorkflowNode(id="aico_eol_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": "END OF ALARM LIFE.\nReplace the alarm. Can silence for 24hrs (max 30 days).\nNo engineer visit needed."}),
            WorkflowNode(id="aico_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."}),

            # ─── Kidde branch ─────────────────────────────────
            WorkflowNode(id="kidde_q1", type=WorkflowNodeType.QUESTION, data={
                "group": "Kidde",
                "question": "What colour light is flashing on your Kidde alarm?",
                "variable": "kidde_led", "options": [
                    {"label": "Red", "score": 20}, {"label": "Amber", "score": 0},
                    {"label": "Green", "score": 0}, {"label": "No light", "score": 3},
                ]}),
            WorkflowNode(id="kidde_check_red", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_led == 'Red'"}),
            WorkflowNode(id="kidde_q2_red", type=WorkflowNodeType.QUESTION, data={
                "group": "Kidde",
                "question": "Is your Kidde alarm beeping loudly?",
                "variable": "kidde_red_sound", "options": [
                    {"label": "Yes - 4 quick beeps repeating", "score": 25},
                    {"label": "No sound (red light blinking slowly)", "score": 10},
                ]}),
            WorkflowNode(id="kidde_check_co", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_red_sound == 'Yes - 4 quick beeps repeating'"}),
            WorkflowNode(id="kidde_co_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "emergency_dispatch", "message": "CO DETECTED by your Kidde alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched. Kidde Support: 0800 917 0722"}),
            WorkflowNode(id="kidde_memory_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "schedule_engineer", "message": "Your Kidde alarm detected CO in the last 14 days.\n\n1. Ventilate the property\n2. Don't use gas appliances\n3. Press test button to clear\n\nEngineer will investigate."}),
            WorkflowNode(id="kidde_check_amber", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_led == 'Amber'"}),
            WorkflowNode(id="kidde_q2_amber", type=WorkflowNodeType.QUESTION, data={
                "group": "Kidde",
                "question": "How many amber flashes before a pause?",
                "variable": "kidde_amber_count", "options": [
                    {"label": "1 flash", "score": 0}, {"label": "2 flashes", "score": 0},
                    {"label": "5 flashes (fast)", "score": 0},
                ]}),
            WorkflowNode(id="kidde_check_1f", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_amber_count == '1 flash'"}),
            WorkflowNode(id="kidde_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": "LOW BATTERY (not CO).\n\nReplace 2x AA batteries (or entire alarm if sealed).\nPress test button to silence for 24 hours.\nNo engineer visit needed."}),
            WorkflowNode(id="kidde_check_2f", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_amber_count == '2 flashes'"}),
            WorkflowNode(id="kidde_eol_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": "END OF UNIT LIFE (10 years).\nReplace the alarm. No engineer visit needed."}),
            WorkflowNode(id="kidde_fault_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": "SENSOR FAULT.\nClean the alarm and press test. If fault persists, replace.\nNo engineer visit needed."}),
            WorkflowNode(id="kidde_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."}),

            # ─── X-Sense branch ───────────────────────────────
            WorkflowNode(id="xs_q1", type=WorkflowNodeType.QUESTION, data={
                "group": "X-Sense",
                "question": "What colour light is showing on your X-Sense alarm?",
                "variable": "xs_led", "options": [
                    {"label": "Red (flashing)", "score": 20}, {"label": "Red (steady, not flashing)", "score": 10},
                    {"label": "Yellow", "score": 0}, {"label": "Green", "score": 0},
                ]}),
            WorkflowNode(id="xs_check_red_flash", type=WorkflowNodeType.CONDITION, data={"group": "X-Sense", "expression": "xs_led == 'Red (flashing)'"}),
            WorkflowNode(id="xs_co_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "emergency_dispatch", "message": "CO DETECTED by your X-Sense alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nNote: Cannot silence if CO > 300 ppm.\nEngineer dispatched."}),
            WorkflowNode(id="xs_check_red_steady", type=WorkflowNodeType.CONDITION, data={"group": "X-Sense", "expression": "xs_led == 'Red (steady, not flashing)'"}),
            WorkflowNode(id="xs_silenced_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "schedule_engineer", "message": "Alarm was silenced but CO may still be present.\nIt will re-activate after 9 minutes if CO > 50 ppm.\n\n1. Ventilate the property\n2. Don't use gas appliances\n\nEngineer will investigate."}),
            WorkflowNode(id="xs_check_yellow", type=WorkflowNodeType.CONDITION, data={"group": "X-Sense", "expression": "xs_led == 'Yellow'"}),
            WorkflowNode(id="xs_q2_yellow", type=WorkflowNodeType.QUESTION, data={
                "group": "X-Sense",
                "question": "How many yellow flashes before each pause?",
                "variable": "xs_flashes", "options": [
                    {"label": "1 flash", "score": 0}, {"label": "3 flashes", "score": 0},
                ]}),
            WorkflowNode(id="xs_check_1f", type=WorkflowNodeType.CONDITION, data={"group": "X-Sense", "expression": "xs_flashes == '1 flash'"}),
            WorkflowNode(id="xs_battery_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "close_with_guidance", "message": "LOW BATTERY (not CO).\nReplace CR123A battery. LCD shows 'Lb' when low.\nNo engineer visit needed."}),
            WorkflowNode(id="xs_eol_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "close_with_guidance", "message": "END OF ALARM LIFE (10 years).\nPress test to silence for 22 hours (max 30 days).\nReplace the alarm. No engineer visit needed."}),
            WorkflowNode(id="xs_normal_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."}),

            # ─── Generic branch (unknown manufacturers) ───────
            WorkflowNode(id="gen_q1", type=WorkflowNodeType.QUESTION, data={
                "group": "Other",
                "question": "What colour light is flashing on the alarm?",
                "variable": "gen_led", "options": [
                    {"label": "Red", "score": 20}, {"label": "Amber / Yellow", "score": 0},
                    {"label": "Green", "score": 0}, {"label": "No light", "score": 3},
                ]}),
            WorkflowNode(id="gen_check_red", type=WorkflowNodeType.CONDITION, data={"group": "Other", "expression": "gen_led == 'Red'"}),
            WorkflowNode(id="gen_q2", type=WorkflowNodeType.QUESTION, data={
                "group": "Other",
                "question": "Is the alarm beeping loudly?",
                "variable": "gen_sound", "options": [
                    {"label": "Yes - loud repeated beeps", "score": 25},
                    {"label": "No - chirping or silent", "score": 5},
                ]}),
            WorkflowNode(id="gen_check_co", type=WorkflowNodeType.CONDITION, data={"group": "Other", "expression": "gen_sound == 'Yes - loud repeated beeps'"}),
            WorkflowNode(id="gen_co_out", type=WorkflowNodeType.DECISION, data={"group": "Other", "outcome": "emergency_dispatch", "message": "CO ALARM - POSSIBLE CO DETECTED.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched."}),
            WorkflowNode(id="gen_schedule_out", type=WorkflowNodeType.DECISION, data={"group": "Other", "outcome": "schedule_engineer", "message": "We recommend an engineer investigates.\n\nVentilate and don't use gas appliances until checked."}),
            WorkflowNode(id="gen_check_amber", type=WorkflowNodeType.CONDITION, data={"group": "Other", "expression": "gen_led == 'Amber / Yellow'"}),
            WorkflowNode(id="gen_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Other", "outcome": "close_with_guidance", "message": "Amber/yellow usually means low battery or end of life (not CO).\n\nReplace batteries or the alarm. No engineer visit needed."}),
            WorkflowNode(id="gen_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Other", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."}),
        ],
        edges=[
            # Phase 1: Safety
            WorkflowEdge(source="safety_check", target="co_symptoms"),
            WorkflowEdge(source="co_symptoms", target="check_severe_symptoms"),
            WorkflowEdge(source="check_severe_symptoms", target="emergency_symptoms_outcome", condition="True"),
            WorkflowEdge(source="check_severe_symptoms", target="alarm_type", condition="False"),

            # Phase 2: Alarm type
            WorkflowEdge(source="alarm_type", target="check_smoke_alarm"),
            WorkflowEdge(source="check_smoke_alarm", target="smoke_alarm_guidance", condition="True"),
            WorkflowEdge(source="check_smoke_alarm", target="alarm_manufacturer", condition="False"),

            # Phase 3: SWITCH on manufacturer
            WorkflowEdge(source="alarm_manufacturer", target="manufacturer_switch"),
            WorkflowEdge(source="manufacturer_switch", target="fa_q1", condition="manufacturer == 'FireAngel'"),
            WorkflowEdge(source="manufacturer_switch", target="fh_q1", condition="manufacturer == 'Firehawk'"),
            WorkflowEdge(source="manufacturer_switch", target="aico_q1", condition="manufacturer == 'Aico'"),
            WorkflowEdge(source="manufacturer_switch", target="kidde_q1", condition="manufacturer == 'Kidde'"),
            WorkflowEdge(source="manufacturer_switch", target="xs_q1", condition="manufacturer == 'X-Sense'"),
            WorkflowEdge(source="manufacturer_switch", target="gen_q1"),  # default

            # === FireAngel ===
            WorkflowEdge(source="fa_q1", target="fa_check_red"),
            WorkflowEdge(source="fa_check_red", target="fa_q2_red", condition="True"),
            WorkflowEdge(source="fa_q2_red", target="fa_check_co"),
            WorkflowEdge(source="fa_check_co", target="fa_co_out", condition="True"),
            WorkflowEdge(source="fa_check_co", target="fa_memory_out", condition="False"),
            WorkflowEdge(source="fa_check_red", target="fa_check_amber", condition="False"),
            WorkflowEdge(source="fa_check_amber", target="fa_q2_amber", condition="True"),
            WorkflowEdge(source="fa_q2_amber", target="fa_check_sync"),
            WorkflowEdge(source="fa_check_sync", target="fa_battery_out", condition="True"),
            WorkflowEdge(source="fa_check_sync", target="fa_fault_out", condition="False"),
            WorkflowEdge(source="fa_check_amber", target="fa_normal_out", condition="False"),

            # === Firehawk ===
            WorkflowEdge(source="fh_q1", target="fh_check_red"),
            WorkflowEdge(source="fh_check_red", target="fh_q2", condition="True"),
            WorkflowEdge(source="fh_q2", target="fh_check_co"),
            WorkflowEdge(source="fh_check_co", target="fh_co_out", condition="True"),
            WorkflowEdge(source="fh_check_co", target="fh_check_eol", condition="False"),
            WorkflowEdge(source="fh_check_eol", target="fh_eol_out", condition="True"),
            WorkflowEdge(source="fh_check_eol", target="fh_battery_out", condition="False"),
            WorkflowEdge(source="fh_check_red", target="fh_check_fault", condition="False"),
            WorkflowEdge(source="fh_check_fault", target="fh_fault_out", condition="True"),
            WorkflowEdge(source="fh_check_fault", target="fh_normal_out", condition="False"),

            # === Aico ===
            WorkflowEdge(source="aico_q1", target="aico_check_red"),
            WorkflowEdge(source="aico_check_red", target="aico_co_out", condition="True"),
            WorkflowEdge(source="aico_check_red", target="aico_check_yellow", condition="False"),
            WorkflowEdge(source="aico_check_yellow", target="aico_q2", condition="True"),
            WorkflowEdge(source="aico_q2", target="aico_check_1f"),
            WorkflowEdge(source="aico_check_1f", target="aico_battery_out", condition="True"),
            WorkflowEdge(source="aico_check_1f", target="aico_check_2f", condition="False"),
            WorkflowEdge(source="aico_check_2f", target="aico_fault_out", condition="True"),
            WorkflowEdge(source="aico_check_2f", target="aico_eol_out", condition="False"),
            WorkflowEdge(source="aico_check_yellow", target="aico_normal_out", condition="False"),

            # === Kidde ===
            WorkflowEdge(source="kidde_q1", target="kidde_check_red"),
            WorkflowEdge(source="kidde_check_red", target="kidde_q2_red", condition="True"),
            WorkflowEdge(source="kidde_q2_red", target="kidde_check_co"),
            WorkflowEdge(source="kidde_check_co", target="kidde_co_out", condition="True"),
            WorkflowEdge(source="kidde_check_co", target="kidde_memory_out", condition="False"),
            WorkflowEdge(source="kidde_check_red", target="kidde_check_amber", condition="False"),
            WorkflowEdge(source="kidde_check_amber", target="kidde_q2_amber", condition="True"),
            WorkflowEdge(source="kidde_q2_amber", target="kidde_check_1f"),
            WorkflowEdge(source="kidde_check_1f", target="kidde_battery_out", condition="True"),
            WorkflowEdge(source="kidde_check_1f", target="kidde_check_2f", condition="False"),
            WorkflowEdge(source="kidde_check_2f", target="kidde_eol_out", condition="True"),
            WorkflowEdge(source="kidde_check_2f", target="kidde_fault_out", condition="False"),
            WorkflowEdge(source="kidde_check_amber", target="kidde_normal_out", condition="False"),

            # === X-Sense ===
            WorkflowEdge(source="xs_q1", target="xs_check_red_flash"),
            WorkflowEdge(source="xs_check_red_flash", target="xs_co_out", condition="True"),
            WorkflowEdge(source="xs_check_red_flash", target="xs_check_red_steady", condition="False"),
            WorkflowEdge(source="xs_check_red_steady", target="xs_silenced_out", condition="True"),
            WorkflowEdge(source="xs_check_red_steady", target="xs_check_yellow", condition="False"),
            WorkflowEdge(source="xs_check_yellow", target="xs_q2_yellow", condition="True"),
            WorkflowEdge(source="xs_q2_yellow", target="xs_check_1f"),
            WorkflowEdge(source="xs_check_1f", target="xs_battery_out", condition="True"),
            WorkflowEdge(source="xs_check_1f", target="xs_eol_out", condition="False"),
            WorkflowEdge(source="xs_check_yellow", target="xs_normal_out", condition="False"),

            # === Generic ===
            WorkflowEdge(source="gen_q1", target="gen_check_red"),
            WorkflowEdge(source="gen_check_red", target="gen_q2", condition="True"),
            WorkflowEdge(source="gen_q2", target="gen_check_co"),
            WorkflowEdge(source="gen_check_co", target="gen_co_out", condition="True"),
            WorkflowEdge(source="gen_check_co", target="gen_schedule_out", condition="False"),
            WorkflowEdge(source="gen_check_red", target="gen_check_amber", condition="False"),
            WorkflowEdge(source="gen_check_amber", target="gen_battery_out", condition="True"),
            WorkflowEdge(source="gen_check_amber", target="gen_normal_out", condition="False"),
        ],
    )


# ============================================================
# CO ALARM ARCHITECTURE V2: Master flow + manufacturer sub-workflows
# These definitions intentionally override the earlier monolithic version.
# ============================================================

CO_ALARM_SUBFLOW_FIREANGEL = "co_alarm_fireangel"
CO_ALARM_SUBFLOW_FIREHAWK = "co_alarm_firehawk"
CO_ALARM_SUBFLOW_AICO = "co_alarm_aico"
CO_ALARM_SUBFLOW_KIDDE = "co_alarm_kidde"
CO_ALARM_SUBFLOW_XSENSE = "co_alarm_xsense"
CO_ALARM_SUBFLOW_HONEYWELL = "co_alarm_honeywell"
CO_ALARM_SUBFLOW_GOOGLE_NEST = "co_alarm_google_nest"
CO_ALARM_SUBFLOW_NETATMO = "co_alarm_netatmo"
CO_ALARM_SUBFLOW_CAVIUS = "co_alarm_cavius"
CO_ALARM_SUBFLOW_OTHER = "co_alarm_other"


def _co_alarm_subworkflow_id(tenant_id: str, subflow_use_case: str) -> str:
    return f"{tenant_id}_{subflow_use_case}_v1"


def _build_manufacturer_workflow(
    tenant_id: str,
    subflow_use_case: str,
    start_node: str,
    nodes: list[WorkflowNode],
    edges: list[WorkflowEdge],
) -> WorkflowDefinition:
    return WorkflowDefinition(
        workflow_id=_co_alarm_subworkflow_id(tenant_id, subflow_use_case),
        tenant_id=tenant_id,
        use_case=subflow_use_case,
        version=1,
        start_node=start_node,
        nodes=nodes,
        edges=edges,
    )


def _create_co_alarm_workflow(tenant_id: str) -> WorkflowDefinition:
    workflow_id = f"{tenant_id}_{CO_ALARM}_v1"
    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_ALARM,
        version=1,
        start_node="safety_check",
        nodes=[
            WorkflowNode(id="safety_check", type=WorkflowNodeType.QUESTION, data={"question": "Are you and everyone in the property safe? Have you evacuated or moved to fresh air?", "variable": "is_safe", "options": [{"label": "Yes, we are outside/in fresh air", "score": 0}, {"label": "No, still inside the property", "score": 15}, {"label": "Someone is feeling unwell and cannot move", "score": 30}]}),
            WorkflowNode(id="co_symptoms", type=WorkflowNodeType.QUESTION, data={"question": "Is anyone experiencing any of these symptoms: headache, dizziness, nausea, breathlessness, or confusion?", "variable": "co_symptoms", "options": [{"label": "Yes - multiple people feel unwell", "score": 30}, {"label": "Yes - one person feels unwell", "score": 20}, {"label": "Mild headache only", "score": 10}, {"label": "No symptoms at all", "score": 0}]}),
            WorkflowNode(id="check_severe_symptoms", type=WorkflowNodeType.CONDITION, data={"expression": "total_score >= 45"}),
            WorkflowNode(id="emergency_symptoms_outcome", type=WorkflowNodeType.DECISION, data={"outcome": "emergency_dispatch", "message": "EMERGENCY: CO symptoms detected. Stay outside, do NOT re-enter. Emergency engineer being dispatched. Call 999 if anyone loses consciousness."}),
            WorkflowNode(id="alarm_type", type=WorkflowNodeType.QUESTION, data={"question": "What type of alarm is sounding?", "variable": "alarm_type", "options": [{"label": "CO (Carbon Monoxide) alarm", "score": 10}, {"label": "Smoke alarm", "score": 0}, {"label": "Combined smoke and CO alarm", "score": 10}, {"label": "Not sure / Don't know", "score": 5}]}),
            WorkflowNode(id="check_smoke_alarm", type=WorkflowNodeType.CONDITION, data={"expression": "alarm_type == 'Smoke alarm'"}),
            WorkflowNode(id="smoke_alarm_guidance", type=WorkflowNodeType.DECISION, data={"outcome": "close_with_guidance", "message": "This appears to be a smoke alarm, not a CO alarm. Smoke alarms detect fire/smoke, not carbon monoxide. Please check for any source of smoke. If you smell gas, call us back. If there is a fire, call 999."}),
            WorkflowNode(id="alarm_manufacturer", type=WorkflowNodeType.QUESTION, data={"question": "Can you see the brand name on the alarm?", "variable": "manufacturer", "options": [{"label": "Kidde", "score": 0}, {"label": "FireAngel", "score": 0}, {"label": "Aico", "score": 0}, {"label": "Firehawk", "score": 0}, {"label": "X-Sense", "score": 0}, {"label": "Honeywell", "score": 0}, {"label": "Google Nest", "score": 0}, {"label": "Netatmo", "score": 0}, {"label": "Cavius", "score": 0}, {"label": "Other / Cannot see", "score": 5}]}),
            WorkflowNode(id="model_number", type=WorkflowNodeType.QUESTION, data={"question": "What model number is written on the alarm? If you cannot read it, type 'Unknown'.", "variable": "model_number"}),
            WorkflowNode(id="manufacturer_switch", type=WorkflowNodeType.SWITCH, data={"variable": "manufacturer", "label": "Manufacturer Routing", "cases": ["FireAngel", "Firehawk", "Aico", "Kidde", "X-Sense", "Honeywell", "Google Nest", "Netatmo", "Cavius"], "default": "Other"}),
            WorkflowNode(id="run_fireangel_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "FireAngel manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_FIREANGEL), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_firehawk_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "Firehawk manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_FIREHAWK), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_aico_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "Aico manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_AICO), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_kidde_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "Kidde manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_KIDDE), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_xsense_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "X-Sense manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_XSENSE), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_honeywell_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "Honeywell manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_HONEYWELL), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_google_nest_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "Google Nest manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_GOOGLE_NEST), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_netatmo_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "Netatmo manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_NETATMO), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_cavius_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "Cavius manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_CAVIUS), "result_prefix": "manufacturer_triage"}),
            WorkflowNode(id="run_generic_triage", type=WorkflowNodeType.SUB_WORKFLOW, data={"label": "Generic manufacturer workflow", "workflow_id": _co_alarm_subworkflow_id(tenant_id, CO_ALARM_SUBFLOW_OTHER), "result_prefix": "manufacturer_triage"}),
        ],
        edges=[
            WorkflowEdge(source="safety_check", target="co_symptoms"),
            WorkflowEdge(source="co_symptoms", target="check_severe_symptoms"),
            WorkflowEdge(source="check_severe_symptoms", target="emergency_symptoms_outcome", condition="True"),
            WorkflowEdge(source="check_severe_symptoms", target="alarm_type", condition="False"),
            WorkflowEdge(source="alarm_type", target="check_smoke_alarm"),
            WorkflowEdge(source="check_smoke_alarm", target="smoke_alarm_guidance", condition="True"),
            WorkflowEdge(source="check_smoke_alarm", target="alarm_manufacturer", condition="False"),
            WorkflowEdge(source="alarm_manufacturer", target="model_number"),
            WorkflowEdge(source="model_number", target="manufacturer_switch"),
            WorkflowEdge(source="manufacturer_switch", target="run_fireangel_triage", condition="manufacturer == 'FireAngel'"),
            WorkflowEdge(source="manufacturer_switch", target="run_firehawk_triage", condition="manufacturer == 'Firehawk'"),
            WorkflowEdge(source="manufacturer_switch", target="run_aico_triage", condition="manufacturer == 'Aico'"),
            WorkflowEdge(source="manufacturer_switch", target="run_kidde_triage", condition="manufacturer == 'Kidde'"),
            WorkflowEdge(source="manufacturer_switch", target="run_xsense_triage", condition="manufacturer == 'X-Sense'"),
            WorkflowEdge(source="manufacturer_switch", target="run_honeywell_triage", condition="manufacturer == 'Honeywell'"),
            WorkflowEdge(source="manufacturer_switch", target="run_google_nest_triage", condition="manufacturer == 'Google Nest'"),
            WorkflowEdge(source="manufacturer_switch", target="run_netatmo_triage", condition="manufacturer == 'Netatmo'"),
            WorkflowEdge(source="manufacturer_switch", target="run_cavius_triage", condition="manufacturer == 'Cavius'"),
            WorkflowEdge(source="manufacturer_switch", target="run_generic_triage"),
        ],
    )


def _create_co_alarm_fireangel_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_FIREANGEL, "fa_q1", [WorkflowNode(id="fa_q1", type=WorkflowNodeType.QUESTION, data={"group": "FireAngel", "question": "What colour light is flashing on your FireAngel alarm?", "variable": "fa_led", "options": [{"label": "Red", "score": 20}, {"label": "Amber / Yellow", "score": 0}, {"label": "Green", "score": 0}, {"label": "No light", "score": 3}]}), WorkflowNode(id="fa_check_red", type=WorkflowNodeType.CONDITION, data={"group": "FireAngel", "expression": "fa_led == 'Red'"}), WorkflowNode(id="fa_q2_red", type=WorkflowNodeType.QUESTION, data={"group": "FireAngel", "question": "Is your FireAngel alarm beeping loudly?", "variable": "fa_red_sound", "options": [{"label": "Yes - loud repeated beeps", "score": 25}, {"label": "Single chirp every minute", "score": 5}, {"label": "No sound (red light only)", "score": 10}]}), WorkflowNode(id="fa_check_co", type=WorkflowNodeType.CONDITION, data={"group": "FireAngel", "expression": "fa_red_sound == 'Yes - loud repeated beeps'"}), WorkflowNode(id="fa_co_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "emergency_dispatch", "message": "CO DETECTED by your FireAngel alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched. FireAngel Support: 0330 094 5830"}), WorkflowNode(id="fa_memory_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "schedule_engineer", "message": "Your FireAngel alarm detected CO while you were away.\n\n1. Ventilate the property\n2. Don't use gas appliances\n3. Press test button to clear memory\n\nEngineer will investigate."}), WorkflowNode(id="fa_check_amber", type=WorkflowNodeType.CONDITION, data={"group": "FireAngel", "expression": "fa_led == 'Amber / Yellow'"}), WorkflowNode(id="fa_q2_amber", type=WorkflowNodeType.QUESTION, data={"group": "FireAngel", "question": "Does the chirp happen at the same time as the amber flash?", "variable": "fa_chirp_sync", "options": [{"label": "Yes - chirp and flash together", "score": 0}, {"label": "No - chirp and flash at different times", "score": 0}]}), WorkflowNode(id="fa_check_sync", type=WorkflowNodeType.CONDITION, data={"group": "FireAngel", "expression": "fa_chirp_sync == 'Yes - chirp and flash together'"}), WorkflowNode(id="fa_battery_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "close_with_guidance", "message": "LOW BATTERY / END OF LIFE (not CO).\n\nReplace batteries (FA6813) or the entire alarm (sealed models).\nPress test button to silence for 8 hours.\nNo engineer visit needed."}), WorkflowNode(id="fa_fault_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "close_with_guidance", "message": "SENSOR FAULT - alarm cannot detect CO.\n\nReplace the alarm immediately.\nNo engineer visit needed."}), WorkflowNode(id="fa_normal_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."})], [WorkflowEdge(source="fa_q1", target="fa_check_red"), WorkflowEdge(source="fa_check_red", target="fa_q2_red", condition="True"), WorkflowEdge(source="fa_q2_red", target="fa_check_co"), WorkflowEdge(source="fa_check_co", target="fa_co_out", condition="True"), WorkflowEdge(source="fa_check_co", target="fa_memory_out", condition="False"), WorkflowEdge(source="fa_check_red", target="fa_check_amber", condition="False"), WorkflowEdge(source="fa_check_amber", target="fa_q2_amber", condition="True"), WorkflowEdge(source="fa_q2_amber", target="fa_check_sync"), WorkflowEdge(source="fa_check_sync", target="fa_battery_out", condition="True"), WorkflowEdge(source="fa_check_sync", target="fa_fault_out", condition="False"), WorkflowEdge(source="fa_check_amber", target="fa_normal_out", condition="False")])


def _create_co_alarm_firehawk_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_FIREHAWK, "fh_q1", [WorkflowNode(id="fh_q1", type=WorkflowNodeType.QUESTION, data={"group": "Firehawk", "question": "What colour light is flashing on your Firehawk alarm?", "variable": "fh_led", "options": [{"label": "Red", "score": 20}, {"label": "Red + Yellow together", "score": 0}, {"label": "Green", "score": 0}, {"label": "No light", "score": 3}]}), WorkflowNode(id="fh_check_red", type=WorkflowNodeType.CONDITION, data={"group": "Firehawk", "expression": "fh_led == 'Red'"}), WorkflowNode(id="fh_q2", type=WorkflowNodeType.QUESTION, data={"group": "Firehawk", "question": "How many beeps between pauses?", "variable": "fh_beeps", "options": [{"label": "4 beeps repeating (loud)", "score": 25}, {"label": "1 beep every minute", "score": 0}, {"label": "3 beeps every minute", "score": 0}]}), WorkflowNode(id="fh_check_co", type=WorkflowNodeType.CONDITION, data={"group": "Firehawk", "expression": "fh_beeps == '4 beeps repeating (loud)'"}), WorkflowNode(id="fh_co_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "emergency_dispatch", "message": "CO DETECTED by your Firehawk alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched."}), WorkflowNode(id="fh_check_eol", type=WorkflowNodeType.CONDITION, data={"group": "Firehawk", "expression": "fh_beeps == '3 beeps every minute'"}), WorkflowNode(id="fh_eol_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": "END OF ALARM LIFE.\n\nReplace the entire alarm. No engineer visit needed."}), WorkflowNode(id="fh_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": "LOW BATTERY (not CO). Replace the alarm (sealed battery).\nNo engineer visit needed."}), WorkflowNode(id="fh_check_fault", type=WorkflowNodeType.CONDITION, data={"group": "Firehawk", "expression": "fh_led == 'Red + Yellow together'"}), WorkflowNode(id="fh_fault_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": "ALARM FAULT. Red + Yellow LEDs = hardware/sensor fault.\nReplace the alarm immediately. No engineer visit needed."}), WorkflowNode(id="fh_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."})], [WorkflowEdge(source="fh_q1", target="fh_check_red"), WorkflowEdge(source="fh_check_red", target="fh_q2", condition="True"), WorkflowEdge(source="fh_q2", target="fh_check_co"), WorkflowEdge(source="fh_check_co", target="fh_co_out", condition="True"), WorkflowEdge(source="fh_check_co", target="fh_check_eol", condition="False"), WorkflowEdge(source="fh_check_eol", target="fh_eol_out", condition="True"), WorkflowEdge(source="fh_check_eol", target="fh_battery_out", condition="False"), WorkflowEdge(source="fh_check_red", target="fh_check_fault", condition="False"), WorkflowEdge(source="fh_check_fault", target="fh_fault_out", condition="True"), WorkflowEdge(source="fh_check_fault", target="fh_normal_out", condition="False")])


def _create_co_alarm_aico_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_AICO, "aico_q1", [WorkflowNode(id="aico_q1", type=WorkflowNodeType.QUESTION, data={"group": "Aico", "question": "What colour light is flashing on your Aico alarm?", "variable": "aico_led", "options": [{"label": "Red", "score": 20}, {"label": "Yellow", "score": 0}, {"label": "Green", "score": 0}, {"label": "No light", "score": 3}]}), WorkflowNode(id="aico_check_red", type=WorkflowNodeType.CONDITION, data={"group": "Aico", "expression": "aico_led == 'Red'"}), WorkflowNode(id="aico_co_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "emergency_dispatch", "message": "CO DETECTED by your Aico alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched."}), WorkflowNode(id="aico_check_yellow", type=WorkflowNodeType.CONDITION, data={"group": "Aico", "expression": "aico_led == 'Yellow'"}), WorkflowNode(id="aico_q2", type=WorkflowNodeType.QUESTION, data={"group": "Aico", "question": "How many yellow flashes before a pause?", "variable": "aico_flashes", "options": [{"label": "1 flash", "score": 0}, {"label": "2 flashes", "score": 0}, {"label": "3 flashes", "score": 0}]}), WorkflowNode(id="aico_check_1f", type=WorkflowNodeType.CONDITION, data={"group": "Aico", "expression": "aico_flashes == '1 flash'"}), WorkflowNode(id="aico_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": "LOW BATTERY (not CO).\n\nEi207: replace AAA batteries. Ei208 (sealed): replace alarm.\nPress test button to silence for 12 hours.\nNo engineer visit needed."}), WorkflowNode(id="aico_check_2f", type=WorkflowNodeType.CONDITION, data={"group": "Aico", "expression": "aico_flashes == '2 flashes'"}), WorkflowNode(id="aico_fault_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": "SENSOR FAULT - alarm cannot detect CO.\nReplace immediately. No engineer visit needed."}), WorkflowNode(id="aico_eol_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": "END OF ALARM LIFE.\nReplace the alarm. Can silence for 24hrs (max 30 days).\nNo engineer visit needed."}), WorkflowNode(id="aico_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."})], [WorkflowEdge(source="aico_q1", target="aico_check_red"), WorkflowEdge(source="aico_check_red", target="aico_co_out", condition="True"), WorkflowEdge(source="aico_check_red", target="aico_check_yellow", condition="False"), WorkflowEdge(source="aico_check_yellow", target="aico_q2", condition="True"), WorkflowEdge(source="aico_q2", target="aico_check_1f"), WorkflowEdge(source="aico_check_1f", target="aico_battery_out", condition="True"), WorkflowEdge(source="aico_check_1f", target="aico_check_2f", condition="False"), WorkflowEdge(source="aico_check_2f", target="aico_fault_out", condition="True"), WorkflowEdge(source="aico_check_2f", target="aico_eol_out", condition="False"), WorkflowEdge(source="aico_check_yellow", target="aico_normal_out", condition="False")])


def _create_co_alarm_kidde_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_KIDDE, "kidde_q1", [WorkflowNode(id="kidde_q1", type=WorkflowNodeType.QUESTION, data={"group": "Kidde", "question": "What colour light is flashing on your Kidde alarm?", "variable": "kidde_led", "options": [{"label": "Red", "score": 20}, {"label": "Amber", "score": 0}, {"label": "Green", "score": 0}, {"label": "No light", "score": 3}]}), WorkflowNode(id="kidde_check_red", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_led == 'Red'"}), WorkflowNode(id="kidde_q2_red", type=WorkflowNodeType.QUESTION, data={"group": "Kidde", "question": "Is your Kidde alarm beeping loudly?", "variable": "kidde_red_sound", "options": [{"label": "Yes - 4 quick beeps repeating", "score": 25}, {"label": "No sound (red light blinking slowly)", "score": 10}]}), WorkflowNode(id="kidde_check_co", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_red_sound == 'Yes - 4 quick beeps repeating'"}), WorkflowNode(id="kidde_co_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "emergency_dispatch", "message": "CO DETECTED by your Kidde alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched. Kidde Support: 0800 917 0722"}), WorkflowNode(id="kidde_memory_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "schedule_engineer", "message": "Your Kidde alarm detected CO in the last 14 days.\n\n1. Ventilate the property\n2. Don't use gas appliances\n3. Press test button to clear\n\nEngineer will investigate."}), WorkflowNode(id="kidde_check_amber", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_led == 'Amber'"}), WorkflowNode(id="kidde_q2_amber", type=WorkflowNodeType.QUESTION, data={"group": "Kidde", "question": "How many amber flashes before a pause?", "variable": "kidde_amber_count", "options": [{"label": "1 flash", "score": 0}, {"label": "2 flashes", "score": 0}, {"label": "5 flashes (fast)", "score": 0}]}), WorkflowNode(id="kidde_check_1f", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_amber_count == '1 flash'"}), WorkflowNode(id="kidde_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": "LOW BATTERY (not CO).\n\nReplace 2x AA batteries (or entire alarm if sealed).\nPress test button to silence for 24 hours.\nNo engineer visit needed."}), WorkflowNode(id="kidde_check_2f", type=WorkflowNodeType.CONDITION, data={"group": "Kidde", "expression": "kidde_amber_count == '2 flashes'"}), WorkflowNode(id="kidde_eol_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": "END OF UNIT LIFE (10 years).\nReplace the alarm. No engineer visit needed."}), WorkflowNode(id="kidde_fault_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": "SENSOR FAULT.\nClean the alarm and press test. If fault persists, replace.\nNo engineer visit needed."}), WorkflowNode(id="kidde_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."})], [WorkflowEdge(source="kidde_q1", target="kidde_check_red"), WorkflowEdge(source="kidde_check_red", target="kidde_q2_red", condition="True"), WorkflowEdge(source="kidde_q2_red", target="kidde_check_co"), WorkflowEdge(source="kidde_check_co", target="kidde_co_out", condition="True"), WorkflowEdge(source="kidde_check_co", target="kidde_memory_out", condition="False"), WorkflowEdge(source="kidde_check_red", target="kidde_check_amber", condition="False"), WorkflowEdge(source="kidde_check_amber", target="kidde_q2_amber", condition="True"), WorkflowEdge(source="kidde_q2_amber", target="kidde_check_1f"), WorkflowEdge(source="kidde_check_1f", target="kidde_battery_out", condition="True"), WorkflowEdge(source="kidde_check_1f", target="kidde_check_2f", condition="False"), WorkflowEdge(source="kidde_check_2f", target="kidde_eol_out", condition="True"), WorkflowEdge(source="kidde_check_2f", target="kidde_fault_out", condition="False"), WorkflowEdge(source="kidde_check_amber", target="kidde_normal_out", condition="False")])


def _create_co_alarm_xsense_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_XSENSE, "xs_q1", [WorkflowNode(id="xs_q1", type=WorkflowNodeType.QUESTION, data={"group": "X-Sense", "question": "What colour light is showing on your X-Sense alarm?", "variable": "xs_led", "options": [{"label": "Red (flashing)", "score": 20}, {"label": "Red (steady, not flashing)", "score": 10}, {"label": "Yellow", "score": 0}, {"label": "Green", "score": 0}]}), WorkflowNode(id="xs_check_red_flash", type=WorkflowNodeType.CONDITION, data={"group": "X-Sense", "expression": "xs_led == 'Red (flashing)'"}), WorkflowNode(id="xs_co_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "emergency_dispatch", "message": "CO DETECTED by your X-Sense alarm.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nNote: Cannot silence if CO > 300 ppm.\nEngineer dispatched."}), WorkflowNode(id="xs_check_red_steady", type=WorkflowNodeType.CONDITION, data={"group": "X-Sense", "expression": "xs_led == 'Red (steady, not flashing)'"}), WorkflowNode(id="xs_silenced_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "schedule_engineer", "message": "Alarm was silenced but CO may still be present.\nIt will re-activate after 9 minutes if CO > 50 ppm.\n\n1. Ventilate the property\n2. Don't use gas appliances\n\nEngineer will investigate."}), WorkflowNode(id="xs_check_yellow", type=WorkflowNodeType.CONDITION, data={"group": "X-Sense", "expression": "xs_led == 'Yellow'"}), WorkflowNode(id="xs_q2_yellow", type=WorkflowNodeType.QUESTION, data={"group": "X-Sense", "question": "How many yellow flashes before each pause?", "variable": "xs_flashes", "options": [{"label": "1 flash", "score": 0}, {"label": "3 flashes", "score": 0}]}), WorkflowNode(id="xs_check_1f", type=WorkflowNodeType.CONDITION, data={"group": "X-Sense", "expression": "xs_flashes == '1 flash'"}), WorkflowNode(id="xs_battery_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "close_with_guidance", "message": "LOW BATTERY (not CO).\nReplace CR123A battery. LCD shows 'Lb' when low.\nNo engineer visit needed."}), WorkflowNode(id="xs_eol_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "close_with_guidance", "message": "END OF ALARM LIFE (10 years).\nPress test to silence for 22 hours (max 30 days).\nReplace the alarm. No engineer visit needed."}), WorkflowNode(id="xs_normal_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."})], [WorkflowEdge(source="xs_q1", target="xs_check_red_flash"), WorkflowEdge(source="xs_check_red_flash", target="xs_co_out", condition="True"), WorkflowEdge(source="xs_check_red_flash", target="xs_check_red_steady", condition="False"), WorkflowEdge(source="xs_check_red_steady", target="xs_silenced_out", condition="True"), WorkflowEdge(source="xs_check_red_steady", target="xs_check_yellow", condition="False"), WorkflowEdge(source="xs_check_yellow", target="xs_q2_yellow", condition="True"), WorkflowEdge(source="xs_q2_yellow", target="xs_check_1f"), WorkflowEdge(source="xs_check_1f", target="xs_battery_out", condition="True"), WorkflowEdge(source="xs_check_1f", target="xs_eol_out", condition="False"), WorkflowEdge(source="xs_check_yellow", target="xs_normal_out", condition="False")])


def _create_co_alarm_honeywell_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_HONEYWELL, "hw_model", [WorkflowNode(id="hw_model", type=WorkflowNodeType.QUESTION, data={"group": "Honeywell", "question": "Which Honeywell X-Series model do you have?", "variable": "hw_model", "options": [{"label": "XC70", "score": 0}, {"label": "XC100", "score": 0}, {"label": "XC100D / with display", "score": 0}, {"label": "Not sure", "score": 0}]}), WorkflowNode(id="hw_status", type=WorkflowNodeType.QUESTION, data={"group": "Honeywell", "question": "What is the alarm doing right now?", "variable": "hw_status", "options": [{"label": "Full alarm / loud warning", "score": 25}, {"label": "Pre-alarm / low level warning", "score": 15}, {"label": "Yellow or fault indication", "score": 0}, {"label": "Green light only / normal", "score": 0}]}), WorkflowNode(id="hw_alarm_check", type=WorkflowNodeType.CONDITION, data={"group": "Honeywell", "expression": "hw_status == 'Full alarm / loud warning'"}), WorkflowNode(id="hw_alarm_out", type=WorkflowNodeType.DECISION, data={"group": "Honeywell", "outcome": "emergency_dispatch", "message": "HONEYWELL CO ALARM ACTIVATED.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched."}), WorkflowNode(id="hw_prealarm_check", type=WorkflowNodeType.CONDITION, data={"group": "Honeywell", "expression": "hw_status == 'Pre-alarm / low level warning'"}), WorkflowNode(id="hw_prealarm_out", type=WorkflowNodeType.DECISION, data={"group": "Honeywell", "outcome": "schedule_engineer", "message": "Honeywell pre-alarm or low-level monitoring alert reported.\n\nVentilate the property and avoid using gas appliances until checked.\nAn engineer will investigate."}), WorkflowNode(id="hw_fault_type", type=WorkflowNodeType.QUESTION, data={"group": "Honeywell", "question": "Is it showing a low battery / end-of-life warning or a fault warning?", "variable": "hw_fault_type", "options": [{"label": "Low battery or end of life", "score": 0}, {"label": "Fault / sensor problem", "score": 0}, {"label": "Not sure", "score": 0}]}), WorkflowNode(id="hw_battery_check", type=WorkflowNodeType.CONDITION, data={"group": "Honeywell", "expression": "hw_fault_type == 'Low battery or end of life'"}), WorkflowNode(id="hw_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Honeywell", "outcome": "close_with_guidance", "message": "Honeywell X-Series battery/end-of-life warning reported.\n\nThese units are sealed maintenance-free alarms. Replace the alarm when end-of-life is indicated.\nNo engineer visit needed."}), WorkflowNode(id="hw_fault_out", type=WorkflowNodeType.DECISION, data={"group": "Honeywell", "outcome": "close_with_guidance", "message": "Honeywell X-Series fault warning reported.\n\nThis indicates a device issue rather than confirmed CO. Replace the alarm and investigate appliances if concerns remain.\nNo engineer visit needed."}), WorkflowNode(id="hw_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Honeywell", "outcome": "close_with_guidance", "message": "The Honeywell alarm appears to be in normal status. Press the test button to confirm operation. If it warns again, call us back."})], [WorkflowEdge(source="hw_model", target="hw_status"), WorkflowEdge(source="hw_status", target="hw_alarm_check"), WorkflowEdge(source="hw_alarm_check", target="hw_alarm_out", condition="True"), WorkflowEdge(source="hw_alarm_check", target="hw_prealarm_check", condition="False"), WorkflowEdge(source="hw_prealarm_check", target="hw_prealarm_out", condition="True"), WorkflowEdge(source="hw_prealarm_check", target="hw_fault_type", condition="False"), WorkflowEdge(source="hw_fault_type", target="hw_battery_check"), WorkflowEdge(source="hw_battery_check", target="hw_battery_out", condition="True"), WorkflowEdge(source="hw_battery_check", target="hw_fault_out", condition="False"), WorkflowEdge(source="hw_status", target="hw_normal_out", condition="hw_status == 'Green light only / normal'")])


def _create_co_alarm_google_nest_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_GOOGLE_NEST, "nest_alert_type", [WorkflowNode(id="nest_alert_type", type=WorkflowNodeType.QUESTION, data={"group": "Google Nest", "question": "What is your Nest Protect doing?", "variable": "nest_alert_type", "options": [{"label": "Red emergency CO alarm", "score": 25}, {"label": "Yellow Heads-Up warning", "score": 15}, {"label": "Yellow issue / maintenance warning", "score": 0}, {"label": "Only chirping / no alarm", "score": 0}]}), WorkflowNode(id="nest_red_check", type=WorkflowNodeType.CONDITION, data={"group": "Google Nest", "expression": "nest_alert_type == 'Red emergency CO alarm'"}), WorkflowNode(id="nest_red_out", type=WorkflowNodeType.DECISION, data={"group": "Google Nest", "outcome": "emergency_dispatch", "message": "NEST PROTECT RED CO EMERGENCY ALARM.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone is unwell\n\nEmergency engineer dispatched."}), WorkflowNode(id="nest_heads_up_check", type=WorkflowNodeType.CONDITION, data={"group": "Google Nest", "expression": "nest_alert_type == 'Yellow Heads-Up warning'"}), WorkflowNode(id="nest_heads_up_out", type=WorkflowNodeType.DECISION, data={"group": "Google Nest", "outcome": "schedule_engineer", "message": "Nest Protect Heads-Up CO warning reported.\n\nThis is an early warning that may indicate rising CO levels. Ventilate the property and avoid using gas appliances until checked.\nAn engineer will investigate."}), WorkflowNode(id="nest_issue_type", type=WorkflowNodeType.QUESTION, data={"group": "Google Nest", "question": "Is Nest reporting a device issue such as sensors, battery, or expiry?", "variable": "nest_issue_type", "options": [{"label": "Battery / power issue", "score": 0}, {"label": "Sensor / expired / maintenance issue", "score": 0}, {"label": "Not sure", "score": 0}]}), WorkflowNode(id="nest_battery_check", type=WorkflowNodeType.CONDITION, data={"group": "Google Nest", "expression": "nest_issue_type == 'Battery / power issue'"}), WorkflowNode(id="nest_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Google Nest", "outcome": "close_with_guidance", "message": "Nest Protect battery/power warning reported.\n\nReplace the batteries on the battery model or service the unit if applicable. This is not a confirmed CO event.\nNo engineer visit needed."}), WorkflowNode(id="nest_issue_out", type=WorkflowNodeType.DECISION, data={"group": "Google Nest", "outcome": "close_with_guidance", "message": "Nest Protect maintenance or sensor issue reported.\n\nThis indicates a device issue rather than confirmed CO. Test the unit and replace if expired or faulty.\nNo engineer visit needed."}), WorkflowNode(id="nest_chirp_out", type=WorkflowNodeType.DECISION, data={"group": "Google Nest", "outcome": "close_with_guidance", "message": "Nest Protect chirping without a CO alarm usually indicates a battery or maintenance issue.\nTest the unit and address the warning in the app/device guidance.\nNo engineer visit needed."})], [WorkflowEdge(source="nest_alert_type", target="nest_red_check"), WorkflowEdge(source="nest_red_check", target="nest_red_out", condition="True"), WorkflowEdge(source="nest_red_check", target="nest_heads_up_check", condition="False"), WorkflowEdge(source="nest_heads_up_check", target="nest_heads_up_out", condition="True"), WorkflowEdge(source="nest_heads_up_check", target="nest_issue_type", condition="False"), WorkflowEdge(source="nest_issue_type", target="nest_battery_check"), WorkflowEdge(source="nest_battery_check", target="nest_battery_out", condition="True"), WorkflowEdge(source="nest_battery_check", target="nest_issue_out", condition="False"), WorkflowEdge(source="nest_alert_type", target="nest_chirp_out", condition="nest_alert_type == 'Only chirping / no alarm'")])


def _create_co_alarm_netatmo_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_NETATMO, "netatmo_status", [WorkflowNode(id="netatmo_status", type=WorkflowNodeType.QUESTION, data={"group": "Netatmo", "question": "What is the Netatmo Smart CO Alarm indicating?", "variable": "netatmo_status", "options": [{"label": "Alarm sounding / dangerous CO detected", "score": 25}, {"label": "Fault indicator / product issue", "score": 0}, {"label": "Test or maintenance alert only", "score": 0}, {"label": "Not sure", "score": 10}]}), WorkflowNode(id="netatmo_alarm_check", type=WorkflowNodeType.CONDITION, data={"group": "Netatmo", "expression": "netatmo_status == 'Alarm sounding / dangerous CO detected'"}), WorkflowNode(id="netatmo_alarm_out", type=WorkflowNodeType.DECISION, data={"group": "Netatmo", "outcome": "emergency_dispatch", "message": "NETATMO CO ALARM ACTIVATED.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone is unwell\n\nEmergency engineer dispatched."}), WorkflowNode(id="netatmo_fault_check", type=WorkflowNodeType.CONDITION, data={"group": "Netatmo", "expression": "netatmo_status == 'Fault indicator / product issue'"}), WorkflowNode(id="netatmo_fault_out", type=WorkflowNodeType.DECISION, data={"group": "Netatmo", "outcome": "close_with_guidance", "message": "Netatmo fault indicator reported.\n\nThis suggests a device problem rather than confirmed CO. Test the unit, check the app/status guidance, and replace if faulty.\nNo engineer visit needed."}), WorkflowNode(id="netatmo_maint_out", type=WorkflowNodeType.DECISION, data={"group": "Netatmo", "outcome": "close_with_guidance", "message": "Netatmo maintenance/test alert reported.\n\nComplete the device test and maintenance steps. If a real alarm occurs again, call us back immediately.\nNo engineer visit needed."}), WorkflowNode(id="netatmo_unsure_out", type=WorkflowNodeType.DECISION, data={"group": "Netatmo", "outcome": "schedule_engineer", "message": "Because the Netatmo alarm status is unclear, ventilate the property and avoid using gas appliances until checked.\nAn engineer will investigate."})], [WorkflowEdge(source="netatmo_status", target="netatmo_alarm_check"), WorkflowEdge(source="netatmo_alarm_check", target="netatmo_alarm_out", condition="True"), WorkflowEdge(source="netatmo_alarm_check", target="netatmo_fault_check", condition="False"), WorkflowEdge(source="netatmo_fault_check", target="netatmo_fault_out", condition="True"), WorkflowEdge(source="netatmo_fault_check", target="netatmo_maint_out", condition="False"), WorkflowEdge(source="netatmo_status", target="netatmo_unsure_out", condition="netatmo_status == 'Not sure'")])


def _create_co_alarm_cavius_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_CAVIUS, "cav_status", [WorkflowNode(id="cav_status", type=WorkflowNodeType.QUESTION, data={"group": "Cavius", "question": "What is the Cavius alarm doing?", "variable": "cav_status", "options": [{"label": "Repeated alarm tones with red LED flashing every 0.5 second", "score": 25}, {"label": "Single beep every 60 seconds with yellow LED", "score": 0}, {"label": "Two beeps every 60 seconds with yellow LED", "score": 0}, {"label": "Three beeps every 60 seconds with yellow LED", "score": 0}, {"label": "Green LED flash every 60 seconds only", "score": 0}]}), WorkflowNode(id="cav_alarm_check", type=WorkflowNodeType.CONDITION, data={"group": "Cavius", "expression": "cav_status == 'Repeated alarm tones with red LED flashing every 0.5 second'"}), WorkflowNode(id="cav_alarm_out", type=WorkflowNodeType.DECISION, data={"group": "Cavius", "outcome": "emergency_dispatch", "message": "CAVIUS CO ALARM ACTIVATED.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone is unwell\n\nEmergency engineer dispatched."}), WorkflowNode(id="cav_battery_check", type=WorkflowNodeType.CONDITION, data={"group": "Cavius", "expression": "cav_status == 'Single beep every 60 seconds with yellow LED'"}), WorkflowNode(id="cav_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Cavius", "outcome": "close_with_guidance", "message": "Cavius low battery warning reported.\n\nReplace the 3V lithium battery. This is not a confirmed CO event.\nNo engineer visit needed."}), WorkflowNode(id="cav_sensor_check", type=WorkflowNodeType.CONDITION, data={"group": "Cavius", "expression": "cav_status == 'Two beeps every 60 seconds with yellow LED'"}), WorkflowNode(id="cav_sensor_out", type=WorkflowNodeType.DECISION, data={"group": "Cavius", "outcome": "close_with_guidance", "message": "Cavius sensor fault warning reported.\n\nThe alarm will not respond correctly to CO. Replace the unit.\nNo engineer visit needed."}), WorkflowNode(id="cav_eol_check", type=WorkflowNodeType.CONDITION, data={"group": "Cavius", "expression": "cav_status == 'Three beeps every 60 seconds with yellow LED'"}), WorkflowNode(id="cav_eol_out", type=WorkflowNodeType.DECISION, data={"group": "Cavius", "outcome": "close_with_guidance", "message": "Cavius end-of-life warning reported.\n\nReplace the alarm unit.\nNo engineer visit needed."}), WorkflowNode(id="cav_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Cavius", "outcome": "close_with_guidance", "message": "Green LED flashing every 60 seconds indicates normal mode on the Cavius unit. Test the alarm if needed and call back if it alarms again."})], [WorkflowEdge(source="cav_status", target="cav_alarm_check"), WorkflowEdge(source="cav_alarm_check", target="cav_alarm_out", condition="True"), WorkflowEdge(source="cav_alarm_check", target="cav_battery_check", condition="False"), WorkflowEdge(source="cav_battery_check", target="cav_battery_out", condition="True"), WorkflowEdge(source="cav_battery_check", target="cav_sensor_check", condition="False"), WorkflowEdge(source="cav_sensor_check", target="cav_sensor_out", condition="True"), WorkflowEdge(source="cav_sensor_check", target="cav_eol_check", condition="False"), WorkflowEdge(source="cav_eol_check", target="cav_eol_out", condition="True"), WorkflowEdge(source="cav_eol_check", target="cav_normal_out", condition="False")])


def _create_co_alarm_other_workflow(tenant_id: str) -> WorkflowDefinition:
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_OTHER, "gen_q1", [WorkflowNode(id="gen_q1", type=WorkflowNodeType.QUESTION, data={"group": "Other", "question": "What colour light is flashing on the alarm?", "variable": "gen_led", "options": [{"label": "Red", "score": 20}, {"label": "Amber / Yellow", "score": 0}, {"label": "Green", "score": 0}, {"label": "No light", "score": 3}]}), WorkflowNode(id="gen_check_red", type=WorkflowNodeType.CONDITION, data={"group": "Other", "expression": "gen_led == 'Red'"}), WorkflowNode(id="gen_q2", type=WorkflowNodeType.QUESTION, data={"group": "Other", "question": "Is the alarm beeping loudly?", "variable": "gen_sound", "options": [{"label": "Yes - loud repeated beeps", "score": 25}, {"label": "No - chirping or silent", "score": 5}]}), WorkflowNode(id="gen_check_co", type=WorkflowNodeType.CONDITION, data={"group": "Other", "expression": "gen_sound == 'Yes - loud repeated beeps'"}), WorkflowNode(id="gen_co_out", type=WorkflowNodeType.DECISION, data={"group": "Other", "outcome": "emergency_dispatch", "message": "CO ALARM - POSSIBLE CO DETECTED.\n\n1. Evacuate NOW\n2. Open doors/windows\n3. Do NOT re-enter\n4. Call 999 if unwell\n\nEngineer dispatched."}), WorkflowNode(id="gen_schedule_out", type=WorkflowNodeType.DECISION, data={"group": "Other", "outcome": "schedule_engineer", "message": "We recommend an engineer investigates.\n\nVentilate and don't use gas appliances until checked."}), WorkflowNode(id="gen_check_amber", type=WorkflowNodeType.CONDITION, data={"group": "Other", "expression": "gen_led == 'Amber / Yellow'"}), WorkflowNode(id="gen_battery_out", type=WorkflowNodeType.DECISION, data={"group": "Other", "outcome": "close_with_guidance", "message": "Amber/yellow usually means low battery or end of life (not CO).\n\nReplace batteries or the alarm. No engineer visit needed."}), WorkflowNode(id="gen_normal_out", type=WorkflowNodeType.DECISION, data={"group": "Other", "outcome": "close_with_guidance", "message": "Alarm appears normal. Press test button to confirm.\nIf it sounds again, call us back."})], [WorkflowEdge(source="gen_q1", target="gen_check_red"), WorkflowEdge(source="gen_check_red", target="gen_q2", condition="True"), WorkflowEdge(source="gen_q2", target="gen_check_co"), WorkflowEdge(source="gen_check_co", target="gen_co_out", condition="True"), WorkflowEdge(source="gen_check_co", target="gen_schedule_out", condition="False"), WorkflowEdge(source="gen_check_red", target="gen_check_amber", condition="False"), WorkflowEdge(source="gen_check_amber", target="gen_battery_out", condition="True"), WorkflowEdge(source="gen_check_amber", target="gen_normal_out", condition="False")])


CO_ALARM_SUBWORKFLOW_CREATORS = {
    CO_ALARM_SUBFLOW_FIREANGEL: _create_co_alarm_fireangel_workflow,
    CO_ALARM_SUBFLOW_FIREHAWK: _create_co_alarm_firehawk_workflow,
    CO_ALARM_SUBFLOW_AICO: _create_co_alarm_aico_workflow,
    CO_ALARM_SUBFLOW_KIDDE: _create_co_alarm_kidde_workflow,
    CO_ALARM_SUBFLOW_XSENSE: _create_co_alarm_xsense_workflow,
    CO_ALARM_SUBFLOW_HONEYWELL: _create_co_alarm_honeywell_workflow,
    CO_ALARM_SUBFLOW_GOOGLE_NEST: _create_co_alarm_google_nest_workflow,
    CO_ALARM_SUBFLOW_NETATMO: _create_co_alarm_netatmo_workflow,
    CO_ALARM_SUBFLOW_CAVIUS: _create_co_alarm_cavius_workflow,
    CO_ALARM_SUBFLOW_OTHER: _create_co_alarm_other_workflow,
}
# ============================================================
# WORKFLOW 2: SUSPECTED CO LEAK - Enhanced symptom triage
# Based on CO Data symptom reports
# ============================================================

def _create_suspected_co_leak_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    Enhanced CO Symptoms workflow.

    Symptoms from PPT: Tiredness, Dizziness, Headache, Nausea,
    Flu-like, Shortness of breath.
    Key triage question: Do symptoms occur inside AND outside property?
    (If only inside = likely CO; if both = likely illness)
    """
    workflow_id = f"{tenant_id}_{SUSPECTED_CO_LEAK}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=SUSPECTED_CO_LEAK,
        version=1,
        start_node="evacuation_status",
        nodes=[
            # === Q1: Evacuation ===
            WorkflowNode(
                id="evacuation_status",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you left the property and are you in fresh air?",
                    "variable": "is_evacuated",
                    "options": [
                        {"label": "Yes, I am outside", "score": 0},
                        {"label": "No, I am still inside", "score": 15},
                    ]
                },
            ),
            # === Q2: Specific symptoms ===
            WorkflowNode(
                id="symptom_type",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Which symptoms are you or others experiencing? Select the most severe:",
                    "variable": "symptom_type",
                    "options": [
                        {"label": "Loss of consciousness / collapse", "score": 40},
                        {"label": "Confusion or difficulty thinking", "score": 30},
                        {"label": "Nausea and vomiting", "score": 25},
                        {"label": "Severe headache and dizziness", "score": 20},
                        {"label": "Headache only", "score": 10},
                        {"label": "Tiredness / flu-like feelings", "score": 8},
                        {"label": "Shortness of breath", "score": 25},
                    ]
                },
            ),
            # === Q3: Key triage - symptoms inside vs outside (from PPT Slide 6) ===
            WorkflowNode(
                id="symptoms_location",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do the symptoms occur only inside the property, or also when you are outside?",
                    "variable": "symptoms_location",
                    "options": [
                        {"label": "Only when inside the property (improve when I go outside)", "score": 20},
                        {"label": "Both inside and outside the property", "score": 0},
                        {"label": "Not sure", "score": 10},
                    ]
                },
            ),
            # === Q4: Number of people affected ===
            WorkflowNode(
                id="people_affected",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How many people in the property are experiencing symptoms?",
                    "variable": "people_affected",
                    "options": [
                        {"label": "Multiple people (2 or more)", "score": 15},
                        {"label": "Just me", "score": 5},
                        {"label": "Pets also seem unwell", "score": 20},
                    ]
                },
            ),
            # === Q5: CO alarm present? ===
            WorkflowNode(
                id="co_alarm_status",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do you have a CO alarm in the property? Is it sounding?",
                    "variable": "co_alarm_status",
                    "options": [
                        {"label": "Yes - CO alarm is sounding", "score": 20},
                        {"label": "Yes - CO alarm is NOT sounding", "score": 0},
                        {"label": "No CO alarm installed", "score": 5},
                        {"label": "Don't know", "score": 5},
                    ]
                },
            ),
            # === Q6: Gas appliances running ===
            WorkflowNode(
                id="appliances_running",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Were any gas appliances running when symptoms started? (boiler, gas fire, hob, cooker)",
                    "variable": "appliances_running",
                    "options": [
                        {"label": "Yes - boiler was running", "score": 10},
                        {"label": "Yes - gas fire was on", "score": 12},
                        {"label": "Yes - multiple appliances", "score": 15},
                        {"label": "No appliances were on", "score": 0},
                        {"label": "Not sure", "score": 5},
                    ]
                },
            ),
            # === Q7: Vulnerable people ===
            WorkflowNode(
                id="vulnerable_people",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are there children, elderly, pregnant people, or anyone with breathing difficulties in the property?",
                    "variable": "vulnerable_people",
                    "options": [
                        {"label": "Yes - children under 5", "score": 15},
                        {"label": "Yes - elderly or pregnant", "score": 12},
                        {"label": "Yes - someone with respiratory condition", "score": 15},
                        {"label": "No", "score": 0},
                    ]
                },
            ),

            # === Risk Calculation ===
            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),

            # === Decision: symptoms only outside = likely not CO ===
            WorkflowNode(
                id="check_outside_symptoms",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "symptoms_location == 'Both inside and outside the property' and co_alarm_status == 'Yes - CO alarm is NOT sounding' and risk_score < 30"
                },
            ),
            WorkflowNode(
                id="not_co_guidance",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": (
                        "Your symptoms occur both inside and outside the property, your CO alarm is not sounding, "
                        "and the overall risk indicators are low. This is less likely to be CO-related.\n\n"
                        "HOWEVER, if symptoms persist or worsen:\n"
                        "1. See your GP or call NHS 111\n"
                        "2. If symptoms only occur at home, call us back\n"
                        "3. Ensure your CO alarm is working (test button)\n"
                        "4. Get gas appliances serviced annually by a Gas Safe engineer"
                    )
                },
            ),

            # Risk routing
            WorkflowNode(
                id="check_emergency",
                type=WorkflowNodeType.SWITCH,
                data={"variable": "risk_score", "label": "Risk Level", "cases": ["Emergency", "Schedule Engineer"]},
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": (
                        "SUSPECTED CO EXPOSURE - EMERGENCY RESPONSE.\n\n"
                        "IMMEDIATE ACTIONS:\n"
                        "1. Evacuate ALL people and pets from the property NOW\n"
                        "2. Do NOT re-enter the property\n"
                        "3. Call 999 if anyone is unconscious or severely unwell\n"
                        "4. Leave windows and doors open as you exit\n"
                        "5. Turn off gas supply at the meter if safely accessible\n\n"
                        "An emergency engineer is being dispatched."
                    )
                },
            ),

            # Schedule engineer for investigation
            WorkflowNode(
                id="schedule_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": (
                        "We are scheduling a Gas Safe engineer to investigate potential CO.\n\n"
                        "WHILE YOU WAIT:\n"
                        "1. Open windows for ventilation\n"
                        "2. Turn off gas appliances if safe to do so\n"
                        "3. Monitor symptoms - if they worsen, evacuate and call back\n"
                        "4. Do not sleep in the property until the engineer has attended"
                    )
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="evacuation_status", target="symptom_type"),
            WorkflowEdge(source="symptom_type", target="symptoms_location"),
            WorkflowEdge(source="symptoms_location", target="people_affected"),
            WorkflowEdge(source="people_affected", target="co_alarm_status"),
            WorkflowEdge(source="co_alarm_status", target="appliances_running"),
            WorkflowEdge(source="appliances_running", target="vulnerable_people"),
            WorkflowEdge(source="vulnerable_people", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="check_outside_symptoms"),

            # Not CO path
            WorkflowEdge(source="check_outside_symptoms", target="not_co_guidance", condition="True"),
            WorkflowEdge(source="check_outside_symptoms", target="check_emergency", condition="False"),

            # Risk routing
            WorkflowEdge(source="check_emergency", target="emergency_outcome", condition="risk_score >= 55"),
            WorkflowEdge(source="check_emergency", target="schedule_outcome"),
        ],
    )


# ============================================================
# WORKFLOW 3: CO ORANGE FLAMES
# Orange/yellow flames indicating incomplete combustion
# ============================================================

def _create_co_orange_flames_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    CO Orange Flames workflow.
    From CO Data: Reported as "Orange Flames" sign.
    Orange/yellow lazy flames indicate incomplete combustion → CO risk.
    """
    workflow_id = f"{tenant_id}_{CO_ORANGE_FLAMES}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_ORANGE_FLAMES,
        version=1,
        start_node="flame_location",
        nodes=[
            WorkflowNode(
                id="flame_location",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Which appliance is showing orange/yellow flames?",
                    "variable": "flame_location",
                    "options": [
                        {"label": "Gas hob / cooker", "score": 10},
                        {"label": "Gas fire / fireplace", "score": 15},
                        {"label": "Boiler (visible flame)", "score": 20},
                        {"label": "Multiple appliances", "score": 25},
                    ]
                },
            ),
            WorkflowNode(
                id="flame_colour",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What colour are the flames?",
                    "variable": "flame_colour",
                    "options": [
                        {"label": "Mostly orange/yellow with no blue", "score": 20},
                        {"label": "Orange tips on otherwise blue flame", "score": 8},
                        {"label": "Flickering between orange and blue", "score": 12},
                        {"label": "Red/sooty flame", "score": 25},
                    ]
                },
            ),
            WorkflowNode(
                id="flame_symptoms",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are you experiencing any symptoms (headache, dizziness, nausea)?",
                    "variable": "flame_symptoms",
                    "options": [
                        {"label": "Yes - feeling unwell", "score": 25},
                        {"label": "No symptoms", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="co_alarm_present",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do you have a CO alarm? Is it sounding?",
                    "variable": "co_alarm_present",
                    "options": [
                        {"label": "Yes - CO alarm is sounding", "score": 25},
                        {"label": "Yes - CO alarm is NOT sounding", "score": 0},
                        {"label": "No CO alarm installed", "score": 5},
                    ]
                },
            ),
            WorkflowNode(
                id="soot_visible",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is there any soot, black marks, or staining on or around the appliance?",
                    "variable": "soot_visible",
                    "options": [
                        {"label": "Yes - visible soot/black marks", "score": 15},
                        {"label": "No", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="ventilation_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is the room well ventilated? Are air vents clear and unblocked?",
                    "variable": "ventilation",
                    "options": [
                        {"label": "Good ventilation / vents clear", "score": 0},
                        {"label": "Poor ventilation / vents blocked", "score": 10},
                        {"label": "No vents in the room", "score": 12},
                    ]
                },
            ),

            # Risk calculation → SWITCH routing
            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="risk_switch",
                type=WorkflowNodeType.SWITCH,
                data={
                    "variable": "risk_score",
                    "label": "Risk Level",
                    "cases": ["Emergency", "Schedule Engineer", "Guidance"],
                },
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "Orange/yellow flames with CO indicators detected. Turn off the appliance, ventilate, and evacuate. Engineer dispatched."
                },
            ),
            WorkflowNode(
                id="schedule_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "Orange/yellow flames indicate incomplete combustion which can produce CO.\n\n1. Turn off the affected appliance\n2. Do not use until inspected by Gas Safe engineer\n3. Open windows for ventilation"
                },
            ),
            WorkflowNode(
                id="guidance_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": "Minor orange tipping can be normal (dust, cooking residue).\n\n1. Clean burner ports with a stiff brush\n2. Ensure air vents are unblocked\n3. Get appliances serviced annually\n4. Ensure you have a working CO alarm\n5. If flames become fully orange, call back"
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="flame_location", target="flame_colour"),
            WorkflowEdge(source="flame_colour", target="flame_symptoms"),
            WorkflowEdge(source="flame_symptoms", target="co_alarm_present"),
            WorkflowEdge(source="co_alarm_present", target="soot_visible"),
            WorkflowEdge(source="soot_visible", target="ventilation_check"),
            WorkflowEdge(source="ventilation_check", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="risk_switch"),
            WorkflowEdge(source="risk_switch", target="emergency_outcome", condition="risk_score >= 60"),
            WorkflowEdge(source="risk_switch", target="schedule_outcome", condition="risk_score >= 30"),
            WorkflowEdge(source="risk_switch", target="guidance_outcome"),
        ],
    )


# ============================================================
# WORKFLOW 4: CO SOOTING/SCARRING
# ============================================================

def _create_co_sooting_scarring_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    CO Sooting/Scarring workflow.
    Sooting or scarring on/around gas appliances indicates
    incomplete combustion and potential CO production.
    """
    workflow_id = f"{tenant_id}_{CO_SOOTING_SCARRING}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_SOOTING_SCARRING,
        version=1,
        start_node="soot_location",
        nodes=[
            WorkflowNode(
                id="soot_location",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Where have you noticed the sooting or black marks?",
                    "variable": "soot_location",
                    "options": [
                        {"label": "On/around the boiler", "score": 20},
                        {"label": "On/around gas fire or fireplace", "score": 18},
                        {"label": "On/around gas hob or cooker", "score": 12},
                        {"label": "On walls or ceiling near appliance", "score": 15},
                        {"label": "Multiple locations", "score": 25},
                    ]
                },
            ),
            WorkflowNode(
                id="soot_severity",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How severe is the sooting?",
                    "variable": "soot_severity",
                    "options": [
                        {"label": "Heavy black deposits / thick soot", "score": 25},
                        {"label": "Moderate staining", "score": 15},
                        {"label": "Light marks / slight discolouration", "score": 5},
                    ]
                },
            ),
            WorkflowNode(
                id="soot_symptoms",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is anyone experiencing symptoms (headache, dizziness, nausea)?",
                    "variable": "soot_symptoms",
                    "options": [
                        {"label": "Yes - symptoms present", "score": 25},
                        {"label": "No symptoms", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="flame_colour_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "If you can see the flame, what colour is it?",
                    "variable": "flame_colour",
                    "options": [
                        {"label": "Orange/yellow (lazy flame)", "score": 15},
                        {"label": "Blue (normal)", "score": 0},
                        {"label": "Cannot see the flame", "score": 5},
                    ]
                },
            ),
            WorkflowNode(
                id="co_alarm_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do you have a CO alarm? Has it activated?",
                    "variable": "co_alarm",
                    "options": [
                        {"label": "Yes - alarm sounding", "score": 25},
                        {"label": "Yes - not sounding", "score": 0},
                        {"label": "No CO alarm", "score": 5},
                    ]
                },
            ),

            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="risk_switch",
                type=WorkflowNodeType.SWITCH,
                data={
                    "variable": "risk_score",
                    "label": "Risk Level",
                    "cases": ["Emergency", "Schedule Engineer"],
                },
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "Significant sooting with CO risk indicators. Turn off the appliance, evacuate, and ventilate. Engineer dispatched."
                },
            ),
            WorkflowNode(
                id="schedule_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": (
                        "Sooting on gas appliances indicates incomplete combustion which can produce carbon monoxide.\n\n"
                        "IMMEDIATE ACTIONS:\n"
                        "1. Stop using the affected appliance immediately\n"
                        "2. Do NOT attempt to clean inside the appliance\n"
                        "3. Ensure the room is ventilated\n"
                        "4. A Gas Safe engineer will inspect the appliance\n\n"
                        "Common causes: blocked flue, faulty burner, poor ventilation, dirty heat exchanger."
                    )
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="soot_location", target="soot_severity"),
            WorkflowEdge(source="soot_severity", target="soot_symptoms"),
            WorkflowEdge(source="soot_symptoms", target="flame_colour_check"),
            WorkflowEdge(source="flame_colour_check", target="co_alarm_check"),
            WorkflowEdge(source="co_alarm_check", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="risk_switch"),
            WorkflowEdge(source="risk_switch", target="emergency_outcome", condition="risk_score >= 55"),
            WorkflowEdge(source="risk_switch", target="schedule_outcome"),
        ],
    )


# ============================================================
# WORKFLOW 5: CO EXCESSIVE CONDENSATION
# ============================================================

def _create_co_excessive_condensation_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    CO Excessive Condensation workflow.
    Excessive condensation near gas appliances can indicate
    blocked flue or poor ventilation → CO buildup risk.
    """
    workflow_id = f"{tenant_id}_{CO_EXCESSIVE_CONDENSATION}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_EXCESSIVE_CONDENSATION,
        version=1,
        start_node="condensation_location",
        nodes=[
            WorkflowNode(
                id="condensation_location",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Where is the excessive condensation appearing?",
                    "variable": "condensation_location",
                    "options": [
                        {"label": "On windows near the boiler", "score": 15},
                        {"label": "On walls near a gas fire", "score": 15},
                        {"label": "Throughout the room with gas appliance", "score": 18},
                        {"label": "In bathroom (near boiler flue)", "score": 12},
                        {"label": "General condensation (not near gas appliance)", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="condensation_timing",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "When does the condensation appear?",
                    "variable": "condensation_timing",
                    "options": [
                        {"label": "Only when gas appliances are running", "score": 20},
                        {"label": "Worse when heating is on", "score": 15},
                        {"label": "All the time regardless", "score": 5},
                        {"label": "Not sure", "score": 8},
                    ]
                },
            ),
            WorkflowNode(
                id="symptoms_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is anyone experiencing symptoms (headache, dizziness, nausea)?",
                    "variable": "symptoms",
                    "options": [
                        {"label": "Yes - symptoms present", "score": 25},
                        {"label": "No symptoms", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="flue_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you see the boiler flue (exhaust pipe) outside? Does it appear blocked or damaged?",
                    "variable": "flue_condition",
                    "options": [
                        {"label": "Flue appears blocked or obstructed", "score": 25},
                        {"label": "Flue looks damaged or disconnected", "score": 30},
                        {"label": "Flue appears normal", "score": 0},
                        {"label": "Cannot see / don't know where it is", "score": 5},
                    ]
                },
            ),
            WorkflowNode(
                id="co_alarm_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do you have a working CO alarm?",
                    "variable": "co_alarm",
                    "options": [
                        {"label": "Yes - and it is sounding", "score": 25},
                        {"label": "Yes - not sounding", "score": 0},
                        {"label": "No CO alarm", "score": 5},
                    ]
                },
            ),

            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="check_not_gas_related",
                type=WorkflowNodeType.CONDITION,
                data={"expression": "condensation_location == 'General condensation (not near gas appliance)' and symptoms == 'No symptoms' and risk_score < 15"},
            ),
            WorkflowNode(
                id="not_gas_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": (
                        "General condensation not near gas appliances is unlikely to be CO-related. "
                        "It is usually caused by poor ventilation, humidity, or inadequate insulation.\n\n"
                        "ADVICE:\n"
                        "1. Improve ventilation - open windows regularly\n"
                        "2. Use extractor fans in kitchen and bathroom\n"
                        "3. Do not dry clothes on radiators\n"
                        "4. Consider a dehumidifier\n"
                        "5. If symptoms develop, call back immediately"
                    )
                },
            ),
            WorkflowNode(
                id="check_emergency",
                type=WorkflowNodeType.SWITCH,
                data={"variable": "risk_score", "label": "Risk Level", "cases": ["Emergency", "Schedule Engineer"]},
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "Excessive condensation with CO risk indicators (blocked/damaged flue or symptoms). Turn off gas appliances, ventilate, and evacuate. Engineer dispatched."
                },
            ),
            WorkflowNode(
                id="schedule_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": (
                        "Excessive condensation near gas appliances may indicate a ventilation or flue issue.\n\n"
                        "ACTIONS:\n"
                        "1. Ensure the room is well ventilated\n"
                        "2. Do not block air vents\n"
                        "3. A Gas Safe engineer will check your appliances and flue\n"
                        "4. If symptoms develop before the visit, evacuate and call back"
                    )
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="condensation_location", target="condensation_timing"),
            WorkflowEdge(source="condensation_timing", target="symptoms_check"),
            WorkflowEdge(source="symptoms_check", target="flue_check"),
            WorkflowEdge(source="flue_check", target="co_alarm_check"),
            WorkflowEdge(source="co_alarm_check", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="check_not_gas_related"),
            WorkflowEdge(source="check_not_gas_related", target="not_gas_outcome", condition="True"),
            WorkflowEdge(source="check_not_gas_related", target="check_emergency", condition="False"),
            WorkflowEdge(source="check_emergency", target="emergency_outcome", condition="risk_score >= 55"),
            WorkflowEdge(source="check_emergency", target="schedule_outcome"),
        ],
    )


# ============================================================
# WORKFLOW 6: CO VISIBLE FUMES
# ============================================================

def _create_co_visible_fumes_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    CO Visible Fumes workflow.
    Visible fumes/smoke from gas appliances - serious CO risk.
    """
    workflow_id = f"{tenant_id}_{CO_VISIBLE_FUMES}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_VISIBLE_FUMES,
        version=1,
        start_node="fumes_source",
        nodes=[
            WorkflowNode(
                id="fumes_source",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Where are the fumes/smoke coming from?",
                    "variable": "fumes_source",
                    "options": [
                        {"label": "From the boiler", "score": 25},
                        {"label": "From a gas fire", "score": 20},
                        {"label": "From the cooker/hob", "score": 15},
                        {"label": "From a gas water heater", "score": 25},
                        {"label": "Not sure - just visible in room", "score": 20},
                    ]
                },
            ),
            WorkflowNode(
                id="fumes_smell",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you describe the smell?",
                    "variable": "fumes_smell",
                    "options": [
                        {"label": "Acrid/burning smell", "score": 20},
                        {"label": "No smell (CO is odourless)", "score": 10},
                        {"label": "Gas/rotten egg smell", "score": 25},
                        {"label": "Musty/damp smell", "score": 5},
                    ]
                },
            ),
            WorkflowNode(
                id="fumes_symptoms",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are you or anyone experiencing symptoms?",
                    "variable": "symptoms",
                    "options": [
                        {"label": "Yes - feeling unwell (headache/dizzy/nausea)", "score": 25},
                        {"label": "Eyes stinging or watering", "score": 15},
                        {"label": "No symptoms", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="appliance_turned_off",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you turned off the appliance producing fumes?",
                    "variable": "appliance_off",
                    "options": [
                        {"label": "Yes - turned it off", "score": 0},
                        {"label": "No - still running", "score": 15},
                        {"label": "Cannot reach it safely", "score": 20},
                    ]
                },
            ),

            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="risk_switch",
                type=WorkflowNodeType.SWITCH,
                data={"variable": "risk_score", "label": "Risk Level", "cases": ["Emergency", "Schedule Engineer"]},
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": (
                        "VISIBLE FUMES FROM GAS APPLIANCE - EMERGENCY.\n\n"
                        "1. Turn off the appliance if safe to do so\n"
                        "2. Evacuate the property immediately\n"
                        "3. Open windows and doors as you leave\n"
                        "4. Do NOT re-enter until engineer declares it safe\n"
                        "5. Call 999 if anyone is unwell\n\n"
                        "Emergency engineer dispatched."
                    )
                },
            ),
            WorkflowNode(
                id="schedule_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": (
                        "Visible fumes from a gas appliance require investigation.\n\n"
                        "1. Keep the appliance turned off\n"
                        "2. Ventilate the room well\n"
                        "3. A Gas Safe engineer will investigate\n"
                        "4. If symptoms develop, evacuate and call back"
                    )
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="fumes_source", target="fumes_smell"),
            WorkflowEdge(source="fumes_smell", target="fumes_symptoms"),
            WorkflowEdge(source="fumes_symptoms", target="appliance_turned_off"),
            WorkflowEdge(source="appliance_turned_off", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="risk_switch"),
            WorkflowEdge(source="risk_switch", target="emergency_outcome", condition="risk_score >= 40"),
            WorkflowEdge(source="risk_switch", target="schedule_outcome"),
        ],
    )


# ============================================================
# WORKFLOW 7: CO BLOOD TEST
# ============================================================

def _create_co_blood_test_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    CO Blood Test Result workflow.
    Carboxyhemoglobin (COHb) test confirms CO exposure.
    Always dispatch - this is confirmed CO exposure.
    """
    workflow_id = f"{tenant_id}_{CO_BLOOD_TEST}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_BLOOD_TEST,
        version=1,
        start_node="test_result",
        nodes=[
            WorkflowNode(
                id="test_result",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What was the CO blood test (carboxyhemoglobin) result?",
                    "variable": "test_result",
                    "options": [
                        {"label": "Elevated / positive for CO exposure", "score": 40},
                        {"label": "Borderline / slightly elevated", "score": 25},
                        {"label": "Normal / negative", "score": 0},
                        {"label": "Don't know the exact result", "score": 15},
                    ]
                },
            ),
            WorkflowNode(
                id="test_who",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Who was tested?",
                    "variable": "test_who",
                    "options": [
                        {"label": "Multiple household members", "score": 20},
                        {"label": "One adult", "score": 10},
                        {"label": "Child or baby", "score": 25},
                        {"label": "Pregnant woman", "score": 25},
                    ]
                },
            ),
            WorkflowNode(
                id="property_status",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is anyone still in the property?",
                    "variable": "property_status",
                    "options": [
                        {"label": "Yes - people are still inside", "score": 20},
                        {"label": "No - everyone has been evacuated", "score": 0},
                        {"label": "Patient is in hospital, family still at home", "score": 15},
                    ]
                },
            ),
            WorkflowNode(
                id="gas_appliances",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What gas appliances are in the property?",
                    "variable": "gas_appliances",
                    "options": [
                        {"label": "Gas boiler", "score": 10},
                        {"label": "Gas fire and boiler", "score": 12},
                        {"label": "Multiple gas appliances", "score": 15},
                        {"label": "Don't know", "score": 8},
                    ]
                },
            ),

            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            # Normal test result - no dispatch needed
            WorkflowNode(
                id="check_normal",
                type=WorkflowNodeType.SWITCH,
                data={"variable": "test_result", "label": "Test Result", "cases": ["Normal", "Positive"]},
            ),
            WorkflowNode(
                id="normal_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": (
                        "The CO blood test came back normal. This is reassuring.\n\n"
                        "ADVICE:\n"
                        "1. If symptoms persist, revisit your GP\n"
                        "2. Ensure you have a working CO alarm\n"
                        "3. Get gas appliances serviced annually\n"
                        "4. If CO alarm sounds in future, evacuate and call us"
                    )
                },
            ),
            # Positive result - always dispatch
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": (
                        "CONFIRMED CO EXPOSURE - EMERGENCY INVESTIGATION REQUIRED.\n\n"
                        "IMMEDIATE ACTIONS:\n"
                        "1. NO ONE should enter or remain in the property\n"
                        "2. All gas appliances must be turned off at the meter\n"
                        "3. Windows and doors should be opened for ventilation\n"
                        "4. Emergency engineer dispatched for full CO investigation\n"
                        "5. All gas appliances will be tested before supply is restored\n"
                        "6. This incident will be reported under RIDDOR if required"
                    )
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="test_result", target="test_who"),
            WorkflowEdge(source="test_who", target="property_status"),
            WorkflowEdge(source="property_status", target="gas_appliances"),
            WorkflowEdge(source="gas_appliances", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="check_normal"),
            WorkflowEdge(source="check_normal", target="normal_outcome", condition="test_result == 'Normal / negative'"),
            WorkflowEdge(source="check_normal", target="emergency_outcome"),
        ],
    )


# ============================================================
# WORKFLOW 8: CO FATALITY
# ============================================================

def _create_co_fatality_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    CO Fatality Emergency Protocol.
    Immediate emergency dispatch + escalation. No triage - just gather info.
    """
    workflow_id = f"{tenant_id}_{CO_FATALITY}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_FATALITY,
        version=1,
        start_node="emergency_alert",
        nodes=[
            WorkflowNode(
                id="emergency_alert",
                type=WorkflowNodeType.ALERT,
                data={
                    "alert_message": "CO FATALITY REPORTED - IMMEDIATE EMERGENCY PROTOCOL ACTIVATED",
                    "severity": "critical",
                },
            ),
            WorkflowNode(
                id="confirm_emergency_services",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have emergency services (999) been called?",
                    "variable": "emergency_called",
                    "options": [
                        {"label": "Yes - emergency services are on scene", "score": 0},
                        {"label": "Yes - they are on their way", "score": 0},
                        {"label": "No - not yet called", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="property_evacuated",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Has the property been fully evacuated? Is anyone else still inside?",
                    "variable": "property_evacuated",
                    "options": [
                        {"label": "Yes - everyone is out", "score": 0},
                        {"label": "No - people may still be inside", "score": 0},
                        {"label": "Not sure", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="reporter_type",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Who is reporting this?",
                    "variable": "reporter_type",
                    "options": [
                        {"label": "Emergency Services (Police/Ambulance/Fire)", "score": 0},
                        {"label": "Occupier / Family member", "score": 0},
                        {"label": "Landlord / Housing Association", "score": 0},
                        {"label": "Neighbour", "score": 0},
                        {"label": "Other", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="location_details",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is the gas supply to the property still on?",
                    "variable": "gas_supply",
                    "options": [
                        {"label": "Yes - gas is still on", "score": 0},
                        {"label": "No - gas has been turned off", "score": 0},
                        {"label": "Don't know", "score": 0},
                    ]
                },
            ),

            # Escalation
            WorkflowNode(
                id="escalation",
                type=WorkflowNodeType.ESCALATION,
                data={
                    "escalation_to": "emergency_response_manager",
                    "escalation_level": 5,
                    "reason": "CO fatality reported - requires immediate senior management involvement, HSE notification, and RIDDOR reporting",
                },
            ),
            WorkflowNode(
                id="notification",
                type=WorkflowNodeType.NOTIFICATION,
                data={
                    "notification_type": "sms",
                    "recipients": ["emergency_response_team", "senior_management", "hse_liaison"],
                    "message": "CRITICAL: CO fatality reported. Emergency protocol activated. Immediate attendance required.",
                },
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": (
                        "CO FATALITY - EMERGENCY PROTOCOL ACTIVATED.\n\n"
                        "1. Emergency engineer dispatched immediately\n"
                        "2. Senior management notified\n"
                        "3. HSE will be notified under RIDDOR\n"
                        "4. Police and emergency services coordination in progress\n"
                        "5. DO NOT enter the property under any circumstances\n"
                        "6. Gas supply will be isolated at the earliest safe opportunity\n\n"
                        "This is being treated as the highest priority."
                    )
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="emergency_alert", target="confirm_emergency_services"),
            WorkflowEdge(source="confirm_emergency_services", target="property_evacuated"),
            WorkflowEdge(source="property_evacuated", target="reporter_type"),
            WorkflowEdge(source="reporter_type", target="location_details"),
            WorkflowEdge(source="location_details", target="escalation"),
            WorkflowEdge(source="escalation", target="notification"),
            WorkflowEdge(source="notification", target="emergency_outcome"),
        ],
    )


# ============================================================
# WORKFLOW 9: CO SMOKE ALARM DIFFERENTIATION
# ============================================================

def _create_co_smoke_alarm_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    Smoke Alarm Differentiation workflow.
    Many callers confuse smoke alarms with CO alarms.
    This workflow helps differentiate and route correctly.
    """
    workflow_id = f"{tenant_id}_{CO_SMOKE_ALARM}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=CO_SMOKE_ALARM,
        version=1,
        start_node="alarm_identification",
        nodes=[
            WorkflowNode(
                id="alarm_identification",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Let's identify your alarm. Does it say 'CO', 'Carbon Monoxide', or 'Smoke' on it?",
                    "variable": "alarm_label",
                    "options": [
                        {"label": "Says 'CO' or 'Carbon Monoxide'", "score": 0},
                        {"label": "Says 'Smoke' or 'Smoke Detector'", "score": 0},
                        {"label": "Says both (combined smoke/CO alarm)", "score": 0},
                        {"label": "Cannot see any label", "score": 0},
                    ]
                },
            ),
            # If it says CO - redirect to CO alarm workflow
            WorkflowNode(
                id="check_is_co",
                type=WorkflowNodeType.CONDITION,
                data={"expression": "alarm_label == \"Says 'CO' or 'Carbon Monoxide'\" or alarm_label == \"Says both (combined smoke/CO alarm)\""},
            ),
            WorkflowNode(
                id="redirect_co",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": (
                        "This is a CO (Carbon Monoxide) alarm. This requires investigation.\n\n"
                        "IMMEDIATE ACTIONS:\n"
                        "1. Evacuate the property\n"
                        "2. Open windows and doors\n"
                        "3. Do not use gas appliances\n"
                        "4. An engineer will be scheduled to investigate\n\n"
                        "If you feel unwell (headache, dizziness, nausea), call 999 immediately."
                    )
                },
            ),

            # Smoke alarm path
            WorkflowNode(
                id="smoke_source",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you see any source of smoke, steam, or cooking fumes?",
                    "variable": "smoke_source",
                    "options": [
                        {"label": "Yes - cooking / toast / steam", "score": 0},
                        {"label": "Yes - something is burning", "score": 0},
                        {"label": "No visible smoke or source", "score": 5},
                    ]
                },
            ),
            WorkflowNode(
                id="gas_smell_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you smell gas (rotten egg smell)?",
                    "variable": "gas_smell",
                    "options": [
                        {"label": "Yes - I can smell gas", "score": 30},
                        {"label": "No gas smell", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="symptoms_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is anyone feeling unwell (headache, dizziness, nausea)?",
                    "variable": "symptoms",
                    "options": [
                        {"label": "Yes", "score": 25},
                        {"label": "No", "score": 0},
                    ]
                },
            ),

            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="risk_switch",
                type=WorkflowNodeType.SWITCH,
                data={"variable": "risk_score", "label": "Risk Level", "cases": ["Gas Emergency", "Smoke Only"]},
            ),
            WorkflowNode(
                id="gas_emergency",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "Gas smell or CO symptoms detected alongside smoke alarm. Emergency engineer dispatched. Evacuate the property and call 999 if there is a fire."
                },
            ),
            WorkflowNode(
                id="smoke_guidance",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": (
                        "This appears to be a smoke alarm (not a CO alarm). Smoke alarms are not a gas emergency service matter.\n\n"
                        "ADVICE:\n"
                        "1. If there is a fire, call 999 (Fire Service)\n"
                        "2. If triggered by cooking/steam, ventilate and press the silence button\n"
                        "3. If the alarm keeps sounding without cause, replace the batteries\n"
                        "4. Contact your local Fire Service for free smoke alarm checks\n\n"
                        "If you have any concerns about gas safety or CO, call us back."
                    )
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="alarm_identification", target="check_is_co"),
            WorkflowEdge(source="check_is_co", target="redirect_co", condition="True"),
            WorkflowEdge(source="check_is_co", target="smoke_source", condition="False"),
            WorkflowEdge(source="smoke_source", target="gas_smell_check"),
            WorkflowEdge(source="gas_smell_check", target="symptoms_check"),
            WorkflowEdge(source="symptoms_check", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="risk_switch"),
            WorkflowEdge(source="risk_switch", target="gas_emergency", condition="risk_score >= 25"),
            WorkflowEdge(source="risk_switch", target="smoke_guidance"),
        ],
    )


# ============================================================
# WORKFLOW 10: GAS SMELL (retained core workflow)
# ============================================================

def _create_gas_smell_workflow(tenant_id: str) -> WorkflowDefinition:
    """Gas smell workflow - retained from original. Indoor gas odour triage."""
    workflow_id = f"{tenant_id}_{GAS_SMELL}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=GAS_SMELL,
        version=1,
        start_node="smell_intensity",
        nodes=[
            WorkflowNode(
                id="smell_intensity",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How strong is the gas smell?",
                    "variable": "smell_intensity",
                    "options": [
                        {"label": "Faint", "score": 5},
                        {"label": "Moderate", "score": 15},
                        {"label": "Strong", "score": 30},
                        {"label": "Overwhelming", "score": 40},
                    ]
                },
            ),
            WorkflowNode(
                id="check_symptoms",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are you experiencing any symptoms?",
                    "variable": "symptoms",
                    "options": [
                        {"label": "None", "score": 0},
                        {"label": "Headache", "score": 25},
                        {"label": "Dizziness", "score": 25},
                        {"label": "Nausea", "score": 25},
                        {"label": "Multiple symptoms", "score": 40},
                    ]
                },
            ),
            WorkflowNode(
                id="check_hissing",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do you hear any hissing or unusual sounds?",
                    "variable": "has_hissing",
                    "options": [
                        {"label": "Yes", "score": 20},
                        {"label": "No", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="check_location",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is the smell near your gas meter or appliances?",
                    "variable": "near_meter_appliance",
                    "options": [
                        {"label": "Yes", "score": 10},
                        {"label": "No", "score": 0},
                        {"label": "Not sure", "score": 5},
                    ]
                },
            ),
            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="risk_switch",
                type=WorkflowNodeType.SWITCH,
                data={"variable": "risk_score", "label": "Risk Level", "cases": ["Emergency", "Schedule Engineer", "Guidance"]},
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "emergency_dispatch"},
            ),
            WorkflowNode(
                id="schedule_engineer_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "schedule_engineer"},
            ),
            WorkflowNode(
                id="guidance_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "close_with_guidance"},
            ),
        ],
        edges=[
            WorkflowEdge(source="smell_intensity", target="check_symptoms"),
            WorkflowEdge(source="check_symptoms", target="check_hissing"),
            WorkflowEdge(source="check_hissing", target="check_location"),
            WorkflowEdge(source="check_location", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="risk_switch"),
            WorkflowEdge(source="risk_switch", target="emergency_outcome", condition="risk_score >= 80"),
            WorkflowEdge(source="risk_switch", target="schedule_engineer_outcome", condition="risk_score >= 50"),
            WorkflowEdge(source="risk_switch", target="guidance_outcome"),
        ],
    )


# ============================================================
# WORKFLOW 11: HISSING SOUND (retained core workflow)
# ============================================================

def _create_hissing_sound_workflow(tenant_id: str) -> WorkflowDefinition:
    """Hissing sound workflow - retained from original. Audible gas leak triage."""
    workflow_id = f"{tenant_id}_{HISSING_SOUND}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=HISSING_SOUND,
        version=1,
        start_node="sound_location",
        nodes=[
            WorkflowNode(
                id="sound_location",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Where is the hissing or whistling sound coming from?",
                    "variable": "sound_location",
                    "options": [
                        {"label": "Near gas meter", "score": 25},
                        {"label": "Near a gas pipe", "score": 20},
                        {"label": "Behind a wall", "score": 15},
                        {"label": "Near an appliance", "score": 10},
                    ]
                },
            ),
            WorkflowNode(
                id="sound_type",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What does the sound like?",
                    "variable": "sound_type",
                    "options": [
                        {"label": "High-pitched hissing (like air escaping)", "score": 40},
                        {"label": "Low rumbling", "score": 15},
                        {"label": "Whistling", "score": 25},
                        {"label": "Intermittent clicking", "score": 10},
                    ]
                },
            ),
            WorkflowNode(
                id="gas_smell",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you smell gas?",
                    "variable": "gas_smell",
                    "options": [
                        {"label": "Yes - strong smell", "score": 30},
                        {"label": "Yes - faint smell", "score": 15},
                        {"label": "No smell", "score": 0},
                    ]
                },
            ),
            WorkflowNode(
                id="meter_spinning",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is the gas meter dial spinning faster than usual?",
                    "variable": "meter_spinning",
                    "options": [
                        {"label": "Yes - spinning fast", "score": 35},
                        {"label": "No / Cannot check", "score": 0},
                    ]
                },
            ),

            WorkflowNode(
                id="calculate_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="risk_switch",
                type=WorkflowNodeType.SWITCH,
                data={"variable": "risk_score", "label": "Risk Level", "cases": ["Emergency", "Schedule Engineer"]},
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "High-confidence gas leak detected. Evacuate the property, do not use electrical switches, and wait outside. Emergency engineer dispatched."
                },
            ),
            WorkflowNode(
                id="schedule_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "A hissing sound near gas infrastructure requires investigation. Do not use the affected area. An engineer will attend for visual inspection."
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="sound_location", target="sound_type"),
            WorkflowEdge(source="sound_type", target="gas_smell"),
            WorkflowEdge(source="gas_smell", target="meter_spinning"),
            WorkflowEdge(source="meter_spinning", target="calculate_risk"),
            WorkflowEdge(source="calculate_risk", target="risk_switch"),
            WorkflowEdge(source="risk_switch", target="emergency_outcome", condition="risk_score >= 60"),
            WorkflowEdge(source="risk_switch", target="schedule_outcome"),
        ],
    )
