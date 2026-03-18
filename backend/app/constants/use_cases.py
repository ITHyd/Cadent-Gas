"""
Centralized use case constants - Single Source of Truth
Based on Cadent CO Data 2024-25 and CO Process Improvement analysis.
All components must use these constants for use_case identification.
"""

# ============================================================
# CO Process Improvement use cases (data-driven from CO Data 2024-25)
# These map to the "What Was Reported" categories in the real data:
#   CO Alarm Sounding, Smoke Alarm Sounding, Orange Flames,
#   Sooting/Scarring, Symptoms, Blood Test, Excessive Condensation,
#   Fumes (See), Fatality
# ============================================================

# Primary CO alarm workflow - enhanced with manufacturer-specific triage
# Targets: 32.7% battery failures + 23.2% active alarm no CO = 55.9% of all visits
CO_ALARM = "co_alarm"

# CO symptoms-based investigation (headache, dizziness, nausea, flu-like)
SUSPECTED_CO_LEAK = "suspected_co_leak"

# CO signs - Orange/yellow flames on gas appliances
CO_ORANGE_FLAMES = "co_orange_flames"

# CO signs - Sooting or scarring on/around gas appliances
CO_SOOTING_SCARRING = "co_sooting_scarring"

# CO signs - Excessive condensation on windows/walls near appliances
CO_EXCESSIVE_CONDENSATION = "co_excessive_condensation"

# CO signs - Visible fumes from gas appliances
CO_VISIBLE_FUMES = "co_visible_fumes"

# CO blood test result reported (confirmed CO exposure)
CO_BLOOD_TEST = "co_blood_test"

# CO-related fatality reported (immediate emergency protocol)
CO_FATALITY = "co_fatality"

# Smoke alarm sounding (differentiate from CO alarm - common confusion)
CO_SMOKE_ALARM = "co_smoke_alarm"

# Core gas emergency use cases (retained - common gas incidents)
GAS_SMELL = "gas_smell"
HISSING_SOUND = "hissing_sound"


# All available use cases
ALL_USE_CASES = [
    CO_ALARM,
    SUSPECTED_CO_LEAK,
    CO_ORANGE_FLAMES,
    CO_SOOTING_SCARRING,
    CO_EXCESSIVE_CONDENSATION,
    CO_VISIBLE_FUMES,
    CO_BLOOD_TEST,
    CO_FATALITY,
    CO_SMOKE_ALARM,
    GAS_SMELL,
    HISSING_SOUND,
]

# Use case descriptions for classifier
USE_CASE_DESCRIPTIONS = {
    CO_ALARM: "CO alarm or carbon monoxide detector sounding, beeping, chirping, or flashing. Includes battery failures and genuine CO detection alerts.",
    SUSPECTED_CO_LEAK: "Suspected carbon monoxide leak based on physical symptoms: headache, dizziness, nausea, tiredness, flu-like symptoms, shortness of breath. Symptoms may improve when leaving the property.",
    CO_ORANGE_FLAMES: "Orange, yellow, or lazy flames on gas appliances such as hob, cooker, boiler, or gas fire. Indicates incomplete combustion and potential CO production.",
    CO_SOOTING_SCARRING: "Sooting, black marks, or scarring on or around gas appliances, walls, or ceilings near gas equipment. Indicates incomplete combustion.",
    CO_EXCESSIVE_CONDENSATION: "Excessive condensation on windows, walls, or surfaces near gas appliances. Can indicate blocked flue or poor ventilation allowing CO buildup.",
    CO_VISIBLE_FUMES: "Visible fumes, smoke, or haze coming from a gas appliance. Indicates combustion problems and potential CO release.",
    CO_BLOOD_TEST: "CO blood test (carboxyhemoglobin) result reported positive. Confirmed carbon monoxide exposure requiring immediate investigation.",
    CO_FATALITY: "Death reported potentially linked to carbon monoxide exposure. Immediate emergency protocol required.",
    CO_SMOKE_ALARM: "Smoke alarm sounding - not a CO alarm. Common confusion between smoke detectors and CO detectors that needs differentiation.",
    GAS_SMELL: "User reports smelling gas (mercaptan/rotten egg odour) inside or outside their property.",
    HISSING_SOUND: "Hissing or whistling sound near gas line, meter, or appliance indicating possible gas leak.",
}

# CO alarm manufacturers supported for triage (from CO ALarms-Mac.xlsx)
CO_ALARM_MANUFACTURERS = [
    "Kidde",
    "FireAngel",
    "Aico",
    "Firehawk",
    "X-Sense",
    "Honeywell",
    "Google Nest",
    "Netatmo",
    "Cavius",
]

# Default workflows that must exist for each tenant
# Order matters: workflows appear in this order in the UI
DEFAULT_WORKFLOWS = [
    CO_ALARM,
    SUSPECTED_CO_LEAK,
    CO_ORANGE_FLAMES,
    CO_SOOTING_SCARRING,
    CO_EXCESSIVE_CONDENSATION,
    CO_VISIBLE_FUMES,
    CO_BLOOD_TEST,
    CO_FATALITY,
    CO_SMOKE_ALARM,
    GAS_SMELL,
    HISSING_SOUND,
]
