"""Offline sources + the two search tools subagents can use."""
import os

WEB = [
    {"url": "https://example.org/ai-music-2026", "title": "AI tools reshape music production",
     "text": "Survey of 1,200 producers: 64% use AI for mastering or stem separation. Session musician "
             "bookings fell 18% year on year in pop and advertising work."},
    {"url": "https://example.org/visual-artists-licensing", "title": "Illustrators push for licensing deals",
     "text": "Several stock-image platforms now pay contributors when their images are used to train "
             "models. Payouts averaged under $40 per artist in the first year."},
    {"url": "https://example.org/film-vfx-jobs", "title": "VFX studios automate rotoscoping",
     "text": "Large VFX houses report rotoscoping and cleanup time down 50-70%. Entry-level roles shrank "
             "while demand for pipeline TDs grew."},
    {"url": "https://example.org/writers-guild", "title": "Writers' contracts add AI clauses",
     "text": "New screenwriting contracts bar studios from crediting AI as a writer and require disclosure "
             "when AI-generated material is handed to writers."},
]
REPORTS = [
    {"doc": "Creative-Economy-Outlook-2026.pdf", "page": 12,
     "text": "Total creative-sector employment rose 2.1% despite automation, driven by game development "
             "and independent content creation."},
    {"doc": "Creative-Economy-Outlook-2026.pdf", "page": 31,
     "text": "Copyright litigation over training data: 40+ active cases; outcomes will set licensing norms "
             "for visual art and music."},
    {"doc": "Skills-Gap-Survey.pdf", "page": 4,
     "text": "Employers rank AI-assisted workflow skills as the top hiring gap for junior creative roles."},
]


def _words(s):
    return set("".join(c.lower() if c.isalnum() else " " for c in s).split())


def web_search(query):
    if os.environ.get("LAB_FAIL_WEB"):                      # used in Step 2.6 to simulate an outage
        raise TimeoutError("web search service is down")
    q = _words(query)
    hits = [d for d in WEB if q & _words(d["title"] + " " + d["text"])]
    return hits or [{"note": "no results", "query": query}]


def search_reports(query):
    q = _words(query)
    hits = [d for d in REPORTS if q & _words(d["text"])]
    return hits or [{"note": "no results", "query": query}]


TOOL_IMPLS = {"web_search": web_search, "search_reports": search_reports}
TOOL_SCHEMAS = {
    "web_search": {"name": "web_search", "description": "Search web articles. Returns url, title, text.",
                   "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                                    "required": ["query"]}},
    "search_reports": {"name": "search_reports",
                       "description": "Search internal PDF reports. Returns doc, page, text.",
                       "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                                        "required": ["query"]}},
}
