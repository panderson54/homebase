"""Choices, field specs, and agent instructions for agent-filed feature requests.
The instructions live here (not only in a template) so the web page and the MCP
server hand agents the exact same guidance."""

REQUEST_TYPE_LABELS = {
    'new_feature': 'New feature',
    'enhancement': 'Enhancement',
    'missing_field': 'Missing field / data',
    'workflow_gap': 'Workflow gap',
    'bug': 'Bug / broken behavior',
    'agent_tooling': 'Agent tooling (MCP, export)',
}

AREA_LABELS = {
    'dashboard': 'Dashboard',
    'home': 'Home profile',
    'rooms': 'Rooms',
    'zones': 'Zones',
    'paint': 'Paint colors',
    'appliances': 'Appliances',
    'maintenance': 'Maintenance tasks',
    'consumables': 'Consumables',
    'service_records': 'Service records',
    'vendors': 'Vendors',
    'documents': 'Documents',
    'export': 'Context export',
    'mcp_server': 'MCP server',
    'other': 'Other',
}

PRIORITY_LABELS = {
    'low': 'Low',
    'medium': 'Medium',
    'high': 'High',
}

STATUS_LABELS = {
    'unread': 'Unread',
    'approved': 'Approved',
    'denied': 'Denied',
    'implemented': 'Implemented',
}

# (name, label, kind, required, max_length, help). `kind` drives the form widget:
# text / url / textarea / select:<choices-attr>. Order is the form + Markdown order.
FIELDS = [
    ('title', 'Title', 'text', True, 100,
     'Short, starts with a verb. e.g. "Add warranty expiry reminders to appliances".'),
    ('summary', 'Summary', 'text', True, 300,
     'One or two sentences — this is what shows in the list.'),
    ('request_type', 'Request type', 'select:request_type', True, None, ''),
    ('area', 'Area of site', 'select:area', True, None, 'Which part of Homebase this mostly touches.'),
    ('page_url', 'Page URL where noticed', 'text', False, 500,
     'e.g. /appliances/12 — the page you were on when you hit the gap.'),
    ('trying_to_do', 'What were you trying to do?', 'textarea', True, None,
     'The real task you were doing for the user when you got blocked. Be concrete.'),
    ('problem', "Problem / what's missing", 'textarea', True, None,
     "What the site can't do today."),
    ('workaround', 'Current workaround', 'textarea', False, None,
     'How you got around it (if you could), e.g. "put the date in the notes field".'),
    ('proposed_behavior', 'Proposed behavior', 'textarea', True, None,
     'What a user or agent should be able to do afterwards. Describe behavior, not code.'),
    ('acceptance_criteria', 'Acceptance criteria', 'textarea', True, None,
     'One per line. Each line a pass/fail check, e.g. "Appliance detail page shows warranty expiry date".'),
    ('data_entities', 'Data / entities involved', 'textarea', False, None,
     'Models or fields affected, e.g. "Appliance.warranty_expires (new date column)".'),
    ('implementation_notes', 'Implementation notes', 'textarea', False, None,
     'Optional hints — likely files, routes, existing helpers to reuse. Only if fairly confident.'),
    ('out_of_scope', 'Out of scope', 'textarea', False, None,
     'What this request deliberately does NOT include, so builders don\'t over-build.'),
    ('priority', 'Suggested priority', 'select:priority', True, None,
     'High = blocks real tasks often. Most requests are Low or Medium.'),
    ('priority_reason', 'Priority reason', 'text', False, 300, 'One line on why that priority.'),
    ('related_requests', 'Related requests', 'text', False, 200,
     'Other request ids, e.g. "#3, #7" (duplicates, dependencies).'),
    ('submitted_by', 'Submitted by', 'text', True, 120,
     'Your agent name or role, e.g. "maintenance-planner agent".'),
    ('context_url', 'Session / context link', 'url', False, 500,
     'Link back to the conversation/session this came from, if you have one.'),
]

CHOICES = {
    'request_type': REQUEST_TYPE_LABELS,
    'area': AREA_LABELS,
    'priority': PRIORITY_LABELS,
}

AGENT_INSTRUCTIONS_INTRO = (
    'File a request when you were trying to do something for the user in Homebase and the '
    'site couldn\'t do it (a missing page, field, filter, action, or export) or forced an '
    'awkward workaround. Don\'t file requests for one-off data problems (fix the data '
    'instead) or for things that are already possible another way.'
)

AGENT_INSTRUCTIONS = [
    ('Check for duplicates first.',
     'Scan the list (All tab, including Denied). If a request already covers it, edit that one '
     'and add your use case to "What were you trying to do?" instead of filing a new one. If a '
     'similar one was denied, read its review notes before filing again.'),
    ('One request per feature.',
     'Found two gaps? File two requests and link them via "Related requests".'),
    ('Write for a different agent.',
     'Someone with no access to your conversation will build this. Use concrete examples — real '
     'field names, page URLs, sample values. Avoid "it", "this page", "as discussed".'),
    ('Describe behavior, not code.',
     '"Proposed behavior" is what the user can do afterwards. Put file/model guesses in '
     '"Implementation notes", and only if you\'re fairly confident.'),
    ('Make acceptance criteria testable.',
     'One per line, each a pass/fail check, e.g. "Dashboard lists warranties expiring within 30 days".'),
    ('Be honest about priority.',
     'High means it blocks real tasks frequently. Most requests are Low or Medium.'),
    ("Don't change the status.",
     'Approve / Deny / Implemented are the homeowner\'s decisions. Editing a request never changes '
     'its status.'),
    ('Building an approved request?',
     'Read /agent-request/<id>.md (or the MCP get_feature_request tool) and treat its acceptance '
     'criteria and out-of-scope list as the spec. Tell the homeowner when it\'s done so they can '
     'mark it Implemented.'),
]


def agent_instructions_text():
    """Plain-text rendering for the MCP server."""
    steps = '\n'.join(
        f'{i}. {heading} {body}' for i, (heading, body) in enumerate(AGENT_INSTRUCTIONS, start=1)
    )
    fields = '\n'.join(
        f'- {name}{" (required)" if required else ""}: {label}. {help_}'.rstrip()
        + (f' Choices: {", ".join(CHOICES[kind.split(":", 1)[1]])}.' if kind.startswith('select:') else '')
        for name, label, kind, required, _max, help_ in FIELDS
    )
    return f'{AGENT_INSTRUCTIONS_INTRO}\n\n{steps}\n\nFields:\n{fields}'
