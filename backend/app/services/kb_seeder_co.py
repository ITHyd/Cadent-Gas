"""
CO Knowledge Base entries derived from Cadent CO Data 2024-25.

True incidents: Real CO emergencies from field engineer reports.
False incidents: Common CO false alarms (battery failures, faulty detectors, etc.)
Manufacturer data: Alarm indicator patterns from official product manuals.

Data sources:
Data source: 50,957 workorders from CO Data 2024-25.xlsx across 5 sheets:
  - Extracted Data: Summary of all 17 outcome categories
  - No CO Evident: 11,799 active alarm records (engineer found no CO)
  - Battery Fail No CO Evident: 16,656 battery failure records
  - Advice Only: 11,425 advice/minor records
  - Lists: Dropdown values (Reported By, What Was Reported, Alarm Detail)
- FireAngel product manuals: W2-CO-10X, FA3313/3322/3328/3820, FA6812/6813, FA6829S

Key statistics:
  - 78.3% false alarm rate (39,880 unnecessary visits)
  - 17.6% CO evident/suspected (8,970 real incidents)
  - 32.7% battery failures alone (16,656 visits)
  - 23.2% active alarm no CO (11,799 visits)
  - 22.4% advice only (11,425 visits)

Real CO breakdown:
  - 3,557 active alarm suspect CO
  - 3,383 active alarm CO evident
  - 1,089 suspect fumes
  - 588 battery fail but CO suspected
  - 331 battery fail but CO evident
"""
from datetime import datetime


# ============================================================
# MANUFACTURER TRIAGE DATA
# Structured alarm indicator patterns from official product manuals.
# Used by the CO alarm workflow to determine battery vs CO vs fault.
# ============================================================

FIREANGEL_ALARM_DATA = {
    "manufacturer": "FireAngel",
    "support_phone": "0330 094 5830",
    "support_email": "technicalsupport@fireangeltech.com",
    "website": "www.fireangeltech.com",
    "models": {
        "W2-CO-10X": {
            "name": "Wi-Safe 2 CO Alarm 10 Year Life",
            "battery": "sealed_10_year",
            "sensor_life_years": 10,
            "warranty_years": 5,
            "features": ["wi_safe_2_wireless_interlink", "electrochemical_sensor", "sleep_easy"],
            "indicators": {
                "normal": {
                    "green_led": "flashes once per minute",
                    "red_led": "off",
                    "amber_led": "off",
                    "sound": "none",
                    "meaning": "Normal operation - alarm is working correctly",
                    "action": "No action needed. Test weekly.",
                },
                "co_detected": {
                    "green_led": "off",
                    "red_led": "flashes once every 5 seconds",
                    "amber_led": "off",
                    "sound": "4 loud chirps repeated continuously",
                    "meaning": "CARBON MONOXIDE DETECTED - EMERGENCY",
                    "action": "Evacuate immediately. Open doors/windows. Call 0800 111 999. Do not re-enter.",
                },
                "low_battery_end_of_life": {
                    "green_led": "off",
                    "red_led": "off",
                    "amber_led": "flashes once per minute",
                    "sound": "chirps once per minute AT SAME TIME as amber LED",
                    "meaning": "Low battery or end of sensor life - NOT a CO detection",
                    "action": "Replace alarm within 30 days. Use Sleep Easy to silence for 8 hours overnight.",
                },
                "sensor_fault": {
                    "green_led": "off",
                    "red_led": "off",
                    "amber_led": "double flashes",
                    "sound": "chirps at DIFFERENT TIME to amber LED flashes",
                    "meaning": "Sensor fault - alarm is not reliable",
                    "action": "Replace alarm immediately. Sensor cannot detect CO.",
                },
            },
            "co_thresholds": {
                "50ppm": "alarm sounds in 60-90 minutes",
                "100ppm": "alarm sounds in 10-40 minutes",
                "300ppm": "alarm sounds within 3 minutes",
            },
        },
        "FA6813": {
            "name": "CO Alarm with Replaceable Batteries",
            "battery": "replaceable_AA",
            "sensor_life_years": 7,
            "warranty_years": 3,
            "features": ["replaceable_batteries", "electrochemical_sensor"],
            "indicators": {
                "normal": {
                    "green_led": "heartbeat flash",
                    "red_led": "off",
                    "amber_led": "off",
                    "sound": "none",
                    "meaning": "Normal operation",
                    "action": "No action needed. Test weekly. Replace batteries when indicated.",
                },
                "co_detected": {
                    "green_led": "off",
                    "red_led": "flashing rapidly",
                    "amber_led": "off",
                    "sound": "4 loud chirps repeated",
                    "meaning": "CARBON MONOXIDE DETECTED - EMERGENCY",
                    "action": "Evacuate immediately. Open doors/windows. Call 0800 111 999.",
                },
                "low_battery": {
                    "green_led": "off",
                    "red_led": "off",
                    "amber_led": "flashing",
                    "sound": "intermittent chirp",
                    "meaning": "Batteries need replacing - NOT a CO detection",
                    "action": "Replace AA batteries immediately. Alarm cannot protect you without power.",
                },
            },
            "co_thresholds": {
                "50ppm": "alarm sounds in 60-90 minutes",
                "100ppm": "alarm sounds in 10-40 minutes",
                "300ppm": "alarm sounds within 3 minutes",
            },
        },
        "FA6829S": {
            "name": "CO Alarm with Alarm Memory",
            "battery": "sealed_10_year",
            "sensor_life_years": 10,
            "warranty_years": 5,
            "features": ["alarm_memory", "electrochemical_sensor"],
            "indicators": {
                "normal": {
                    "green_led": "flashes periodically",
                    "red_led": "off",
                    "amber_led": "off",
                    "sound": "none",
                    "meaning": "Normal operation",
                    "action": "No action needed. Test weekly.",
                },
                "co_detected": {
                    "green_led": "off",
                    "red_led": "flashing",
                    "amber_led": "off",
                    "sound": "4 chirps repeated (85dB at 3m)",
                    "meaning": "CARBON MONOXIDE DETECTED - EMERGENCY",
                    "action": "Evacuate immediately. Open doors/windows. Call 0800 111 999.",
                },
                "alarm_in_absence": {
                    "green_led": "off",
                    "red_led": "flashes once per minute",
                    "amber_led": "off",
                    "sound": "chirps once per minute",
                    "meaning": "CO was detected while you were away - alarm memory activated",
                    "action": "Do NOT ignore. Ventilate property. Call 0800 111 999. Press test button to clear memory after investigation.",
                },
                "low_battery_end_of_life": {
                    "green_led": "off",
                    "red_led": "off",
                    "amber_led": "flashing",
                    "sound": "intermittent chirp",
                    "meaning": "Low battery or end of sensor life - NOT a CO detection",
                    "action": "Replace alarm. Sealed battery cannot be changed.",
                },
            },
            "co_thresholds": {
                "50ppm": "alarm sounds in 60-90 minutes",
                "100ppm": "alarm sounds in 10-40 minutes",
                "300ppm": "alarm sounds within 3 minutes",
            },
        },
        "FA3313_FA3322_FA3328_FA3820": {
            "name": "Standard CO Alarm Range",
            "battery": "varies_by_model",
            "sensor_life_years": 7,
            "warranty_years": 5,
            "features": ["electrochemical_sensor"],
            "indicators": {
                "co_detected": {
                    "red_led": "flashing",
                    "sound": "loud repeated chirps",
                    "meaning": "CARBON MONOXIDE DETECTED - EMERGENCY",
                    "action": "Evacuate immediately. Call 0800 111 999.",
                },
                "low_battery": {
                    "amber_led": "flashing",
                    "sound": "intermittent chirp every 30-60 seconds",
                    "meaning": "Low battery - NOT a CO detection",
                    "action": "Replace batteries or alarm unit.",
                },
            },
            "co_thresholds": {
                "50ppm": "alarm sounds in 60-90 minutes",
                "100ppm": "alarm sounds in 10-40 minutes",
                "300ppm": "alarm sounds within 3 minutes",
            },
        },
    },
    "triage_rules": {
        "co_detected_pattern": {
            "description": "Red LED flashing + 4 loud chirps repeated continuously",
            "outcome": "emergency_dispatch",
            "confidence": 0.95,
        },
        "low_battery_pattern": {
            "description": "Amber LED flashing + intermittent chirp at SAME time as LED",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
            "guidance": "Replace alarm batteries or unit. No engineer visit needed.",
        },
        "sensor_fault_pattern": {
            "description": "Amber LED double-flash + chirp at DIFFERENT time to LED",
            "outcome": "close_with_guidance",
            "confidence": 0.88,
            "guidance": "Replace alarm immediately - sensor unreliable.",
        },
        "alarm_in_absence_pattern": {
            "description": "Red LED flashes once/min + chirps once/min (FA6829S only)",
            "outcome": "schedule_engineer",
            "confidence": 0.85,
            "guidance": "CO was detected while away. Ventilate. Call gas emergency.",
        },
    },
    "common_false_alarm_causes": [
        "Low battery chirping mistaken for CO alarm",
        "End-of-life chirping on expired alarm (>7-10 years old)",
        "Sensor fault double-chirp confused with CO detection",
        "Paint fumes / aerosols / cleaning chemicals triggering sensor",
        "Steam / high humidity causing false readings",
        "Alarm in absence memory chirp mistaken for active CO alarm",
    ],
    "sleep_easy_feature": {
        "available_on": ["W2-CO-10X"],
        "description": "Silences low battery chirp for 8 hours by pressing test button. Can be repeated up to 10 times. Alarm still detects CO during this period. Must replace alarm within 30 days.",
    },
}


FIREHAWK_ALARM_DATA = {
    "manufacturer": "Firehawk",
    "website": "www.firehawksafety.co.uk",
    "models": {
        "CO10-RF": {
            "name": "CO Alarm 10 Year with RF-Link",
            "battery": "sealed_10_year",
            "sensor_life_years": 10,
            "warranty_years": 7,
            "features": ["rf_link_wireless", "alarm_silence", "data_scan_app"],
        },
        "CO7B-10Y_W": {
            "name": "CO Alarm 10 Year Wireless",
            "battery": "sealed_10_year",
            "sensor_life_years": 10,
            "warranty_years": 7,
            "features": ["wireless_interlink"],
        },
        "CO7BD": {
            "name": "CO Alarm 7 Year with LCD Display",
            "battery": "sealed_7_year",
            "sensor_life_years": 7,
            "warranty_years": 7,
            "features": ["lcd_display_ppm_peak_cohb"],
        },
        "CO7B": {
            "name": "CO Alarm 7 Year",
            "battery": "sealed_7_year",
            "sensor_life_years": 7,
            "warranty_years": 7,
            "features": [],
        },
        "CO5B": {
            "name": "CO Alarm 5 Year",
            "battery": "sealed_5_year",
            "sensor_life_years": 5,
            "warranty_years": 5,
            "features": [],
        },
    },
    "indicators": {
        "co_detected": {
            "led": "Red LED",
            "sound": "Repeating series of 4 beeps",
            "meaning": "CARBON MONOXIDE DETECTED - EMERGENCY",
            "action": "Evacuate immediately. Call 0800 111 999.",
        },
        "normal": {
            "led": "Green LED flashes once every minute",
            "sound": "Silent",
            "meaning": "Normal operation",
            "action": "No action needed. Test weekly.",
        },
        "low_battery": {
            "led": "Not specified",
            "sound": "1 beep every minute",
            "meaning": "Low battery - NOT CO detection",
            "action": "Replace entire alarm (sealed battery).",
        },
        "fault": {
            "led": "Red and Yellow LEDs",
            "sound": "2 beeps every minute",
            "meaning": "Sensor or hardware fault",
            "action": "Replace alarm immediately.",
        },
        "end_of_life": {
            "led": "Not specified",
            "sound": "3 beeps every minute",
            "meaning": "Alarm has reached end of life",
            "action": "Replace alarm immediately.",
        },
    },
    "co_thresholds": {
        "30ppm": "no alarm before 120 minutes",
        "50ppm": "alarm sounds in 60-90 minutes",
        "100ppm": "alarm sounds in 10-40 minutes",
        "300ppm": "alarm sounds within 3 minutes",
    },
    "triage_rules": {
        "co_detected_pattern": {
            "description": "Red LED + 4 beeps repeating",
            "outcome": "emergency_dispatch",
            "confidence": 0.95,
        },
        "low_battery_pattern": {
            "description": "1 beep every minute, no red light",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
        },
        "fault_pattern": {
            "description": "Red + Yellow LEDs + 2 beeps every minute",
            "outcome": "close_with_guidance",
            "confidence": 0.88,
        },
        "end_of_life_pattern": {
            "description": "3 beeps every minute",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
        },
    },
}


AICO_ALARM_DATA = {
    "manufacturer": "Aico",
    "support_phone": "01onal 691 664100",
    "website": "www.aico.co.uk",
    "models": {
        "Ei208": {
            "name": "CO Alarm Sealed Battery (10 Year Life)",
            "battery": "sealed_lithium",
            "sensor_life_years": 10,
            "warranty_years": 5,
            "features": ["audiolink", "alarm_memory", "pre_alarm", "hush"],
        },
        "Ei208WRF": {
            "name": "CO Alarm with RadioLINK Wireless",
            "battery": "sealed_lithium",
            "sensor_life_years": 10,
            "warranty_years": 5,
            "features": ["radiolink_wireless", "audiolink", "alarm_memory", "pre_alarm"],
        },
        "Ei208DW": {
            "name": "CO Alarm with LCD Display",
            "battery": "sealed_lithium",
            "sensor_life_years": 10,
            "warranty_years": 5,
            "features": ["lcd_display", "audiolink", "alarm_memory", "pre_alarm"],
        },
        "Ei207": {
            "name": "CO Alarm Replaceable Battery",
            "battery": "replaceable_AAA",
            "sensor_life_years": 10,
            "warranty_years": 5,
            "features": ["alarm_memory"],
        },
        "Ei3030": {
            "name": "Multi-Sensor Fire & CO Alarm (Mains)",
            "battery": "mains_with_rechargeable_backup",
            "sensor_life_years": 10,
            "warranty_years": 10,
            "features": ["multi_sensor_fire_heat_co", "audiolink_plus", "alarm_memory", "smartlink"],
        },
    },
    "indicators": {
        "co_detected": {
            "led": "Red LED flashing (rate increases with ppm)",
            "sound": "3 beep pulses + pause, repeating",
            "meaning": "CARBON MONOXIDE DETECTED - EMERGENCY",
            "action": "Evacuate immediately. Call 0800 111 999.",
        },
        "normal": {
            "led": "Green LED 1 flash per minute",
            "sound": "Silent",
            "meaning": "Normal standby operation",
            "action": "No action needed. Test weekly.",
        },
        "low_battery": {
            "yellow_led": "1 flash every 48 seconds",
            "sound": "1 beep every 48 seconds",
            "meaning": "Low battery - NOT CO detection",
            "action": "Ei207: replace AAA batteries. Ei208: replace entire alarm.",
        },
        "sensor_fault": {
            "yellow_led": "2 flashes every 48 seconds",
            "sound": "2 beeps every 48 seconds",
            "meaning": "Sensor malfunction - alarm unreliable",
            "action": "Replace alarm immediately.",
        },
        "end_of_life": {
            "yellow_led": "3 flashes every 48 seconds",
            "sound": "3 beeps every 48 seconds",
            "meaning": "Alarm expired - sensor no longer reliable",
            "action": "Replace alarm. Can silence for 24hrs (max 30 days).",
        },
    },
    "co_thresholds": {
        "43ppm": "alarm sounds in 60-90 minutes",
        "80ppm": "alarm sounds in 10-40 minutes",
        "150ppm": "alarm sounds within 2 minutes",
    },
    "triage_rules": {
        "co_detected_pattern": {
            "description": "Red LED flashing + 3 beep pulses repeating",
            "outcome": "emergency_dispatch",
            "confidence": 0.95,
        },
        "low_battery_pattern": {
            "description": "Yellow LED 1 flash + 1 beep every 48 seconds",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
        },
        "sensor_fault_pattern": {
            "description": "Yellow LED 2 flashes + 2 beeps every 48 seconds",
            "outcome": "close_with_guidance",
            "confidence": 0.88,
        },
        "end_of_life_pattern": {
            "description": "Yellow LED 3 flashes + 3 beeps every 48 seconds",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
        },
    },
}


KIDDE_ALARM_DATA = {
    "manufacturer": "Kidde",
    "support_phone": "0800 917 0722",
    "website": "www.kidde.com",
    "models": {
        "2030-DCR": {
            "name": "Battery CO Alarm",
            "battery": "replaceable_AA",
            "sensor_life_years": 10,
            "warranty_years": 3,
            "features": ["alarm_memory_14day", "alarm_reset"],
        },
        "K10LLCO": {
            "name": "10-Year Sealed Lithium CO Alarm",
            "battery": "sealed_lithium_10_year",
            "sensor_life_years": 10,
            "warranty_years": 10,
            "features": ["alarm_memory"],
        },
        "K10LLDCO": {
            "name": "10-Year Sealed Lithium CO Alarm with Digital Display",
            "battery": "sealed_lithium_10_year",
            "sensor_life_years": 10,
            "warranty_years": 10,
            "features": ["lcd_display_ppm_peak", "alarm_memory"],
        },
        "K10SCO": {
            "name": "Combination Smoke + CO Alarm with Voice Warning",
            "battery": "replaceable_AA",
            "sensor_life_years": 10,
            "warranty_years": 10,
            "features": ["voice_warning", "dual_sensor_smoke_co", "hush"],
        },
        "K5CO": {
            "name": "Lightweight Battery CO Alarm",
            "battery": "replaceable_AA",
            "sensor_life_years": 10,
            "warranty_years": 7,
            "features": [],
        },
        "K7CO": {
            "name": "Battery CO Alarm (Boat/Caravan Approved)",
            "battery": "replaceable_AA",
            "sensor_life_years": 10,
            "warranty_years": 10,
            "features": ["boat_caravan_approved"],
        },
        "K4MCO": {
            "name": "230V Mains CO Alarm with Battery Backup",
            "battery": "mains_with_rechargeable_backup_72hr",
            "sensor_life_years": 10,
            "warranty_years": 10,
            "features": ["mains_powered", "battery_backup"],
        },
    },
    "indicators": {
        "co_detected": {
            "led": "Red LED blinks in sync with beeps",
            "sound": "4 quick beeps every 5 seconds",
            "meaning": "CARBON MONOXIDE DETECTED - EMERGENCY",
            "action": "Evacuate immediately. Call 0800 111 999.",
        },
        "normal": {
            "led": "Green LED blinks every ~60 seconds",
            "sound": "Silent",
            "meaning": "Normal standby operation",
            "action": "No action needed. Test weekly.",
        },
        "alarm_memory": {
            "led": "Red LED blinks once every 60 seconds",
            "sound": "Silent",
            "meaning": "CO detected (>=100ppm) in last 14 days",
            "action": "Ventilate. Call gas emergency. Press button to clear.",
        },
        "low_battery": {
            "led": "Amber LED blinks every 60 seconds",
            "sound": "Chirp every 60 seconds",
            "meaning": "Low battery - NOT CO detection",
            "action": "Replace AA batteries or entire alarm (sealed models).",
        },
        "end_of_life": {
            "led": "Amber LED blinks 2x every 60 seconds",
            "sound": "2 chirps every 60 seconds",
            "meaning": "Alarm has reached 10-year end of life",
            "action": "Replace entire alarm unit.",
        },
        "co_fault": {
            "led": "Amber LED blinks 5x every 30 seconds",
            "sound": "Chirp every 30 seconds",
            "meaning": "CO sensor fault - alarm unreliable",
            "action": "Clean alarm and press test button. Replace if fault persists.",
        },
    },
    "co_thresholds": {
        "50ppm": "alarm sounds in 60-90 minutes",
        "100ppm": "alarm sounds in 10-40 minutes",
        "300ppm": "alarm sounds within 3 minutes",
    },
    "triage_rules": {
        "co_detected_pattern": {
            "description": "Red LED + 4 quick beeps every 5 seconds",
            "outcome": "emergency_dispatch",
            "confidence": 0.95,
        },
        "alarm_memory_pattern": {
            "description": "Red LED once/60s, no sound (CO in last 14 days)",
            "outcome": "schedule_engineer",
            "confidence": 0.85,
        },
        "low_battery_pattern": {
            "description": "Amber LED 1x/60s + chirp every 60s",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
        },
        "end_of_life_pattern": {
            "description": "Amber LED 2x/60s + 2 chirps every 60s",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
        },
        "sensor_fault_pattern": {
            "description": "Amber LED 5x/30s + chirps",
            "outcome": "close_with_guidance",
            "confidence": 0.88,
        },
    },
}


XSENSE_ALARM_DATA = {
    "manufacturer": "X-Sense",
    "support_email": "support@x-sense.com",
    "website": "www.x-sense.com",
    "models": {
        "SC07-WX": {
            "name": "Wi-Fi Combination Smoke and CO Alarm",
            "battery": "replaceable_CR123A",
            "sensor_life_years": 10,
            "features": ["wifi", "lcd_display", "app_notifications", "dual_sensor_smoke_co", "silence_mode"],
        },
        "SC07-W": {
            "name": "Wi-Fi Combination Smoke and CO Alarm",
            "battery": "replaceable_CR123A",
            "sensor_life_years": 10,
            "features": ["wifi", "app_notifications", "dual_sensor_smoke_co"],
        },
        "XC04-WX": {
            "name": "Wi-Fi CO Alarm with LCD Display",
            "battery": "sealed",
            "sensor_life_years": 10,
            "features": ["wifi", "lcd_display", "app_notifications"],
        },
        "XC01-M": {
            "name": "CO Alarm",
            "battery": "sealed",
            "sensor_life_years": 10,
            "features": [],
        },
        "XC01-R": {
            "name": "CO Alarm with Replaceable Battery",
            "battery": "replaceable",
            "sensor_life_years": 10,
            "features": [],
        },
    },
    "indicators": {
        "co_detected": {
            "led": "Red LED flashing",
            "sound": "4 short beeps every 5.8 seconds",
            "meaning": "CARBON MONOXIDE DETECTED - EMERGENCY",
            "action": "Evacuate immediately. Call 0800 111 999. Cannot silence if >300ppm.",
        },
        "normal": {
            "led": "Green LED flashing",
            "sound": "Silent",
            "meaning": "Normal standby",
            "action": "No action needed. Test weekly.",
        },
        "low_battery": {
            "led": "Yellow LED flash every 60 seconds",
            "sound": "1 beep every 60 seconds",
            "meaning": "Low battery - NOT CO detection",
            "action": "Replace CR123A battery. LCD shows 'Lb'.",
        },
        "end_of_life": {
            "led": "Yellow LED 3 flashes every 60 seconds",
            "sound": "3 beeps every 60 seconds",
            "meaning": "Alarm expired (10 year max life)",
            "action": "Replace alarm. Can silence 22hrs (max 30 days).",
        },
        "silenced": {
            "led": "Red LED steady",
            "sound": "Silent (re-activates after 9 mins if CO >50ppm)",
            "meaning": "Alarm temporarily silenced - CO may still be present",
            "action": "Ventilate. Wait for alarm to re-check. Call gas emergency.",
        },
        "co_precaution": {
            "led": "Normal",
            "sound": "Silent (app notification only)",
            "meaning": "CO detected below alarm threshold - early warning",
            "action": "Check app. Ventilate property. Monitor for rising levels.",
        },
    },
    "additional_models": {
        "XC04-WX": {
            "name": "Wi-Fi CO Alarm with LCD Display",
            "battery": "replaceable_CR123A",
            "sensor_life_years": 10,
            "features": ["wifi", "lcd_display", "app_notifications", "peak_co_display"],
        },
        "XC01-M": {
            "name": "Mini CO Alarm",
            "battery": "sealed",
            "sensor_life_years": 10,
            "features": [],
        },
        "XC01-R": {
            "name": "CO Alarm with Replaceable Battery",
            "battery": "replaceable",
            "sensor_life_years": 10,
            "features": [],
        },
        "XC0C-SR": {
            "name": "CO Alarm",
            "battery": "sealed",
            "sensor_life_years": 10,
            "features": [],
        },
    },
    "co_thresholds": {
        "30ppm": "no alarm for 120 minutes",
        "50ppm": "alarm sounds in 60-90 minutes",
        "100ppm": "alarm sounds in 10-40 minutes",
        "300ppm": "alarm sounds within 3 minutes (cannot be silenced)",
    },
    "triage_rules": {
        "co_detected_pattern": {
            "description": "Red LED flashing + 4 short beeps every 5.8 seconds",
            "outcome": "emergency_dispatch",
            "confidence": 0.95,
        },
        "silenced_pattern": {
            "description": "Red LED steady, no beeping (someone pressed silence)",
            "outcome": "schedule_engineer",
            "confidence": 0.80,
        },
        "low_battery_pattern": {
            "description": "Yellow LED every 60s + 1 beep every 60s",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
        },
        "end_of_life_pattern": {
            "description": "Yellow LED 3 flashes + 3 beeps every 60s",
            "outcome": "close_with_guidance",
            "confidence": 0.90,
        },
    },
}


def get_co_true_incidents_kb():
    """
    True CO incidents from real Cadent field data.
    These represent confirmed CO emergencies that required engineer attendance.
    """
    return [
        # === CO ALARM - True CO Detected ===
        {
            "kb_id": "co_true_001",
            "tenant_id": None,
            "use_case": "co_alarm",
            "description": "Active CO alarm sounding. Engineer found CO readings near boiler. Made safe at meter outlet. Boiler flue at risk. Gas Safe engineer required to inspect.",
            "key_indicators": {
                "co_alarm_active": True,
                "co_readings_detected": True,
                "boiler_flue_at_risk": True,
                "made_safe_at_meter": True
            },
            "risk_factors": {
                "co_alarm_triggered": 1.0,
                "safety_symptoms": 0.8,
                "faulty_flue": 1.0
            },
            "outcome": "emergency_dispatch",
            "tags": ["co_alarm", "active_alarm", "co_evident", "boiler", "flue_risk", "meter_capped"],
            "root_cause": "Boiler flue defect allowing CO spillage into living space. CO alarm correctly detected elevated CO levels.",
            "actions_taken": "FCO engineer attended. CO readings confirmed. Gas supply made safe at meter outlet. Appliance classified as At Risk. CO investigation raised for Gas Safe engineer attendance.",
            "resolution_summary": "Confirmed CO incident from active alarm. Boiler flue at risk causing CO spillage. Made safe at meter, GSRI raised.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_true_002",
            "tenant_id": None,
            "use_case": "co_alarm",
            "description": "Active CO alarm with multiple occupants reporting headaches and dizziness. CO readings detected around gas fire. Made safe, disconnected appliance.",
            "key_indicators": {
                "co_alarm_active": True,
                "multiple_symptoms": True,
                "co_readings_at_appliance": True,
                "gas_fire_source": True
            },
            "risk_factors": {
                "co_alarm_triggered": 1.0,
                "safety_symptoms": 1.0,
                "enclosed_space": 0.9
            },
            "outcome": "emergency_dispatch",
            "tags": ["co_alarm", "symptoms", "headache", "dizziness", "gas_fire", "disconnected"],
            "root_cause": "Gas fire producing CO due to blocked flue or incomplete combustion. Multiple occupants symptomatic.",
            "actions_taken": "Emergency attendance. CO readings confirmed at gas fire. Appliance disconnected for safety. Occupants advised to seek medical attention. Property ventilated.",
            "resolution_summary": "Confirmed CO incident. Gas fire causing CO with symptomatic occupants. Appliance disconnected, medical advice given.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_true_003",
            "tenant_id": None,
            "use_case": "co_alarm",
            "description": "CO alarm activated in kitchen. Engineer found CO around base of boiler flue/top of casing when boiler in use. ECV capped. Referred to SBTM scheme for new boiler.",
            "key_indicators": {
                "co_alarm_active": True,
                "co_at_boiler_flue": True,
                "co_only_when_boiler_running": True,
                "boiler_classified_id": True
            },
            "risk_factors": {
                "co_alarm_triggered": 1.0,
                "faulty_flue": 1.0,
                "safety_symptoms": 0.7
            },
            "outcome": "emergency_dispatch",
            "tags": ["co_alarm", "boiler_flue", "id_classified", "sbtm_scheme", "new_boiler"],
            "root_cause": "CO leaking from boiler flue/casing junction. Boiler classified as Immediately Dangerous (ID). Required replacement.",
            "actions_taken": "Gas capped at ECV. Boiler classified ID. Customer referred to SBTM scheme for boiler replacement. CO investigation report raised.",
            "resolution_summary": "Confirmed CO from faulty boiler flue. Classified ID, gas capped, referred for new boiler.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_true_004",
            "tenant_id": None,
            "use_case": "suspected_co_leak",
            "description": "Customer reporting CO symptoms - headaches, dizziness, nausea. No CO alarm installed. Engineer found raised CO readings near boiler. Made safe at meter outlet.",
            "key_indicators": {
                "co_symptoms_reported": True,
                "no_co_alarm": True,
                "co_readings_elevated": True,
                "boiler_source": True
            },
            "risk_factors": {
                "safety_symptoms": 1.0,
                "co_alarm_triggered": 0.5,
                "faulty_flue": 0.9
            },
            "outcome": "emergency_dispatch",
            "tags": ["co_symptoms", "no_alarm", "headache", "dizziness", "nausea", "boiler"],
            "root_cause": "Unserviced boiler producing CO. No CO alarm installed to provide early warning. Customer symptomatic for extended period.",
            "actions_taken": "Emergency attendance. CO readings confirmed. Gas made safe at meter outlet. Customer advised to seek medical attention. Landlord contacted for Gas Safe inspection.",
            "resolution_summary": "Confirmed CO leak from unserviced boiler. No CO alarm present. Customer symptomatic. Made safe, GSRI raised.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_true_005",
            "tenant_id": None,
            "use_case": "co_alarm",
            "description": "Suspect fumes reported. Engineer found CO readings at boiler. Boiler flue terminates too close to opening window. Made safe at meter, appliance isolated.",
            "key_indicators": {
                "suspect_fumes": True,
                "co_readings_at_boiler": True,
                "flue_near_window": True,
                "appliance_isolated": True
            },
            "risk_factors": {
                "co_alarm_triggered": 0.8,
                "safety_symptoms": 0.9,
                "faulty_flue": 1.0
            },
            "outcome": "emergency_dispatch",
            "tags": ["suspect_fumes", "boiler_flue", "flue_position", "window", "isolated"],
            "root_cause": "Boiler flue positioned too close to an openable window. Exhaust gases (including CO) re-entering property when window opened.",
            "actions_taken": "Gas made safe at meter outlet. Boiler isolated. Flue position documented as non-compliant. Landlord/homeowner advised to relocate flue or install CO-safe ventilation.",
            "resolution_summary": "Confirmed CO risk from incorrectly positioned boiler flue near window. Appliance isolated, remedial work required.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === CO ORANGE FLAMES ===
        {
            "kb_id": "co_true_006",
            "tenant_id": None,
            "use_case": "co_orange_flames",
            "description": "Orange flames reported on gas hob. Engineer found CO alarm not activated but soot deposits on pans and wall behind cooker. Burner ports clogged. Air shutters misaligned.",
            "key_indicators": {
                "orange_flames": True,
                "soot_on_pans": True,
                "soot_on_wall": True,
                "burner_ports_clogged": True
            },
            "risk_factors": {
                "strong_gas_smell": 0.3,
                "safety_symptoms": 0.5
            },
            "outcome": "schedule_engineer",
            "tags": ["orange_flames", "incomplete_combustion", "soot", "burner_clogged", "co_risk"],
            "root_cause": "Clogged burner ports and misaligned air shutters causing incomplete combustion, producing CO and soot.",
            "actions_taken": "Gas Safe engineer attended. Burner ports cleaned. Air shutters adjusted. Post-repair flame confirmed blue. Customer advised on regular cleaning.",
            "resolution_summary": "Orange flames from clogged burners causing incomplete combustion. Cleaned and adjusted, blue flame restored.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === CO SOOTING/SCARRING ===
        {
            "kb_id": "co_true_007",
            "tenant_id": None,
            "use_case": "co_sooting_scarring",
            "description": "Heavy sooting around boiler casing and adjacent wall. Customer reported recurring headaches. CO readings elevated. Boiler heat exchanger cracked.",
            "key_indicators": {
                "heavy_sooting": True,
                "sooting_on_wall": True,
                "recurring_headaches": True,
                "co_readings_elevated": True
            },
            "risk_factors": {
                "safety_symptoms": 1.0,
                "co_alarm_triggered": 0.7,
                "faulty_flue": 1.0
            },
            "outcome": "emergency_dispatch",
            "tags": ["sooting", "boiler", "heat_exchanger", "cracked", "co_elevated", "headaches"],
            "root_cause": "Cracked heat exchanger allowing combustion products including CO to leak into the room. Heavy sooting indicates prolonged incomplete combustion.",
            "actions_taken": "Gas supply capped. Boiler classified Immediately Dangerous. Customer advised medical attention. Boiler replacement arranged.",
            "resolution_summary": "Confirmed CO from cracked boiler heat exchanger. Heavy sooting indicating prolonged issue. Boiler condemned.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === CO EXCESSIVE CONDENSATION ===
        {
            "kb_id": "co_true_008",
            "tenant_id": None,
            "use_case": "co_excessive_condensation",
            "description": "Excessive condensation on windows in room with boiler. Engineer found boiler flue disconnected from chimney. Combustion products venting directly into room.",
            "key_indicators": {
                "excessive_condensation": True,
                "condensation_near_boiler": True,
                "flue_disconnected": True,
                "co_readings_elevated": True
            },
            "risk_factors": {
                "co_alarm_triggered": 0.9,
                "safety_symptoms": 1.0,
                "faulty_flue": 1.0
            },
            "outcome": "emergency_dispatch",
            "tags": ["condensation", "flue_disconnected", "boiler", "combustion_products", "co_risk"],
            "root_cause": "Boiler flue had become disconnected from chimney, venting all combustion products (including CO and water vapour) directly into the room.",
            "actions_taken": "Gas supply isolated immediately. Boiler classified Immediately Dangerous. Flue reconnection required by Gas Safe engineer. Property ventilated.",
            "resolution_summary": "Confirmed CO risk from disconnected boiler flue causing excessive condensation and CO buildup in room.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === CO VISIBLE FUMES ===
        {
            "kb_id": "co_true_009",
            "tenant_id": None,
            "use_case": "co_visible_fumes",
            "description": "Visible fumes and burning smell from boiler. Occupant experiencing headache and nausea. Gas fire also showing yellow flames. Multiple appliance issue.",
            "key_indicators": {
                "visible_fumes": True,
                "burning_smell": True,
                "co_symptoms": True,
                "multiple_appliances_affected": True
            },
            "risk_factors": {
                "safety_symptoms": 1.0,
                "co_alarm_triggered": 0.8,
                "strong_gas_smell": 0.7
            },
            "outcome": "emergency_dispatch",
            "tags": ["visible_fumes", "burning_smell", "boiler", "gas_fire", "headache", "nausea"],
            "root_cause": "Multiple gas appliances with combustion issues. Boiler producing visible fumes due to blocked heat exchanger. Gas fire also showing signs of incomplete combustion.",
            "actions_taken": "All gas appliances made safe. Property evacuated and ventilated. Both appliances classified as At Risk. Full CO investigation arranged.",
            "resolution_summary": "Confirmed CO risk from multiple appliances with combustion problems. All made safe, full investigation required.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === CO BLOOD TEST ===
        {
            "kb_id": "co_true_010",
            "tenant_id": None,
            "use_case": "co_blood_test",
            "description": "Hospital reports elevated carboxyhemoglobin in patient. Family of 4 affected. Source identified as gas boiler with failed flue in rented property. No CO alarm installed.",
            "key_indicators": {
                "elevated_cohb": True,
                "multiple_family_members": True,
                "rented_property": True,
                "no_co_alarm": True,
                "boiler_flue_failed": True
            },
            "risk_factors": {
                "co_alarm_triggered": 0.9,
                "safety_symptoms": 1.0,
                "faulty_flue": 1.0
            },
            "outcome": "emergency_dispatch",
            "tags": ["blood_test", "cohb", "hospital", "family", "rented", "no_alarm", "RIDDOR"],
            "root_cause": "Gas boiler with failed flue in rented property. Landlord had not maintained Gas Safety Certificate. No CO alarm provided as legally required in rented property.",
            "actions_taken": "Emergency attendance. Gas supply capped. Property condemned until remedial work complete. Landlord served with improvement notice. Incident reported under RIDDOR.",
            "resolution_summary": "Confirmed CO poisoning from failed boiler flue in rented property. Family hospitalised. Landlord enforcement action taken.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === CO FATALITY ===
        {
            "kb_id": "co_true_011",
            "tenant_id": None,
            "use_case": "co_fatality",
            "description": "CO-related fatality in residential property. Deceased found by emergency services. Boiler with blocked flue identified as source. No CO alarm present.",
            "key_indicators": {
                "fatality": True,
                "boiler_blocked_flue": True,
                "no_co_alarm": True,
                "emergency_services_attended": True
            },
            "risk_factors": {
                "co_alarm_triggered": 1.0,
                "safety_symptoms": 1.0,
                "faulty_flue": 1.0
            },
            "outcome": "emergency_dispatch",
            "tags": ["fatality", "co_death", "boiler", "blocked_flue", "no_alarm", "RIDDOR", "HSE"],
            "root_cause": "Boiler flue blocked causing CO to accumulate in living space. No CO alarm installed. Victim exposed over extended period while sleeping.",
            "actions_taken": "Emergency services secured scene. Gas supply isolated. HSE and DNV investigation launched. RIDDOR report filed. Post-mortem confirmed CO poisoning.",
            "resolution_summary": "Fatal CO incident from blocked boiler flue. No CO alarm. HSE investigation, RIDDOR reported.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === CO SMOKE ALARM CONFUSION (true - actually was CO) ===
        {
            "kb_id": "co_true_012",
            "tenant_id": None,
            "use_case": "co_smoke_alarm",
            "description": "Caller reported smoke alarm sounding but it was actually a combined smoke/CO alarm. CO readings confirmed at property. Boiler producing CO.",
            "key_indicators": {
                "alarm_misidentified": True,
                "combined_alarm": True,
                "co_readings_confirmed": True,
                "boiler_source": True
            },
            "risk_factors": {
                "co_alarm_triggered": 1.0,
                "safety_symptoms": 0.7
            },
            "outcome": "emergency_dispatch",
            "tags": ["smoke_alarm_confusion", "combined_alarm", "co_confirmed", "boiler", "misidentified"],
            "root_cause": "Caller believed it was a smoke alarm but it was a combined smoke/CO detector. The CO element had triggered. Boiler confirmed as CO source.",
            "actions_taken": "Emergency attendance. CO readings confirmed. Boiler made safe. Customer educated on alarm type identification.",
            "resolution_summary": "Smoke alarm reported but was actually combined CO alarm. CO confirmed from boiler. Made safe.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === ADDITIONAL TRUE CO PATTERNS FROM CO DATA 2024-25 ===

        # --- Active alarm with CO readings, made safe at meter (3.3% = 1,319 visits) ---
        {
            "kb_id": "co_true_013",
            "tenant_id": None,
            "use_case": "co2_alarm",
            "description": "Active CO alarm with readings detected. Gas supply made safe at meter outlet. Appliance disconnected. Customer not evacuated at time of engineer arrival.",
            "key_indicators": {
                "continuous_beeping": True,
                "co_readings_detected": True,
                "not_evacuated": True,
                "co_alarm_type": True,
                "red_light_flashing": True
            },
            "risk_factors": {
                "co_confirmed": 1.0,
                "not_evacuated": 0.9,
                "active_alarm": 0.8
            },
            "outcome": "emergency_dispatch",
            "tags": ["active_alarm", "co_readings", "made_safe", "meter", "not_evacuated"],
            "root_cause": "CO production from faulty appliance. Gas made safe at meter outlet. Appliance disconnected.",
            "actions_taken": "Emergency attendance. CO readings confirmed. Made safe at meter outlet. Appliance disconnected for safety.",
            "resolution_summary": "Active CO alarm with real readings. Gas capped at meter. Appliance disconnected. Customer advised to contact Gas Safe engineer.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Symptoms with active alarm - confirmed CO (4.1% = 1,641 with symptoms) ---
        {
            "kb_id": "co_true_014",
            "tenant_id": None,
            "use_case": "co2_alarm",
            "description": "CO alarm active with occupant reporting headache and nausea. Engineer found CO readings near boiler. Multiple people unwell. Made safe and advised hospital attendance.",
            "key_indicators": {
                "continuous_beeping": True,
                "symptoms_present": True,
                "multiple_symptoms": True,
                "co_alarm_type": True,
                "not_evacuated": True
            },
            "risk_factors": {
                "co_symptoms": 1.0,
                "multiple_occupants_affected": 0.9,
                "not_evacuated": 0.8
            },
            "outcome": "emergency_dispatch",
            "tags": ["symptoms", "headache", "nausea", "multiple_occupants", "co_confirmed", "hospital"],
            "root_cause": "CO exposure from defective boiler/flue. Occupants experiencing CO poisoning symptoms.",
            "actions_taken": "Emergency attendance. CO readings confirmed. Gas made safe. Advised hospital/ambulance. HSE notification if severe.",
            "resolution_summary": "Confirmed CO incident with symptomatic occupants. Gas supply isolated. Hospital attendance advised.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Fumes visible with boiler issues (0.7% = 360 visits) ---
        {
            "kb_id": "co_true_015",
            "tenant_id": None,
            "use_case": "co2_alarm",
            "description": "Visible fumes reported near gas appliance. CO alarm may or may not be sounding. Engineer found signs of incomplete combustion - sooting, orange flames, or spillage at flue.",
            "key_indicators": {
                "symptoms_present": True,
                "co_alarm_type": True,
                "soot_visible": True,
                "flue_blocked": True
            },
            "risk_factors": {
                "visible_fumes": 0.9,
                "incomplete_combustion": 0.8,
                "flue_compromise": 0.9
            },
            "outcome": "emergency_dispatch",
            "tags": ["fumes", "sooting", "orange_flames", "spillage", "incomplete_combustion", "boiler"],
            "root_cause": "Incomplete combustion from blocked/defective flue or boiler fault. Visible signs of CO production.",
            "actions_taken": "Emergency attendance. Appliance disconnected. Flue inspected. Made safe at meter if readings present.",
            "resolution_summary": "Visible signs of CO production from incomplete combustion. Appliance made safe. Gas Safe repair required.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Suspect CO with 4-beep pattern (real CO alarm pattern) ---
        {
            "kb_id": "co_true_016",
            "tenant_id": None,
            "use_case": "co2_alarm",
            "description": "CO alarm sounding with 4-beep pattern (4 loud beeps, pause, repeat). This is the standard CO detection alert pattern. Occupants inside property with mild symptoms.",
            "key_indicators": {
                "four_beep_pattern": True,
                "symptoms_present": True,
                "not_evacuated": True,
                "co_alarm_type": True
            },
            "risk_factors": {
                "co_detection_pattern": 1.0,
                "symptoms": 0.7,
                "not_evacuated": 0.8
            },
            "outcome": "emergency_dispatch",
            "tags": ["4_beep_pattern", "co_detection", "symptoms", "standard_alert", "not_evacuated"],
            "root_cause": "Confirmed CO detection via standard 4-beep alarm pattern with symptomatic occupants.",
            "actions_taken": "Emergency attendance. CO detection confirmed. Gas supply isolated. Occupants advised to evacuate and ventilate.",
            "resolution_summary": "Standard CO detection alarm pattern with symptoms. Confirmed real CO incident.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === SUSPECT FUMES (1,089 workorders = 2.1%) ===
        {
            "kb_id": "co_true_017",
            "tenant_id": None,
            "use_case": "co_fumes",
            "description": "Suspected fumes reported. Engineer found holes in boiler flue, incorrect fittings, or signs of spillage. CO may or may not be present but appliance unsafe. Made safe and isolated.",
            "key_indicators": {
                "symptoms_present": True,
                "flue_blocked": True,
                "soot_visible": True
            },
            "risk_factors": {
                "flue_compromise": 0.9,
                "visible_fumes": 0.8,
                "spillage_signs": 0.7
            },
            "outcome": "emergency_dispatch",
            "tags": ["fumes", "flue_holes", "incorrect_fittings", "spillage", "boiler", "unsafe"],
            "root_cause": "Boiler flue compromised - holes, incorrect fittings, or altered flue causing fume escape into living space.",
            "actions_taken": "Emergency attendance. Flue defects identified. Appliance isolated at meter outlet. Referred for urgent Gas Safe repair.",
            "resolution_summary": "Suspected fumes confirmed from compromised boiler flue. Appliance isolated. Gas Safe repair required.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # === BATTERY FAIL BUT CO EVIDENT (331 workorders = 0.6%) ===
        {
            "kb_id": "co_true_018",
            "tenant_id": None,
            "use_case": "co2_alarm",
            "description": "Initial report appeared to be battery failure (chirping alarm) but engineer found actual CO readings. Battery was low AND CO was present - dual issue. This is a critical pattern: battery fail does NOT always mean false alarm.",
            "key_indicators": {
                "symptoms_present": True,
                "co_alarm_type": True
            },
            "risk_factors": {
                "co_confirmed_despite_battery": 1.0,
                "misleading_presentation": 0.8,
                "dual_fault": 0.7
            },
            "outcome": "emergency_dispatch",
            "tags": ["battery_fail", "co_evident", "dual_fault", "misleading", "real_co", "critical"],
            "root_cause": "Alarm battery was low causing chirp, but actual CO was also present from faulty appliance. The battery issue masked the real CO detection.",
            "actions_taken": "Emergency attendance despite battery fail presentation. CO readings confirmed. Gas supply isolated. New alarm issued. Appliance made safe.",
            "resolution_summary": "Critical: battery fail alarm that also had real CO. 331 cases (0.6%) show battery fail does not exclude real CO. Always check readings.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # === BATTERY FAIL BUT CO SUSPECTED (588 workorders = 1.2%) ===
        {
            "kb_id": "co_true_019",
            "tenant_id": None,
            "use_case": "co2_alarm",
            "description": "Battery failure with suspected CO. Alarm chirping (battery) but engineer found signs suggesting possible CO - appliance at risk, spillage signs, or occupant symptoms. Precautionary made safe.",
            "key_indicators": {
                "symptoms_present": True,
                "co_alarm_type": True
            },
            "risk_factors": {
                "suspected_co": 0.7,
                "battery_mask": 0.6,
                "precautionary": 0.5
            },
            "outcome": "schedule_engineer",
            "tags": ["battery_fail", "co_suspected", "precautionary", "made_safe", "appliance_risk"],
            "root_cause": "Battery chirp but additional signs of possible CO - appliance at risk, mild symptoms, or signs of incomplete combustion. Precautionary isolation.",
            "actions_taken": "Attendance for battery fail. Additional signs found. Made safe at meter as precaution. Customer advised to arrange Gas Safe inspection.",
            "resolution_summary": "Battery fail with suspected CO signs. 588 cases (1.2%) - precautionary made safe. Gas Safe inspection required.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # === DUE TO ESCAPE (47 workorders) ===
        {
            "kb_id": "co_true_020",
            "tenant_id": None,
            "use_case": "gas_escape",
            "description": "Gas escape confirmed during CO investigation. Meter or pipework leak found. Emergency repair or meter replacement required.",
            "key_indicators": {
                "symptoms_present": True,
                "co_alarm_type": True,
                "not_evacuated": True
            },
            "risk_factors": {
                "gas_escape": 1.0,
                "meter_leak": 0.9,
                "explosion_risk": 0.8
            },
            "outcome": "emergency_dispatch",
            "tags": ["gas_escape", "meter_leak", "emergency", "repair_required", "pipework"],
            "root_cause": "Gas escape from meter, pipework, or inlet connection. Found during CO alarm investigation.",
            "actions_taken": "Emergency attendance. Gas escape confirmed. Meter/pipework isolated. Emergency repair or meter replacement arranged.",
            "resolution_summary": "Gas escape found during CO investigation. 47 cases. Emergency repair required.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
    ]


def get_co_false_incidents_kb():
    """
    False CO incidents from real Cadent field data.
    These represent the 78.3% of visits that were unnecessary.
    Critical for reducing wasted visits through better triage.
    """
    return [
        # === BATTERY FAILURE - NO CO (32.7% of all visits = 16,656 wasted visits) ===
        {
            "kb_id": "co_false_001",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "CO alarm battery failure - low battery chirping mistaken for CO alert",
            "false_positive_reason": "Intermittent chirp every 30-60 seconds is a low battery warning, NOT a CO detection alert. CO detection produces continuous loud beeping. 32.7% of all CO workorders are battery failures.",
            "key_indicators": {
                "intermittent_chirp": True,
                "every_30_60_seconds": True,
                "no_co_readings": True,
                "no_symptoms": True,
                "battery_low": True
            },
            "tags": ["battery_failure", "false_alarm", "chirping", "no_co", "low_battery"],
            "resolution": "No CO detected. Alarm battery replaced. Engineer confirmed no readings. Customer advised on difference between battery chirp (intermittent) and CO alarm (continuous).",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_002",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "CO alarm expired / end-of-life - alarm beeping due to age, not CO detection",
            "false_positive_reason": "CO alarms have a 5-7 year lifespan. When expired, they emit a warning chirp/beep that is commonly mistaken for a CO alert. The sensor is no longer reliable after expiry.",
            "key_indicators": {
                "alarm_over_7_years": True,
                "intermittent_beep": True,
                "no_co_readings": True,
                "no_symptoms": True,
                "alarm_out_of_date": True
            },
            "tags": ["expired_alarm", "end_of_life", "false_alarm", "out_of_date", "replace_alarm"],
            "resolution": "BSEN 50291 CO detector out of date and chirping. No CO readings. Engineer left new alarm. Customer advised CO alarms must be replaced every 5-7 years.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_003",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Faulty CO alarm - defective detector giving false alarm",
            "false_positive_reason": "Defective CO alarm producing false activation. All safety checks clear, tightness test passed, no CO readings. Second working alarm in same location not activated.",
            "key_indicators": {
                "faulty_alarm": True,
                "tt_passed": True,
                "no_co_readings": True,
                "second_alarm_not_activated": True,
                "all_checks_clear": True
            },
            "tags": ["faulty_alarm", "defective", "false_alarm", "tightness_test_passed"],
            "resolution": "TT pass, no readings. Confirmed faulty alarm - second working alarm present in same location not activated. Defective alarm removed, new alarm issued.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_004",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Hard-wired smoke and CO alarms all activated due to electrical fault, not CO",
            "false_positive_reason": "Hard-wired CO and smoke alarms on same circuit all went off simultaneously, but portable CO alarm did not activate. Electrical fault on shared fuse caused false activation.",
            "key_indicators": {
                "hard_wired_alarm": True,
                "all_alarms_activated": True,
                "portable_alarm_not_activated": True,
                "electrical_fault_suspected": True,
                "no_co_readings": True
            },
            "tags": ["hard_wired", "electrical_fault", "false_alarm", "fuse", "multiple_alarms"],
            "resolution": "Hard wired CO and smoke alarms all went off but portable CO alarm didn't. Customer told council. Advised to get electrics checked as all wires on same fuse. No CO found.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_005",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "CO alarm activated by strong paint smell/VOCs - not actual CO",
            "false_positive_reason": "Active CO alarm triggered by strong paint smell in flat. Some CO detectors can cross-react with volatile organic compounds (VOCs) from paint, varnish, or cleaning chemicals.",
            "key_indicators": {
                "paint_smell_present": True,
                "recent_decorating": True,
                "no_co_readings": True,
                "alarm_triggered_by_voc": True
            },
            "tags": ["paint_fumes", "voc", "cross_reaction", "false_alarm", "decorating"],
            "resolution": "Active alarm from strong paint smell in flat. ECV off. No CO readings. Customer advised to ventilate and that paint fumes can trigger some CO alarms.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_006",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "CO alarm activated by cooking - charcoal burning near alarm",
            "false_positive_reason": "Occupier burning charcoal near CO alarm. Charcoal combustion produces CO but this is a known indoor source, not a gas appliance fault.",
            "key_indicators": {
                "charcoal_burning": True,
                "near_co_alarm": True,
                "appliances_checked_clear": True,
                "no_gas_fault": True
            },
            "tags": ["charcoal", "cooking", "indoor_burning", "false_alarm", "known_source"],
            "resolution": "Checked appliances for signs of spillage, no signs evident. Occupier burning charcoal near CO alarm. Advised on dangers of indoor charcoal use and not to burn charcoal indoors.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_007",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "CO alarm activated by steam/humidity - not CO",
            "false_positive_reason": "High humidity or steam from bathroom/kitchen can cause some CO alarm sensors to malfunction and give false readings.",
            "key_indicators": {
                "high_humidity": True,
                "steam_present": True,
                "no_co_readings": True,
                "alarm_near_bathroom": True
            },
            "tags": ["humidity", "steam", "false_alarm", "sensor_interference", "bathroom"],
            "resolution": "No CO readings. Alarm triggered by humidity/steam. Advised to relocate alarm away from steam sources. TT passed, all checks clear.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_008",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Alarm dropped from ceiling - impact triggered false activation",
            "false_positive_reason": "CO alarm fell from ceiling onto floor and then went off. Physical impact can trigger a false alarm on some detector models. Other CO alarm in property not active.",
            "key_indicators": {
                "alarm_fell": True,
                "impact_triggered": True,
                "other_alarm_not_active": True,
                "no_co_readings": True,
                "tightness_test_passed": True
            },
            "tags": ["dropped_alarm", "impact", "false_alarm", "physical_damage"],
            "resolution": "No readings, no drop. Unknown alarm going off. Alarm fell from ceiling onto floor and then went off. Other CO alarm not active. Faulty alarm left on.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_009",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Alarm 5 years out of date - intermittent beeping, not CO detection",
            "false_positive_reason": "Alarm was 5 years past its expiry date and beeping intermittently. Customer also has a newer alarm that is not activating, confirming no CO present.",
            "key_indicators": {
                "alarm_5_years_expired": True,
                "intermittent_beeping": True,
                "newer_alarm_not_active": True,
                "no_trace_bascom": True
            },
            "tags": ["expired_alarm", "5_years_overdue", "false_alarm", "intermittent"],
            "resolution": "Alarm 5 years out of date was beeping intermittently. Customer has a new alarm also that isn't activating. No trace with bascom. Took batteries out of old alarm.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_010",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Heat alarm / combined heat-CO alarm activated - not CO, heat sensor triggered",
            "false_positive_reason": "Combined heat/CO alarm activated. The heat element triggered, not the CO sensor. Customer confused heat alarm activation with CO detection.",
            "key_indicators": {
                "heat_alarm_activated": True,
                "combined_heat_co": True,
                "no_co_readings": True,
                "heat_source_present": True
            },
            "tags": ["heat_alarm", "combined_alarm", "false_alarm", "heat_not_co", "confusion"],
            "resolution": "Heat alarm/CO alarm been activated twice. No trace. Customer vented down. New build property. Heat/cook alarm activated, not CO sensor. Followed new CO policy.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === ACTIVE ALARM NO CO EVIDENT (23.2% of visits) ===
        {
            "kb_id": "co_false_011",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Active CO alarm but all checks clear - no CO found, possible transient trigger",
            "false_positive_reason": "CO alarm was actively sounding on arrival but all checks showed no CO. TT passed. Sweeps clear. Alarm may have detected a transient CO spike that dissipated before engineer arrival.",
            "key_indicators": {
                "active_alarm_on_arrival": True,
                "all_checks_clear": True,
                "tightness_test_passed": True,
                "no_co_readings": True,
                "no_symptoms": True
            },
            "tags": ["active_alarm", "no_co_evident", "transient", "all_clear", "false_alarm"],
            "resolution": "Active alarm. All sweeps clear, building line and letter box clear. TT passed, no readings. Possible transient trigger. Alarm reset.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_012",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Active alarm in multiple flats - capped at meters but no CO found",
            "false_positive_reason": "Active alarms in upstairs and downstairs flat. Both capped at meters. No CO readings at either property. Likely electrical or environmental trigger affecting multiple hardwired alarms.",
            "key_indicators": {
                "multiple_properties": True,
                "alarms_in_both": True,
                "both_capped": True,
                "no_co_readings": True
            },
            "tags": ["multiple_flats", "both_capped", "no_co", "false_alarm", "hardwired"],
            "resolution": "Active alarm in upstairs and downstairs flat. Capped both. No CO readings at either property. Likely environmental or electrical trigger.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === ADVICE ONLY (22.4% of visits) ===
        {
            "kb_id": "co_false_013",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Not a CO job - occupier concerned about water on pipes underfloor",
            "false_positive_reason": "Customer called about CO but actual concern was water on pipes underfloor. Not a CO-related issue at all. Misrouted call.",
            "key_indicators": {
                "not_co_related": True,
                "plumbing_issue": True,
                "misrouted_call": True,
                "no_gas_concern": True
            },
            "tags": ["not_co", "plumbing", "misrouted", "advice_only", "wrong_service"],
            "resolution": "Not a CO job, occupier concerned about water on pipes underfloor. Carried out pressure test as precaution. No gas issue found.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_014",
            "tenant_id": None,
            "reported_as": "co_orange_flames",
            "actual_issue": "Orange flames reported but flame picture excellent on examination - all blue, no orange",
            "false_positive_reason": "Hob reportedly burning orange, but on engineer examination flame picture was excellent (all blue). No trace of fault or escape. Customer may have seen normal flame colouring from cooking residue.",
            "key_indicators": {
                "flame_excellent_on_examination": True,
                "all_blue_no_orange": True,
                "no_trace_fault": True,
                "co_detector_not_activated": True
            },
            "tags": ["orange_flame_reported", "blue_flame_found", "false_alarm", "cooking_residue"],
            "resolution": "No trace of escape. Report of hob burning orange. Flame picture excellent on examination (no orange, all blue). Pressures all checked satisfactory. CO detector present not activated.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_015",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Nebuliser in use impacting flame colour - not a gas appliance fault",
            "false_positive_reason": "Medical nebuliser in use at customer home was causing particles in the air that affected the visual appearance of flame colour on the gas hob. No actual CO or combustion problem.",
            "key_indicators": {
                "nebuliser_in_use": True,
                "no_alarm_activation": True,
                "no_symptoms": True,
                "flame_appearance_affected": True
            },
            "tags": ["nebuliser", "medical_device", "flame_colour", "false_alarm", "environmental"],
            "resolution": "No CO alarm activation or symptoms. Nebuliser in use at customer home impacting colour of flame picture. No gas fault.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_016",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "Council sent engineer for CO but no CO present - hardwired alarm making noise due to electrical fault",
            "false_positive_reason": "Council sent FCO for CO investigation but issue was old hardwired CO alarm that keeps making a high pitch noise. New CO alarm in property has not activated. Electrical issue, not gas.",
            "key_indicators": {
                "council_referral": True,
                "old_hardwired_alarm": True,
                "high_pitch_noise": True,
                "new_alarm_not_activated": True,
                "electrical_issue": True
            },
            "tags": ["council_referral", "hardwired", "electrical", "false_alarm", "old_alarm"],
            "resolution": "Council sent us out for CO. No CO present. Issue is old hardwired CO alarm that keeps making high pitch noise. New CO alarm in property has not activated. Council need to send electrician to remove redundant faulty alarm.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_017",
            "tenant_id": None,
            "reported_as": "co_smoke_alarm",
            "actual_issue": "Smoke alarm sounding, not CO alarm - not a gas emergency",
            "false_positive_reason": "Customer reported 'alarm sounding' but it was a smoke alarm (fire detection), not a CO detector. Smoke alarms are not gas emergency service responsibility.",
            "key_indicators": {
                "smoke_alarm_not_co": True,
                "no_gas_smell": True,
                "no_co_readings": True,
                "cooking_fumes_present": True
            },
            "tags": ["smoke_alarm", "not_co", "confusion", "false_alarm", "fire_service"],
            "resolution": "Not a CO job. Smoke alarm activated (not CO alarm). No CO readings. Customer cooking triggered smoke alarm. Advised to call Fire Service for smoke alarm issues.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_018",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "CO alarm fell in water - false alarm from water damage",
            "false_positive_reason": "No active alarm. Customer's CO alarm fell in water. All servicing was done recently. TT passed. Property clear. New alarm left for customer.",
            "key_indicators": {
                "alarm_water_damaged": True,
                "no_active_alarm": True,
                "recent_servicing_done": True,
                "tt_passed": True,
                "property_clear": True
            },
            "tags": ["water_damage", "dropped_in_water", "false_alarm", "faulty_alarm"],
            "resolution": "No active alarm. VC dropped old alarm in water. All servicing done on Thursday. TT pass. Property clear. New alarm left for customer.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_019",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "3 active alarms but no appliances on - false alarm, called 5 hours after event",
            "false_positive_reason": "3 alarms activated but no gas appliances were on at the time. Neighbouring properties checked. Customer called us 5 hours after the event. Transient environmental trigger likely.",
            "key_indicators": {
                "multiple_alarms": True,
                "no_appliances_running": True,
                "delayed_reporting": True,
                "neighbours_checked": True,
                "no_co_found": True
            },
            "tags": ["multiple_alarms", "no_appliances", "delayed_call", "transient", "false_alarm"],
            "resolution": "3 active alarms. No appliances on at time. Next doors checked. Called us five hours after event. Gas turned off for safety as precaution.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "kb_id": "co_false_020",
            "tenant_id": None,
            "reported_as": "co_alarm",
            "actual_issue": "CO alarm with foil on cooker - removed foil, no readings, no gas fault",
            "false_positive_reason": "Customer had placed aluminium foil on gas cooker burners. This can interfere with combustion and cause temporary CO spikes or trigger alarms without a genuine appliance fault.",
            "key_indicators": {
                "foil_on_cooker": True,
                "no_readings_after_removal": True,
                "no_gas_fault": True,
                "user_error": True
            },
            "tags": ["foil_on_cooker", "user_error", "false_alarm", "no_fault", "advice"],
            "resolution": "Foil on cooker removed. No readings. No gas fault. Customer advised not to place foil on gas burners as it interferes with combustion.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === ADDITIONAL PATTERNS FROM CO DATA 2024-25 DSR ANALYSIS ===

        # --- No trace found (14.6% = 5,817 visits) ---
        {
            "kb_id": "co_false_021",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "No trace of CO found after full investigation - alarm triggered by environmental factor",
            "false_positive_reason": "Engineer checked all appliances, carried out tightness test, no CO readings. Alarm activation likely caused by transient environmental factor (aerosols, cleaning products, humidity). 14.6% of all CO workorders result in no trace found.",
            "key_indicators": {
                "no_co_readings": True,
                "no_symptoms": True,
                "alarm_stopped": True,
                "no_gas_fault": True
            },
            "tags": ["no_trace", "false_alarm", "environmental", "tightness_passed", "no_readings"],
            "resolution": "Full investigation. No trace of CO. Tightness test passed. All appliances checked. No fault found. Alarm likely triggered by environmental factor.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Active alarm but no readings (1.6% = 654 visits) ---
        {
            "kb_id": "co_false_022",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "Active CO alarm sounding but engineer found zero CO readings - faulty sensor or transient spike",
            "false_positive_reason": "Active alarm at time of engineer visit but portable CO monitor showed zero readings. Faulty alarm sensor or brief transient trigger. Common with older alarms or after power surges.",
            "key_indicators": {
                "continuous_beeping": True,
                "no_co_readings": True,
                "no_symptoms": True,
                "co_alarm_type": True
            },
            "tags": ["active_alarm", "no_readings", "faulty_sensor", "false_alarm", "transient"],
            "resolution": "Active alarm. No CO readings on portable monitor. All appliances checked. Faulty alarm replaced. No gas fault found.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Smoke alarm confused with CO alarm (2.3% = 919 visits) ---
        {
            "kb_id": "co_false_023",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "Smoke alarm misidentified as CO alarm - no CO involved",
            "false_positive_reason": "Customer reported CO alarm but engineer identified it as a smoke alarm. Smoke alarms and CO alarms are frequently confused. 2.3% of all CO workorders are smoke alarm misidentifications.",
            "key_indicators": {
                "smoke_alarm_type": True,
                "no_co_readings": True,
                "no_symptoms": True
            },
            "tags": ["smoke_alarm", "misidentification", "false_alarm", "not_co", "advice"],
            "resolution": "Not a CO alarm. Smoke alarm activated. No CO readings. Customer educated on difference between smoke and CO alarms. Advised to install separate CO alarm.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Cooking/steam/nebuliser trigger (0.7% = 294 visits) ---
        {
            "kb_id": "co_false_024",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "CO alarm triggered by cooking fumes, steam, or nebuliser - no actual CO present",
            "false_positive_reason": "Cooking on gas hob, steam from boiling water, or medical nebuliser use can produce particles that trigger some CO alarm sensors. No actual CO is present.",
            "key_indicators": {
                "no_co_readings": True,
                "no_symptoms": True,
                "alarm_stopped": True
            },
            "tags": ["cooking", "steam", "nebuliser", "false_alarm", "environmental_trigger"],
            "resolution": "No CO detected. Alarm triggered by cooking/steam/nebuliser. All checks passed. Customer advised on alarm placement away from kitchens and steam sources.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Paint/VOC trigger (0.3% = 100 visits) ---
        {
            "kb_id": "co_false_025",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "CO alarm triggered by fresh paint or decorating chemicals - VOC cross-sensitivity",
            "false_positive_reason": "Some electrochemical CO sensors cross-react with volatile organic compounds (VOCs) from paint, varnish, adhesives, and cleaning products. No actual CO is present.",
            "key_indicators": {
                "no_co_readings": True,
                "no_symptoms": True,
                "alarm_stopped": True,
                "no_gas_fault": True
            },
            "tags": ["paint", "voc", "decorating", "cross_sensitivity", "false_alarm"],
            "resolution": "Active alarm from strong paint smell. No CO readings. ECV off as precaution. Customer advised to ventilate and relocate alarm during decorating.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Alarm stopped before engineer arrived - no evidence (common pattern) ---
        {
            "kb_id": "co_false_026",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "CO alarm had stopped before engineer arrived - no CO evidence found on investigation",
            "false_positive_reason": "Alarm stopped by the time engineer attended. No readings, no symptoms, tightness test passed. Could be transient trigger, power glitch, or approaching end-of-life. Without active alarm, cannot determine original cause.",
            "key_indicators": {
                "alarm_stopped": True,
                "no_co_readings": True,
                "no_symptoms": True,
                "no_light": True
            },
            "tags": ["alarm_stopped", "no_evidence", "false_alarm", "transient", "inconclusive"],
            "resolution": "Alarm had stopped. Full checks carried out. No CO readings. Tightness test passed. All appliances checked. No fault found. Advised customer to call back if alarm reactivates.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Near end-of-life alarm with no light (5-7 years, common pattern) ---
        {
            "kb_id": "co_false_027",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "CO alarm nearing end of 5-7 year lifespan - intermittent alerts with no CO detected",
            "false_positive_reason": "CO alarms have a 5-7 year lifespan. As electrochemical sensors degrade, they become unreliable and may trigger false alerts. Alarm may show no active light, intermittent beeping, or stop working entirely.",
            "key_indicators": {
                "alarm_5_to_7_years": True,
                "no_co_readings": True,
                "no_symptoms": True,
                "no_light": True,
                "alarm_stopped": True
            },
            "tags": ["near_end_of_life", "aging_sensor", "false_alarm", "replace_alarm", "5_to_7_years"],
            "resolution": "Alarm 5-7 years old with degraded sensor. No CO readings. New alarm issued. Customer advised on alarm lifespan and replacement schedule.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === ADVICE ONLY SHEET PATTERNS (11,425 records) ===

        # --- Orange flames reported but no CO (44 cases, mostly false) ---
        {
            "kb_id": "co_false_028",
            "tenant_id": None,
            "reported_as": "co_orange_flames",
            "actual_issue": "Orange flames on gas cooker/hob reported but no CO detected - combustion normal on inspection",
            "false_positive_reason": "Orange/yellow flames on gas hobs can be caused by dust, food residue, sprayed substances on burners, or air flow. Engineer examined flame picture and found excellent blue flame on inspection. 0.4% of advice-only visits.",
            "key_indicators": {
                "no_co_readings": True,
                "no_symptoms": True,
                "no_gas_fault": True
            },
            "tags": ["orange_flames", "cooker", "hob", "false_alarm", "flame_picture_normal", "advice"],
            "resolution": "Orange flame reported. Flame picture excellent on examination (all blue). Pressures satisfactory. CO detector present not activated. No fault found.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Sooting/scorching reported (63 cases) ---
        {
            "kb_id": "co_false_029",
            "tenant_id": None,
            "reported_as": "co_orange_flames",
            "actual_issue": "Sooting or scorch marks visible on appliances - requires service but not emergency CO",
            "false_positive_reason": "Visible soot on ceiling, boiler flue, or cupboard indicates past incomplete combustion but may not mean active CO risk. Often from poorly serviced appliances. Requires Gas Safe inspection but not always emergency.",
            "key_indicators": {
                "soot_visible": True,
                "no_co_readings": True,
                "no_symptoms": True
            },
            "tags": ["sooting", "scorch_marks", "incomplete_combustion", "service_required", "advice"],
            "resolution": "Visible soot on ceiling and boiler area. Disc fitted to meter outlet for safety. Customer contacted council/landlord for boiler service.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Excessive condensation reported (10 cases) ---
        {
            "kb_id": "co_false_030",
            "tenant_id": None,
            "reported_as": "co_excessive_condensation",
            "actual_issue": "Condensation from boiler or condensate pipe issue - not CO related",
            "false_positive_reason": "Condensate pipe disconnected or boiler producing excessive condensation. Often confused with gas/CO issue. Usually a plumbing/boiler maintenance issue, not a gas emergency.",
            "key_indicators": {
                "no_co_readings": True,
                "no_symptoms": True,
                "no_gas_fault": True
            },
            "tags": ["condensation", "condensate_pipe", "boiler", "maintenance", "false_alarm", "advice"],
            "resolution": "Condensate pipe had come away from connection. Refitted. Premises clear. CO alarm out of date, replacement issued.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Symptoms reported but no CO found (499 cases from Advice Only + 452 from Battery Fail) ---
        {
            "kb_id": "co_false_031",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "Occupant reporting CO symptoms (headache, dizziness) but engineer found no CO readings - symptoms from other cause",
            "false_positive_reason": "Customer claiming CO symptoms but zero readings on portable monitor. Symptoms likely from illness, stress, poor ventilation, or other environmental factors. 2.7% of battery fail visits and 4.4% of advice visits have reported symptoms with no CO found.",
            "key_indicators": {
                "symptoms_present": True,
                "no_co_readings": True,
                "alarm_stopped": True
            },
            "tags": ["symptoms", "no_co", "false_alarm", "headache", "dizziness", "other_cause"],
            "resolution": "Customer reporting symptoms. All property checks clear. Zero CO readings. Turned off at ECV as precaution. Customer advised to see GP if symptoms persist.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Hardwired alarm fault (99 cases from Battery Fail + more from others) ---
        {
            "kb_id": "co_false_032",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "Hardwired CO/smoke alarm system fault - electrical issue, not gas/CO",
            "false_positive_reason": "Hardwired alarm systems in council/housing association properties can trigger from electrical faults, power surges, or wiring issues. Portable CO alarm in same property did not activate. Requires electrician, not gas engineer.",
            "key_indicators": {
                "no_co_readings": True,
                "no_symptoms": True
            },
            "tags": ["hardwired", "electrical_fault", "housing_association", "council", "false_alarm", "not_co"],
            "resolution": "Hardwired alarm activated. Portable CO alarm not activated. No CO readings. Advised customer to contact housing association/council for electrical inspection of hardwired alarm system.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
        # --- Fumes reported but not CO (140 cases from Advice Only) ---
        {
            "kb_id": "co_false_033",
            "tenant_id": None,
            "reported_as": "co_fumes",
            "actual_issue": "Fumes reported but investigation found non-CO source - often boiler flue needing service",
            "false_positive_reason": "Suspected fumes can come from many sources: poorly ventilated boiler, disturbed insulation, nearby construction, car exhaust ingress. Engineer investigation found no CO readings. Boiler may need service but not an emergency.",
            "key_indicators": {
                "no_co_readings": True,
                "no_symptoms": True,
                "no_gas_fault": True
            },
            "tags": ["fumes", "suspected", "no_co", "ventilation", "boiler_service", "advice"],
            "resolution": "Suspected fumes investigated. Holes found in boiler flue/incorrect fittings. Isolated for safety. Customer advised to arrange Gas Safe repair. No active CO present.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === NO CO EVIDENT SHEET SPECIFIC PATTERNS (11,799 records) ===

        # --- Charcoal burning near CO alarm (16 cases but distinctive pattern) ---
        {
            "kb_id": "co_false_034",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "CO alarm triggered by charcoal burning or BBQ inside/near property",
            "false_positive_reason": "Charcoal and BBQ produce real CO but from non-gas-appliance source. Alarm correctly detects CO but the source is not a faulty gas appliance. Requires ventilation advice, not gas repair.",
            "key_indicators": {
                "no_gas_fault": True,
                "co_alarm_type": True
            },
            "tags": ["charcoal", "bbq", "indoor_burning", "ventilation", "real_co_non_gas", "advice"],
            "resolution": "CO alarm activated by charcoal/BBQ use near alarm. No gas fault. Customer advised never to burn charcoal indoors and to ventilate properly.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },

        # === EDGE CASE: Battery fail BUT CO suspected (588 cases) ===
        # This is tricky - alarm was battery-related BUT engineer found possible CO
        {
            "kb_id": "co_false_035",
            "tenant_id": None,
            "reported_as": "co2_alarm",
            "actual_issue": "CO alarm initially appeared to be battery failure but symptoms present - borderline case requiring caution",
            "false_positive_reason": "452 cases (2.7%) in battery fail category had reported symptoms. In most cases, symptoms were unrelated (illness, anxiety) but alarm was battery-related. However, 588 cases in this category showed suspected CO, meaning battery fail does NOT always mean false alarm.",
            "key_indicators": {
                "symptoms_present": True,
                "no_co_readings": True
            },
            "tags": ["battery_fail", "symptoms", "borderline", "caution", "suspected_co"],
            "resolution": "Alarm appeared battery-related. Symptoms reported. All checks clear but capped at ECV as precaution. Customer advised to see GP and arrange boiler service.",
            "source": "cadent_co_data_2024_25",
            "verified_by": "system",
            "verified_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat()
        },
    ]
