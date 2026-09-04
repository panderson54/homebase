"""Seed data mapping appliance category -> default maintenance tasks / consumables /
pro-service interval. Loaded into the category_templates table by `flask seed-templates`;
the pro-service interval is applied directly to a new Appliance (it isn't a per-task row).

Sourced from the user's 7 reference appliances (see docs/appliance-tracker-plan.md).
"""

CATEGORY_LABELS = {
    # Kitchen
    'dishwasher': 'Dishwasher',
    'refrigerator': 'Refrigerator',
    'freezer': 'Freezer',
    'range': 'Range / Stove',
    'wall_oven': 'Wall Oven',
    'cooktop': 'Cooktop',
    'microwave': 'Microwave',
    'garbage_disposal': 'Garbage Disposal',
    'range_hood': 'Range Hood',
    'wine_cooler': 'Wine / Beverage Cooler',
    # Laundry
    'washer': 'Washer',
    'dryer': 'Dryer',
    # HVAC / Climate
    'furnace': 'Furnace',
    'boiler': 'Boiler',
    'central_ac': 'Central Air Conditioner',
    'window_ac': 'Window / Portable AC',
    'heat_pump': 'Heat Pump',
    'mini_split_outdoor': 'AC / Mini-Split (Outdoor Unit)',
    'mini_split_indoor': 'AC / Mini-Split (Indoor Head)',
    'dehumidifier': 'Dehumidifier',
    'humidifier': 'Humidifier',
    # Water
    'water_heater': 'Water Heater',
    'tankless_water_heater': 'Tankless Water Heater',
    'water_softener': 'Water Softener',
    'sump_pump': 'Sump Pump',
    'well_pump': 'Well Pump',
    'water_filter': 'Whole-House Water Filter',
    # Other
    'generator': 'Standby Generator',
}

CATEGORY_TEMPLATES = {
    'furnace': {
        'pro_service_interval': (1, 'years'),
        'maintenance': [
            {
                'title': 'Check/replace filter',
                'description': 'Check monthly during heating season; replace when dirty.',
                'frequency_value': 1,
                'frequency_unit': 'months',
            },
            {
                'title': 'Vacuum around unit',
                'description': 'Clear dust and debris from around the furnace.',
                'frequency_value': 3,
                'frequency_unit': 'months',
            },
        ],
        'consumables': [
            {'name': '1" pleated filter', 'frequency_value': 2, 'frequency_unit': 'months'},
        ],
    },
    'water_heater': {
        'pro_service_interval': (1, 'years'),
        'maintenance': [
            {
                'title': 'Flush tank',
                'description': 'Drain and flush sediment from the tank.',
                'frequency_value': 1,
                'frequency_unit': 'years',
            },
            {
                'title': 'Test T&P valve',
                'description': 'Test the temperature/pressure relief valve.',
                'frequency_value': 1,
                'frequency_unit': 'years',
            },
        ],
        'consumables': [
            {'name': 'Anode rod', 'frequency_value': 4, 'frequency_unit': 'years'},
        ],
    },
    'dishwasher': {
        'pro_service_interval': None,
        'maintenance': [
            {
                'title': 'Clean filter',
                'description': 'Remove and rinse the filter screen.',
                'frequency_value': 1,
                'frequency_unit': 'months',
            },
            {
                'title': 'Run cleaner cycle',
                'description': 'Run an empty cycle with dishwasher cleaner.',
                'frequency_value': 1,
                'frequency_unit': 'months',
            },
        ],
        'consumables': [
            {'name': 'Cleaner/descaler tablets', 'frequency_value': 4, 'frequency_unit': 'months'},
        ],
    },
    'refrigerator': {
        'pro_service_interval': None,
        'maintenance': [
            {
                'title': 'Vacuum condenser coils',
                'description': 'Clear dust from the condenser coils.',
                'frequency_value': 6,
                'frequency_unit': 'months',
            },
            {
                'title': 'Check door gasket',
                'description': 'Inspect the door seal for gaps or wear.',
                'frequency_value': 6,
                'frequency_unit': 'months',
            },
        ],
        'consumables': [
            {'name': 'Water filter', 'frequency_value': 6, 'frequency_unit': 'months'},
        ],
    },
    'dehumidifier': {
        'pro_service_interval': None,
        'maintenance': [
            {
                'title': 'Clean washable filter',
                'description': 'Rinse and dry the washable filter.',
                'frequency_value': 3,
                'frequency_unit': 'weeks',
            },
        ],
        'consumables': [],
    },
    'mini_split_outdoor': {
        'pro_service_interval': (1, 'years'),
        'maintenance': [
            {
                'title': 'Keep unit clear of debris',
                'description': 'Clear leaves, snow, and debris from around the outdoor unit.',
                'frequency_value': 3,
                'frequency_unit': 'months',
            },
        ],
        'consumables': [],
    },
    'mini_split_indoor': {
        'pro_service_interval': (1, 'years'),
        'maintenance': [
            {
                'title': 'Clean washable mesh filter',
                'description': 'Rinse and dry the washable mesh filter.',
                'frequency_value': 3,
                'frequency_unit': 'weeks',
            },
        ],
        'consumables': [],
    },
}
