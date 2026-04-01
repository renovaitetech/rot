# =============================================================================
# Presentation prompts
# =============================================================================

PRESENTATION_SLIDE_PROMPT = """You are analyzing a slide from a presentation document in a Swedish construction project.

Describe the slide content in Swedish. Focus on extracting ALL useful information for search and retrieval (RAG).

GUIDELINES:
- If the slide contains a chart or diagram: describe what it shows, axes, trends, key numbers
- If the slide contains a list or bullet points: extract ALL items
- If the slide contains a table: describe columns and key data
- If the slide contains a photo of a building, room, entrance, etc.: describe what is shown in detail (building type, materials, surroundings, condition)
- If the slide is a title/cover slide with just a title and background image: describe the title and briefly note the background, do NOT over-describe decorative imagery
- If the slide contains text paragraphs: extract the key information

Return a JSON object:
{
  "slide_type": "title | content | chart | photo | table | mixed",
  "title": "slide title if visible, or null",
  "description": "detailed description in Swedish of what the slide contains and shows",
  "key_facts": ["fact 1", "fact 2", ...],
  "has_image": true/false,
  "image_description": "description of photo/image if present, or null"
}

Return ONLY valid JSON, no markdown formatting, no code blocks."""


# =============================================================================
# Drawing prompts — Step 1: Classify drawing subtype
# =============================================================================

DRAWING_CLASSIFY_PROMPT = """You are analyzing a page from a technical drawing document in a Swedish construction project.

Determine the drawing subtype based on its visual appearance.

Return a JSON object:
{
  "drawing_subtype": one of:
    - "floor_plan" — plan view of a full floor/level showing rooms, walls, doors
    - "apartment_plan" — plan view of a single apartment or dwelling unit
    - "room_plan" — detailed plan of a single room
    - "facade" — exterior elevation/facade view of a building
    - "section" — cross-section or longitudinal section of a building
    - "site_plan" — site/area plan showing building placement, roads, landscape
    - "window_detail" — detailed drawing of windows or window systems
    - "door_detail" — detailed drawing of doors or door systems
    - "structural_detail" — structural/construction detail (joints, connections, etc.)
    - "installation" — MEP/HVAC/electrical installation drawing
    - "roof_plan" — roof plan or roof detail
    - "staircase" — staircase detail or section
    - "other" — does not fit any category above
  "confidence": "high" / "medium" / "low",
  "visual_cues": ["cue 1", "cue 2", "cue 3"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks."""


# =============================================================================
# Drawing prompts — Step 2: Detailed analysis per subtype
# =============================================================================

_DRAWING_DETAIL_PROMPTS = {
    "floor_plan": """You are analyzing a floor plan drawing from a Swedish construction project.

Extract the following information in Swedish:
- Number of apartments/units on the floor
- Names/numbers of apartments or spaces
- Common areas (trapphus, korridor, tvättstuga, etc.)
- Approximate layout description
- Any dimensions or area measurements visible
- Floor level if indicated

Return a JSON object:
{
  "description": "detailed description in Swedish",
  "units": ["unit names/numbers"],
  "common_areas": ["area names"],
  "floor_level": "floor level or null",
  "dimensions": ["any visible dimensions"],
  "features": ["notable features"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks.""",

    "apartment_plan": """You are analyzing an apartment plan drawing from a Swedish construction project.

Extract the following information in Swedish:
- Number of rooms (antal rum)
- Room names and approximate sizes if visible
- Kitchen type (separate, open, kitchenette)
- Number of bathrooms/WC
- Balcony/terrace if present
- Total area if indicated
- Apartment designation/number

Return a JSON object:
{
  "description": "detailed description in Swedish",
  "apartment_id": "designation or null",
  "room_count": number or null,
  "rooms": [{"name": "room name", "area": "area or null"}],
  "kitchen_type": "type or null",
  "bathrooms": number or null,
  "has_balcony": true/false/null,
  "total_area": "area or null",
  "features": ["notable features"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks.""",

    "room_plan": """You are analyzing a detailed room plan from a Swedish construction project.

Extract the following information in Swedish:
- Room type and name
- Dimensions
- Fixtures and furniture shown
- Door and window positions
- Materials or finishes if indicated

Return a JSON object:
{
  "description": "detailed description in Swedish",
  "room_type": "type",
  "dimensions": ["dimensions"],
  "fixtures": ["items shown"],
  "features": ["notable features"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks.""",

    "facade": """You are analyzing a facade/elevation drawing from a Swedish construction project.

Extract the following information in Swedish:
- Which facade (north, south, east, west, or designation)
- Number of floors visible
- Building height if indicated
- Material/cladding visible
- Window pattern
- Entrance locations
- Roof type

Return a JSON object:
{
  "description": "detailed description in Swedish",
  "facade_direction": "direction or designation",
  "floors_visible": number or null,
  "building_height": "height or null",
  "materials": ["visible materials"],
  "roof_type": "type or null",
  "features": ["notable features"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks.""",

    "section": """You are analyzing a cross-section drawing from a Swedish construction project.

Extract the following information in Swedish:
- Section designation (e.g. A-A, B-B)
- Number of floors/levels shown
- Floor-to-floor heights if visible
- Foundation type if visible
- Roof construction
- Notable structural elements

Return a JSON object:
{
  "description": "detailed description in Swedish",
  "section_id": "designation or null",
  "floors": number or null,
  "floor_heights": ["heights"],
  "foundation": "type or null",
  "roof": "type or null",
  "features": ["notable features"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks.""",

    "site_plan": """You are analyzing a site plan from a Swedish construction project.

Extract the following information in Swedish:
- Number of buildings shown
- Building names/designations
- Roads and pathways
- Parking areas
- Green areas / landscaping
- North direction if indicated
- Scale if indicated

Return a JSON object:
{
  "description": "detailed description in Swedish",
  "buildings": ["building names/designations"],
  "roads": ["road descriptions"],
  "parking": "description or null",
  "landscaping": "description or null",
  "scale": "scale or null",
  "features": ["notable features"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks.""",

    "window_detail": """You are analyzing a window detail drawing from a Swedish construction project.

Extract the following information in Swedish:
- Window types shown
- Number of windows
- Window designations/names
- Dimensions if visible
- Opening mechanism (fixed, tilt, turn, etc.)
- Material (wood, aluminium, etc.)

Return a JSON object:
{
  "description": "detailed description in Swedish",
  "window_types": ["types"],
  "window_count": number or null,
  "designations": ["names/codes"],
  "dimensions": ["dimensions"],
  "materials": ["materials"],
  "features": ["notable features"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks.""",

    "door_detail": """You are analyzing a door detail drawing from a Swedish construction project.

Extract the following information in Swedish:
- Door types shown
- Number of doors
- Door designations
- Dimensions
- Material and finish

Return a JSON object:
{
  "description": "detailed description in Swedish",
  "door_types": ["types"],
  "door_count": number or null,
  "designations": ["names/codes"],
  "dimensions": ["dimensions"],
  "materials": ["materials"],
  "features": ["notable features"]
}

Return ONLY valid JSON, no markdown formatting, no code blocks.""",
}

# Fallback prompt for subtypes without a specific detail prompt
_DRAWING_GENERIC_DETAIL = """You are analyzing a technical drawing from a Swedish construction project.
The drawing has been classified as: {drawing_subtype}

Describe in detail what is shown in this drawing. Write in Swedish.
Extract all useful information: dimensions, labels, annotations, materials, counts of elements.

Return a JSON object:
{{
  "description": "detailed description in Swedish",
  "drawing_subtype": "{drawing_subtype}",
  "elements": ["key elements visible"],
  "dimensions": ["any visible dimensions"],
  "annotations": ["any visible text labels/annotations"],
  "features": ["notable features"]
}}

Return ONLY valid JSON, no markdown formatting, no code blocks."""


def get_drawing_detail_prompt(drawing_subtype: str) -> str:
    """Get the detail extraction prompt for a given drawing subtype."""
    prompt = _DRAWING_DETAIL_PROMPTS.get(drawing_subtype)
    if prompt:
        return prompt
    return _DRAWING_GENERIC_DETAIL.format(drawing_subtype=drawing_subtype)
