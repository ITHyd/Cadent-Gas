"""Advanced workflow definitions for CV/AI-powered use cases"""
import logging
from app.constants.use_cases import (
    WEAK_FLAME, GAS_SMELL_OUTSIDE, HISSING_SOUND,
    SUSPECTED_CO_LEAK, GAS_SUPPLY_STOPPED, METER_TAMPERING,
    SMART_HOME_ALERT,
    NEW_INSTALLATION_NOT_WORKING, GAS_LEAK_HEAVY_RAIN,
    UNDERGROUND_GAS_LEAK,
)
from app.schemas.workflow_definition import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    WorkflowNodeType,
)

logger = logging.getLogger(__name__)


def _create_weak_flame_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 3: Weak/Yellow Flame - Stove Flame Analysis
    Uses CV model to analyze flame photo and determine if it's area-wide or appliance-specific
    """
    workflow_id = f"{tenant_id}_{WEAK_FLAME}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=WEAK_FLAME,
        version=1,
        start_node="upload_flame_photo",
        nodes=[
            # === Q1: Flame Photo ===
            WorkflowNode(
                id="upload_flame_photo",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Please upload a photo of the flame for analysis",
                    "variable": "flame_photo",
                    "input_type": "image",
                    "options": ["Skip"]
                },
            ),
            # === Q2: Flame Color ===
            WorkflowNode(
                id="flame_color",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What color is the flame?",
                    "variable": "flame_color",
                    "options": [
                        {"label": "Blue (normal)", "score": 0},
                        {"label": "Yellow / Orange", "score": 15},
                        {"label": "Red", "score": 20},
                        {"label": "Flickering between colors", "score": 10}
                    ]
                },
            ),
            # === Q3: Issue Onset ===
            WorkflowNode(
                id="issue_onset_flame",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "When did you first notice the weak flame?",
                    "variable": "flame_onset",
                    "options": [
                        {"label": "Today", "score": 3},
                        {"label": "Within last week", "score": 2},
                        {"label": "Gradual over weeks", "score": 5},
                        {"label": "Sudden change", "score": 8}
                    ]
                },
            ),
            # === Q4: Gas Smell ===
            WorkflowNode(
                id="gas_smell_flame",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do you smell gas while the appliance is running?",
                    "variable": "smell_during_use",
                    "options": [
                        {"label": "Yes - Strong smell", "score": 20},
                        {"label": "Yes - Faint smell", "score": 10},
                        {"label": "No smell", "score": 0}
                    ]
                },
            ),
            # === Q5: Pilot Light ===
            WorkflowNode(
                id="pilot_light",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is the pilot light staying on or going out?",
                    "variable": "pilot_status",
                    "options": [
                        {"label": "Stays on", "score": 0},
                        {"label": "Goes out occasionally", "score": 8},
                        {"label": "Goes out frequently", "score": 12},
                        {"label": "No pilot light", "score": 3}
                    ]
                },
            ),
            # === Q6: Other Appliances ===
            WorkflowNode(
                id="check_other_appliances",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are other gas appliances in your home also affected?",
                    "variable": "other_appliances_affected",
                    "options": [
                        {"label": "Yes - All appliances", "score": 20},
                        {"label": "Yes - Some appliances", "score": 12},
                        {"label": "No - Only this one", "score": 0},
                        {"label": "Not sure", "score": 5}
                    ]
                },
            ),
            # === Q7: Appliance Age ===
            WorkflowNode(
                id="appliance_age",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How old is this appliance?",
                    "variable": "appliance_age",
                    "options": [
                        {"label": "Less than 5 years", "score": 0},
                        {"label": "5-10 years", "score": 5},
                        {"label": "More than 10 years", "score": 8},
                        {"label": "Don't know", "score": 3}
                    ]
                },
            ),
            # === Q8: Recent Area Changes ===
            WorkflowNode(
                id="recent_maintenance",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you noticed any recent changes in your area (construction, maintenance work)?",
                    "variable": "recent_area_changes",
                    "options": [
                        {"label": "Yes - Gas line work", "score": 10},
                        {"label": "Yes - Road construction", "score": 10},
                        {"label": "Yes - Other work", "score": 5},
                        {"label": "No changes", "score": 0}
                    ]
                },
            ),
            # === Risk Calculation ===
            WorkflowNode(
                id="calculate_flame_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="check_area_wide",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "other_appliances_affected == 'Yes - All appliances' or risk_score >= 60"
                },
            ),
            WorkflowNode(
                id="area_wide_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "schedule_engineer", "message": "Area-wide pressure issue detected - Utility ticket raised"},
            ),
            WorkflowNode(
                id="check_old_appliance",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "appliance_age == 'More than 10 years' and other_appliances_affected == 'No - Only this one'"
                },
            ),
            WorkflowNode(
                id="appliance_service_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "close_with_guidance", "message": "Single appliance issue - Service technician recommended"},
            ),
            WorkflowNode(
                id="regulator_check_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "schedule_engineer", "message": "Possible regulator fault - Engineer scheduled"},
            ),
        ],
        edges=[
            WorkflowEdge(source="upload_flame_photo", target="flame_color"),
            WorkflowEdge(source="flame_color", target="issue_onset_flame"),
            WorkflowEdge(source="issue_onset_flame", target="gas_smell_flame"),
            WorkflowEdge(source="gas_smell_flame", target="pilot_light"),
            WorkflowEdge(source="pilot_light", target="check_other_appliances"),
            WorkflowEdge(source="check_other_appliances", target="appliance_age"),
            WorkflowEdge(source="appliance_age", target="recent_maintenance"),
            WorkflowEdge(source="recent_maintenance", target="calculate_flame_risk"),
            WorkflowEdge(source="calculate_flame_risk", target="check_area_wide"),
            WorkflowEdge(source="check_area_wide", target="area_wide_outcome", condition="True"),
            WorkflowEdge(source="check_area_wide", target="check_old_appliance", condition="False"),
            WorkflowEdge(source="check_old_appliance", target="appliance_service_outcome", condition="True"),
            WorkflowEdge(source="check_old_appliance", target="regulator_check_outcome", condition="False"),
        ],
    )


def _create_gas_smell_outside_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 4: Gas Smell Outside Near Meter
    Uses geo-tagging and image analysis to detect pipe damage
    """
    workflow_id = f"{tenant_id}_{GAS_SMELL_OUTSIDE}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=GAS_SMELL_OUTSIDE,
        version=1,
        start_node="location_check",
        nodes=[
            WorkflowNode(
                id="location_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Where exactly do you smell gas?",
                    "variable": "smell_location",
                    "options": [
                        {"label": "Near gas meter", "score": 20},
                        {"label": "Near main pipeline", "score": 30},
                        {"label": "Street/sidewalk", "score": 30},
                        {"label": "Property boundary", "score": 15},
                        {"label": "Other outdoor area", "score": 10}
                    ]
                },
            ),
            WorkflowNode(
                id="upload_photo",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you upload a photo of the area?",
                    "variable": "area_photo",
                    "input_type": "image",
                    "options": ["Skip"]
                },
            ),
            WorkflowNode(
                id="visible_damage",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do you see any visible damage to pipes or fittings?",
                    "variable": "visible_damage",
                    "options": [
                        {"label": "Yes - Corrosion", "score": 40},
                        {"label": "Yes - Cracks", "score": 40},
                        {"label": "Yes - Loose fittings", "score": 35},
                        {"label": "Yes - Other damage", "score": 30},
                        {"label": "No visible damage", "score": 0}
                    ]
                },
            ),
            WorkflowNode(
                id="smell_strength",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How strong is the smell?",
                    "variable": "outdoor_smell_strength",
                    "options": [
                        {"label": "Very strong", "score": 30},
                        {"label": "Moderate", "score": 15},
                        {"label": "Faint", "score": 5},
                        {"label": "Comes and goes", "score": 10}
                    ]
                },
            ),
            # === Q6: Community Reports ===
            WorkflowNode(
                id="others_reporting",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are other people in the area also reporting the smell?",
                    "variable": "community_reports",
                    "options": [
                        {"label": "Yes - Multiple people", "score": 15},
                        {"label": "Yes - One neighbor", "score": 8},
                        {"label": "No one else", "score": 0},
                        {"label": "Haven't asked", "score": 5}
                    ]
                },
            ),
            # === Q7: Smell Distance ===
            WorkflowNode(
                id="smell_distance",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How far from the source can you detect the smell?",
                    "variable": "smell_spread",
                    "options": [
                        {"label": "Very localized (< 5m)", "score": 5},
                        {"label": "Moderate spread (5-20m)", "score": 10},
                        {"label": "Wide area (> 20m)", "score": 20},
                        {"label": "Entire street", "score": 25}
                    ]
                },
            ),
            WorkflowNode(
                id="recent_work",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Has there been any recent construction or excavation work nearby?",
                    "variable": "recent_excavation",
                    "options": [
                        {"label": "Yes - Within last week", "score": 20},
                        {"label": "Yes - Within last month", "score": 10},
                        {"label": "Yes - Ongoing now", "score": 20},
                        {"label": "No recent work", "score": 0}
                    ]
                },
            ),
            WorkflowNode(
                id="calculate_outdoor_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="check_pipe_damage",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "risk_score >= 70"
                },
            ),
            WorkflowNode(
                id="urgent_ticket_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "emergency_dispatch", "message": "Pipe damage detected - Urgent ticket raised"},
            ),
            WorkflowNode(
                id="safety_instructions_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "close_with_guidance", "message": "No visible damage - Safety instructions provided"},
            ),
        ],
        edges=[
            WorkflowEdge(source="location_check", target="upload_photo"),
            WorkflowEdge(source="upload_photo", target="visible_damage"),
            WorkflowEdge(source="visible_damage", target="smell_strength"),
            WorkflowEdge(source="smell_strength", target="others_reporting"),
            WorkflowEdge(source="others_reporting", target="smell_distance"),
            WorkflowEdge(source="smell_distance", target="recent_work"),
            WorkflowEdge(source="recent_work", target="calculate_outdoor_risk"),
            WorkflowEdge(source="calculate_outdoor_risk", target="check_pipe_damage"),
            WorkflowEdge(source="check_pipe_damage", target="urgent_ticket_outcome", condition="True"),
            WorkflowEdge(source="check_pipe_damage", target="safety_instructions_outcome", condition="False"),
        ],
    )


def _create_hissing_sound_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 5: Hissing Sound Near Gas Line
    Uses audio analysis to detect leak patterns
    """
    workflow_id = f"{tenant_id}_{HISSING_SOUND}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=HISSING_SOUND,
        version=1,
        start_node="upload_audio",
        nodes=[
            WorkflowNode(
                id="upload_audio",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Please record a 10-second audio clip of the sound",
                    "variable": "audio_recording",
                    "input_type": "audio",
                    "options": ["Record Audio", "Skip"]
                },
            ),
            WorkflowNode(
                id="sound_location",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Where is the hissing sound coming from?",
                    "variable": "hissing_location",
                    "options": [
                        {"label": "Gas meter", "score": 20},
                        {"label": "Pipe connection", "score": 20},
                        {"label": "Behind wall", "score": 25},
                        {"label": "Appliance connection", "score": 15},
                        {"label": "Not sure", "score": 10}
                    ]
                },
            ),
            WorkflowNode(
                id="sound_characteristics",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How would you describe the sound?",
                    "variable": "sound_type",
                    "options": [
                        {"label": "High-pitched hissing", "score": 40},
                        {"label": "Low rumbling", "score": 15},
                        {"label": "Whistling", "score": 35},
                        {"label": "Intermittent", "score": 20},
                        {"label": "Constant", "score": 25}
                    ]
                },
            ),
            WorkflowNode(
                id="gas_meter_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is your gas meter dial spinning faster than usual?",
                    "variable": "meter_spinning",
                    "options": [
                        {"label": "Yes - Very fast", "score": 35},
                        {"label": "Yes - Slightly faster", "score": 20},
                        {"label": "Normal speed", "score": 0},
                        {"label": "Not sure", "score": 5}
                    ]
                },
            ),
            # === Q6: Isolation Test ===
            WorkflowNode(
                id="isolation_test",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Does the sound stop when you turn off all gas appliances?",
                    "variable": "sound_stops_isolated",
                    "options": [
                        {"label": "Yes - Sound stops", "score": 0},
                        {"label": "No - Sound continues", "score": 20},
                        {"label": "Partially reduced", "score": 10},
                        {"label": "Haven't tried", "score": 5}
                    ]
                },
            ),
            # === Q7: Evacuation Status ===
            WorkflowNode(
                id="evacuation_status_hiss",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you moved away from the sound source?",
                    "variable": "evacuated_from_sound",
                    "options": [
                        {"label": "Yes - Left the area", "score": 0},
                        {"label": "No - Still nearby", "score": 5},
                        {"label": "Cannot leave", "score": 8}
                    ]
                },
            ),
            WorkflowNode(
                id="recent_installation",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Has there been any recent gas work or installation?",
                    "variable": "recent_gas_work",
                    "options": [
                        {"label": "Yes - Within last week", "score": 15},
                        {"label": "Yes - Within last month", "score": 10},
                        {"label": "No recent work", "score": 0}
                    ]
                },
            ),
            WorkflowNode(
                id="calculate_leak_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="check_emergency",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "risk_score >= 80"
                },
            ),
            WorkflowNode(
                id="emergency_dispatch_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "emergency_dispatch", "message": "High-confidence leak detected - Emergency dispatch"},
            ),
            WorkflowNode(
                id="inspection_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "schedule_engineer", "message": "Visual inspection recommended - Engineer scheduled"},
            ),
        ],
        edges=[
            WorkflowEdge(source="upload_audio", target="sound_location"),
            WorkflowEdge(source="sound_location", target="sound_characteristics"),
            WorkflowEdge(source="sound_characteristics", target="gas_meter_check"),
            WorkflowEdge(source="gas_meter_check", target="isolation_test"),
            WorkflowEdge(source="isolation_test", target="evacuation_status_hiss"),
            WorkflowEdge(source="evacuation_status_hiss", target="recent_installation"),
            WorkflowEdge(source="recent_installation", target="calculate_leak_risk"),
            WorkflowEdge(source="calculate_leak_risk", target="check_emergency"),
            WorkflowEdge(source="check_emergency", target="emergency_dispatch_outcome", condition="True"),
            WorkflowEdge(source="check_emergency", target="inspection_outcome", condition="False"),
        ],
    )



def _create_suspected_co_leak_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 6: Suspected CO Leak
    Thorough triage with risk-based branching - high scores emergency, lower scores engineer visit.
    """
    workflow_id = f"{tenant_id}_{SUSPECTED_CO_LEAK}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=SUSPECTED_CO_LEAK,
        version=1,
        start_node="check_evacuation",
        nodes=[
            # === Q1: Evacuation Status ===
            WorkflowNode(
                id="check_evacuation",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you evacuated the property and are you in a safe location?",
                    "variable": "is_evacuated",
                    "options": [
                        {"label": "Yes - I'm outside", "score": 5},
                        {"label": "No - Still inside", "score": 12},
                        {"label": "Not sure what to do", "score": 12}
                    ]
                },
            ),
            # === Q2: Symptoms ===
            WorkflowNode(
                id="check_symptoms",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are you experiencing any of these symptoms?",
                    "variable": "co_symptoms",
                    "options": [
                        {"label": "Headache", "score": 8},
                        {"label": "Dizziness", "score": 10},
                        {"label": "Nausea", "score": 8},
                        {"label": "Multiple symptoms", "score": 15},
                        {"label": "No symptoms", "score": 0}
                    ]
                },
            ),
            # === Q3: CO Alarm Status ===
            WorkflowNode(
                id="check_co_alarm",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is your CO alarm beeping or triggered?",
                    "variable": "co_alarm_triggered",
                    "options": [
                        {"label": "Yes - Beeping now", "score": 15},
                        {"label": "Yes - Beeped earlier", "score": 10},
                        {"label": "No alarm", "score": 2},
                        {"label": "Don't have CO alarm", "score": 5}
                    ]
                },
            ),
            # === Q4: People Count ===
            WorkflowNode(
                id="people_affected",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How many people are in or near the property?",
                    "variable": "people_count",
                    "options": [
                        {"label": "Already evacuated - None inside", "score": 0},
                        {"label": "1-2 people", "score": 5},
                        {"label": "3-5 people", "score": 8},
                        {"label": "More than 5", "score": 12}
                    ]
                },
            ),
            # === Q5: Heating System ===
            WorkflowNode(
                id="heating_type",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What type of heating system do you have?",
                    "variable": "heating_type",
                    "options": [
                        {"label": "Gas boiler", "score": 10},
                        {"label": "Gas fire / heater", "score": 8},
                        {"label": "Oil / electric heating", "score": 2},
                        {"label": "Don't know", "score": 5}
                    ]
                },
            ),
            # === Q6: Boiler Service ===
            WorkflowNode(
                id="boiler_service",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "When was your boiler or heating system last serviced?",
                    "variable": "last_service",
                    "options": [
                        {"label": "Within last year", "score": 0},
                        {"label": "1-2 years ago", "score": 5},
                        {"label": "Over 2 years ago", "score": 10},
                        {"label": "Never / Don't know", "score": 12}
                    ]
                },
            ),
            # === Q7: Appliances Running ===
            WorkflowNode(
                id="appliances_running",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are any gas appliances currently running?",
                    "variable": "gas_appliances_on",
                    "options": [
                        {"label": "Yes - Boiler is on", "score": 8},
                        {"label": "Yes - Multiple running", "score": 12},
                        {"label": "Turned everything off", "score": 0},
                        {"label": "No gas appliances", "score": 0}
                    ]
                },
            ),
            # === Risk Calculation ===
            WorkflowNode(
                id="calculate_co_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "risk_score = min(total_score, 100)",
                    "result_variable": "risk_score"
                },
            ),
            # === Decision Branching ===
            WorkflowNode(
                id="check_emergency",
                type=WorkflowNodeType.CONDITION,
                data={"expression": "risk_score >= 55"},
            ),
            WorkflowNode(
                id="emergency_dispatch",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "EMERGENCY: Evacuate immediately if you haven't already. Emergency services have been dispatched. Do not re-enter the property."
                },
            ),
            WorkflowNode(
                id="schedule_engineer_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "A gas safety engineer will be sent to inspect your property and check for CO sources."
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="check_evacuation", target="check_symptoms"),
            WorkflowEdge(source="check_symptoms", target="check_co_alarm"),
            WorkflowEdge(source="check_co_alarm", target="people_affected"),
            WorkflowEdge(source="people_affected", target="heating_type"),
            WorkflowEdge(source="heating_type", target="boiler_service"),
            WorkflowEdge(source="boiler_service", target="appliances_running"),
            WorkflowEdge(source="appliances_running", target="calculate_co_risk"),
            WorkflowEdge(source="calculate_co_risk", target="check_emergency"),
            WorkflowEdge(source="check_emergency", target="emergency_dispatch", condition="True"),
            WorkflowEdge(source="check_emergency", target="schedule_engineer_outcome", condition="False"),
        ],
    )


def _create_gas_supply_stopped_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 7: Gas Supply Completely Stopped
    System checks for area outage, valve position, and planned maintenance
    """
    workflow_id = f"{tenant_id}_{GAS_SUPPLY_STOPPED}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=GAS_SUPPLY_STOPPED,
        version=1,
        start_node="when_stopped",
        nodes=[
            # === Q1: When Stopped ===
            WorkflowNode(
                id="when_stopped",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "When did your gas supply stop?",
                    "variable": "outage_time",
                    "options": [
                        {"label": "Just now", "score": 15},
                        {"label": "Within last hour", "score": 10},
                        {"label": "Today", "score": 5},
                        {"label": "Yesterday or earlier", "score": 5}
                    ]
                },
            ),
            # === Q2: Prepayment Meter ===
            WorkflowNode(
                id="prepayment_meter",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Do you have a prepayment meter? Is there credit remaining?",
                    "variable": "prepayment_status",
                    "options": [
                        {"label": "Yes - Has credit", "score": 0},
                        {"label": "Yes - No credit / Low", "score": 0},
                        {"label": "No - Standard meter", "score": 5},
                        {"label": "Don't know", "score": 3}
                    ]
                },
            ),
            # === Q3: Planned Maintenance ===
            WorkflowNode(
                id="planned_maintenance",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you received any notice about planned gas maintenance?",
                    "variable": "maintenance_notice",
                    "options": [
                        {"label": "Yes - Received notice", "score": 0},
                        {"label": "No notice received", "score": 10},
                        {"label": "Not sure", "score": 5}
                    ]
                },
            ),
            # === Q4: Neighbors ===
            WorkflowNode(
                id="check_neighbors",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you checked if your neighbors also have no gas?",
                    "variable": "neighbors_affected",
                    "options": [
                        {"label": "Yes - They have no gas too", "score": 0},
                        {"label": "Yes - They have gas", "score": 10},
                        {"label": "Haven't checked", "score": 5}
                    ]
                },
            ),
            # === Area Outage Check ===
            WorkflowNode(
                id="check_area_outage",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "neighbors_affected == 'Yes - They have no gas too'"
                },
            ),
            WorkflowNode(
                id="area_outage_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": "Area-wide outage detected. This is likely planned maintenance or emergency work. We'll notify you when service is restored."
                },
            ),
            # === Q5: Gas Smell (non-area-outage path) ===
            WorkflowNode(
                id="gas_smell_supply",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you smell gas near the meter or pipework?",
                    "variable": "gas_smell_detected",
                    "options": [
                        {"label": "Yes - Strong smell", "score": 25},
                        {"label": "Yes - Faint smell", "score": 10},
                        {"label": "No smell", "score": 0}
                    ]
                },
            ),
            # === Gas Smell Emergency Check ===
            WorkflowNode(
                id="check_gas_smell_emergency",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "gas_smell_detected == 'Yes - Strong smell'"
                },
            ),
            WorkflowNode(
                id="gas_smell_emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "Gas smell detected with supply interruption - possible leak. Emergency services dispatched. Evacuate the area immediately."
                },
            ),
            # === Q6: Valve Photo ===
            WorkflowNode(
                id="valve_check_request",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you check your gas meter valve? Please upload a photo if possible.",
                    "variable": "valve_photo",
                    "input_type": "image",
                    "options": ["Skip"]
                },
            ),
            # === Q7: Valve Position ===
            WorkflowNode(
                id="valve_position",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is the valve handle parallel to the pipe (open) or perpendicular (closed)?",
                    "variable": "valve_position",
                    "options": [
                        {"label": "Parallel - Open", "score": 10},
                        {"label": "Perpendicular - Closed", "score": 0},
                        {"label": "Not sure", "score": 5}
                    ]
                },
            ),
            # === Valve Position Check ===
            WorkflowNode(
                id="check_valve_closed",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "valve_position == 'Perpendicular - Closed'"
                },
            ),
            WorkflowNode(
                id="valve_guidance_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": "Your meter valve is closed. Turn the handle parallel to the pipe to restore gas supply. If you need assistance, we can send a technician."
                },
            ),
            WorkflowNode(
                id="raise_ticket_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "No obvious cause found. An engineer will be scheduled to investigate your gas supply issue."
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="when_stopped", target="prepayment_meter"),
            WorkflowEdge(source="prepayment_meter", target="planned_maintenance"),
            WorkflowEdge(source="planned_maintenance", target="check_neighbors"),
            WorkflowEdge(source="check_neighbors", target="check_area_outage"),
            WorkflowEdge(source="check_area_outage", target="area_outage_outcome", condition="True"),
            WorkflowEdge(source="check_area_outage", target="gas_smell_supply", condition="False"),
            WorkflowEdge(source="gas_smell_supply", target="check_gas_smell_emergency"),
            WorkflowEdge(source="check_gas_smell_emergency", target="gas_smell_emergency_outcome", condition="True"),
            WorkflowEdge(source="check_gas_smell_emergency", target="valve_check_request", condition="False"),
            WorkflowEdge(source="valve_check_request", target="valve_position"),
            WorkflowEdge(source="valve_position", target="check_valve_closed"),
            WorkflowEdge(source="check_valve_closed", target="valve_guidance_outcome", condition="True"),
            WorkflowEdge(source="check_valve_closed", target="raise_ticket_outcome", condition="False"),
        ],
    )


def _create_meter_tampering_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 9: Meter Tampering / Fraud Suspicion
    OCR seal validation and consumption anomaly detection
    """
    workflow_id = f"{tenant_id}_{METER_TAMPERING}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=METER_TAMPERING,
        version=1,
        start_node="suspicion_reason",
        nodes=[
            WorkflowNode(
                id="suspicion_reason",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What makes you suspect meter tampering?",
                    "variable": "tampering_reason",
                    "options": [
                        {"label": "Broken seal", "score": 30},
                        {"label": "Missing label", "score": 20},
                        {"label": "Unusual consumption", "score": 15},
                        {"label": "Physical damage", "score": 30},
                        {"label": "Other", "score": 5}
                    ]
                },
            ),
            WorkflowNode(
                id="meter_photo_request",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Please upload a clear photo of your gas meter showing the seal and labels",
                    "variable": "meter_photo",
                    "input_type": "image",
                    "options": ["Skip"]
                },
            ),
            WorkflowNode(
                id="seal_condition",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What is the condition of the meter seal?",
                    "variable": "seal_status",
                    "options": [
                        {"label": "Intact", "score": 0},
                        {"label": "Broken", "score": 40},
                        {"label": "Missing", "score": 35},
                        {"label": "Tampered", "score": 45},
                        {"label": "Can't see clearly", "score": 10}
                    ]
                },
            ),
            WorkflowNode(
                id="consumption_pattern",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How has your gas consumption changed?",
                    "variable": "consumption_change",
                    "options": [
                        {"label": "Suddenly much higher", "score": 15},
                        {"label": "Suddenly much lower", "score": 25},
                        {"label": "Erratic/unpredictable", "score": 15},
                        {"label": "No change", "score": 0}
                    ]
                },
            ),
            WorkflowNode(
                id="household_changes",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have there been any changes in your household recently?",
                    "variable": "household_change",
                    "options": [
                        {"label": "More people living here", "score": 0},
                        {"label": "New appliances", "score": 0},
                        {"label": "Weather got colder", "score": 0},
                        {"label": "No changes", "score": 15}
                    ]
                },
            ),
            WorkflowNode(
                id="previous_issues",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you reported meter issues before?",
                    "variable": "previous_reports",
                    "options": [
                        {"label": "Yes - Multiple times", "score": 10},
                        {"label": "Yes - Once", "score": 5},
                        {"label": "No - First time", "score": 0}
                    ]
                },
            ),
            WorkflowNode(
                id="calculate_fraud_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": "fraud_probability = min(total_score, 100)",
                    "result_variable": "fraud_probability"
                },
            ),
            WorkflowNode(
                id="check_fraud_threshold",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "fraud_probability >= 60"
                },
            ),
            WorkflowNode(
                id="investigation_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "High fraud probability detected. An investigation team will inspect your meter. Tampering with gas meters is illegal and dangerous."
                },
            ),
            WorkflowNode(
                id="false_alarm_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": "No significant tampering indicators found. Consumption changes may be due to weather or usage patterns. We'll monitor your account."
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="suspicion_reason", target="meter_photo_request"),
            WorkflowEdge(source="meter_photo_request", target="seal_condition"),
            WorkflowEdge(source="seal_condition", target="consumption_pattern"),
            WorkflowEdge(source="consumption_pattern", target="household_changes"),
            WorkflowEdge(source="household_changes", target="previous_issues"),
            WorkflowEdge(source="previous_issues", target="calculate_fraud_risk"),
            WorkflowEdge(source="calculate_fraud_risk", target="check_fraud_threshold"),
            WorkflowEdge(source="check_fraud_threshold", target="investigation_outcome", condition="True"),
            WorkflowEdge(source="check_fraud_threshold", target="false_alarm_outcome", condition="False"),
        ],
    )



def _create_new_installation_not_working_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 10: New Installation - Gas Not Working
    Check installation status, valve position, and activation
    """
    workflow_id = f"{tenant_id}_{NEW_INSTALLATION_NOT_WORKING}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=NEW_INSTALLATION_NOT_WORKING,
        version=1,
        start_node="installation_date",
        nodes=[
            WorkflowNode(
                id="installation_date",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "When was your gas installation completed?",
                    "variable": "install_date",
                    "options": [
                        {"label": "Today", "score": 5},
                        {"label": "Within last week", "score": 10},
                        {"label": "1-2 weeks ago", "score": 15},
                        {"label": "More than 2 weeks ago", "score": 20}
                    ]
                },
            ),
            WorkflowNode(
                id="activation_request",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you submitted an activation request?",
                    "variable": "activation_requested",
                    "options": [
                        {"label": "Yes - Approved", "score": 15},
                        {"label": "Yes - Waiting for approval", "score": 5},
                        {"label": "No - Not yet", "score": 10},
                        {"label": "Not sure", "score": 10}
                    ]
                },
            ),
            WorkflowNode(
                id="meter_photo_request",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Please upload a photo of your gas meter and valve",
                    "variable": "meter_photo",
                    "input_type": "image",
                    "options": ["Skip"]
                },
            ),
            # === Q4: Gas Smell Check ===
            WorkflowNode(
                id="gas_smell_install",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Can you smell gas around the new installation?",
                    "variable": "smell_near_install",
                    "options": [
                        {"label": "Yes - Strong smell", "score": 20},
                        {"label": "Yes - Faint smell", "score": 10},
                        {"label": "No smell", "score": 0}
                    ]
                },
            ),
            # === Q5: Pressure Test ===
            WorkflowNode(
                id="pressure_test",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Did the installer perform a gas pressure test after installation?",
                    "variable": "pressure_test_done",
                    "options": [
                        {"label": "Yes - Passed", "score": 0},
                        {"label": "Yes - Had issues", "score": 10},
                        {"label": "No / Don't know", "score": 5}
                    ]
                },
            ),
            WorkflowNode(
                id="valve_position_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is the valve handle parallel to the pipe (ON) or perpendicular (OFF)?",
                    "variable": "valve_position",
                    "options": [
                        {"label": "Parallel - ON", "score": 10},
                        {"label": "Perpendicular - OFF", "score": 0},
                        {"label": "Not sure", "score": 5}
                    ]
                },
            ),
            WorkflowNode(
                id="installer_contact",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Did the installer inform you about the activation process?",
                    "variable": "installer_informed",
                    "options": [
                        {"label": "Yes - Said it's ready", "score": 15},
                        {"label": "Yes - Said wait for activation", "score": 5},
                        {"label": "No information given", "score": 10}
                    ]
                },
            ),
            WorkflowNode(
                id="check_valve_off",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "valve_position == 'Perpendicular - OFF'"
                },
            ),
            WorkflowNode(
                id="valve_off_guidance",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": "Your valve is OFF. Turn the handle parallel to the pipe to turn it ON. If you're unsure, contact your installer or we can send a technician."
                },
            ),
            WorkflowNode(
                id="check_activation_pending",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "activation_requested in ['Yes - Waiting for approval', 'No - Not yet']"
                },
            ),
            WorkflowNode(
                id="activation_pending_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": "Your activation is pending. This typically takes 24-48 hours after installation. We'll notify you when your meter is remotely activated."
                },
            ),
            WorkflowNode(
                id="raise_ticket_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "No technical reason found for the issue. An engineer will investigate your new installation."
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="installation_date", target="activation_request"),
            WorkflowEdge(source="activation_request", target="meter_photo_request"),
            WorkflowEdge(source="meter_photo_request", target="gas_smell_install"),
            WorkflowEdge(source="gas_smell_install", target="pressure_test"),
            WorkflowEdge(source="pressure_test", target="valve_position_check"),
            WorkflowEdge(source="valve_position_check", target="check_valve_off"),
            WorkflowEdge(source="check_valve_off", target="valve_off_guidance", condition="True"),
            WorkflowEdge(source="check_valve_off", target="installer_contact", condition="False"),
            WorkflowEdge(source="installer_contact", target="check_activation_pending"),
            WorkflowEdge(source="check_activation_pending", target="activation_pending_outcome", condition="True"),
            WorkflowEdge(source="check_activation_pending", target="raise_ticket_outcome", condition="False"),
        ],
    )


def _create_gas_leak_heavy_rain_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 12: Gas Leak Report During Heavy Rain
    Weather API check and soil gas diffusion analysis
    """
    workflow_id = f"{tenant_id}_{GAS_LEAK_HEAVY_RAIN}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=GAS_LEAK_HEAVY_RAIN,
        version=1,
        start_node="weather_timing",
        nodes=[
            WorkflowNode(
                id="weather_timing",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "When did you first notice the gas smell in relation to the rain?",
                    "variable": "smell_timing",
                    "options": [
                        {"label": "During heavy rain", "score": 10},
                        {"label": "Right after rain started", "score": 10},
                        {"label": "After rain stopped", "score": 20},
                        {"label": "Before rain started", "score": 30}
                    ]
                },
            ),
            WorkflowNode(
                id="smell_location_rain",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Where do you smell the gas?",
                    "variable": "rain_smell_location",
                    "options": [
                        {"label": "Outside near ground", "score": 10},
                        {"label": "Inside property", "score": 25},
                        {"label": "Near drainage", "score": 10},
                        {"label": "Multiple locations", "score": 20},
                        {"label": "Street/sidewalk", "score": 15}
                    ]
                },
            ),
            WorkflowNode(
                id="smell_strength_rain",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How strong is the gas smell?",
                    "variable": "rain_smell_strength",
                    "options": [
                        {"label": "Very strong", "score": 35},
                        {"label": "Moderate", "score": 20},
                        {"label": "Faint", "score": 5},
                        {"label": "Comes and goes", "score": 10}
                    ]
                },
            ),
            WorkflowNode(
                id="flooding_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is there any flooding or standing water in the area?",
                    "variable": "has_flooding",
                    "options": [
                        {"label": "Yes - Significant flooding", "score": 10},
                        {"label": "Yes - Some puddles", "score": 5},
                        {"label": "No flooding", "score": 5},
                        {"label": "Not sure", "score": 5}
                    ]
                },
            ),
            WorkflowNode(
                id="previous_rain_smell",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you noticed this smell during previous rain events?",
                    "variable": "recurring_rain_smell",
                    "options": [
                        {"label": "Yes - Every time it rains", "score": 5},
                        {"label": "Yes - Sometimes", "score": 10},
                        {"label": "No - First time", "score": 15},
                        {"label": "Can't remember", "score": 5}
                    ]
                },
            ),
            WorkflowNode(
                id="nearby_construction",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Has there been any recent construction or excavation near your property?",
                    "variable": "recent_construction",
                    "options": [
                        {"label": "Yes - Within last month", "score": 25},
                        {"label": "Yes - Within last 6 months", "score": 15},
                        {"label": "No recent work", "score": 0},
                        {"label": "Not aware", "score": 5}
                    ]
                },
            ),
            WorkflowNode(
                id="calculate_rain_risk",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": """
# Weather-related gas smell risk calculation
risk = total_score
diffusion_likely = False

# Timing pattern (soil diffusion indicator)
if smell_timing in ['During heavy rain', 'Right after rain started']:
    diffusion_likely = True

# Location (ground-level = diffusion)
if rain_smell_location in ['Outside near ground', 'Near drainage']:
    diffusion_likely = True

# Flooding (soil saturation)
if has_flooding == 'Yes - Significant flooding':
    diffusion_likely = True

# Recurring pattern (likely diffusion)
if recurring_rain_smell == 'Yes - Every time it rains':
    diffusion_likely = True

# Normalize
risk_score = min(risk, 100)

# Diffusion likelihood
if diffusion_likely and risk_score < 50:
    is_likely_diffusion = True
else:
    is_likely_diffusion = False
""",
                    "result_variable": "risk_score"
                },
            ),
            WorkflowNode(
                id="check_infrastructure_risk",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "risk_score >= 60 or recent_construction == 'Yes - Within last month'"
                },
            ),
            WorkflowNode(
                id="infrastructure_ticket_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "Infrastructure vulnerability confirmed. Heavy rain may have exposed or damaged underground pipes. An engineer will inspect the area."
                },
            ),
            WorkflowNode(
                id="check_diffusion_pattern",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "recurring_rain_smell == 'Yes - Every time it rains' and rain_smell_location in ['Outside near ground', 'Near drainage']"
                },
            ),
            WorkflowNode(
                id="diffusion_monitor_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "monitor",
                    "message": "Pattern consistent with soil gas diffusion during rain (wet soil changes gas movement). This is likely temporary. We'll monitor the situation. If smell persists after rain stops, please report again."
                },
            ),
            WorkflowNode(
                id="standard_inspection_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "Gas smell during rain requires inspection to rule out infrastructure issues. An engineer will check for pipe damage and soil conditions."
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="weather_timing", target="smell_location_rain"),
            WorkflowEdge(source="smell_location_rain", target="smell_strength_rain"),
            WorkflowEdge(source="smell_strength_rain", target="flooding_check"),
            WorkflowEdge(source="flooding_check", target="previous_rain_smell"),
            WorkflowEdge(source="previous_rain_smell", target="nearby_construction"),
            WorkflowEdge(source="nearby_construction", target="calculate_rain_risk"),
            WorkflowEdge(source="calculate_rain_risk", target="check_infrastructure_risk"),
            WorkflowEdge(source="check_infrastructure_risk", target="infrastructure_ticket_outcome", condition="True"),
            WorkflowEdge(source="check_infrastructure_risk", target="check_diffusion_pattern", condition="False"),
            WorkflowEdge(source="check_diffusion_pattern", target="diffusion_monitor_outcome", condition="True"),
            WorkflowEdge(source="check_diffusion_pattern", target="standard_inspection_outcome", condition="False"),
        ],
    )



def _create_smart_home_alert_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    USE CASE 14: Smart Home Integration Alert
    Sensor data validation with cross-verification
    """
    workflow_id = f"{tenant_id}_{SMART_HOME_ALERT}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=SMART_HOME_ALERT,
        version=1,
        start_node="sensor_data_check",
        nodes=[
            WorkflowNode(
                id="sensor_data_check",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": """
# Sensor data validation
# Placeholder - would come from smart home API

sensor_ppm = 50  # Gas concentration in parts per million
threshold_ppm = 100  # Safety threshold
meter_activity = True  # Is meter showing unusual activity
appliance_activity = False  # Are appliances currently running

# Check if high ppm
high_ppm = sensor_ppm >= threshold_ppm

# Calculate confidence (0-100 scale)
if high_ppm and meter_activity:
    sensor_confidence = 90  # High confidence - emergency
elif high_ppm and not meter_activity:
    sensor_confidence = 50  # Single sensor spike - needs confirmation
elif not high_ppm and meter_activity:
    sensor_confidence = 40  # Meter activity but low ppm
else:
    sensor_confidence = 20  # Low confidence
""",
                    "result_variable": "sensor_confidence"
                },
            ),
            WorkflowNode(
                id="check_emergency_threshold",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "high_ppm and meter_activity"
                },
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "emergency_dispatch",
                    "message": "High gas concentration detected with meter activity. Emergency services dispatched. Evacuate immediately."
                },
            ),
            WorkflowNode(
                id="user_confirmation",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Your gas sensor detected elevated levels. Do you smell gas or notice anything unusual?",
                    "variable": "user_confirms",
                    "options": [
                        {"label": "Yes - I smell gas", "score": 30},
                        {"label": "Yes - Unusual sounds", "score": 25},
                        {"label": "No - Everything seems normal", "score": 0},
                        {"label": "Not sure", "score": 10}
                    ]
                },
            ),
            WorkflowNode(
                id="check_area_alerts",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have your neighbors reported any gas issues recently?",
                    "variable": "area_alerts",
                    "options": [
                        {"label": "Yes", "score": 20},
                        {"label": "No", "score": 0},
                        {"label": "Don't know", "score": 5}
                    ]
                },
            ),
            WorkflowNode(
                id="appliance_check",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Are any gas appliances currently running?",
                    "variable": "appliances_running",
                    "options": [
                        {"label": "Yes - Stove", "score": 10},
                        {"label": "Yes - Heater", "score": 10},
                        {"label": "Yes - Multiple", "score": 15},
                        {"label": "No appliances on", "score": 5}
                    ]
                },
            ),
            # === Q4: Sensor Age ===
            WorkflowNode(
                id="sensor_age",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "How old is your gas detection sensor?",
                    "variable": "sensor_age",
                    "options": [
                        {"label": "Less than 2 years", "score": 0},
                        {"label": "2-5 years", "score": 3},
                        {"label": "Over 5 years", "score": 8},
                        {"label": "Don't know", "score": 5}
                    ]
                },
            ),
            # === Q5: False Alert History ===
            WorkflowNode(
                id="sensor_history",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Have you experienced false alerts from this sensor before?",
                    "variable": "false_alert_history",
                    "options": [
                        {"label": "Yes - Frequently", "score": 0},
                        {"label": "Yes - Once or twice", "score": 2},
                        {"label": "No - First time", "score": 8},
                        {"label": "New sensor", "score": 5}
                    ]
                },
            ),
            # === Q6: Occupant Symptoms ===
            WorkflowNode(
                id="occupant_symptoms",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is anyone in the home experiencing symptoms (headache, dizziness, nausea)?",
                    "variable": "occupant_symptoms",
                    "options": [
                        {"label": "Yes - Multiple people", "score": 20},
                        {"label": "Yes - One person", "score": 12},
                        {"label": "No symptoms", "score": 0},
                        {"label": "Home is empty", "score": 0}
                    ]
                },
            ),
            # === Q7: Sensor Last Test ===
            WorkflowNode(
                id="recent_sensor_test",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "When was the sensor last tested or calibrated?",
                    "variable": "sensor_last_test",
                    "options": [
                        {"label": "Within last month", "score": 0},
                        {"label": "Within last 6 months", "score": 2},
                        {"label": "Over 6 months ago", "score": 5},
                        {"label": "Never tested", "score": 8}
                    ]
                },
            ),
            WorkflowNode(
                id="cross_verification",
                type=WorkflowNodeType.CALCULATE,
                data={
                    "calculation": """
# Cross verification score (0-100 scale)
verification_score = sensor_confidence

# User confirmation adds weight
if user_confirms in ['Yes - I smell gas', 'Yes - Unusual sounds']:
    verification_score += 25
elif user_confirms == 'No - Everything seems normal':
    verification_score -= 20

# Area cluster alerts
if area_alerts == 'Yes':
    verification_score += 15

# Appliance activity correlation
if appliances_running in ['Yes - Multiple', 'Yes - Stove', 'Yes - Heater']:
    verification_score += 5

# Occupant symptoms strongly indicate real issue
if occupant_symptoms in ['Yes - Multiple people', 'Yes - One person']:
    verification_score += 20

# Sensor reliability factors
if false_alert_history == 'Yes - Frequently':
    verification_score -= 15
if sensor_age == 'Over 5 years':
    verification_score -= 5

# Normalize
final_verification = min(max(verification_score, 0), 100)
""",
                    "result_variable": "final_verification"
                },
            ),
            WorkflowNode(
                id="check_verification_threshold",
                type=WorkflowNodeType.CONDITION,
                data={
                    "expression": "final_verification >= 70"
                },
            ),
            WorkflowNode(
                id="schedule_inspection_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "schedule_engineer",
                    "message": "Sensor alert verified. An engineer will inspect your system and sensors."
                },
            ),
            WorkflowNode(
                id="false_alarm_outcome",
                type=WorkflowNodeType.DECISION,
                data={
                    "outcome": "close_with_guidance",
                    "message": "Likely sensor false alarm. We'll monitor your system. If you notice any issues, report immediately."
                },
            ),
        ],
        edges=[
            WorkflowEdge(source="sensor_data_check", target="check_emergency_threshold"),
            WorkflowEdge(source="check_emergency_threshold", target="emergency_outcome", condition="True"),
            WorkflowEdge(source="check_emergency_threshold", target="user_confirmation", condition="False"),
            WorkflowEdge(source="user_confirmation", target="check_area_alerts"),
            WorkflowEdge(source="check_area_alerts", target="appliance_check"),
            WorkflowEdge(source="appliance_check", target="sensor_age"),
            WorkflowEdge(source="sensor_age", target="sensor_history"),
            WorkflowEdge(source="sensor_history", target="occupant_symptoms"),
            WorkflowEdge(source="occupant_symptoms", target="recent_sensor_test"),
            WorkflowEdge(source="recent_sensor_test", target="cross_verification"),
            WorkflowEdge(source="cross_verification", target="check_verification_threshold"),
            WorkflowEdge(source="check_verification_threshold", target="schedule_inspection_outcome", condition="True"),
            WorkflowEdge(source="check_verification_threshold", target="false_alarm_outcome", condition="False"),
        ],
    )


def _create_underground_gas_leak_workflow(tenant_id: str) -> WorkflowDefinition:
    """
    UNDERGROUND GAS LEAK - Uses DATA_FETCH, SCRIPT, ALERT, ESCALATION, NOTIFICATION, TIMER.

    Flow:
    Q (evidence) > Q (ground damage) > Q (excavation nearby) > DATA_FETCH (pipeline data)
    > SCRIPT (risk calc) > CONDITION
      True  > ALERT > ESCALATION > NOTIFICATION > DECISION (emergency)
      False > TIMER > NOTIFICATION > DECISION (schedule_engineer)
    """
    workflow_id = f"{tenant_id}_{UNDERGROUND_GAS_LEAK}_v1"

    return WorkflowDefinition(
        workflow_id=workflow_id,
        tenant_id=tenant_id,
        use_case=UNDERGROUND_GAS_LEAK,
        version=1,
        start_node="evidence_type",
        nodes=[
            # === Questions ===
            WorkflowNode(
                id="evidence_type",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "What evidence of an underground gas leak have you observed?",
                    "variable": "evidence_type",
                    "options": [
                        {"label": "Strong gas smell from ground", "score": 30},
                        {"label": "Bubbling in standing water", "score": 25},
                        {"label": "Dead vegetation patch", "score": 20},
                        {"label": "Hissing from ground", "score": 35},
                    ],
                },
            ),
            WorkflowNode(
                id="ground_damage",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Is there visible damage to the ground surface?",
                    "variable": "ground_damage",
                    "options": [
                        {"label": "Sinkhole or collapse", "score": 30},
                        {"label": "Cracks in pavement", "score": 15},
                        {"label": "Frost heave or soil displacement", "score": 10},
                        {"label": "No visible damage", "score": 0},
                    ],
                },
            ),
            WorkflowNode(
                id="nearby_excavation",
                type=WorkflowNodeType.QUESTION,
                data={
                    "question": "Has there been recent excavation or construction nearby?",
                    "variable": "nearby_excavation",
                    "options": [
                        {"label": "Yes - Active construction", "score": 20},
                        {"label": "Yes - Recently completed", "score": 10},
                        {"label": "No", "score": 0},
                        {"label": "Not sure", "score": 5},
                    ],
                },
            ),

            # === DATA_FETCH: Pull pipeline data for this location ===
            WorkflowNode(
                id="fetch_pipeline_data",
                type=WorkflowNodeType.DATA_FETCH,
                data={
                    "source_name": "pipeline_registry",
                    "endpoint": "/api/v1/pipeline/nearby",
                    "query_params": "radius=500m&type=gas",
                    "output_variable": "pipeline_data",
                },
            ),

            # === SCRIPT: Calculate composite risk score ===
            WorkflowNode(
                id="calc_risk",
                type=WorkflowNodeType.SCRIPT,
                data={
                    "script_code": "base_risk = min(total_score, 100)\npipeline_age_factor = 10\nrisk_score = min(base_risk + pipeline_age_factor, 100)",
                    "script_language": "python",
                    "output_variables": "risk_score",
                },
            ),

            # === CONDITION: High risk? ===
            WorkflowNode(
                id="check_risk",
                type=WorkflowNodeType.CONDITION,
                data={"expression": "risk_score >= 70"},
            ),

            # === HIGH RISK PATH ===
            WorkflowNode(
                id="critical_alert",
                type=WorkflowNodeType.ALERT,
                data={
                    "alert_message": "Underground gas leak confirmed - critical risk",
                    "severity": "critical",
                    "alert_type": "underground_leak",
                },
            ),
            WorkflowNode(
                id="escalate_field_mgr",
                type=WorkflowNodeType.ESCALATION,
                data={
                    "escalation_reason": "Underground leak requires field manager authorization for excavation",
                    "escalation_level": 3,
                    "target_role": "field_manager",
                },
            ),
            WorkflowNode(
                id="notify_emergency",
                type=WorkflowNodeType.NOTIFICATION,
                data={
                    "notification_message": "Emergency crew dispatched for underground gas leak",
                    "channel": "sms",
                    "recipient": "emergency_response_team",
                },
            ),
            WorkflowNode(
                id="emergency_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "emergency_dispatch"},
            ),

            # === LOW RISK PATH ===
            WorkflowNode(
                id="monitoring_timer",
                type=WorkflowNodeType.TIMER,
                data={
                    "timer_label": "Monitor area for 24 hours",
                    "duration": 86400,
                    "timeout_action": "continue",
                },
            ),
            WorkflowNode(
                id="notify_inspection",
                type=WorkflowNodeType.NOTIFICATION,
                data={
                    "notification_message": "Schedule underground pipeline inspection",
                    "channel": "email",
                    "recipient": "pipeline_inspection_team",
                },
            ),
            WorkflowNode(
                id="schedule_outcome",
                type=WorkflowNodeType.DECISION,
                data={"outcome": "schedule_engineer"},
            ),
        ],
        edges=[
            # Questions flow
            WorkflowEdge(source="evidence_type", target="ground_damage"),
            WorkflowEdge(source="ground_damage", target="nearby_excavation"),
            WorkflowEdge(source="nearby_excavation", target="fetch_pipeline_data"),
            # Data fetch + script
            WorkflowEdge(source="fetch_pipeline_data", target="calc_risk"),
            WorkflowEdge(source="calc_risk", target="check_risk"),
            # High risk path
            WorkflowEdge(source="check_risk", target="critical_alert", condition="True"),
            WorkflowEdge(source="critical_alert", target="escalate_field_mgr"),
            WorkflowEdge(source="escalate_field_mgr", target="notify_emergency"),
            WorkflowEdge(source="notify_emergency", target="emergency_outcome"),
            # Low risk path
            WorkflowEdge(source="check_risk", target="monitoring_timer", condition="False"),
            WorkflowEdge(source="monitoring_timer", target="notify_inspection"),
            WorkflowEdge(source="notify_inspection", target="schedule_outcome"),
        ],
    )


