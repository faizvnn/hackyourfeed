"""Guest categories for the Oriane pull (stage 3).

Oriane is keyword search; it does not know that "interviews with founders" means "clips of Sam Altman,
Hormozi and Diary of a CEO". We encode that here: each category is a set of podcast / clip accounts whose
short-form posts ARE the viral interview clips in that lane, plus the canonical famous names an episode
guest may be compared to. Verified against Oriane's profile search on Nov 6 (IG + TikTok, all handles exist).

Fallback only: stage 3 prefers Understanding.references (shows / people with aliases, hashtags, handles) when stage 2
provides them. Stage 2 may set Understanding.category directly; otherwise `pick(u)` matches niche/topic words.
"""

from __future__ import annotations

from .contracts import Understanding

CATEGORIES: dict[str, dict[str, list[str]]] = {
    "founders_tech": {
        "match": ["founder", "startup", "tech", "software", "engineer", "developer", "coding", "ai", "saas", "venture",
                  "vc", "entrepreneur", "business", "ceo", "product", "programming"],
        "handles": ["wealth", "steven", "thediaryofaceopodcast", "diaryofaceoclip", "garyvee", "hormozi", "ahormozi",
                    "leilahormozi", "codiesanchez", "realcodiesanchez", "chriswillx", "lexfridman", "ycombinator",
                    "colinandsamir", "dwarkesh", "tbpn", "sourcerypod", "profgmarkets", "figuringout.co", "theallinpod"],
        "names": ["Sam Altman", "Elon Musk", "Mark Zuckerberg", "Jensen Huang", "Alex Hormozi", "Steven Bartlett",
                  "Peter Thiel", "Marc Andreessen", "Naval Ravikant", "Paul Graham", "Garry Tan", "Brian Chesky"],
    },
    "creators_social": {
        "match": ["creator", "youtuber", "influencer", "social media", "content", "tiktok", "instagram", "streamer",
                  "vlog", "comedy", "comedian", "podcast host"],
        "handles": ["colinandsamir", "loganpaul", "impaulsive", "mrbeast", "garyvee", "ksi", "jakepaul", "fullsendpodcast",
                    "nelkboys", "andrewschulz", "zane", "chrisvanvliet", "callherdaddy", "caseyneistat", "mkbhd", "airrack",
                    "rhettandlink"],
        "names": ["Logan Paul", "MrBeast", "KSI", "Jake Paul", "Casey Neistat", "Marques Brownlee", "Alex Cooper",
                  "Andrew Schulz", "Theo Von", "Emma Chamberlain"],
    },
    "health_science": {
        "match": ["health", "fitness", "neuroscience", "doctor", "medical", "sleep", "nutrition", "longevity", "mental",
                  "psychology", "wellness", "science", "biology", "mindset", "habit", "self-improvement"],
        "handles": ["hubermanlab", "melrobbins", "themelrobbinspodcast", "jayshetty", "peterattiamd", "drmarkhyman",
                    "thediaryofaceopodcast", "bryanjohnson_", "lewishowes", "richroll", "foundmyfitness"],
        "names": ["Andrew Huberman", "Mel Robbins", "Jay Shetty", "Peter Attia", "Bryan Johnson", "Mark Hyman",
                  "Rhonda Patrick", "Gabor Mate", "Jordan Peterson"],
    },
    "money_finance": {
        "match": ["money", "finance", "investing", "invest", "stocks", "crypto", "real estate", "wealth", "budget",
                  "debt", "retire", "economy", "markets", "personal finance"],
        "handles": ["codiesanchez", "profgmarkets", "profgalloway", "ramit", "grahamstephan", "humphreytalks", "daveramsey",
                    "georgekamel", "nischa.me", "tori.dunlap", "herfirst100k"],
        "names": ["Scott Galloway", "Codie Sanchez", "Ramit Sethi", "Dave Ramsey", "Graham Stephan", "Warren Buffett",
                  "Ray Dalio", "Robert Kiyosaki"],
    },
}

DEFAULT = "founders_tech"


def pick(u: Understanding) -> str:
    """Category named by stage 2, else the one whose match words appear most in niche + topics + summary."""
    if u.category in CATEGORIES:
        return u.category
    text = " ".join([u.niche, u.summary, *u.topics]).lower()
    scores = {c: sum(text.count(w) for w in spec["match"]) for c, spec in CATEGORIES.items()}
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 0 else DEFAULT


def handles(u: Understanding, category: str) -> list[str]:
    """Episode-specific accounts from stage 2 first, then the category's accounts. Deduped, order kept."""
    seen: dict[str, None] = {}
    for h in [*u.competitor_handles, *CATEGORIES[category]["handles"]]:
        h = h.strip().lstrip("@").lower()
        if h:
            seen.setdefault(h)
    return list(seen)
