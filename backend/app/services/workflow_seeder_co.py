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
        start_node="alarm_type",
        nodes=[
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
        start_node="alarm_type",
        nodes=[
            WorkflowNode(id="alarm_type", type=WorkflowNodeType.QUESTION, data={"question": "What type of alarm is sounding?", "variable": "alarm_type", "options": [{"label": "CO (Carbon Monoxide) alarm", "score": 10}, {"label": "Smoke alarm", "score": 0}, {"label": "Combined smoke and CO alarm", "score": 10}, {"label": "Not sure / Don't know", "score": 5}]}),
            WorkflowNode(id="co_symptoms", type=WorkflowNodeType.QUESTION, data={"question": "Is anyone feeling unwell?", "variable": "co_symptoms", "options": [{"label": "No symptoms", "score": 0}, {"label": "Headache, dizziness, or nausea", "score": 25}, {"label": "Breathing difficulty or chest pain", "score": 40}, {"label": "Drowsy, confused, or collapsed", "score": 50}, {"label": "Pets seem unwell", "score": 20}, {"label": "Not sure", "score": 10}]}),
            WorkflowNode(id="alarm_manufacturer", type=WorkflowNodeType.QUESTION, data={"question": "Can you see the brand name on the alarm?", "variable": "manufacturer", "options": [{"label": "Kidde", "score": 0}, {"label": "FireAngel", "score": 0}, {"label": "Aico", "score": 0}, {"label": "Firehawk", "score": 0}, {"label": "X-Sense", "score": 0}, {"label": "Honeywell", "score": 0}, {"label": "Google Nest", "score": 0}, {"label": "Netatmo", "score": 0}, {"label": "Cavius", "score": 0}, {"label": "Other / Cannot see", "score": 5}]}),
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
            WorkflowEdge(source="alarm_type", target="co_symptoms"),
            WorkflowEdge(source="co_symptoms", target="alarm_manufacturer"),
            WorkflowEdge(source="alarm_manufacturer", target="manufacturer_switch"),
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
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "FireAngel", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(prefix: str, questions: list[dict], messages: dict, label: str | None = None) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        score_variable = f"{prefix}_score"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(
            f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
            for question in questions
        )

        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "FireAngel",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "FireAngel",
                    "variable": normalized_variable,
                    "label": f"{label or prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        nodes.extend(
            [
                WorkflowNode(id=f"{prefix}_emergency_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "emergency_dispatch", "message": messages["emergency"]}),
                WorkflowNode(id=f"{prefix}_monitor_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "monitor", "message": messages["monitor"]}),
                WorkflowNode(id=f"{prefix}_guidance_out", type=WorkflowNodeType.DECISION, data={"group": "FireAngel", "outcome": "close_with_guidance", "message": messages["guidance"]}),
            ]
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )
        return nodes, edges

    fa6813_questions = [
        {"variable": "fa6813_sound", "question": "What is the FA6813 doing?", "options": [{"label": "4 loud chirps", "score": 25}, {"label": "1 chirp / 40 sec", "score": 2}, {"label": "2 chirps / 40 sec", "score": 4}, {"label": "3 chirps / 40 sec", "score": 5}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa6813_led", "question": "Which FA6813 light fits?", "options": [{"label": "Red with sound", "score": 12}, {"label": "Amber 1 flash / 40 sec", "score": 2}, {"label": "Amber 2 flashes / 40 sec", "score": 4}, {"label": "Amber 3 flashes / 40 sec", "score": 5}, {"label": "Green pulse / 40 sec", "score": 1}]},
        {"variable": "fa6813_timing", "question": "Which repeat time fits?", "options": [{"label": "Repeating alarm now", "score": 14}, {"label": "Every 40 sec only", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 5}]},
        {"variable": "fa6813_now", "question": "What best describes it right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Just a warning chirp", "score": 2}, {"label": "No sound, just a light", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa6813_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "Fault", "score": 4}, {"label": "End of life", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    fa6829s_questions = [
        {"variable": "fa6829s_sound", "question": "What is the FA6829S doing?", "options": [{"label": "4 loud chirps", "score": 25}, {"label": "1 chirp / 60 sec", "score": 2}, {"label": "2 chirps / 60 sec", "score": 4}, {"label": "3 chirps / 60 sec", "score": 5}, {"label": "Memory chirp", "score": 10}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa6829s_led", "question": "Which FA6829S light fits?", "options": [{"label": "Red with sound", "score": 12}, {"label": "Yellow 1 flash / 60 sec", "score": 2}, {"label": "Yellow 2 flashes / 60 sec", "score": 4}, {"label": "Yellow 3 flashes / 60 sec", "score": 5}, {"label": "Green pulse / 60 sec", "score": 1}]},
        {"variable": "fa6829s_absence", "question": "Did it sound earlier when no one was there?", "options": [{"label": "Yes, memory only", "score": 10}, {"label": "No, alarm now", "score": 16}, {"label": "No, warning only", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa6829s_timing", "question": "Which repeat time fits?", "options": [{"label": "Repeating alarm now", "score": 14}, {"label": "Every 60 sec only", "score": 3}, {"label": "Stops after pressing test", "score": 2}, {"label": "Not sure", "score": 5}]},
        {"variable": "fa6829s_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Alarm from earlier", "score": 10}, {"label": "Low battery", "score": 2}, {"label": "Fault / end of life", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    fa33xx_questions = [
        {"variable": "fa33xx_sound", "question": "What is the FA33xx alarm doing?", "options": [{"label": "4 loud chirps", "score": 25}, {"label": "1 chirp / min", "score": 2}, {"label": "2 chirps / min", "score": 4}, {"label": "3 chirps / min", "score": 5}, {"label": "1 short + 1 long", "score": 10}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa33xx_led", "question": "Which FA33xx light fits?", "options": [{"label": "Red flash each sec", "score": 12}, {"label": "Amber 1 flash / min", "score": 2}, {"label": "Amber 2 flashes / min", "score": 4}, {"label": "Amber 3 flashes / min", "score": 5}, {"label": "Amber / 25 sec", "score": 10}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa33xx_feature", "question": "What best describes it?", "options": [{"label": "Early warning", "score": 10}, {"label": "Alarm from earlier", "score": 10}, {"label": "Battery warning", "score": 2}, {"label": "Fault / end of life", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa33xx_now", "question": "What is happening right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Quiet now, but showed warning", "score": 10}, {"label": "Replace soon warning", "score": 2}, {"label": "Replace now warning", "score": 4}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa33xx_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Alarm from earlier", "score": 10}, {"label": "Low battery", "score": 2}, {"label": "Fault / end of life", "score": 4}, {"label": "Normal", "score": 1}]},
    ]
    fa6812_questions = [
        {"variable": "fa6812_sound", "question": "What is the FA6812 doing?", "options": [{"label": "4 loud chirps", "score": 25}, {"label": "1 chirp warning", "score": 2}, {"label": "2 chirps warning", "score": 4}, {"label": "3 chirps warning", "score": 5}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa6812_led", "question": "Which FA6812 light fits?", "options": [{"label": "Red with sound", "score": 12}, {"label": "Amber warning flash", "score": 4}, {"label": "Green pulse", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa6812_timing", "question": "Which repeat time fits?", "options": [{"label": "Repeating alarm now", "score": 14}, {"label": "Periodic warning only", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa6812_now", "question": "What best describes it right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Replace warning showing", "score": 4}, {"label": "Fault warning only", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fa6812_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Battery / end of life", "score": 4}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    fascb_questions = [
        {"variable": "fascb_alarm_type", "question": "Which SCB10-R sound fits?", "options": [{"label": "4 quick beeps", "score": 25}, {"label": "3 long smoke beeps", "score": 6}, {"label": "1 chirp / 40 sec", "score": 2}, {"label": "2 chirps / 40 sec", "score": 4}, {"label": "Not sure", "score": 6}]},
        {"variable": "fascb_led", "question": "Which SCB10-R light fits?", "options": [{"label": "Red with alarm", "score": 12}, {"label": "Amber 1 flash / 40 sec", "score": 2}, {"label": "Amber 2 flashes / 40 sec", "score": 4}, {"label": "Green pulse / 40 sec", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fascb_precedence", "question": "Which does it sound more like?", "options": [{"label": "CO alarm", "score": 20}, {"label": "Smoke alarm", "score": 6}, {"label": "Battery warning", "score": 2}, {"label": "Fault", "score": 4}, {"label": "Not sure", "score": 6}]},
        {"variable": "fascb_smoke", "question": "Is there smoke or burning too?", "options": [{"label": "No, just the alarm", "score": 16}, {"label": "Yes, there is smoke", "score": 6}, {"label": "No, just a warning chirp", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fascb_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Smoke alarm", "score": 6}, {"label": "Low battery", "score": 2}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    fafp_questions = [
        {"variable": "fafp_led", "question": "Which FP1820W2 light fits?", "options": [{"label": "Red flash / 5 sec", "score": 12}, {"label": "Green flash / min", "score": 1}, {"label": "Amber flash / min", "score": 2}, {"label": "Double amber flash", "score": 4}, {"label": "Not sure", "score": 6}]},
        {"variable": "fafp_sound", "question": "What is the W2-CO-10X doing?", "options": [{"label": "4 audible chirps", "score": 25}, {"label": "1 chirp / min", "score": 2}, {"label": "Chirp off-sync to amber", "score": 4}, {"label": "No sound", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fafp_sync", "question": "Does the chirp happen with the amber light?", "options": [{"label": "Yes, same time", "score": 2}, {"label": "No, different time", "score": 4}, {"label": "Red alarm is sounding", "score": 16}, {"label": "Not sure", "score": 6}]},
        {"variable": "fafp_now", "question": "What best describes it right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Replace-soon warning", "score": 2}, {"label": "Replace-now warning", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fafp_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery / sensor life", "score": 2}, {"label": "Sensor fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    fageneric_questions = [
        {"variable": "fageneric_sound", "question": "What is the FireAngel alarm doing?", "options": [{"label": "4 loud chirps", "score": 25}, {"label": "1 warning chirp", "score": 2}, {"label": "2-3 warning chirps", "score": 4}, {"label": "3 long smoke beeps", "score": 6}, {"label": "Not sure", "score": 6}]},
        {"variable": "fageneric_led", "question": "Which FireAngel light fits?", "options": [{"label": "Red with sound", "score": 12}, {"label": "Amber warning flash", "score": 4}, {"label": "Green power flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fageneric_timing", "question": "Which repeat time fits?", "options": [{"label": "Continuous alarm", "score": 15}, {"label": "Every 25 sec", "score": 10}, {"label": "Every 40 sec", "score": 4}, {"label": "Every 60 sec", "score": 4}, {"label": "Not sure", "score": 6}]},
        {"variable": "fageneric_feature", "question": "What best describes it?", "options": [{"label": "Early warning / memory", "score": 10}, {"label": "Battery warning", "score": 2}, {"label": "Fault / end of life", "score": 4}, {"label": "Smoke alarm", "score": 6}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fageneric_action", "question": "What is happening right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Quiet, but warning shown", "score": 10}, {"label": "Battery or replace warning showing", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]

    nodes = [
        WorkflowNode(
            id="fa_model",
            type=WorkflowNodeType.QUESTION,
            data={
                "group": "FireAngel",
                "question": "Which FireAngel model is shown?",
                "variable": "fa_model",
                "options": [
                    {"label": "FA6813", "score": 1},
                    {"label": "FA6829S", "score": 1},
                    {"label": "FA3313", "score": 1},
                    {"label": "FA3322", "score": 1},
                    {"label": "FA3328", "score": 1},
                    {"label": "FA3820", "score": 1},
                    {"label": "FA6812", "score": 1},
                    {"label": "SCB10-R", "score": 1},
                    {"label": "FP1820W2", "score": 1},
                    {"label": "Not sure / another FireAngel model", "score": 1},
                ],
            },
        ),
        WorkflowNode(
            id="fa_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "FireAngel",
                "variable": "fa_model",
                "label": "FireAngel model routing",
                "cases": ["FA6813", "FA6829S", "FA3313", "FA3322", "FA3328", "FA3820", "FA6812", "SCB10-R", "FP1820W2", "Not sure / another FireAngel model"],
                "default": "Not sure / another FireAngel model",
            },
        ),
    ]
    edges = [
        WorkflowEdge(source="fa_model", target="fa_model_switch"),
        WorkflowEdge(source="fa_model_switch", target="fa6813_q1", condition="fa_model == 'FA6813'"),
        WorkflowEdge(source="fa_model_switch", target="fa6829s_q1", condition="fa_model == 'FA6829S'"),
        WorkflowEdge(source="fa_model_switch", target="fa33xx_q1", condition="fa_model == 'FA3313'"),
        WorkflowEdge(source="fa_model_switch", target="fa33xx_q1", condition="fa_model == 'FA3322'"),
        WorkflowEdge(source="fa_model_switch", target="fa33xx_q1", condition="fa_model == 'FA3328'"),
        WorkflowEdge(source="fa_model_switch", target="fa33xx_q1", condition="fa_model == 'FA3820'"),
        WorkflowEdge(source="fa_model_switch", target="fa6812_q1", condition="fa_model == 'FA6812'"),
        WorkflowEdge(source="fa_model_switch", target="fascb_q1", condition="fa_model == 'SCB10-R'"),
        WorkflowEdge(source="fa_model_switch", target="fafp_q1", condition="fa_model == 'FP1820W2'"),
        WorkflowEdge(source="fa_model_switch", target="fageneric_q1", condition="fa_model == 'Not sure / another FireAngel model'"),
    ]

    branch_specs = [
        ("fa6813", fa6813_questions, {
            "emergency": "FireAngel FA6813 score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "FireAngel FA6813 score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens.",
            "guidance": "FireAngel FA6813 score fits a maintenance or non-emergency pattern.\n\nFollow the FA6813 guidance for battery, fault, end-of-life, or test status.",
        }),
        ("fa6829s", fa6829s_questions, {
            "emergency": "FireAngel FA6829S score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "FireAngel FA6829S score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens.",
            "guidance": "FireAngel FA6829S score fits a maintenance or non-emergency pattern.\n\nFollow the FA6829S guidance for battery, fault, end-of-life, or test status.",
        }),
        ("fa33xx", fa33xx_questions, {
            "emergency": "FireAngel FA3313 / FA3322 / FA3328 / FA3820 score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "FireAngel FA3313 / FA3322 / FA3328 / FA3820 score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens.",
            "guidance": "FireAngel FA3313 / FA3322 / FA3328 / FA3820 score fits a maintenance or non-emergency pattern.\n\nFollow the manual guidance for battery, fault, end-of-life, or test status.",
        }),
        ("fa6812", fa6812_questions, {
            "emergency": "FireAngel FA6812 score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "FireAngel FA6812 score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens.",
            "guidance": "FireAngel FA6812 score fits a maintenance or non-emergency pattern.\n\nFollow the FA6812 guidance for battery, fault, end-of-life, or test status.",
        }),
        ("fascb", fascb_questions, {
            "emergency": "FireAngel SCB10-R score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "FireAngel SCB10-R score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens.",
            "guidance": "FireAngel SCB10-R score fits a maintenance or non-emergency pattern.\n\nFollow the SCB10-R guidance for battery, fault, end-of-life, or test status.",
        }),
        ("fafp", fafp_questions, {
            "emergency": "FireAngel FP1820W2 score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "FireAngel FP1820W2 score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens.",
            "guidance": "FireAngel FP1820W2 score fits a maintenance or non-emergency pattern.\n\nFollow the FP1820W2 guidance for battery, fault, end-of-life, or test status.",
        }),
        ("fageneric", fageneric_questions, {
            "emergency": "Generic FireAngel score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Generic FireAngel score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens.",
            "guidance": "Generic FireAngel score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, fault, end-of-life, or test status.",
        }),
    ]

    for prefix, questions, messages in branch_specs:
        branch_nodes, branch_edges = _build_branch(prefix, questions, messages)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_FIREANGEL, "fa_model", nodes, edges)


def _create_co_alarm_firehawk_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "Firehawk", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(prefix: str, questions: list[dict], messages: dict, label: str | None = None) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        score_variable = f"{prefix}_score"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(
            f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
            for question in questions
        )

        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "Firehawk",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "Firehawk",
                    "variable": normalized_variable,
                    "label": f"{label or prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        nodes.extend(
            [
                WorkflowNode(id=f"{prefix}_emergency_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "emergency_dispatch", "message": messages["emergency"]}),
                WorkflowNode(id=f"{prefix}_monitor_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "monitor", "message": messages["monitor"]}),
                WorkflowNode(id=f"{prefix}_guidance_out", type=WorkflowNodeType.DECISION, data={"group": "Firehawk", "outcome": "close_with_guidance", "message": messages["guidance"]}),
            ]
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )
        return nodes, edges

    fh57_questions = [
        {"variable": "fh57_sound", "question": "What is the alarm doing?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "1 beep / min", "score": 2}, {"label": "2 beeps / min", "score": 4}, {"label": "3 beeps / min", "score": 5}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh57_led", "question": "Which light do you see?", "options": [{"label": "Red with sound", "score": 12}, {"label": "Red + yellow", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "No light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh57_now", "question": "What best describes it right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Just warning chirps", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Quiet now", "score": 4}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh57_pattern", "question": "How often does it repeat?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh57_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "Fault", "score": 4}, {"label": "End of life", "score": 5}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    fh10rf_questions = [
        {"variable": "fh10rf_sound", "question": "What is the CO10-RF doing?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "1 beep / min", "score": 2}, {"label": "2 beeps / min", "score": 4}, {"label": "3 beeps / min", "score": 5}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh10rf_led", "question": "Which CO10-RF light fits?", "options": [{"label": "Red with sound", "score": 12}, {"label": "Yellow warning light", "score": 4}, {"label": "Green power flash", "score": 1}, {"label": "No light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh10rf_hush", "question": "Did it stop after hush / test?", "options": [{"label": "No, it keeps alarming", "score": 16}, {"label": "Yes, only after pressing test", "score": 2}, {"label": "Yes, warning only", "score": 3}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh10rf_pattern", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh10rf_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "Fault", "score": 4}, {"label": "End of life", "score": 5}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    fh10y_questions = [
        {"variable": "fh10y_sound", "question": "What is the CO7B-10Y doing?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "1 beep / min", "score": 2}, {"label": "2 beeps / min", "score": 4}, {"label": "3 beeps / min", "score": 5}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh10y_led", "question": "Which light do you see?", "options": [{"label": "Red with sound", "score": 12}, {"label": "Yellow warning light", "score": 4}, {"label": "Green power flash", "score": 1}, {"label": "No light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh10y_now", "question": "What best describes it right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Just warning chirps", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Quiet now", "score": 4}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh10y_replace", "question": "Does it sound like a replace warning?", "options": [{"label": "Yes, needs replacing", "score": 5}, {"label": "No, active alarm", "score": 16}, {"label": "No, battery / fault only", "score": 3}, {"label": "Not sure", "score": 6}]},
        {"variable": "fh10y_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "Fault", "score": 4}, {"label": "End of life", "score": 5}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    fhgeneric_questions = [
        {"variable": "fhgeneric_sound", "question": "What is the Firehawk alarm doing?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "1 warning beep", "score": 2}, {"label": "2 warning beeps", "score": 4}, {"label": "3 warning beeps", "score": 5}, {"label": "Not sure", "score": 6}]},
        {"variable": "fhgeneric_led", "question": "Which light do you see?", "options": [{"label": "Red with sound", "score": 12}, {"label": "Yellow warning light", "score": 4}, {"label": "Green power flash", "score": 1}, {"label": "No light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "fhgeneric_now", "question": "What best describes it right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Just warning chirps", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Quiet now", "score": 4}, {"label": "Not sure", "score": 6}]},
        {"variable": "fhgeneric_pattern", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "fhgeneric_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "Fault", "score": 4}, {"label": "End of life", "score": 5}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]

    nodes = [
        WorkflowNode(
            id="fh_model",
            type=WorkflowNodeType.QUESTION,
            data={
                "group": "Firehawk",
                "question": "Which Firehawk model is shown?",
                "variable": "fh_model",
                "options": [
                    {"label": "CO5B", "score": 1},
                    {"label": "CO7B", "score": 1},
                    {"label": "CO7BD", "score": 1},
                    {"label": "CO10-RF", "score": 1},
                    {"label": "CO7B-10Y", "score": 1},
                    {"label": "Not sure / another Firehawk model", "score": 1},
                ],
            },
        ),
        WorkflowNode(
            id="fh_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "Firehawk",
                "variable": "fh_model",
                "label": "Firehawk model routing",
                "cases": ["CO5B", "CO7B", "CO7BD", "CO10-RF", "CO7B-10Y", "Not sure / another Firehawk model"],
                "default": "Not sure / another Firehawk model",
            },
        ),
    ]
    edges = [
        WorkflowEdge(source="fh_model", target="fh_model_switch"),
        WorkflowEdge(source="fh_model_switch", target="fh57_q1", condition="fh_model == 'CO5B'"),
        WorkflowEdge(source="fh_model_switch", target="fh57_q1", condition="fh_model == 'CO7B'"),
        WorkflowEdge(source="fh_model_switch", target="fh57_q1", condition="fh_model == 'CO7BD'"),
        WorkflowEdge(source="fh_model_switch", target="fh10rf_q1", condition="fh_model == 'CO10-RF'"),
        WorkflowEdge(source="fh_model_switch", target="fh10y_q1", condition="fh_model == 'CO7B-10Y'"),
        WorkflowEdge(source="fh_model_switch", target="fhgeneric_q1", condition="fh_model == 'Not sure / another Firehawk model'"),
    ]

    branch_specs = [
        ("fh57", fh57_questions, {
            "emergency": "Firehawk CO5B / CO7B / CO7BD score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Firehawk CO5B / CO7B / CO7BD score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "Firehawk CO5B / CO7B / CO7BD score fits a maintenance or non-emergency pattern.\n\nFollow the manual guidance for battery, fault, end-of-life, or test status.",
        }, "CO5B / CO7B / CO7BD"),
        ("fh10rf", fh10rf_questions, {
            "emergency": "Firehawk CO10-RF score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Firehawk CO10-RF score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "Firehawk CO10-RF score fits a maintenance or non-emergency pattern.\n\nFollow the CO10-RF guidance for battery, fault, end-of-life, or test status.",
        }, "CO10-RF"),
        ("fh10y", fh10y_questions, {
            "emergency": "Firehawk CO7B-10Y score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Firehawk CO7B-10Y score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "Firehawk CO7B-10Y score fits a maintenance or non-emergency pattern.\n\nFollow the CO7B-10Y guidance for battery, fault, end-of-life, or test status.",
        }, "CO7B-10Y"),
        ("fhgeneric", fhgeneric_questions, {
            "emergency": "Generic Firehawk score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Generic Firehawk score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "Generic Firehawk score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, fault, end-of-life, or test status.",
        }, "Unknown Firehawk"),
    ]

    for prefix, questions, messages, label in branch_specs:
        branch_nodes, branch_edges = _build_branch(prefix, questions, messages, label)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_FIREHAWK, "fh_model", nodes, edges)


def _create_co_alarm_aico_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "Aico", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(prefix: str, questions: list[dict], summary: dict) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        score_variable = f"{prefix}_score"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(
            f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
            for question in questions
        )
        emergency_message = next(
            (route["message"] for route in summary["routes"] if route["outcome"] == "emergency_dispatch"),
            "Aico score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
        )
        monitor_message = next(
            (route["message"] for route in summary["routes"] if route["outcome"] in {"schedule_engineer", "monitor"}),
            "Aico score is inconclusive.\n\nThis may be a false case or a true CO event. Ventilate the property, avoid fuel-burning appliances, and monitor the situation closely.",
        )
        guidance_message = next(
            (route["message"] for route in summary["routes"] if route["outcome"] == "close_with_guidance"),
            "Aico score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, fault, end-of-life, or test status.",
        )
        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "Aico",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "Aico",
                    "variable": normalized_variable,
                    "label": f"{prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        nodes.extend(
            [
                WorkflowNode(id=f"{prefix}_emergency_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "emergency_dispatch", "message": emergency_message}),
                WorkflowNode(id=f"{prefix}_monitor_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "monitor", "message": monitor_message}),
                WorkflowNode(id=f"{prefix}_guidance_out", type=WorkflowNodeType.DECISION, data={"group": "Aico", "outcome": "close_with_guidance", "message": guidance_message}),
            ]
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )

        return nodes, edges

    model_options = [
        {"label": "Ei3030", "score": 1},
        {"label": "Ei3018", "score": 1},
        {"label": "Ei3028", "score": 1},
        {"label": "Ei207 / Ei208 Series", "score": 1},
        {"label": "Not sure / another Aico model", "score": 1},
    ]
    nodes = [
        WorkflowNode(
            id="aico_model",
            type=WorkflowNodeType.QUESTION,
            data={"group": "Aico", "question": "Which Aico model is shown on the alarm?", "variable": "aico_model", "options": model_options},
        ),
        WorkflowNode(
            id="aico_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "Aico",
                "variable": "aico_model",
                "label": "Aico model routing",
                "cases": ["Ei3030", "Ei3018", "Ei3028", "Ei207 / Ei208 Series", "Not sure / another Aico model"],
                "default": "Not sure / another Aico model",
            },
        ),
    ]
    edges = [
        WorkflowEdge(source="aico_model", target="aico_model_switch"),
        WorkflowEdge(source="aico_model_switch", target="aico3030_q1", condition="aico_model == 'Ei3030'"),
        WorkflowEdge(source="aico_model_switch", target="aico3018_q1", condition="aico_model == 'Ei3018'"),
        WorkflowEdge(source="aico_model_switch", target="aico3028_q1", condition="aico_model == 'Ei3028'"),
        WorkflowEdge(source="aico_model_switch", target="aico208_q1", condition="aico_model == 'Ei207 / Ei208 Series'"),
        WorkflowEdge(source="aico_model_switch", target="aicogeneric_q1", condition="aico_model == 'Not sure / another Aico model'"),
    ]
    aico3030_nodes, aico3030_edges = _build_branch(
        "aico3030",
        [
            {"variable": "aico3030_light", "question": "What light do you see?", "options": [{"label": "Red", "score": 10}, {"label": "Yellow", "score": 2}, {"label": "Green", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3030_sound", "question": "What sound do you hear?", "options": [{"label": "3 slow pulses", "score": 20}, {"label": "Rapid fire", "score": 5}, {"label": "Single chirp", "score": 2}, {"label": "Silent", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3030_count", "question": "How many beeps or flashes?", "options": [{"label": "1", "score": 1}, {"label": "2", "score": 2}, {"label": "3", "score": 4}, {"label": "4+", "score": 3}, {"label": "Unknown", "score": 2}]},
            {"variable": "aico3030_timing", "question": "When does it repeat?", "options": [{"label": "Continuous", "score": 10}, {"label": "Every 48 sec", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3030_summary", "question": "Which matches best?", "options": [{"label": "CO alarm", "score": 25}, {"label": "Fire alarm", "score": 5}, {"label": "Low battery", "score": 2}, {"label": "Sensor fault", "score": 2}, {"label": "End of life", "score": 2}, {"label": "Dust / maintenance", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 8}]},
        ],
        {"variable": "aico3030_summary", "routes": [
            {"label": "CO alarm", "outcome": "emergency_dispatch", "message": "Aico Ei3030 CO alarm reported.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched."},
            {"label": "Fire alarm", "outcome": "close_with_guidance", "message": "This sounds like the Ei3030 fire alarm rather than CO.\n\nCheck for smoke or fire and call 999 if there is any fire risk."},
            {"label": "Low battery", "outcome": "close_with_guidance", "message": "Aico Ei3030 low battery warning reported.\n\nCheck mains power first. If mains is present, the backup battery is depleted and the alarm needs service or replacement."},
            {"label": "Sensor fault", "outcome": "close_with_guidance", "message": "Aico Ei3030 sensor fault reported.\n\nReplace or service the unit because it may no longer detect correctly."},
            {"label": "End of life", "outcome": "close_with_guidance", "message": "Aico Ei3030 end-of-life warning reported.\n\nReplace the alarm unit."},
            {"label": "Dust / maintenance", "outcome": "close_with_guidance", "message": "Aico Ei3030 maintenance warning reported.\n\nClean the unit and replace it if the warning persists."},
            {"label": "Normal", "outcome": "close_with_guidance", "message": "The Aico Ei3030 appears normal or in test mode. Press the test button to confirm operation."},
            {"label": "Not sure", "outcome": "monitor", "message": "Because the Ei3030 pattern is unclear, ventilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens."},
        ]},
    )
    aico3018_nodes, aico3018_edges = _build_branch(
        "aico3018",
        [
            {"variable": "aico3018_light", "question": "What light do you see?", "options": [{"label": "Red", "score": 5}, {"label": "Yellow", "score": 2}, {"label": "Green", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3018_sound", "question": "What sound do you hear?", "options": [{"label": "Rapid fire", "score": 10}, {"label": "Single chirp", "score": 2}, {"label": "No sound", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3018_count", "question": "How many beeps or flashes?", "options": [{"label": "1", "score": 1}, {"label": "2", "score": 2}, {"label": "3", "score": 3}, {"label": "4+", "score": 2}, {"label": "Unknown", "score": 2}]},
            {"variable": "aico3018_timing", "question": "When does it repeat?", "options": [{"label": "Continuous", "score": 5}, {"label": "Every 48 sec", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3018_summary", "question": "Which matches best?", "options": [{"label": "Fire alarm", "score": 10}, {"label": "Low battery", "score": 2}, {"label": "Sensor fault", "score": 2}, {"label": "End of life", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 8}]},
        ],
        {"variable": "aico3018_summary", "routes": [
            {"label": "Fire alarm", "outcome": "close_with_guidance", "message": "This sounds like the Aico Ei3018 fire or heat alarm.\n\nCheck for fire, smoke, or overheating appliances and call 999 if needed."},
            {"label": "Low battery", "outcome": "close_with_guidance", "message": "Aico Ei3018 low battery warning reported.\n\nCheck mains power and replace or service the alarm if the warning continues."},
            {"label": "Sensor fault", "outcome": "close_with_guidance", "message": "Aico Ei3018 sensor fault reported.\n\nThe unit should be serviced or replaced."},
            {"label": "End of life", "outcome": "close_with_guidance", "message": "Aico Ei3018 end-of-life warning reported.\n\nReplace the alarm unit."},
            {"label": "Normal", "outcome": "close_with_guidance", "message": "The Aico Ei3018 appears normal or in test mode. Press the test button to confirm operation."},
            {"label": "Not sure", "outcome": "monitor", "message": "Because the Ei3018 pattern is unclear, keep the area ventilated and monitor the alarm closely. Escalate if it repeats."},
        ]},
    )
    aico3028_nodes, aico3028_edges = _build_branch(
        "aico3028",
        [
            {"variable": "aico3028_light", "question": "What light do you see?", "options": [{"label": "Red", "score": 10}, {"label": "Yellow", "score": 2}, {"label": "Green", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3028_sound", "question": "What sound do you hear?", "options": [{"label": "3 slow pulses", "score": 20}, {"label": "Rapid fire", "score": 5}, {"label": "Single chirp", "score": 2}, {"label": "Silent", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3028_count", "question": "How many beeps or flashes?", "options": [{"label": "1", "score": 1}, {"label": "2", "score": 2}, {"label": "3", "score": 4}, {"label": "4+", "score": 3}, {"label": "Unknown", "score": 2}]},
            {"variable": "aico3028_timing", "question": "When does it repeat?", "options": [{"label": "Continuous", "score": 10}, {"label": "Every 48 sec", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico3028_summary", "question": "Which matches best?", "options": [{"label": "CO alarm", "score": 25}, {"label": "Fire alarm", "score": 5}, {"label": "Low battery", "score": 2}, {"label": "Sensor fault", "score": 2}, {"label": "End of life", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 8}]},
        ],
        {"variable": "aico3028_summary", "routes": [
            {"label": "CO alarm", "outcome": "emergency_dispatch", "message": "Aico Ei3028 CO alarm reported.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched."},
            {"label": "Fire alarm", "outcome": "close_with_guidance", "message": "This sounds like the Ei3028 fire alarm rather than CO.\n\nCheck for smoke or fire and call 999 if there is any fire risk."},
            {"label": "Low battery", "outcome": "close_with_guidance", "message": "Aico Ei3028 low battery warning reported.\n\nCheck mains power and replace or service the alarm if the warning continues."},
            {"label": "Sensor fault", "outcome": "close_with_guidance", "message": "Aico Ei3028 sensor fault reported.\n\nThe unit should be serviced or replaced."},
            {"label": "End of life", "outcome": "close_with_guidance", "message": "Aico Ei3028 end-of-life warning reported.\n\nReplace the alarm unit."},
            {"label": "Normal", "outcome": "close_with_guidance", "message": "The Aico Ei3028 appears normal or in test mode. Press the test button to confirm operation."},
            {"label": "Not sure", "outcome": "monitor", "message": "Because the Ei3028 pattern is unclear, ventilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens."},
        ]},
    )
    aico208_nodes, aico208_edges = _build_branch(
        "aico208",
        [
            {"variable": "aico208_light", "question": "What light do you see?", "options": [{"label": "Red", "score": 10}, {"label": "Yellow", "score": 2}, {"label": "Green", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico208_sound", "question": "What sound do you hear?", "options": [{"label": "Full CO alarm", "score": 20}, {"label": "Single chirp", "score": 2}, {"label": "No sound", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico208_count", "question": "How many beeps or flashes?", "options": [{"label": "1", "score": 1}, {"label": "2", "score": 2}, {"label": "3", "score": 4}, {"label": "4+", "score": 3}, {"label": "Unknown", "score": 2}]},
            {"variable": "aico208_timing", "question": "When does it repeat?", "options": [{"label": "Continuous", "score": 10}, {"label": "Every 48 sec", "score": 2}, {"label": "Once a minute", "score": 5}, {"label": "Unknown", "score": 3}]},
            {"variable": "aico208_summary", "question": "Which matches best?", "options": [{"label": "CO alarm", "score": 25}, {"label": "Alarm memory", "score": 12}, {"label": "Low battery", "score": 2}, {"label": "Sensor fault", "score": 2}, {"label": "End of life", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 8}]},
        ],
        {"variable": "aico208_summary", "routes": [
            {"label": "CO alarm", "outcome": "emergency_dispatch", "message": "Aico Ei207 / Ei208 CO alarm reported.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched."},
            {"label": "Alarm memory", "outcome": "monitor", "message": "Aico Ei207 / Ei208 alarm memory reported.\n\nCO may have been detected earlier. Ventilate the property, avoid fuel-burning appliances, and monitor conditions closely."},
            {"label": "Low battery", "outcome": "close_with_guidance", "message": "Aico Ei207 / Ei208 low battery warning reported.\n\nEi207 models use AAA batteries. Ei208 sealed-life models should be replaced rather than re-batteried."},
            {"label": "Sensor fault", "outcome": "close_with_guidance", "message": "Aico Ei207 / Ei208 sensor fault reported.\n\nReplace the alarm because it may no longer detect CO reliably."},
            {"label": "End of life", "outcome": "close_with_guidance", "message": "Aico Ei207 / Ei208 end-of-life warning reported.\n\nReplace the alarm unit."},
            {"label": "Normal", "outcome": "close_with_guidance", "message": "The Aico Ei207 / Ei208 alarm appears normal or in test mode. Press the test button to confirm operation."},
            {"label": "Not sure", "outcome": "monitor", "message": "Because the Ei207 / Ei208 pattern is unclear, ventilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens."},
        ]},
    )
    aicogeneric_nodes, aicogeneric_edges = _build_branch(
        "aicogeneric",
        [
            {"variable": "aicogeneric_light", "question": "What light do you see?", "options": [{"label": "Red", "score": 10}, {"label": "Yellow", "score": 2}, {"label": "Green", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aicogeneric_sound", "question": "What sound do you hear?", "options": [{"label": "3 slow pulses", "score": 20}, {"label": "Rapid fire", "score": 8}, {"label": "Single chirp", "score": 2}, {"label": "Silent", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aicogeneric_count", "question": "How many beeps or flashes?", "options": [{"label": "1", "score": 1}, {"label": "2", "score": 2}, {"label": "3", "score": 4}, {"label": "4+", "score": 3}, {"label": "Unknown", "score": 2}]},
            {"variable": "aicogeneric_timing", "question": "When does it repeat?", "options": [{"label": "Continuous", "score": 10}, {"label": "Every 48 sec", "score": 2}, {"label": "Once a minute", "score": 5}, {"label": "Normal", "score": 1}, {"label": "Unknown", "score": 3}]},
            {"variable": "aicogeneric_summary", "question": "Which matches best?", "options": [{"label": "CO alarm", "score": 25}, {"label": "Fire alarm", "score": 8}, {"label": "Alarm memory", "score": 12}, {"label": "Low battery", "score": 2}, {"label": "Sensor fault", "score": 2}, {"label": "End of life", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 8}]},
        ],
        {"variable": "aicogeneric_summary", "routes": [
            {"label": "CO alarm", "outcome": "emergency_dispatch", "message": "Generic Aico CO alarm pattern reported.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched."},
            {"label": "Fire alarm", "outcome": "close_with_guidance", "message": "This sounds more like an Aico fire alarm than a CO-only alarm.\n\nCheck for smoke or fire and call 999 if there is any fire risk."},
            {"label": "Alarm memory", "outcome": "monitor", "message": "The Aico alarm may be showing alarm memory from an earlier event.\n\nVentilate the property, avoid fuel-burning appliances, and monitor conditions closely."},
            {"label": "Low battery", "outcome": "close_with_guidance", "message": "This Aico pattern sounds like a low battery warning rather than a live CO alarm.\n\nReplace the battery if the model uses replaceable cells, or replace the alarm if it is sealed-life."},
            {"label": "Sensor fault", "outcome": "close_with_guidance", "message": "This Aico pattern sounds like a sensor fault.\n\nReplace or service the alarm because it may no longer detect correctly."},
            {"label": "End of life", "outcome": "close_with_guidance", "message": "This Aico pattern sounds like end-of-life.\n\nReplace the alarm unit."},
            {"label": "Normal", "outcome": "close_with_guidance", "message": "The Aico alarm sounds normal or in test mode. Press the test button to confirm operation."},
            {"label": "Not sure", "outcome": "monitor", "message": "Because the Aico model and pattern are unclear, ventilate the property, avoid fuel-burning appliances, and monitor the alarm closely. Escalate if it repeats or worsens."},
        ]},
    )
    nodes.extend(aico3030_nodes + aico3018_nodes + aico3028_nodes + aico208_nodes + aicogeneric_nodes)
    edges.extend(aico3030_edges + aico3018_edges + aico3028_edges + aico208_edges + aicogeneric_edges)
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_AICO, "aico_model", nodes, edges)


def _create_co_alarm_kidde_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "Kidde", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(prefix: str, questions: list[dict], messages: dict, label: str | None = None) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        score_variable = f"{prefix}_score"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(
            f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
            for question in questions
        )

        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "Kidde",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "Kidde",
                    "variable": normalized_variable,
                    "label": f"{label or prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        nodes.extend(
            [
                WorkflowNode(id=f"{prefix}_emergency_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "emergency_dispatch", "message": messages["emergency"]}),
                WorkflowNode(id=f"{prefix}_monitor_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "monitor", "message": messages["monitor"]}),
                WorkflowNode(id=f"{prefix}_guidance_out", type=WorkflowNodeType.DECISION, data={"group": "Kidde", "outcome": "close_with_guidance", "message": messages["guidance"]}),
            ]
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )
        return nodes, edges

    def _base_questions(prefix: str, model_label: str) -> list[dict]:
        return [
            {"variable": f"{prefix}_light", "question": f"What light do you see on {model_label}?", "options": [{"label": "Red", "score": 12}, {"label": "Amber / yellow", "score": 4}, {"label": "Green", "score": 1}, {"label": "No light", "score": 2}, {"label": "Not sure", "score": 6}]},
            {"variable": f"{prefix}_sound", "question": f"What sound do you hear from {model_label}?", "options": [{"label": "4 quick beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "2 warning chirps", "score": 4}, {"label": "5 fast chirps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
            {"variable": f"{prefix}_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Warning only", "score": 10}, {"label": "Just chirping", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
            {"variable": f"{prefix}_pattern", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
            {"variable": f"{prefix}_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        ]

    def _kidde_2030_dcr_questions(prefix: str) -> list[dict]:
        return [
            {
                "variable": f"{prefix}_visual_colour",
                "question": "What colour light do you see?",
                "options": [
                    {"label": "Red", "score": 25},
                    {"label": "Amber", "score": 5},
                    {"label": "Green", "score": 0},
                    {"label": "No light", "score": 8},
                    {"label": "Multiple test lights", "score": 0},
                    {"label": "Not sure", "score": 10},
                ],
            },
            {
                "variable": f"{prefix}_visual_cadence",
                "question": "How is the light blinking?",
                "options": [
                    {"label": "Alarm pattern", "score": 30},
                    {"label": "1 blink every 60 sec", "score": 12},
                    {"label": "1 blink every 5 sec", "score": 4},
                    {"label": "2 blinks every 60 sec", "score": 4},
                    {"label": "3 blinks every 30 sec", "score": 6},
                    {"label": "5 blinks every 30 sec", "score": 10},
                    {"label": "Steady / not blinking", "score": 2},
                    {"label": "No visible blinking", "score": 0},
                    {"label": "Not sure", "score": 10},
                ],
            },
            {
                "variable": f"{prefix}_sound_pattern",
                "question": "What sound do you hear?",
                "options": [
                    {"label": "Loud alarm pulses", "score": 35},
                    {"label": "No sound", "score": 8},
                    {"label": "Chirp every 60 sec", "score": 2},
                    {"label": "Chirp every 30 sec", "score": 5},
                    {"label": "2 chirps every 60 sec", "score": 4},
                    {"label": "Constant tone", "score": 8},
                    {"label": "Chirp every 5 sec", "score": 4},
                    {"label": "Test beep pattern", "score": 0},
                    {"label": "Not sure", "score": 12},
                ],
            },
            {
                "variable": f"{prefix}_reset_result",
                "question": "If the test/reset button was pressed, what happened?",
                "options": [
                    {"label": "It started again after reset", "score": 25},
                    {"label": "It stopped and stayed stopped", "score": 8},
                    {"label": "Only warning chirps remain", "score": 2},
                    {"label": "Button still feels stuck", "score": 3},
                    {"label": "Not pressed / not sure", "score": 8},
                ],
            },
            {
                "variable": f"{prefix}_state",
                "question": "What best describes the alarm right now?",
                "options": [
                    {"label": "Alarm is sounding now", "score": 20},
                    {"label": "Light only, no alarm sound", "score": 12},
                    {"label": "Chirping only", "score": 3},
                    {"label": "Normal or test only", "score": 0},
                    {"label": "Not sure", "score": 12},
                ],
            },
        ]

    model_specs = [
        ("kidde1", "2030-DCR"),
        ("kidde2", "K5CO"),
        ("kidde3", "K5DCO"),
        ("kidde4", "K7CO"),
        ("kidde5", "K7DCO"),
        ("kidde6", "K10LLCO"),
        ("kidde7", "K10LLDCO"),
        ("kidde8", "KCOSAC2"),
        ("kidde9", "K4MCO"),
        ("kidde10", "K10SCO"),
    ]

    nodes = [
        WorkflowNode(
            id="kidde_model",
            type=WorkflowNodeType.QUESTION,
            data={
                "group": "Kidde",
                "question": "Which Kidde model is shown?",
                "variable": "kidde_model",
                "options": [
                    {"label": "2030-DCR", "score": 1},
                    {"label": "K5CO", "score": 1},
                    {"label": "K5DCO", "score": 1},
                    {"label": "K7CO", "score": 1},
                    {"label": "K7DCO", "score": 1},
                    {"label": "K10LLCO", "score": 1},
                    {"label": "K10LLDCO", "score": 1},
                    {"label": "KCOSAC2", "score": 1},
                    {"label": "K4MCO", "score": 1},
                    {"label": "K10SCO", "score": 1},
                    {"label": "Not sure / another Kidde model", "score": 1},
                ],
            },
        ),
        WorkflowNode(
            id="kidde_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "Kidde",
                "variable": "kidde_model",
                "label": "Kidde model routing",
                "cases": ["2030-DCR", "K5CO", "K5DCO", "K7CO", "K7DCO", "K10LLCO", "K10LLDCO", "KCOSAC2", "K4MCO", "K10SCO", "Not sure / another Kidde model"],
                "default": "Not sure / another Kidde model",
            },
        ),
    ]
    edges = [WorkflowEdge(source="kidde_model", target="kidde_model_switch")]

    branch_specs: list[tuple[str, list[dict], dict, str, str]] = []
    for idx, (prefix, label) in enumerate(model_specs, start=1):
        questions = _kidde_2030_dcr_questions(prefix) if label == "2030-DCR" else _base_questions(prefix, label)
        messages = (
            {
                "emergency": (
                    "Kidde 2030-DCR pattern indicates a likely live CO alarm or a re-alarm after reset.\n\n"
                    "1. Move everyone to fresh air immediately\n"
                    "2. Open doors and windows if safe to do so\n"
                    "3. Do not re-enter until the property is confirmed safe\n"
                    "4. Call 999 if anyone feels unwell\n\n"
                    "Emergency engineer dispatched."
                ),
                "monitor": (
                    "Kidde 2030-DCR pattern needs caution.\n\n"
                    "It may be alarm memory from a CO event in the last 14 days, an unresolved fault, or an unclear alarm state. "
                    "Ventilate the property, avoid fuel-burning appliances, and escalate immediately if the alarm pattern repeats."
                ),
                "guidance": (
                    "Kidde 2030-DCR pattern fits maintenance, fault, test, or normal standby guidance.\n\n"
                    "Follow the matched action for low battery, memory fault, CO fault, end of unit life, stuck button, or weekly test status."
                ),
            }
            if label == "2030-DCR"
            else {
                "emergency": f"Kidde {label} score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
                "monitor": f"Kidde {label} score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
                "guidance": f"Kidde {label} score fits a maintenance or non-emergency pattern.\n\nFollow the model guidance for battery, fault, end-of-life, or test status.",
            }
        )
        branch_specs.append(
            (
                prefix,
                questions,
                messages,
                label,
                label,
            )
        )
        edges.append(WorkflowEdge(source="kidde_model_switch", target=f"{prefix}_q1", condition=f"kidde_model == '{label}'"))

    kiddegeneric_questions = _base_questions("kiddegeneric", "this Kidde alarm")
    branch_specs.append(
        (
            "kiddegeneric",
            kiddegeneric_questions,
            {
                "emergency": "Generic Kidde score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
                "monitor": "Generic Kidde score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
                "guidance": "Generic Kidde score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, fault, end-of-life, or test status.",
            },
            "Unknown Kidde",
            "Not sure / another Kidde model",
        )
    )
    edges.append(WorkflowEdge(source="kidde_model_switch", target="kiddegeneric_q1", condition="kidde_model == 'Not sure / another Kidde model'"))

    for prefix, questions, messages, ui_label, _selection in branch_specs:
        branch_nodes, branch_edges = _build_branch(prefix, questions, messages, ui_label)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_KIDDE, "kidde_model", nodes, edges)


def _create_co_alarm_xsense_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "X-Sense", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(prefix: str, questions: list[dict], messages: dict, label: str | None = None) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        score_variable = f"{prefix}_score"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(
            f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
            for question in questions
        )

        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "X-Sense",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "X-Sense",
                    "variable": normalized_variable,
                    "label": f"{label or prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        nodes.extend(
            [
                WorkflowNode(id=f"{prefix}_emergency_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "emergency_dispatch", "message": messages["emergency"]}),
                WorkflowNode(id=f"{prefix}_monitor_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "monitor", "message": messages["monitor"]}),
                WorkflowNode(id=f"{prefix}_guidance_out", type=WorkflowNodeType.DECISION, data={"group": "X-Sense", "outcome": "close_with_guidance", "message": messages["guidance"]}),
            ]
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )
        return nodes, edges

    xc01m_questions = [
        {"variable": "xc01m_light", "question": "What light do you see?", "options": [{"label": "Red flashing", "score": 12}, {"label": "Red steady", "score": 8}, {"label": "Yellow flashing", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc01m_sound", "question": "What sound do you hear?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "3 warning beeps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc01m_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Silenced but was alarming", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc01m_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc01m_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    xc04wx_questions = [
        {"variable": "xc04wx_light", "question": "What light do you see?", "options": [{"label": "Red flashing", "score": 12}, {"label": "Red steady", "score": 8}, {"label": "Yellow flashing", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc04wx_sound", "question": "What sound do you hear?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "3 warning beeps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc04wx_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Silenced but was alarming", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc04wx_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc04wx_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    xc01r_questions = [
        {"variable": "xc01r_light", "question": "What light do you see?", "options": [{"label": "Red flashing", "score": 12}, {"label": "Red steady", "score": 8}, {"label": "Yellow flashing", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc01r_sound", "question": "What sound do you hear?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "3 warning beeps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc01r_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Silenced but was alarming", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc01r_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc01r_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    xc0c_questions = [
        {"variable": "xc0c_light", "question": "What light do you see?", "options": [{"label": "Red flashing", "score": 12}, {"label": "Red steady", "score": 8}, {"label": "Yellow flashing", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc0c_sound", "question": "What sound do you hear?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "3 warning beeps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc0c_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Silenced but was alarming", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc0c_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xc0c_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    sc07wx_questions = [
        {"variable": "sc07wx_light", "question": "What light do you see?", "options": [{"label": "Red flashing", "score": 12}, {"label": "Red steady", "score": 8}, {"label": "Yellow flashing", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07wx_sound", "question": "What sound do you hear?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "3 warning beeps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07wx_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Silenced but was alarming", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07wx_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07wx_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    sc07_questions = [
        {"variable": "sc07_light", "question": "What light do you see?", "options": [{"label": "Red flashing", "score": 12}, {"label": "Red steady", "score": 8}, {"label": "Yellow flashing", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07_sound", "question": "What sound do you hear?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "3 warning beeps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Silenced but was alarming", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    sc07w_questions = [
        {"variable": "sc07w_light", "question": "What light do you see?", "options": [{"label": "Red flashing", "score": 12}, {"label": "Red steady", "score": 8}, {"label": "Yellow flashing", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07w_sound", "question": "What sound do you hear?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "3 warning beeps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07w_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Silenced but was alarming", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07w_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "sc07w_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    xsgeneric_questions = [
        {"variable": "xsgeneric_light", "question": "What light do you see?", "options": [{"label": "Red flashing", "score": 12}, {"label": "Red steady", "score": 8}, {"label": "Yellow flashing", "score": 4}, {"label": "Green flash", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xsgeneric_sound", "question": "What sound do you hear?", "options": [{"label": "4 loud beeps", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "3 warning beeps", "score": 5}, {"label": "Silent", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xsgeneric_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Silenced but was alarming", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xsgeneric_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "xsgeneric_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "End of life", "score": 5}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]

    nodes = [
        WorkflowNode(
            id="xs_model",
            type=WorkflowNodeType.QUESTION,
            data={
                "group": "X-Sense",
                "question": "Which X-Sense model is shown?",
                "variable": "xs_model",
                "options": [
                    {"label": "XC01-M", "score": 1},
                    {"label": "XC04-WX", "score": 1},
                    {"label": "XC01-R", "score": 1},
                    {"label": "XC0C-SR", "score": 1},
                    {"label": "XC0C-IR", "score": 1},
                    {"label": "SC07-WX", "score": 1},
                    {"label": "SC07", "score": 1},
                    {"label": "SC07-W", "score": 1},
                    {"label": "Not sure / another X-Sense model", "score": 1},
                ],
            },
        ),
        WorkflowNode(
            id="xs_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "X-Sense",
                "variable": "xs_model",
                "label": "X-Sense model routing",
                "cases": ["XC01-M", "XC04-WX", "XC01-R", "XC0C-SR", "XC0C-IR", "SC07-WX", "SC07", "SC07-W", "Not sure / another X-Sense model"],
                "default": "Not sure / another X-Sense model",
            },
        ),
    ]
    edges = [
        WorkflowEdge(source="xs_model", target="xs_model_switch"),
        WorkflowEdge(source="xs_model_switch", target="xc01m_q1", condition="xs_model == 'XC01-M'"),
        WorkflowEdge(source="xs_model_switch", target="xc04wx_q1", condition="xs_model == 'XC04-WX'"),
        WorkflowEdge(source="xs_model_switch", target="xc01r_q1", condition="xs_model == 'XC01-R'"),
        WorkflowEdge(source="xs_model_switch", target="xc0c_q1", condition="xs_model == 'XC0C-SR'"),
        WorkflowEdge(source="xs_model_switch", target="xc0c_q1", condition="xs_model == 'XC0C-IR'"),
        WorkflowEdge(source="xs_model_switch", target="sc07wx_q1", condition="xs_model == 'SC07-WX'"),
        WorkflowEdge(source="xs_model_switch", target="sc07_q1", condition="xs_model == 'SC07'"),
        WorkflowEdge(source="xs_model_switch", target="sc07w_q1", condition="xs_model == 'SC07-W'"),
        WorkflowEdge(source="xs_model_switch", target="xsgeneric_q1", condition="xs_model == 'Not sure / another X-Sense model'"),
    ]

    branch_specs = [
        ("xc01m", xc01m_questions, {
            "emergency": "X-Sense XC01-M score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "X-Sense XC01-M score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "X-Sense XC01-M score fits a maintenance or non-emergency pattern.\n\nFollow the XC01-M guidance for battery, fault, end-of-life, or test status.",
        }, "XC01-M"),
        ("xc04wx", xc04wx_questions, {
            "emergency": "X-Sense XC04-WX score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "X-Sense XC04-WX score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "X-Sense XC04-WX score fits a maintenance or non-emergency pattern.\n\nFollow the XC04-WX guidance for battery, fault, end-of-life, or test status.",
        }, "XC04-WX"),
        ("xc01r", xc01r_questions, {
            "emergency": "X-Sense XC01-R score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "X-Sense XC01-R score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "X-Sense XC01-R score fits a maintenance or non-emergency pattern.\n\nFollow the XC01-R guidance for battery, fault, end-of-life, or test status.",
        }, "XC01-R"),
        ("xc0c", xc0c_questions, {
            "emergency": "X-Sense XC0C-SR / XC0C-IR score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "X-Sense XC0C-SR / XC0C-IR score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "X-Sense XC0C-SR / XC0C-IR score fits a maintenance or non-emergency pattern.\n\nFollow the model guidance for battery, fault, end-of-life, or test status.",
        }, "XC0C-SR / XC0C-IR"),
        ("sc07wx", sc07wx_questions, {
            "emergency": "X-Sense SC07-WX score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "X-Sense SC07-WX score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "X-Sense SC07-WX score fits a maintenance or non-emergency pattern.\n\nFollow the SC07-WX guidance for battery, fault, end-of-life, or test status.",
        }, "SC07-WX"),
        ("sc07", sc07_questions, {
            "emergency": "X-Sense SC07 score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "X-Sense SC07 score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "X-Sense SC07 score fits a maintenance or non-emergency pattern.\n\nFollow the SC07 guidance for battery, fault, end-of-life, or test status.",
        }, "SC07"),
        ("sc07w", sc07w_questions, {
            "emergency": "X-Sense SC07-W score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "X-Sense SC07-W score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "X-Sense SC07-W score fits a maintenance or non-emergency pattern.\n\nFollow the SC07-W guidance for battery, fault, end-of-life, or test status.",
        }, "SC07-W"),
        ("xsgeneric", xsgeneric_questions, {
            "emergency": "Generic X-Sense score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Generic X-Sense score is inconclusive.\n\nVentilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
            "guidance": "Generic X-Sense score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, fault, end-of-life, or test status.",
        }, "Unknown X-Sense"),
    ]

    for prefix, questions, messages, label in branch_specs:
        branch_nodes, branch_edges = _build_branch(prefix, questions, messages, label)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_XSENSE, "xs_model", nodes, edges)


def _create_co_alarm_honeywell_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "Honeywell", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(prefix: str, questions: list[dict], messages: dict, label: str | None = None) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        score_variable = f"{prefix}_score"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(
            f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
            for question in questions
        )

        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "Honeywell",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "Honeywell",
                    "variable": normalized_variable,
                    "label": f"{label or prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        nodes.extend(
            [
                WorkflowNode(id=f"{prefix}_emergency_out", type=WorkflowNodeType.DECISION, data={"group": "Honeywell", "outcome": "emergency_dispatch", "message": messages["emergency"]}),
                WorkflowNode(id=f"{prefix}_monitor_out", type=WorkflowNodeType.DECISION, data={"group": "Honeywell", "outcome": "monitor", "message": messages["monitor"]}),
                WorkflowNode(id=f"{prefix}_guidance_out", type=WorkflowNodeType.DECISION, data={"group": "Honeywell", "outcome": "close_with_guidance", "message": messages["guidance"]}),
            ]
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )
        return nodes, edges

    xc70_questions = [
        {"variable": "hw70_sound", "question": "What is the XC70 doing?", "options": [{"label": "Full loud alarm", "score": 25}, {"label": "Pre-alarm warning", "score": 15}, {"label": "Single warning chirp", "score": 3}, {"label": "No sound", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw70_light", "question": "Which light do you see?", "options": [{"label": "Red alarm light", "score": 12}, {"label": "Yellow warning light", "score": 4}, {"label": "Green normal light", "score": 1}, {"label": "No light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw70_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Low level warning only", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw70_feature", "question": "Which XC70 feature fits?", "options": [{"label": "Alarm memory", "score": 8}, {"label": "Event logger only", "score": 6}, {"label": "End-of-life warning", "score": 5}, {"label": "Fault warning", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw70_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Low battery / end of life", "score": 4}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    xc100_questions = [
        {"variable": "hw100_sound", "question": "What is the XC100 doing?", "options": [{"label": "Full loud alarm", "score": 25}, {"label": "Pre-alarm warning", "score": 15}, {"label": "Single warning chirp", "score": 3}, {"label": "No sound", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw100_light", "question": "Which light do you see?", "options": [{"label": "Red alarm light", "score": 12}, {"label": "Yellow warning light", "score": 4}, {"label": "Green normal light", "score": 1}, {"label": "No light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw100_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Low level warning only", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw100_feature", "question": "Which XC100 feature fits?", "options": [{"label": "Alarm memory", "score": 8}, {"label": "Low level monitor", "score": 10}, {"label": "End-of-life warning", "score": 5}, {"label": "Fault warning", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw100_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Low battery / end of life", "score": 4}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    xc100d_questions = [
        {"variable": "hw100d_sound", "question": "What is the XC100D doing?", "options": [{"label": "Full loud alarm", "score": 25}, {"label": "Pre-alarm warning", "score": 15}, {"label": "Single warning chirp", "score": 3}, {"label": "No sound", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw100d_display", "question": "What does the display or light show?", "options": [{"label": "Red alarm warning", "score": 12}, {"label": "Yellow warning / icon", "score": 4}, {"label": "Green normal", "score": 1}, {"label": "No display / unsure", "score": 6}]},
        {"variable": "hw100d_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Low level warning only", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw100d_feature", "question": "Which XC100D feature fits?", "options": [{"label": "Alarm memory", "score": 8}, {"label": "Low level monitor", "score": 10}, {"label": "End-of-life warning", "score": 5}, {"label": "Fault warning", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hw100d_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Low battery / end of life", "score": 4}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    hwgeneric_questions = [
        {"variable": "hwgeneric_sound", "question": "What is the Honeywell alarm doing?", "options": [{"label": "Full loud alarm", "score": 25}, {"label": "Pre-alarm warning", "score": 15}, {"label": "Single warning chirp", "score": 3}, {"label": "No sound", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hwgeneric_light", "question": "Which light do you see?", "options": [{"label": "Red alarm light", "score": 12}, {"label": "Yellow warning light", "score": 4}, {"label": "Green normal light", "score": 1}, {"label": "No light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "hwgeneric_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Low level warning only", "score": 10}, {"label": "Just a warning chirp", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hwgeneric_feature", "question": "Which feature fits best?", "options": [{"label": "Alarm memory", "score": 8}, {"label": "Low level warning", "score": 10}, {"label": "End-of-life warning", "score": 5}, {"label": "Fault warning", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "hwgeneric_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Low battery / end of life", "score": 4}, {"label": "Fault", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]

    nodes = [
        WorkflowNode(
            id="hw_model",
            type=WorkflowNodeType.QUESTION,
            data={
                "group": "Honeywell",
                "question": "Which Honeywell model is shown?",
                "variable": "hw_model",
                "options": [
                    {"label": "XC70", "score": 1},
                    {"label": "XC100", "score": 1},
                    {"label": "XC100D", "score": 1},
                    {"label": "Not sure / another Honeywell model", "score": 1},
                ],
            },
        ),
        WorkflowNode(
            id="hw_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "Honeywell",
                "variable": "hw_model",
                "label": "Honeywell model routing",
                "cases": ["XC70", "XC100", "XC100D", "Not sure / another Honeywell model"],
                "default": "Not sure / another Honeywell model",
            },
        ),
    ]
    edges = [
        WorkflowEdge(source="hw_model", target="hw_model_switch"),
        WorkflowEdge(source="hw_model_switch", target="hw70_q1", condition="hw_model == 'XC70'"),
        WorkflowEdge(source="hw_model_switch", target="hw100_q1", condition="hw_model == 'XC100'"),
        WorkflowEdge(source="hw_model_switch", target="hw100d_q1", condition="hw_model == 'XC100D'"),
        WorkflowEdge(source="hw_model_switch", target="hwgeneric_q1", condition="hw_model == 'Not sure / another Honeywell model'"),
    ]

    branch_specs = [
        ("hw70", xc70_questions, {
            "emergency": "Honeywell XC70 score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Honeywell XC70 score is inconclusive.\n\nVentilate the property and avoid using fuel-burning appliances while monitoring the alarm.",
            "guidance": "Honeywell XC70 score fits a maintenance or non-emergency pattern.\n\nFollow the XC70 guidance for battery, fault, end-of-life, or test status.",
        }, "XC70"),
        ("hw100", xc100_questions, {
            "emergency": "Honeywell XC100 score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Honeywell XC100 score is inconclusive.\n\nVentilate the property and avoid using fuel-burning appliances while monitoring the alarm.",
            "guidance": "Honeywell XC100 score fits a maintenance or non-emergency pattern.\n\nFollow the XC100 guidance for battery, fault, end-of-life, or test status.",
        }, "XC100"),
        ("hw100d", xc100d_questions, {
            "emergency": "Honeywell XC100D score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Honeywell XC100D score is inconclusive.\n\nVentilate the property and avoid using fuel-burning appliances while monitoring the alarm.",
            "guidance": "Honeywell XC100D score fits a maintenance or non-emergency pattern.\n\nFollow the XC100D guidance for battery, fault, end-of-life, or test status.",
        }, "XC100D"),
        ("hwgeneric", hwgeneric_questions, {
            "emergency": "Generic Honeywell score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
            "monitor": "Generic Honeywell score is inconclusive.\n\nVentilate the property and avoid using fuel-burning appliances while monitoring the alarm.",
            "guidance": "Generic Honeywell score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, fault, end-of-life, or test status.",
        }, "Unknown Honeywell"),
    ]

    for prefix, questions, messages, label in branch_specs:
        branch_nodes, branch_edges = _build_branch(prefix, questions, messages, label)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_HONEYWELL, "hw_model", nodes, edges)


def _create_co_alarm_google_nest_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "Google Nest", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(prefix: str, questions: list[dict], messages: dict, label: str | None = None) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        score_variable = f"{prefix}_score"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(
            f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
            for question in questions
        )

        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "Google Nest",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "Google Nest",
                    "variable": normalized_variable,
                    "label": f"{label or prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        nodes.extend(
            [
                WorkflowNode(id=f"{prefix}_emergency_out", type=WorkflowNodeType.DECISION, data={"group": "Google Nest", "outcome": "emergency_dispatch", "message": messages["emergency"]}),
                WorkflowNode(id=f"{prefix}_monitor_out", type=WorkflowNodeType.DECISION, data={"group": "Google Nest", "outcome": "monitor", "message": messages["monitor"]}),
                WorkflowNode(id=f"{prefix}_guidance_out", type=WorkflowNodeType.DECISION, data={"group": "Google Nest", "outcome": "close_with_guidance", "message": messages["guidance"]}),
            ]
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )
        return nodes, edges

    nest_questions = [
        {"variable": "nest_alert", "question": "What is the Nest Protect doing?", "options": [{"label": "Red emergency alarm", "score": 25}, {"label": "Yellow Heads-Up warning", "score": 15}, {"label": "Yellow issue warning", "score": 4}, {"label": "Only chirping", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "nest_voice", "question": "What voice or message fits?", "options": [{"label": "CO emergency message", "score": 20}, {"label": "Heads-Up message", "score": 10}, {"label": "Battery / sensor issue", "score": 4}, {"label": "No spoken message", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "nest_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Warning only", "score": 10}, {"label": "Just chirping", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "nest_app", "question": "What does the app or light suggest?", "options": [{"label": "Danger / evacuate", "score": 16}, {"label": "Heads-Up / early warning", "score": 10}, {"label": "Battery / maintenance issue", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "nest_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Maintenance issue", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    nestgeneric_questions = [
        {"variable": "nestgeneric_alert", "question": "What is the Nest alarm doing?", "options": [{"label": "Red emergency alarm", "score": 25}, {"label": "Yellow warning", "score": 15}, {"label": "Issue warning", "score": 4}, {"label": "Only chirping", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "nestgeneric_voice", "question": "What voice or message fits?", "options": [{"label": "CO emergency message", "score": 20}, {"label": "Heads-Up message", "score": 10}, {"label": "Battery / sensor issue", "score": 4}, {"label": "No spoken message", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "nestgeneric_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Warning only", "score": 10}, {"label": "Just chirping", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "nestgeneric_hint", "question": "What does the app or light suggest?", "options": [{"label": "Danger / evacuate", "score": 16}, {"label": "Heads-Up / early warning", "score": 10}, {"label": "Battery / maintenance issue", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "nestgeneric_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Maintenance issue", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]

    nodes = [
        WorkflowNode(
            id="nest_model",
            type=WorkflowNodeType.QUESTION,
            data={
                "group": "Google Nest",
                "question": "Which Google Nest alarm is it?",
                "variable": "nest_model",
                "options": [
                    {"label": "Nest Protect", "score": 1},
                    {"label": "Not sure / another Nest alarm", "score": 1},
                ],
            },
        ),
        WorkflowNode(
            id="nest_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "Google Nest",
                "variable": "nest_model",
                "label": "Google Nest model routing",
                "cases": ["Nest Protect", "Not sure / another Nest alarm"],
                "default": "Not sure / another Nest alarm",
            },
        ),
    ]
    edges = [
        WorkflowEdge(source="nest_model", target="nest_model_switch"),
        WorkflowEdge(source="nest_model_switch", target="nest_q1", condition="nest_model == 'Nest Protect'"),
        WorkflowEdge(source="nest_model_switch", target="nestgeneric_q1", condition="nest_model == 'Not sure / another Nest alarm'"),
    ]

    branch_specs = [
        ("nest", nest_questions, {
            "emergency": "Nest Protect score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone is unwell\n\nEmergency engineer dispatched.",
            "monitor": "Nest Protect score is inconclusive.\n\nThis may be an early warning or a real event. Ventilate the property and avoid using gas appliances while monitoring closely.",
            "guidance": "Nest Protect score fits a maintenance or non-emergency pattern.\n\nFollow the Nest guidance for battery, maintenance, sensor issue, or test status.",
        }, "Nest Protect"),
        ("nestgeneric", nestgeneric_questions, {
            "emergency": "Google Nest score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone is unwell\n\nEmergency engineer dispatched.",
            "monitor": "Google Nest score is inconclusive.\n\nThis may be an early warning or a real event. Ventilate the property and avoid using gas appliances while monitoring closely.",
            "guidance": "Google Nest score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, maintenance, sensor issue, or test status.",
        }, "Unknown Nest"),
    ]

    for prefix, questions, messages, label in branch_specs:
        branch_nodes, branch_edges = _build_branch(prefix, questions, messages, label)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_GOOGLE_NEST, "nest_model", nodes, edges)


def _create_co_alarm_netatmo_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "Netatmo", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(prefix: str, questions: list[dict], messages: dict, label: str | None = None) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        score_variable = f"{prefix}_score"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(
            f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
            for question in questions
        )

        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "Netatmo",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "Netatmo",
                    "variable": normalized_variable,
                    "label": f"{label or prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        nodes.extend(
            [
                WorkflowNode(id=f"{prefix}_emergency_out", type=WorkflowNodeType.DECISION, data={"group": "Netatmo", "outcome": "emergency_dispatch", "message": messages["emergency"]}),
                WorkflowNode(id=f"{prefix}_monitor_out", type=WorkflowNodeType.DECISION, data={"group": "Netatmo", "outcome": "monitor", "message": messages["monitor"]}),
                WorkflowNode(id=f"{prefix}_guidance_out", type=WorkflowNodeType.DECISION, data={"group": "Netatmo", "outcome": "close_with_guidance", "message": messages["guidance"]}),
            ]
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )
        return nodes, edges

    netatmo_questions = [
        {"variable": "net_alert", "question": "What is the Netatmo alarm doing?", "options": [{"label": "Danger alarm sounding", "score": 25}, {"label": "Warning or alert", "score": 10}, {"label": "Fault warning", "score": 4}, {"label": "Just test or maintenance", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "net_light", "question": "Which light or status fits?", "options": [{"label": "Red danger warning", "score": 12}, {"label": "Amber / warning", "score": 4}, {"label": "Normal / ready", "score": 1}, {"label": "No clear light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "net_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Warning only", "score": 10}, {"label": "Just a maintenance alert", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "net_app", "question": "What does the app or status suggest?", "options": [{"label": "Danger / evacuate", "score": 16}, {"label": "CO warning", "score": 10}, {"label": "Device fault", "score": 4}, {"label": "Maintenance / test only", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "net_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Fault / maintenance", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]
    netgeneric_questions = [
        {"variable": "netgeneric_alert", "question": "What is the Netatmo alarm doing?", "options": [{"label": "Danger alarm sounding", "score": 25}, {"label": "Warning or alert", "score": 10}, {"label": "Fault warning", "score": 4}, {"label": "Just test or maintenance", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "netgeneric_light", "question": "Which light or status fits?", "options": [{"label": "Red danger warning", "score": 12}, {"label": "Amber / warning", "score": 4}, {"label": "Normal / ready", "score": 1}, {"label": "No clear light", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "netgeneric_now", "question": "What best describes it now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Warning only", "score": 10}, {"label": "Just a maintenance alert", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
        {"variable": "netgeneric_hint", "question": "What does the app or status suggest?", "options": [{"label": "Danger / evacuate", "score": 16}, {"label": "CO warning", "score": 10}, {"label": "Device fault", "score": 4}, {"label": "Maintenance / test only", "score": 2}, {"label": "Not sure", "score": 6}]},
        {"variable": "netgeneric_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Early warning", "score": 10}, {"label": "Fault / maintenance", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 6}]},
    ]

    nodes = [
        WorkflowNode(
            id="net_model",
            type=WorkflowNodeType.QUESTION,
            data={
                "group": "Netatmo",
                "question": "Which Netatmo alarm is it?",
                "variable": "net_model",
                "options": [
                    {"label": "Netatmo Smart CO Alarm", "score": 1},
                    {"label": "Not sure / another Netatmo alarm", "score": 1},
                ],
            },
        ),
        WorkflowNode(
            id="net_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "Netatmo",
                "variable": "net_model",
                "label": "Netatmo model routing",
                "cases": ["Netatmo Smart CO Alarm", "Not sure / another Netatmo alarm"],
                "default": "Not sure / another Netatmo alarm",
            },
        ),
    ]
    edges = [
        WorkflowEdge(source="net_model", target="net_model_switch"),
        WorkflowEdge(source="net_model_switch", target="net_q1", condition="net_model == 'Netatmo Smart CO Alarm'"),
        WorkflowEdge(source="net_model_switch", target="netgeneric_q1", condition="net_model == 'Not sure / another Netatmo alarm'"),
    ]

    branch_specs = [
        ("net", netatmo_questions, {
            "emergency": "Netatmo Smart CO Alarm score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone is unwell\n\nEmergency engineer dispatched.",
            "monitor": "Netatmo Smart CO Alarm score is inconclusive.\n\nThis may be an early warning or a real event. Ventilate the property and avoid using gas appliances while monitoring closely.",
            "guidance": "Netatmo Smart CO Alarm score fits a maintenance or non-emergency pattern.\n\nFollow the Netatmo guidance for fault, maintenance, or test status.",
        }, "Netatmo Smart CO Alarm"),
        ("netgeneric", netgeneric_questions, {
            "emergency": "Netatmo score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone is unwell\n\nEmergency engineer dispatched.",
            "monitor": "Netatmo score is inconclusive.\n\nThis may be an early warning or a real event. Ventilate the property and avoid using gas appliances while monitoring closely.",
            "guidance": "Netatmo score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for fault, maintenance, or test status.",
        }, "Unknown Netatmo"),
    ]

    for prefix, questions, messages, label in branch_specs:
        branch_nodes, branch_edges = _build_branch(prefix, questions, messages, label)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_NETATMO, "net_model", nodes, edges)


def _create_co_alarm_cavius_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "Cavius", "question": question, "variable": variable, "options": options},
        )

    def _build_branch(
        prefix: str,
        questions: list[dict],
        score_variable: str,
        outcomes: dict,
    ) -> tuple[list[WorkflowNode], list[WorkflowEdge]]:
        nodes: list[WorkflowNode] = []
        edges: list[WorkflowEdge] = []

        for index, question in enumerate(questions):
            q_id = f"{prefix}_q{index + 1}"
            nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
            if index > 0:
                edges.append(WorkflowEdge(source=f"{prefix}_q{index}", target=q_id))

        calc_id = f"{prefix}_calculate_score"
        switch_id = f"{prefix}_risk_switch"
        normalized_variable = f"{prefix}_normalized_score"
        max_score = sum(
            max(int(option.get("score", 0)) for option in question["options"])
            for question in questions
        )
        safe_score_parts = " + ".join(f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)" for question in questions)
        nodes.append(
            WorkflowNode(
                id=calc_id,
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "Cavius",
                    "calculation": (
                        f"{score_variable} = {safe_score_parts}\n"
                        f"{normalized_variable} = round(({score_variable} / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": normalized_variable,
                },
            )
        )
        nodes.append(
            WorkflowNode(
                id=switch_id,
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "Cavius",
                    "variable": normalized_variable,
                    "label": f"{prefix} risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            )
        )
        edges.append(WorkflowEdge(source=f"{prefix}_q{len(questions)}", target=calc_id))
        edges.append(WorkflowEdge(source=calc_id, target=switch_id))

        for route_name, route in outcomes.items():
            decision_id = f"{prefix}_{route_name}_out"
            nodes.append(
                WorkflowNode(
                    id=decision_id,
                    type=WorkflowNodeType.DECISION,
                    data={"group": "Cavius", "outcome": route["outcome"], "message": route["message"]},
                )
            )
        edges.extend(
            [
                WorkflowEdge(source=switch_id, target=f"{prefix}_emergency_out", condition=f"{normalized_variable} >= 0.7"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_monitor_out", condition=f"{normalized_variable} >= 0.35"),
                WorkflowEdge(source=switch_id, target=f"{prefix}_guidance_out"),
            ]
        )

        return nodes, edges

    nodes = [
        WorkflowNode(
            id="cav_model",
            type=WorkflowNodeType.QUESTION,
            data={
                "group": "Cavius",
                "question": "Which Cavius model is shown?",
                "variable": "cav_model",
                "options": [
                    {"label": "CV4002", "score": 1},
                    {"label": "Not sure / another Cavius model", "score": 1},
                ],
            },
        ),
        WorkflowNode(
            id="cav_model_switch",
            type=WorkflowNodeType.SWITCH,
            data={
                "group": "Cavius",
                "variable": "cav_model",
                "label": "Cavius model routing",
                "cases": ["CV4002", "Not sure / another Cavius model"],
                "default": "Not sure / another Cavius model",
            },
        ),
    ]
    edges = [
        WorkflowEdge(source="cav_model", target="cav_model_switch"),
        WorkflowEdge(source="cav_model_switch", target="cav4002_q1", condition="cav_model == 'CV4002'"),
        WorkflowEdge(source="cav_model_switch", target="cavgeneric_q1", condition="cav_model == 'Not sure / another Cavius model'"),
    ]

    cav4002_nodes, cav4002_edges = _build_branch(
        "cav4002",
        [
            {"variable": "cav4002_light", "question": "Which LED is showing?", "options": [{"label": "Red LED", "score": 10}, {"label": "Yellow LED", "score": 2}, {"label": "Green LED", "score": 1}, {"label": "Not sure", "score": 3}]},
            {"variable": "cav4002_sound", "question": "Which sound fits best?", "options": [{"label": "Repeated alarm tones", "score": 25}, {"label": "1 short beep", "score": 2}, {"label": "2 short beeps", "score": 2}, {"label": "3 short beeps", "score": 2}, {"label": "No sound", "score": 1}, {"label": "Not sure", "score": 3}]},
            {"variable": "cav4002_timing", "question": "How often does it happen?", "options": [{"label": "About every 0.5 sec", "score": 15}, {"label": "About every 60 sec", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 3}]},
            {"variable": "cav4002_led_timing", "question": "Which LED pattern fits?", "options": [{"label": "Red LED with alarm", "score": 10}, {"label": "Yellow LED with beeps", "score": 2}, {"label": "Green flash every 60 sec", "score": 1}, {"label": "Green for 3 sec after test", "score": 1}, {"label": "Not sure", "score": 3}]},
            {"variable": "cav4002_fit", "question": "Which manual note fits?", "options": [{"label": "Danger alarm note", "score": 15}, {"label": "Low battery note", "score": 2}, {"label": "Fault note", "score": 2}, {"label": "End-of-life note", "score": 2}, {"label": "Standby / test note", "score": 1}, {"label": "Not sure", "score": 5}]},
        ],
        "cav4002_score",
        {
            "emergency": {"outcome": "emergency_dispatch", "message": "Cavius CV4002 score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched."},
            "monitor": {"outcome": "monitor", "message": "Cavius CV4002 score is inconclusive.\n\nThis may be a false case or a true CO event. Ventilate the property, avoid fuel-burning appliances, and monitor the situation closely."},
            "guidance": {"outcome": "close_with_guidance", "message": "Cavius CV4002 score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, fault, end-of-life, or test status."},
        },
    )

    cavgeneric_nodes, cavgeneric_edges = _build_branch(
        "cavgeneric",
        [
            {"variable": "cavgeneric_light", "question": "Which LED is showing?", "options": [{"label": "Red LED", "score": 10}, {"label": "Yellow LED", "score": 2}, {"label": "Green LED", "score": 1}, {"label": "Not sure", "score": 3}]},
            {"variable": "cavgeneric_sound", "question": "Which sound fits best?", "options": [{"label": "Repeated alarm tones", "score": 25}, {"label": "1 short beep", "score": 2}, {"label": "2 short beeps", "score": 2}, {"label": "3 short beeps", "score": 2}, {"label": "No sound", "score": 1}, {"label": "Not sure", "score": 3}]},
            {"variable": "cavgeneric_timing", "question": "How often does it happen?", "options": [{"label": "About every 0.5 sec", "score": 15}, {"label": "About every 60 sec", "score": 2}, {"label": "Normal", "score": 1}, {"label": "Not sure", "score": 3}]},
            {"variable": "cavgeneric_led_timing", "question": "Which LED pattern fits?", "options": [{"label": "Red LED with alarm", "score": 10}, {"label": "Yellow LED with beeps", "score": 2}, {"label": "Green flash every 60 sec", "score": 1}, {"label": "Green for 3 sec after test", "score": 1}, {"label": "Not sure", "score": 3}]},
            {"variable": "cavgeneric_fit", "question": "Which manual note fits?", "options": [{"label": "Danger alarm note", "score": 15}, {"label": "Low battery note", "score": 2}, {"label": "Fault note", "score": 2}, {"label": "End-of-life note", "score": 2}, {"label": "Standby / test note", "score": 1}, {"label": "Not sure", "score": 5}]},
        ],
        "cavgeneric_score",
        {
            "emergency": {"outcome": "emergency_dispatch", "message": "Cavius score indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched."},
            "monitor": {"outcome": "monitor", "message": "Cavius score is inconclusive.\n\nThis may be a false case or a true CO event. Ventilate the property, avoid fuel-burning appliances, and monitor the situation closely."},
            "guidance": {"outcome": "close_with_guidance", "message": "Cavius score fits a maintenance or non-emergency pattern.\n\nFollow the alarm guidance for battery, fault, end-of-life, or test status."},
        },
    )

    nodes.extend(cav4002_nodes + cavgeneric_nodes)
    edges.extend(cav4002_edges + cavgeneric_edges)
    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_CAVIUS, "cav_model", nodes, edges)


def _create_co_alarm_other_workflow(tenant_id: str) -> WorkflowDefinition:
    def _question(node_id: str, variable: str, question: str, options: list[dict]) -> WorkflowNode:
        return WorkflowNode(
            id=node_id,
            type=WorkflowNodeType.QUESTION,
            data={"group": "Other", "question": question, "variable": variable, "options": options},
        )

    questions = [
        {"variable": "other_light", "question": "What light do you see on the alarm?", "options": [{"label": "Red", "score": 12}, {"label": "Amber / yellow", "score": 4}, {"label": "Green", "score": 1}, {"label": "No light", "score": 2}, {"label": "Cannot tell", "score": 6}]},
        {"variable": "other_sound", "question": "What sound do you hear?", "options": [{"label": "Loud repeated alarm", "score": 25}, {"label": "Single chirp", "score": 2}, {"label": "2-3 warning chirps", "score": 4}, {"label": "Silent", "score": 1}, {"label": "Cannot tell", "score": 6}]},
        {"variable": "other_now", "question": "What best describes it right now?", "options": [{"label": "Alarm sounding now", "score": 16}, {"label": "Was sounding, now quiet", "score": 10}, {"label": "Just warning chirps", "score": 3}, {"label": "Normal", "score": 1}, {"label": "Cannot tell", "score": 6}]},
        {"variable": "other_repeat", "question": "How often does it happen?", "options": [{"label": "Keeps repeating", "score": 14}, {"label": "About every minute", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Cannot tell", "score": 6}]},
        {"variable": "other_issue", "question": "What does it seem like?", "options": [{"label": "Possible CO alarm", "score": 20}, {"label": "Low battery", "score": 2}, {"label": "Fault / end of life", "score": 4}, {"label": "Normal", "score": 1}, {"label": "Cannot tell", "score": 6}]},
    ]

    nodes: list[WorkflowNode] = []
    edges: list[WorkflowEdge] = []
    for index, question in enumerate(questions):
        q_id = f"other_q{index + 1}"
        nodes.append(_question(q_id, question["variable"], question["question"], question["options"]))
        if index > 0:
            edges.append(WorkflowEdge(source=f"other_q{index}", target=q_id))

    max_score = sum(max(int(option.get("score", 0)) for option in question["options"]) for question in questions)
    safe_score_parts = " + ".join(
        f"int({question['variable']}_score if '{question['variable']}_score' in locals() else 0)"
        for question in questions
    )

    nodes.extend(
        [
            WorkflowNode(
                id="other_calculate_score",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "group": "Other",
                    "calculation": (
                        f"other_score = {safe_score_parts}\n"
                        f"other_normalized_score = round((other_score / {max_score}), 3) if {max_score} else 0"
                    ),
                    "result_variable": "other_normalized_score",
                },
            ),
            WorkflowNode(
                id="other_risk_switch",
                type=WorkflowNodeType.SWITCH,
                data={
                    "group": "Other",
                    "variable": "other_normalized_score",
                    "label": "Other / Cannot see risk routing",
                    "cases": ["Emergency", "Monitor", "Guidance"],
                },
            ),
            WorkflowNode(
                id="other_emergency_out",
                type=WorkflowNodeType.DECISION,
                data={
                    "group": "Other",
                    "outcome": "emergency_dispatch",
                    "message": "The generic alarm pattern indicates a likely live CO alarm.\n\n1. Evacuate immediately\n2. Open doors and windows\n3. Do not re-enter\n4. Call 999 if anyone feels unwell\n\nEmergency engineer dispatched.",
                },
            ),
            WorkflowNode(
                id="other_monitor_out",
                type=WorkflowNodeType.DECISION,
                data={
                    "group": "Other",
                    "outcome": "monitor",
                    "message": "The alarm pattern is unclear.\n\nThis could be a false case or a real CO event. Ventilate the property, avoid fuel-burning appliances, and monitor the alarm closely.",
                },
            ),
            WorkflowNode(
                id="other_guidance_out",
                type=WorkflowNodeType.DECISION,
                data={
                    "group": "Other",
                    "outcome": "close_with_guidance",
                    "message": "The generic alarm pattern fits a maintenance or non-emergency warning.\n\nFollow guidance for battery, fault, end-of-life, or test status.",
                },
            ),
        ]
    )

    edges.extend(
        [
            WorkflowEdge(source=f"other_q{len(questions)}", target="other_calculate_score"),
            WorkflowEdge(source="other_calculate_score", target="other_risk_switch"),
            WorkflowEdge(source="other_risk_switch", target="other_emergency_out", condition="other_normalized_score >= 0.7"),
            WorkflowEdge(source="other_risk_switch", target="other_monitor_out", condition="other_normalized_score >= 0.35"),
            WorkflowEdge(source="other_risk_switch", target="other_guidance_out"),
        ]
    )

    return _build_manufacturer_workflow(tenant_id, CO_ALARM_SUBFLOW_OTHER, "other_q1", nodes, edges)


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
