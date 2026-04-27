"""Visual image prompt builder for AI image generation.

Converts raw narration text into clean, visual-only image prompts that do
NOT cause image models to render on-screen text, captions, speech bubbles,
or other typographic elements.

When ``settings.VISUAL_SHOT_PLAN_ENABLED`` is ``True`` (the default), each
block receives a distinct shot type drawn from a rotating, category-aware
plan so that a multi-block video about the same subject never produces five
identical close-up portraits.  The category is detected automatically from
the topic and/or scene text via :func:`detect_visual_category`.
"""
from __future__ import annotations

import re

import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Patterns that indicate the scene text is conversational / non-visual.
# These are removed before building the visual prompt.
# ---------------------------------------------------------------------------

# Direct-address / call-to-action openers that add no visual meaning.
_CONVERSATIONAL_PHRASES: list[str] = [
    r"\bhey\s+there\b",
    r"\bhi\s+there\b",
    r"\bhello\s+there\b",
    r"\bfolks\b",
    r"\bfriends\b",
    r"\beveryone\b",
    r"\bguys\b",
    r"\blet'?s\b",
    r"\bjoin\s+me\b",
    r"\bstay\s+tuned\b",
    r"\bcome\s+with\s+me\b",
    r"\bremember\b",
    r"\bnext\s+time\b",
    r"\bhere'?s\s+the\s+(?:good\s+)?news\b",
    r"\bdid\s+you\s+know\b",
    r"\btoday\s+we\b",
    r"\btoday\s+i\b",
    r"\bin\s+this\s+video\b",
    r"\bin\s+today'?s\s+video\b",
    r"\bwelcome\s+(?:back\s+)?to\b",
    r"\bthanks?\s+for\s+watching\b",
    r"\bdon'?t\s+forget\b",
    r"\blike\s+and\s+subscribe\b",
    r"\bsmash\s+that\b",
    r"\bhit\s+that\b",
    r"\bclick\s+(?:the\s+)?(?:link|button|here)\b",
    r"\bcheck\s+(?:it\s+)?out\b",
]

_PHRASE_RE = re.compile(
    "|".join(_CONVERSATIONAL_PHRASES),
    re.IGNORECASE,
)

# Minimum character length for scene text to be considered visually meaningful.
_MIN_VISUAL_LENGTH = 20

# Maximum character length for single-quoted strings to be considered inline
# quotes (not multi-sentence blocks).  Longer single-quoted spans are left
# intact because they are likely chapter titles or proper names.
_MAX_SINGLE_QUOTE_LENGTH = 60

# Maximum number of words taken from scene text when building a subject hint.
_SUBJECT_MAX_WORDS = 10

# Minimum character length for a subject phrase to be considered usable.
_MIN_SUBJECT_LENGTH = 4

# ---------------------------------------------------------------------------
# Visual category string constants
# ---------------------------------------------------------------------------

CATEGORY_ANIMAL: str = "animal"
CATEGORY_MUSIC: str = "music"
CATEGORY_TECHNOLOGY: str = "technology"
CATEGORY_SCIENCE: str = "science"
CATEGORY_HEALTH: str = "health"
CATEGORY_BUSINESS: str = "business"
CATEGORY_HISTORY: str = "history"
CATEGORY_TRAVEL: str = "travel"
CATEGORY_SPORTS: str = "sports"
CATEGORY_EDUCATION: str = "education"
CATEGORY_ABSTRACT: str = "abstract"
CATEGORY_GENERAL: str = "general"  # fallback when no category matches

# ---------------------------------------------------------------------------
# Generic topic words that should NOT override specific visual_tags.
# When the topic is one of these broad category labels and visual_tags contain
# something more concrete, the tags win.
# ---------------------------------------------------------------------------

_GENERIC_TOPIC_WORDS: frozenset[str] = frozenset({
    "animals", "animal", "nature",
    "music",
    "technology", "tech",
    "business",
    "history",
    "health",
    "travel",
    "sports", "sport",
    "education",
    "science",
    "abstract",
    "motivation",
    "tips", "facts",
    "explainer",
    "video", "content",
    "story", "guide",
})

# ---------------------------------------------------------------------------
# Per-category keyword sets used by detect_visual_category.
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: dict[str, frozenset[str]] = {
    CATEGORY_ANIMAL: frozenset({
        # Rodents / burrowing
        "groundhog", "groundhogs", "marmot", "marmots",
        "squirrel", "squirrels", "chipmunk", "chipmunks",
        "beaver", "beavers", "mole", "moles", "vole", "voles",
        "rabbit", "rabbits", "hare", "hares",
        # Canines / felines / large mammals
        "fox", "foxes", "wolf", "wolves", "coyote", "coyotes",
        "bear", "bears", "panda", "pandas",
        "cat", "cats", "kitten", "kittens", "lion", "lions", "tiger", "tigers",
        "leopard", "cheetah", "jaguar",
        "dog", "dogs", "puppy", "puppies",
        # Ungulates
        "deer", "elk", "moose", "bison", "buffalo",
        "horse", "horses", "pony", "donkey",
        "cow", "cows", "goat", "goats", "sheep", "lamb",
        # Primates
        "monkey", "monkeys", "gorilla", "chimpanzee", "orangutan", "baboon",
        # Birds
        "bird", "birds", "eagle", "hawk", "owl", "sparrow", "robin", "crow",
        "parrot", "penguin", "flamingo", "heron", "duck", "goose",
        # Reptiles / amphibians
        "snake", "snakes", "lizard", "gecko", "iguana",
        "frog", "frogs", "toad", "turtle", "tortoise", "crocodile", "alligator",
        # Marine
        "fish", "whale", "dolphin", "shark", "seal", "otter", "walrus",
        "octopus", "jellyfish",
        # Insects
        "bee", "bees", "honeybee", "honeybees", "butterfly", "butterflies",
        "ant", "ants", "dragonfly", "firefly",
        # Other
        "raccoon", "raccoons", "badger", "skunk", "opossum", "armadillo",
        "elephant", "elephants", "giraffe", "hippo", "rhino", "zebra",
        "kangaroo", "koala", "wombat",
    }),
    CATEGORY_MUSIC: frozenset({
        "music", "musical", "musician", "musicians",
        "song", "songs", "album", "albums", "track", "tracks",
        "guitar", "piano", "drums", "bass", "violin", "cello", "flute",
        "trumpet", "saxophone", "synthesizer",
        "band", "bands", "orchestra", "choir",
        "concert", "concerts", "stage", "performance", "performances",
        "singer", "singers", "vocalist", "vocalists",
        "melody", "melodies", "rhythm", "beat", "harmony", "chord", "chords",
        "recording", "studio", "studios", "lyrics",
        "jazz", "rock", "pop", "classical", "rap", "hip", "indie", "electronic",
        "playlist", "streaming", "soundtrack",
    }),
    CATEGORY_TECHNOLOGY: frozenset({
        "technology", "technologies", "tech", "digital",
        "computer", "computers", "software", "hardware",
        "internet", "web", "network", "networks", "server", "servers",
        "robot", "robots", "automation", "drone", "drones",
        "app", "apps", "application", "applications",
        "mobile", "smartphone", "smartphones", "cloud",
        "cybersecurity", "blockchain",
        "algorithm", "algorithms", "code", "coding", "programming",
        "developer", "developers", "innovation", "innovations",
        "machine", "neural", "processor", "processors",
        "semiconductor", "semiconductors",
        "virtual", "augmented", "artificial", "intelligence", "data",
        "database", "databases", "api", "cpu", "gpu",
    }),
    CATEGORY_SCIENCE: frozenset({
        "science", "sciences", "scientific",
        "biology", "chemistry", "physics", "astronomy", "geology", "ecology",
        "experiment", "experiments", "research", "laboratory", "lab", "labs",
        "discovery", "discoveries", "species", "evolution",
        "cell", "cells", "atom", "atoms", "molecule", "molecules",
        "fossil", "fossils", "planet", "planets", "galaxy", "galaxies",
        "climate", "environment", "environmental",
        "ecosystem", "ecosystems", "biodiversity",
        "quantum", "genetics", "genome", "neuroscience", "botany", "zoology",
        "thermodynamics", "astrophysics",
    }),
    CATEGORY_HEALTH: frozenset({
        "health", "healthy", "wellness", "wellbeing",
        "fitness", "exercise", "exercises", "workout", "workouts",
        "nutrition", "diet", "nutrient", "nutrients", "supplement", "supplements",
        "medical", "medicine", "doctor", "doctors", "hospital", "hospitals",
        "therapy", "therapies", "yoga", "meditation", "mindfulness",
        "sleep", "hydration",
        "disease", "diseases", "treatment", "treatments",
        "vaccine", "vaccines", "surgery", "surgeries",
        "mental", "body", "mind",
        "physiotherapy", "rehabilitation", "cardio",
        "immunity", "immune", "pharmaceutical", "pharmaceuticals",
        "symptom", "symptoms", "diagnosis", "cure", "cures", "healing",
    }),
    CATEGORY_BUSINESS: frozenset({
        "business", "businesses", "finance", "financial",
        "money", "investment", "investments",
        "entrepreneur", "entrepreneurs",
        "company", "companies", "corporation", "corporations",
        "market", "markets", "marketing", "sales",
        "revenue", "revenues", "profit", "profits",
        "economy", "economies", "stock", "stocks",
        "brand", "brands", "product", "products",
        "customer", "customers", "strategy", "strategies",
        "management", "leadership", "ceo",
        "office", "offices", "corporate", "trade", "trading",
        "commerce", "commercial", "retail",
        "enterprise", "enterprises", "dividend",
        "budget", "budgets", "accounting", "audit", "merger", "franchise",
    }),
    CATEGORY_HISTORY: frozenset({
        "history", "historical", "ancient", "medieval", "renaissance",
        "war", "wars", "battle", "battles",
        "empire", "empires", "civilization", "civilizations",
        "culture", "cultures", "tradition", "traditions",
        "heritage", "monument", "monuments",
        "artifact", "artifacts", "archive", "archives",
        "museum", "museums", "era", "eras",
        "century", "centuries", "decade", "decades",
        "revolution", "revolutions", "dynasty", "dynasties",
        "archaeological", "archaeology",
        "pharaoh", "knight", "knights", "viking", "vikings", "samurai",
        "colonial", "colonialism", "independence",
        "mythology", "legend", "legends", "folklore",
        "biography", "biographies",
        # Architecture and military terms commonly used as visual tags for historical content.
        "soldier", "soldiers", "army", "armies", "legion", "legions",
        "architecture", "architectural", "ruins", "ruin",
        "roman", "rome", "greece", "greek", "egypt", "egyptian",
        "medieval", "fortress", "castle", "castles",
    }),
    CATEGORY_TRAVEL: frozenset({
        "travel", "traveling", "travelling",
        "journey", "destination", "destinations",
        "trip", "trips", "tourism", "tourist", "tourists",
        "adventure", "adventures", "explore", "exploration", "wanderlust",
        "vacation", "vacations", "holiday", "holidays",
        "country", "countries", "city", "cities",
        "landscape", "landscapes",
        "hotel", "hotels", "flight", "flights",
        "backpacking", "cruise", "cruises",
        "hiking", "hike", "beach", "beaches",
        "mountain", "mountains", "island", "islands",
        "resort", "resorts", "passport", "visa", "airport", "airline", "airlines",
        "sightseeing", "souvenir", "souvenirs", "itinerary",
    }),
    CATEGORY_SPORTS: frozenset({
        "sport", "sports", "athlete", "athletes", "athletics",
        "football", "soccer", "basketball", "baseball",
        "tennis", "golf", "swimming", "swim",
        "running", "run", "marathon", "marathons",
        "cycling", "cycle", "skiing", "ski", "gymnastics",
        "competition", "competitions", "tournament", "tournaments",
        "championship", "championships",
        "training", "train", "coach", "coaches",
        "team", "teams", "stadium", "stadiums",
        "score", "scores", "trophy", "trophies",
        "player", "players", "league", "leagues",
        "olympic", "olympics", "race", "races", "sprint",
    }),
    CATEGORY_EDUCATION: frozenset({
        "education", "educational", "learning",
        "school", "schools", "university", "universities",
        "college", "colleges",
        "student", "students", "teacher", "teachers",
        "professor", "professors",
        "class", "classes", "lesson", "lessons",
        "curriculum", "knowledge", "skill", "skills",
        "course", "courses", "workshop", "workshops",
        "degree", "degrees", "study", "academic", "academics",
        "scholarship", "scholarships",
        "textbook", "textbooks", "lecture", "lectures",
        "kindergarten", "elementary", "secondary",
        "tutoring", "tutor", "tutors",
        "exam", "exams", "homework", "literacy", "numeracy", "campus",
    }),
    CATEGORY_ABSTRACT: frozenset({
        "motivation", "motivational", "inspiration", "inspirational",
        "mindset", "success", "growth", "change",
        "purpose", "meaning", "philosophy", "philosophical",
        "wisdom", "happiness", "fear", "courage",
        "dream", "dreams", "goal", "goals", "potential",
        "gratitude", "resilience", "perseverance", "ambition",
        "confidence", "improvement", "legacy", "vision",
        "values", "belief", "beliefs", "transformation",
        "empowerment", "positivity", "reflection",
        "vulnerability", "authenticity",
    }),
}

# Detection priority: more specific / distinctive categories first.
# CATEGORY_GENERAL is the implicit fallback and is not in this list.
_CATEGORY_DETECTION_ORDER: list[str] = [
    CATEGORY_ANIMAL,
    CATEGORY_MUSIC,
    CATEGORY_TECHNOLOGY,
    CATEGORY_SCIENCE,
    CATEGORY_HEALTH,
    CATEGORY_BUSINESS,
    CATEGORY_HISTORY,
    CATEGORY_TRAVEL,
    CATEGORY_SPORTS,
    CATEGORY_EDUCATION,
    CATEGORY_ABSTRACT,
]

# ---------------------------------------------------------------------------
# Per-category shot plans – each entry is (shot_type_label, prompt_template).
# Templates receive a single ``{subject}`` substitution.
# ---------------------------------------------------------------------------

_CATEGORY_PLANS: dict[str, list[tuple[str, str]]] = {
    CATEGORY_ANIMAL: [
        (
            "animal_establishing",
            "Wide establishing shot of {subject} in natural habitat, full environment "
            "visible, lush surroundings, animal present in scene, "
            "photorealistic vertical 9:16",
        ),
        (
            "animal_medium_fullbody",
            "Medium full-body shot of {subject} near its burrow or home, full body "
            "and paws visible, natural daylight, photorealistic vertical 9:16",
        ),
        (
            "animal_foraging",
            "Dynamic shot of {subject} foraging or eating, natural behaviour and "
            "movement clearly visible, photorealistic vertical 9:16",
        ),
        (
            "animal_habitat_detail",
            "Ground-level detail shot of {subject} burrow, nest, or den entrance, "
            "habitat texture and environment context visible, "
            "photorealistic vertical 9:16",
        ),
        (
            "animal_ecosystem_wide",
            "Wide ecosystem shot with {subject} small in frame, surrounded by "
            "plants, flowers, and natural landscape, environmental context, "
            "photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_MUSIC: [
        (
            "music_establishing",
            "Wide atmospheric shot of concert hall, stage, or recording studio for "
            "{subject}, dramatic stage lighting, photorealistic vertical 9:16",
        ),
        (
            "music_performer_action",
            "Dynamic shot of musician performing {subject}, instrument in motion, "
            "expressive hands and body movement, photorealistic vertical 9:16",
        ),
        (
            "music_instrument_detail",
            "Close-up detail of musical instrument, mixing board, or recording "
            "equipment for {subject}, no readable labels or text, "
            "photorealistic vertical 9:16",
        ),
        (
            "music_crowd_energy",
            "Wide crowd or audience shot during {subject} performance, movement, "
            "energy, and emotion visible, photorealistic vertical 9:16",
        ),
        (
            "music_closing_wide",
            "Cinematic wide stage or outdoor festival panorama for {subject}, "
            "dramatic lighting and silhouettes, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_TECHNOLOGY: [
        (
            "tech_establishing",
            "Wide shot of modern technology workspace, data centre, or innovation "
            "lab for {subject}, photorealistic vertical 9:16",
        ),
        (
            "tech_human_interaction",
            "Person actively engaging with technology related to {subject}, "
            "focused and purposeful, photorealistic vertical 9:16",
        ),
        (
            "tech_concept_detail",
            "Close-up of circuit board, device screen, or interface for {subject}, "
            "no readable text or code visible, photorealistic vertical 9:16",
        ),
        (
            "tech_real_world_impact",
            "Real-world application scene showing the effect of {subject} technology "
            "on everyday life, photorealistic vertical 9:16",
        ),
        (
            "tech_closing_wide",
            "Futuristic cityscape or panoramic technology environment for {subject}, "
            "glowing lights and modern architecture, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_SCIENCE: [
        (
            "science_establishing",
            "Wide shot of natural environment, observatory, or research station for "
            "{subject}, photorealistic vertical 9:16",
        ),
        (
            "science_researcher_action",
            "Scientist or researcher at work studying {subject}, focused activity "
            "visible, photorealistic vertical 9:16",
        ),
        (
            "science_specimen_detail",
            "Microscopic, geological, or biological detail related to {subject}, "
            "textures and patterns visible, photorealistic vertical 9:16",
        ),
        (
            "science_ecological_context",
            "Ecological or experimental context for {subject}, natural processes "
            "in motion, photorealistic vertical 9:16",
        ),
        (
            "science_panoramic_wide",
            "Wide panoramic natural or scientific landscape featuring {subject}, "
            "scale and environment prominent, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_HEALTH: [
        (
            "health_establishing",
            "Wide healthy lifestyle or medical environment for {subject}, bright "
            "and clean setting, photorealistic vertical 9:16",
        ),
        (
            "health_activity",
            "Person engaged in wellness activity related to {subject}, movement "
            "and vitality visible, photorealistic vertical 9:16",
        ),
        (
            "health_detail",
            "Close-up detail of food, equipment, or body related to {subject}, "
            "no text labels or packaging visible, photorealistic vertical 9:16",
        ),
        (
            "health_emotional_context",
            "Calm and supportive social or emotional wellbeing scene for {subject}, "
            "natural expressions and warmth, photorealistic vertical 9:16",
        ),
        (
            "health_closing_wide",
            "Wide serene outdoor or wellness environment for {subject}, natural "
            "light and open space, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_BUSINESS: [
        (
            "business_establishing",
            "Wide shot of professional office, financial district, or commercial "
            "environment for {subject}, photorealistic vertical 9:16",
        ),
        (
            "business_collaboration",
            "Team collaborating or professional working on {subject}, engaged and "
            "focused, photorealistic vertical 9:16",
        ),
        (
            "business_detail",
            "Close-up of business tools, devices, or charts for {subject}, no "
            "readable text or numbers, photorealistic vertical 9:16",
        ),
        (
            "business_customer_context",
            "Customer interaction or product in use scene for {subject}, real-world "
            "commercial context, photorealistic vertical 9:16",
        ),
        (
            "business_closing_wide",
            "Wide professional environment panorama for {subject}, modern "
            "architecture and activity visible, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_HISTORY: [
        (
            "history_establishing",
            "Wide shot of historical setting, monument, or landscape for {subject}, "
            "authentic period atmosphere, photorealistic vertical 9:16",
        ),
        (
            "history_human_activity",
            "People in historical or cultural context engaged with {subject}, "
            "authentic period detail, photorealistic vertical 9:16",
        ),
        (
            "history_artifact_detail",
            "Close-up of historical artifact, architecture, or cultural object "
            "related to {subject}, no readable inscriptions, "
            "photorealistic vertical 9:16",
        ),
        (
            "history_cultural_context",
            "Cultural ceremony, traditional practice, or significant historical "
            "moment for {subject}, photorealistic vertical 9:16",
        ),
        (
            "history_panoramic_wide",
            "Wide panoramic historical or cultural landscape for {subject}, sense "
            "of place and time, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_TRAVEL: [
        (
            "travel_establishing",
            "Wide establishing shot of travel destination or natural landscape for "
            "{subject}, inviting and atmospheric, photorealistic vertical 9:16",
        ),
        (
            "travel_exploration",
            "Traveller actively exploring or experiencing {subject} location, "
            "movement and discovery visible, photorealistic vertical 9:16",
        ),
        (
            "travel_local_detail",
            "Local architecture, cuisine, or cultural object detail for {subject}, "
            "no visible text or signs, photorealistic vertical 9:16",
        ),
        (
            "travel_atmosphere",
            "Local street scene, market, or social activity for {subject} "
            "destination, vibrant and authentic, photorealistic vertical 9:16",
        ),
        (
            "travel_sunset_wide",
            "Panoramic sunset or golden hour wide shot of {subject} destination, "
            "dramatic light and landscape, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_SPORTS: [
        (
            "sports_establishing",
            "Wide establishing shot of sports stadium, venue, or outdoor sports "
            "setting for {subject}, photorealistic vertical 9:16",
        ),
        (
            "sports_athlete_action",
            "Dynamic athlete in motion performing {subject}, peak action and "
            "energy, photorealistic vertical 9:16",
        ),
        (
            "sports_equipment_detail",
            "Close-up of sports equipment or technique detail for {subject}, no "
            "visible branding text, photorealistic vertical 9:16",
        ),
        (
            "sports_competition_context",
            "Team competition, race, or match scene for {subject}, crowd and "
            "competitive atmosphere, photorealistic vertical 9:16",
        ),
        (
            "sports_closing_wide",
            "Wide panoramic sports environment or landscape with {subject} activity "
            "in context, dramatic lighting, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_EDUCATION: [
        (
            "education_establishing",
            "Wide shot of classroom, library, or inspiring learning environment "
            "for {subject}, photorealistic vertical 9:16",
        ),
        (
            "education_learning_activity",
            "Student or learner engaged with {subject} material, focused and "
            "curious, photorealistic vertical 9:16",
        ),
        (
            "education_concept_visual",
            "Visual diagram, map, model, or conceptual illustration for {subject}, "
            "no readable text labels, photorealistic vertical 9:16",
        ),
        (
            "education_instructor_context",
            "Teacher or expert sharing knowledge about {subject}, engaged "
            "interaction visible, photorealistic vertical 9:16",
        ),
        (
            "education_closing_wide",
            "Wide inspiring educational or discovery environment for {subject}, "
            "light and openness, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_ABSTRACT: [
        (
            "abstract_establishing",
            "Wide evocative environmental or symbolic scene suggesting {subject}, "
            "atmospheric and thought-provoking, photorealistic vertical 9:16",
        ),
        (
            "abstract_symbolic_action",
            "Person taking meaningful or transformative action related to {subject}, "
            "visual metaphor, photorealistic vertical 9:16",
        ),
        (
            "abstract_metaphorical_detail",
            "Close-up symbolic or metaphorical detail representing {subject}, "
            "textures and shapes, photorealistic vertical 9:16",
        ),
        (
            "abstract_emotional_context",
            "Emotionally resonant scene illustrating themes of {subject}, warmth "
            "and authenticity, photorealistic vertical 9:16",
        ),
        (
            "abstract_closing_wide",
            "Cinematic wide shot with hopeful or inspiring atmosphere embodying "
            "{subject}, golden light and movement, photorealistic vertical 9:16",
        ),
    ],
    CATEGORY_GENERAL: [
        (
            "establishing",
            "Wide establishing shot featuring {subject}, full environment clearly "
            "visible, natural setting, golden hour lighting, photorealistic vertical 9:16",
        ),
        (
            "medium",
            "Medium shot of {subject}, full body and surrounding context visible, "
            "natural lighting, photorealistic vertical 9:16",
        ),
        (
            "action",
            "Dynamic action shot of {subject} in motion or engaged in activity, "
            "energetic composition, photorealistic vertical 9:16",
        ),
        (
            "detail",
            "Contextual detail shot of {subject} within their ecosystem, environment "
            "and surroundings prominent, photorealistic vertical 9:16",
        ),
        (
            "wide_closing",
            "Wide panoramic shot with {subject} visible in a broader landscape, "
            "emphasizing scale and natural surroundings, photorealistic vertical 9:16",
        ),
    ],
}

# Backward-compatibility aliases kept so that callers referencing the old
# module-level names continue to work without modification.
_ANIMAL_SHOT_PLAN: list[tuple[str, str]] = _CATEGORY_PLANS[CATEGORY_ANIMAL]
_GENERAL_SHOT_PLAN: list[tuple[str, str]] = _CATEGORY_PLANS[CATEGORY_GENERAL]

# Suffix appended to every shot-plan prompt to discourage the image model
# from repeating the same composition across a batch of images.
_ANTI_REPETITION_SUFFIX = (
    "Use a distinct framing and composition from previous images in this set."
)

# ---------------------------------------------------------------------------
# Context-aware visual prompt constants
# ---------------------------------------------------------------------------

# Tags that signal a public event / live-event atmosphere.
_EVENT_TYPE_TAGS: frozenset[str] = frozenset({
    "festival", "ceremony", "event", "concert", "celebration",
    "gathering", "parade", "fair", "carnival", "show", "exhibition",
    "competition", "tournament", "rally", "performance", "gala",
})

# Tags that signal crowd / people context.
_CROWD_TYPE_TAGS: frozenset[str] = frozenset({
    "crowd", "audience", "people", "spectators", "fans", "community",
    "public", "visitors", "attendees",
})

# Season keyword sets (lowercase).
_SEASON_WORDS: dict[str, frozenset[str]] = {
    "winter": frozenset({
        "winter", "snow", "cold", "ice", "frost", "frozen",
        "february", "january", "december",
    }),
    "spring": frozenset({
        "spring", "bloom", "blossoms", "flowers", "april", "march", "sprout",
    }),
    "summer": frozenset({
        "summer", "hot", "july", "august", "heat",
    }),
    "autumn": frozenset({
        "autumn", "fall", "leaves", "october", "november", "harvest",
    }),
}

# Well-known named events: (lowercase_search_pattern, canonical_display_name)
_NAMED_EVENT_PATTERNS: list[tuple[str, str]] = [
    ("groundhog day", "Groundhog Day"),
    ("super bowl", "Super Bowl"),
    ("new year", "New Year"),
    ("christmas", "Christmas"),
    ("halloween", "Halloween"),
    ("thanksgiving", "Thanksgiving"),
    ("independence day", "Independence Day"),
    ("mardi gras", "Mardi Gras"),
    ("fourth of july", "Fourth of July"),
    ("st. patrick", "St. Patrick's Day"),
    ("saint patrick", "St. Patrick's Day"),
    ("valentine", "Valentine's Day"),
    ("midsummer", "Midsummer"),
    ("oktoberfest", "Oktoberfest"),
]

# Capitalised words that are never treated as location names.
_NON_LOCATION_CAPS: frozenset[str] = frozenset({
    "The", "A", "An", "It", "He", "She", "They", "We", "I", "You",
    "This", "That", "These", "Those", "My", "Your", "His", "Her",
    "Our", "Their", "Its", "If", "As", "But", "And", "Or", "So",
    "When", "Where", "What", "Who", "Which", "Why", "How",
    "For", "With", "From", "Into", "Onto", "Upon", "Over",
})

# Threshold below which a specificity score is flagged as too generic.
# The score is 0–10 and accumulates from:
#   +2 if the resolved subject appears in the prompt
#   +1 per visual tag found in the prompt (capped at 2)
#   +2 if a named location appears after a preposition ("in Punxsutawney")
#   +1 if a named event appears (Groundhog Day, Super Bowl …)
#   +1 if a season is mentioned (winter, spring …)
#   +1 if a crowd term is present (crowd, spectators, audience …)
# A score of 2 means only the subject is present — no event/tag/location context.
_SPECIFICITY_WARNING_THRESHOLD: int = 2


# ---------------------------------------------------------------------------
# Subject grounding helpers
# ---------------------------------------------------------------------------


def _dedup_visual_tags(tags: list[str]) -> list[str]:
    """Deduplicate tags, collapsing simple singular/plural pairs.

    ``["groundhog", "groundhogs"]`` → ``["groundhog"]``

    The shorter (singular) form is kept.  Order among non-duplicate tags is
    preserved (shortest first due to the sort, which naturally keeps the
    canonical singular).
    """
    # Sort by length so the singular form (shorter) is processed first.
    sorted_tags = sorted(tags, key=len)
    result: list[str] = []
    seen_lower: set[str] = set()
    for tag in sorted_tags:
        lower = tag.lower().strip()
        if not lower or lower in seen_lower:
            continue
        # Drop this tag if it is the plural of an already-accepted tag.
        is_plural = any(
            lower == existing + "s" or lower == existing + "es"
            for existing in seen_lower
        )
        if not is_plural:
            result.append(tag.strip())
            seen_lower.add(lower)
    return result


def _filter_generic_tags(
    tags: list[str],
) -> tuple[list[str], list[str]]:
    """Split *tags* into ``(specific, generic)`` lists.

    A tag is considered *generic* when its lower-case value matches one of
    the known broad category labels in :data:`_GENERIC_TOPIC_WORDS`.
    """
    specific: list[str] = []
    generic: list[str] = []
    for tag in tags:
        if tag.lower().strip() in _GENERIC_TOPIC_WORDS:
            generic.append(tag)
        else:
            specific.append(tag)
    return specific, generic


def _join_specific_tags(specific_tags: list[str]) -> str:
    """Combine up to two specific tags into a subject phrase.

    ``["groundhog"]`` → ``"groundhog"``
    ``["jazz", "saxophone"]`` → ``"jazz saxophone"``
    """
    if len(specific_tags) == 1:
        return specific_tags[0]
    return " ".join(specific_tags[:2])


def resolve_visual_subject(
    topic: str,
    visual_tags: list[str] | None = None,
    block_text: str = "",
) -> tuple[str, str]:
    """Resolve the most specific concrete visual subject available.

    The fix for generic-topic grounding: when the *topic* is a broad category
    label (e.g. ``"animals"``, ``"music"``) and *visual_tags* contain a more
    concrete entity, the tags win.  When the topic is already specific (e.g.
    ``"ancient rome"``, ``"beekeeping"``), the topic takes priority as before.

    Priority:
    1. Specific (non-generic) *visual_tags* **when topic is generic or absent**.
    2. *topic* when it is concise (≤ 5 words) and not a generic category
       label.
    3. Specific *visual_tags* even when topic is specific but too long to use
       (> 5 words).
    4. A noun phrase extracted from *block_text*.
    5. *topic* of any length as a fallback (even if generic).
    6. ``"abstract cinematic scene"`` (last resort).

    Returns:
        ``(subject, source)`` where *source* is one of
        ``"visual_tags"``, ``"topic"``, ``"block_text"``, or
        ``"fallback"``.
    """
    tags = _dedup_visual_tags(list(visual_tags or []))
    specific_tags, ignored_generic = _filter_generic_tags(tags)

    if ignored_generic:
        logger.debug(
            "ignored_generic_terms",
            ignored=ignored_generic,
            specific_kept=specific_tags,
        )

    stripped_topic = topic.strip()
    topic_lower = stripped_topic.lower()
    topic_is_generic = topic_lower in _GENERIC_TOPIC_WORDS

    # 1. Specific visual_tags win when topic is generic or absent — this is
    #    the core grounding fix: "animals" + ["groundhog"] → "groundhog".
    if specific_tags and (topic_is_generic or not stripped_topic):
        return _join_specific_tags(specific_tags), "visual_tags"

    # 2. Topic when concise and specific (not a broad category label).
    topic_words = stripped_topic.split()
    is_concise = bool(stripped_topic) and len(topic_words) <= 5
    is_specific = not topic_is_generic
    if is_concise and is_specific and len(stripped_topic) >= _MIN_SUBJECT_LENGTH:
        return stripped_topic, "topic"

    # 3. Specific visual_tags as secondary option when topic is long.
    if specific_tags:
        return _join_specific_tags(specific_tags), "visual_tags"

    # 4. Extract a noun phrase from block_text.
    if block_text:
        cleaned = _strip_conversational(block_text)
        first_sentence = re.split(r"[.!?]", cleaned)[0].strip()
        words = first_sentence.split()[:_SUBJECT_MAX_WORDS]
        phrase = " ".join(words).strip(".,!?")
        if len(phrase) >= _MIN_SUBJECT_LENGTH:
            return phrase, "block_text"

    # 5. Fallback: use topic even if generic (better than nothing).
    if stripped_topic:
        return stripped_topic, "fallback"

    return "abstract cinematic scene", "fallback"


# ---------------------------------------------------------------------------
# Context extraction helpers
# ---------------------------------------------------------------------------


def extract_visual_context(
    block_text: str,
    visual_tags: list[str] | None = None,
    topic: str = "",
    full_script_text: str | None = None,
) -> dict:
    """Extract concrete visual context from narration text and visual tags.

    Detects:
    - Event type (festival, ceremony, concert …) from tags then block text
    - Named events (Groundhog Day, Super Bowl …) from block + script text
    - Location (capitalised proper nouns after "in …")
    - Season (winter / spring / summer / autumn)
    - Time of day (morning, evening …)
    - Crowd / people presence
    - Weather / shadow / prediction context
    - Celebration / festive atmosphere

    Args:
        block_text:       Raw narration text for the current block.
        visual_tags:      Explicit user-supplied visual tags.
        topic:            Global video topic / title.
        full_script_text: Full script for global context (optional).

    Returns:
        Dict with keys: ``event_type``, ``named_events``, ``location``,
        ``season``, ``time_of_day``, ``has_crowd``, ``has_weather``,
        ``has_celebration``, ``context_terms``.
    """
    tags_lower = [t.lower().strip() for t in (visual_tags or [])]
    block_lower = block_text.lower()
    # Combine block + full script for global context lookups (season, events).
    search_text = block_lower + " " + (full_script_text or "").lower()

    ctx: dict = {}

    # --- Event type ---
    # Tags take priority; fall through to block text only as backup.
    event_type: str | None = next(
        (t for t in tags_lower if t in _EVENT_TYPE_TAGS), None
    )
    if not event_type:
        event_type = next(
            (w for w in _EVENT_TYPE_TAGS if re.search(r"\b" + w + r"\b", block_lower)),
            None,
        )
    ctx["event_type"] = event_type

    # --- Named events ---
    named_events: list[str] = []
    for pattern, canonical_name in _NAMED_EVENT_PATTERNS:
        if pattern in search_text:
            named_events.append(canonical_name)
    ctx["named_events"] = named_events

    # --- Location extraction ---
    # Look for the pattern "in <TitleCase>" in block text first, then script.
    location: str | None = None
    for search_src in (block_text, full_script_text or ""):
        loc_match = re.search(
            r"\bin ([A-Z][a-z]+(?:[\s\-][A-Z][a-z]+)*)",
            search_src,
        )
        if loc_match:
            candidate = loc_match.group(1)
            if candidate not in _NON_LOCATION_CAPS:
                location = candidate
                break
    ctx["location"] = location

    # --- Season ---
    season: str | None = None
    search_words = set(re.findall(r"\b\w+\b", search_text))
    for s_name, s_words in _SEASON_WORDS.items():
        if s_words.intersection(search_words):
            season = s_name
            break
    ctx["season"] = season

    # --- Time of day ---
    tod_match = re.search(
        r"\b(morning|afternoon|evening|night|dawn|dusk|sunrise|sunset|midday|midnight)\b",
        block_lower,
    )
    ctx["time_of_day"] = tod_match.group(1) if tod_match else None

    # --- Crowd context ---
    _crowd_words = {
        "crowd", "people", "gathered", "gathering", "spectators", "audience",
        "fans", "bundled", "waiting", "attendees", "visitors", "onlookers",
        "bystanders", "residents", "townspeople", "everyone",
    }
    ctx["has_crowd"] = bool(
        _crowd_words.intersection(set(block_lower.split()))
        or set(tags_lower).intersection(_CROWD_TYPE_TAGS)
    )

    # --- Weather / prediction context ---
    ctx["has_weather"] = bool(
        re.search(
            r"\b(shadow|predict|forecast|weather|temperature)\b",
            block_lower,
        )
    )

    # --- Celebration / festive context ---
    ctx["has_celebration"] = bool(
        re.search(r"\b(celebrat|cheer|joy|happy|festiv|excit|delight)\w*\b", block_lower)
        or bool(set(tags_lower).intersection({"celebration", "festival", "festive", "joyful"}))
    )

    # --- Context terms for logging ---
    terms: list[str] = []
    if ctx.get("event_type"):
        terms.append(ctx["event_type"])
    terms.extend(ctx["named_events"])
    if ctx.get("location"):
        terms.append(ctx["location"])
    if ctx.get("season"):
        terms.append(ctx["season"])
    if ctx.get("has_crowd"):
        terms.append("crowd")
    if ctx.get("has_weather"):
        terms.append("weather_context")
    ctx["context_terms"] = terms

    return ctx


def _build_context_aware_prompt(
    shot_type: str,
    subject: str,
    context: dict,
) -> str | None:
    """Build a context-enriched prompt using scene context.

    Returns ``None`` when context is insufficient to meaningfully override the
    category-plan template (caller falls back to the template as before).

    Enrichment requires at least one of: event_type, named_events, location,
    or has_crowd.  Season alone is not enough — the template handles it fine.

    Args:
        shot_type: Shot-type label from the category plan (e.g.
                   ``"animal_establishing"``).
        subject:   Resolved visual subject (e.g. ``"groundhog"``).
        context:   Dict returned by :func:`extract_visual_context`.

    Returns:
        A specific visual prompt string, or ``None`` to fall back.
    """
    event_type = context.get("event_type")
    named_events: list[str] = context.get("named_events", [])
    location = context.get("location")
    season = context.get("season")
    tod = context.get("time_of_day")
    has_crowd = context.get("has_crowd", False)
    has_weather = context.get("has_weather", False)
    has_celebration = context.get("has_celebration", False)

    # Need meaningful context — season-only is not enough.
    has_meaningful = any([event_type, bool(named_events), location, has_crowd])
    if not has_meaningful:
        return None

    # --- Build scene setting descriptor ---
    event_name = named_events[0] if named_events else None

    if event_name and event_type and event_name.lower() not in event_type.lower() and event_type.lower() not in event_name.lower():
        scene_setting = f"{event_name} {event_type}"
    elif event_name:
        scene_setting = event_name
    elif event_type:
        scene_setting = event_type
    else:
        scene_setting = None

    loc_str = f"in {location}" if location else ""
    if scene_setting and loc_str:
        main_setting = f"{scene_setting} {loc_str}"
    elif scene_setting:
        main_setting = scene_setting
    elif loc_str:
        main_setting = f"scene {loc_str}"
    else:
        main_setting = None

    # --- Build atmosphere phrases ---
    atm_parts: list[str] = []
    if season and tod:
        atm_parts.append(f"{season} {tod}")
    elif season:
        atm_parts.append(season)
    elif tod:
        atm_parts.append(tod)
    if has_crowd:
        atm_parts.append("crowd gathered")
    if has_celebration and event_type:
        atm_parts.append("festive atmosphere")

    # --- Map shot-type to composition prefix ---
    st = shot_type.lower()
    if "establishing" in st:
        comp = "Wide establishing shot"
    elif "medium" in st or "fullbody" in st or "full_body" in st:
        comp = "Medium shot"
    elif "foraging" in st or "action" in st:
        comp = "Dynamic shot"
    elif "detail" in st:
        comp = "Close-up detail shot"
    elif "closing" in st or "ecosystem" in st or "panoramic" in st or "wide" in st:
        comp = "Cinematic wide shot"
    else:
        comp = "Shot"

    # --- Assemble the prompt ---
    result: list[str] = []

    if "detail" in st and has_weather:
        # Special case: detail slot + weather context → shadow/prediction shot.
        result.append(f"Ground-level shot of {subject} looking toward shadow")
        if main_setting:
            result.append("public ceremony context")
        if season:
            result.append(f"{season} ground")
        result.append("photorealistic vertical 9:16")
        return ", ".join(p for p in result if p)

    if "foraging" in st and has_crowd:
        # Crowd-reaction slot: show the people waiting for the subject.
        result.append(
            f"Crowd of bundled-up people at {main_setting}"
            if main_setting else "Crowd of people"
        )
        if has_weather:
            result.append(f"waiting for {subject} weather prediction")
        else:
            result.append(f"waiting for {subject}")
        result.extend(atm_parts)
        result.append("photorealistic vertical 9:16")
        return ", ".join(p for p in result if p)

    if "closing" in st or "ecosystem" in st:
        if has_celebration or event_type:
            result.append(
                f"Wide joyful celebration at {main_setting}"
                if main_setting else f"Wide celebration shot featuring {subject}"
            )
        else:
            result.append(
                f"Wide shot of {main_setting}"
                if main_setting else f"Wide shot featuring {subject}"
            )
        result.extend(p for p in atm_parts if "crowd" not in p.lower())
        result.append(f"{subject} ceremony atmosphere")
        result.append("photorealistic vertical 9:16")
        return ", ".join(p for p in result if p)

    # --- Default path for establishing / medium / other ---
    if main_setting:
        result.append(f"{comp} of {main_setting}")
    else:
        result.append(comp)

    result.extend(atm_parts)

    # Ensure subject is mentioned somewhere in the prompt.
    subj_lower = subject.lower()
    combined_lower = " ".join(result).lower()
    if subj_lower and subj_lower not in combined_lower:
        if "medium" in st or "fullbody" in st:
            result.append(f"{subject} in foreground")
        else:
            result.append(f"{subject} present")

    result.append("photorealistic vertical 9:16")
    return ", ".join(p for p in result if p)


def _score_prompt_specificity(
    prompt: str,
    subject: str,
    visual_tags: list[str],
    block_text: str,
) -> int:
    """Score prompt specificity on a 0–10 scale.

    Higher means more context-specific (named events, locations, crowd,
    season, event atmosphere, tag terms).

    Args:
        prompt:      The final visual prompt string.
        subject:     Resolved visual subject.
        visual_tags: User-supplied visual tags.
        block_text:  Raw narration block text.

    Returns:
        Integer in the range [0, 10].
    """
    score = 0
    p = prompt.lower()

    # Subject present (+2).
    if subject and subject.lower() in p:
        score += 2

    # Each visual tag matched (+1 each, max 3).
    tag_matches = sum(1 for t in visual_tags if t.lower() in p)
    score += min(tag_matches, 3)

    # Named event / location: capital word after a preposition (+2).
    if re.search(r"\b(?:in|at|of|near|from|during)\s+[A-Z][a-z]{3,}", prompt):
        score += 2

    # Event / ceremony atmosphere (+1).
    if re.search(r"\b(festival|ceremony|event|celebration|concert|gathering)\b", p):
        score += 1

    # Season / atmosphere (+1).
    if re.search(r"\b(winter|summer|spring|autumn|morning|evening|cold|warm)\b", p):
        score += 1

    # Crowd / people (+1).
    if re.search(r"\b(crowd|people|gathered|audience|bundled|spectators)\b", p):
        score += 1

    return min(score, 10)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_visual_category(
    topic: str,
    scene_text: str = "",
    visual_tags: list[str] | None = None,
) -> str:
    """Return the visual category that best describes the content.

    Detection priority:
    1. *visual_tags* — explicit tags supplied by the user (highest signal).
    2. *topic* / title — the video subject.
    3. *scene_text* — raw narration text (lowest signal).

    Keywords from all three sources are matched against each category's
    keyword set in a fixed priority order.  The first category whose keywords
    overlap with the combined text is returned.  When no category matches,
    :data:`CATEGORY_GENERAL` is returned as a fallback.

    Args:
        topic:       Video title or subject hint (e.g. ``"guitar lessons"``).
        scene_text:  Optional raw narration text for additional signal.
        visual_tags: Optional list of explicit visual tags (e.g.
                     ``["architecture", "soldiers"]``).  These are checked
                     *before* topic and scene text so that a tag such as
                     ``"history"`` overrides a vague topic like
                     ``"interesting facts"``.

    Returns:
        One of the ``CATEGORY_*`` string constants defined in this module.
    """
    # Build separate word sets so that tags get priority over topic/text.
    tag_words: frozenset[str] = frozenset(
        re.findall(r"\b\w+\b", " ".join(visual_tags or []).lower())
    )
    topic_words: frozenset[str] = frozenset(
        re.findall(r"\b\w+\b", f"{topic} {scene_text}".lower())
    )
    combined_words = tag_words | topic_words

    # First pass: check tags-only words for a match (highest priority).
    if tag_words:
        for category in _CATEGORY_DETECTION_ORDER:
            if _CATEGORY_KEYWORDS[category].intersection(tag_words):
                return category

    # Second pass: check topic + scene text.
    for category in _CATEGORY_DETECTION_ORDER:
        if _CATEGORY_KEYWORDS[category].intersection(combined_words):
            return category

    return CATEGORY_GENERAL


def build_image_prompt(
    scene_text: str,
    topic: str = "",
    *,
    block_index: int = 0,
    total_blocks: int = 1,
    previous_prompts: list[str] | None = None,
    visual_tags: list[str] | None = None,
    full_script_text: str | None = None,
) -> str:
    """Return a visual-only image prompt for *scene_text*.

    When ``settings.VISUAL_SHOT_PLAN_ENABLED`` is ``True`` (the default) the
    function detects a :func:`visual category <detect_visual_category>` from
    the topic, visual tags, and scene text, selects the matching shot plan,
    rotates through shot types based on *block_index*, and appends an
    anti-repetition constraint so that an image model never produces identical
    frames for the same subject.

    When context is available (visual_tags include event/festival/crowd,
    block text mentions locations or named events, etc.) the shot-plan
    template is replaced with a context-aware description that reflects the
    actual story being narrated.

    When ``VISUAL_SHOT_PLAN_ENABLED`` is ``False`` the legacy behaviour is
    preserved: raw narration is cleaned of conversational phrases and wrapped
    in a generic cinematic framing sentence.

    Args:
        scene_text:       Raw narration text for the scene.
        topic:            Global topic / title hint (e.g. the video title).
        block_index:      Zero-based position of this block in the sequence.
        total_blocks:     Total number of blocks in the video.
        previous_prompts: Prompts already generated for preceding blocks
                          (reserved for future similarity checks).
        visual_tags:      Optional list of explicit visual tags supplied by
                          the user to guide category detection and subject
                          extraction.
        full_script_text: Full narration script text for global context
                          extraction (locations, named events, season).

    Returns:
        A clean, visual-only prompt string ready to send to an image model.
    """
    if settings.VISUAL_SHOT_PLAN_ENABLED:
        return _build_shot_plan_prompt(
            scene_text,
            topic,
            block_index=block_index,
            total_blocks=total_blocks,
            previous_prompts=previous_prompts,
            visual_tags=visual_tags,
            full_script_text=full_script_text,
        )

    # ── Legacy path ──────────────────────────────────────────────────────────
    cleaned = _strip_conversational(scene_text)
    if _is_non_visual(cleaned):
        visual_core = _fallback_description(scene_text, topic)
    else:
        visual_core = cleaned
    prompt = _wrap_cinematic(visual_core)
    return _append_negative(prompt)


# ---------------------------------------------------------------------------
# Shot-plan helpers
# ---------------------------------------------------------------------------


def _build_shot_plan_prompt(
    scene_text: str,
    topic: str,
    *,
    block_index: int,
    total_blocks: int,
    previous_prompts: list[str] | None,
    visual_tags: list[str] | None = None,
    full_script_text: str | None = None,
) -> str:
    """Build a shot-plan prompt for *scene_text* at position *block_index*.

    When the block or script contains rich context (event/festival tags,
    named events, locations, crowd descriptions) the generic category-plan
    template is overridden with a context-aware prompt that reflects the
    actual story.  Detailed logs are emitted for observability.
    """
    category = detect_visual_category(topic, scene_text, visual_tags=visual_tags)
    plan = _CATEGORY_PLANS.get(category, _CATEGORY_PLANS[CATEGORY_GENERAL])
    subject, subject_source = resolve_visual_subject(
        topic, visual_tags=visual_tags, block_text=scene_text
    )
    shot_idx = block_index % len(plan)
    shot_type, template = plan[shot_idx]

    # ── Extract visual context from block + script ────────────────────────
    visual_context = extract_visual_context(
        scene_text,
        visual_tags,
        topic,
        full_script_text,
    )
    context_terms = visual_context.get("context_terms", [])

    logger.info(
        "visual_context_extracted",
        block_index=block_index,
        context_terms=context_terms,
        visual_tags_used=visual_tags or [],
        event_type=visual_context.get("event_type"),
        location=visual_context.get("location"),
        named_events=visual_context.get("named_events", []),
        season=visual_context.get("season"),
        has_crowd=visual_context.get("has_crowd"),
    )

    # ── Attempt context-enriched prompt ──────────────────────────────────
    enriched = _build_context_aware_prompt(shot_type, subject, visual_context)
    if enriched is not None:
        visual_core = enriched
        used_context = True
    else:
        visual_core = template.format(subject=subject)
        used_context = False

    # ── Validate specificity ──────────────────────────────────────────────
    specificity_score = _score_prompt_specificity(
        visual_core, subject, visual_tags or [], scene_text
    )

    logger.info(
        "visual_prompt_built",
        block_index=block_index,
        total_blocks=total_blocks,
        detected_visual_category=category,
        shot_type=shot_type,
        resolved_visual_subject=subject,
        subject_source=subject_source,
        visual_tags=visual_tags or [],
        context_terms=context_terms,
        used_context_enrichment=used_context,
        prompt_specificity_score=specificity_score,
        final_visual_prompt=visual_core,
    )

    if specificity_score < _SPECIFICITY_WARNING_THRESHOLD:
        logger.warning(
            "visual_prompt_too_generic",
            block_index=block_index,
            subject=subject,
            specificity_score=specificity_score,
            prompt_preview=visual_core[:120],
            context_terms=context_terms,
            hint="Add more specific visual_tags or enrich the script text",
        )

    # Warn when the resolved subject does not appear in the final prompt.
    if subject and subject.lower() not in visual_core.lower():
        logger.warning(
            "visual_prompt_subject_missing",
            resolved_visual_subject=subject,
            subject_source=subject_source,
            final_visual_prompt=visual_core,
        )

    prompt = _append_negative(visual_core)
    return f"{prompt} {_ANTI_REPETITION_SUFFIX}"


def _extract_subject(
    scene_text: str,
    topic: str,
    visual_tags: list[str] | None = None,
) -> str:
    """Return the visual subject to use in a shot-plan template.

    Delegates to :func:`resolve_visual_subject` which applies strong subject
    grounding: specific *visual_tags* always win over generic category topics.

    Priority (via :func:`resolve_visual_subject`):
    1. Specific (non-generic) *visual_tags*.
    2. *topic* when concise and not a generic category label.
    3. Noun phrase extracted from *scene_text*.
    4. *topic* (any length) as a fallback.
    5. ``"abstract cinematic scene"`` as a last resort.
    """
    subject, _ = resolve_visual_subject(topic, visual_tags=visual_tags, block_text=scene_text)
    return subject


def _is_animal_subject(subject: str) -> bool:
    """Return ``True`` when *subject* contains a known animal keyword.

    .. deprecated::
        Use :func:`detect_visual_category` directly.  This shim is kept for
        backward compatibility with existing callers.
    """
    return detect_visual_category(subject) == CATEGORY_ANIMAL


# ---------------------------------------------------------------------------
# Legacy helpers (also used by the legacy path in build_image_prompt)
# ---------------------------------------------------------------------------


def _strip_conversational(text: str) -> str:
    """Remove conversational / direct-address phrases from *text*."""
    # Remove quoted strings (they reproduce spoken words verbatim).
    no_quotes = re.sub(r'"[^"]*"', "", text)
    no_quotes = re.sub(rf"'[^']{{0,{_MAX_SINGLE_QUOTE_LENGTH}}}'", "", no_quotes)

    # Remove matched conversational phrases.
    cleaned = _PHRASE_RE.sub("", no_quotes)

    # Collapse extra whitespace / punctuation left by removals.
    cleaned = re.sub(r"[,!?.]*\s{2,}", " ", cleaned)
    cleaned = re.sub(r"^\s*[,!?.]+\s*", "", cleaned)
    cleaned = cleaned.strip(" ,!?.")
    return cleaned


def _is_non_visual(text: str) -> bool:
    """Return True when *text* is too short or conversational to be visual."""
    return len(text.strip()) < _MIN_VISUAL_LENGTH


def _fallback_description(original_text: str, topic: str) -> str:
    """Create a generic visual description when scene text is non-visual.

    Tries to extract concrete nouns / descriptive fragments; falls back to
    the *topic* hint when nothing useful remains.
    """
    # Try a light extraction: remove filler words and keep the longest fragment.
    stripped = _strip_conversational(original_text)
    words = stripped.split()
    # Remove single-character tokens (punctuation residue).
    words = [w for w in words if len(w) > 1]
    candidate = " ".join(words).strip(" ,!?.")

    if len(candidate) >= _MIN_VISUAL_LENGTH:
        return candidate

    # Fall back to the topic string if provided.
    if topic and topic.strip():
        return topic.strip()

    # Last resort: abstract visually appealing scene.
    return "cinematic natural landscape, golden hour lighting"


def _wrap_cinematic(visual_core: str) -> str:
    """Wrap *visual_core* in a cinematic framing with style suffixes."""
    core = visual_core[:1].upper() + visual_core[1:] if visual_core else visual_core
    return (
        f"{core}, dramatic cinematic lighting, photorealistic, "
        f"high detail, vertical 9:16"
    )


def _append_negative(prompt: str) -> str:
    """Append the configured negative prompt suffix to *prompt*."""
    suffix = settings.AI_IMAGE_NEGATIVE_PROMPT.strip()
    if not suffix:
        return prompt
    return f"{prompt}. {suffix}"
