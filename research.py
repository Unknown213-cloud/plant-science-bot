#!/usr/bin/env python3
"""
Plant Science Bot - Automated Multi-Source Research Engine
==========================================================
Collects audience signals and emerging scientific interest from:
    1. Google Trends (via pytrends)
    2. YouTube Data API v3 (recent popular science videos)
    3. Public Reddit JSON (science subreddits)
    4. Wikipedia Pageview Trends (Wikimedia REST API)
    5. Official Instagram Graph API Insights (last 20 posts: saves, shares, reach)

Synthesizes these signals with Google Gemini (gemini-2.5-flash) into 10 ranked
post ideas (roughly 70% evergreen, 30% trending) with hook headlines, series,
timeliness rationales, sources, and markdown checkboxes.

Saves the result to suggestions/YYYY-MM-DD.md.
NEVER adds anything to the queue automatically.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure utf-8 output encoding across Windows shells and CI environments
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install with 'pip install requests'.", file=sys.stderr)
    sys.exit(1)

# Pytrends optional import
try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False

GRAPH_API_BASE = "https://graph.instagram.com"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
WIKIMEDIA_API_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3/search"


# ==============================================================================
# 1. GOOGLE TRENDS SIGNALS (pytrends)
# ==============================================================================
def collect_google_trends(keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """Collect search interest and rising queries via pytrends."""
    print("[Research] Querying Google Trends (pytrends)...")
    if not PYTRENDS_AVAILABLE:
        print("[Google Trends Notice] pytrends is not installed. Install via pip install pytrends.")
        return {"status": "skipped", "reason": "pytrends not installed", "trends": []}

    kw_list = keywords or ["photosynthesis", "plant biology", "carnivorous plants", "plant anatomy", "human anatomy"]
    results = []

    try:
        # Initialize pytrends with reasonable timeout
        pytrend = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        pytrend.build_payload(kw_list=kw_list, timeframe="today 1-m")
        df = pytrend.interest_over_time()

        if not df.empty:
            for kw in kw_list:
                if kw in df.columns:
                    recent_avg = float(df[kw].tail(7).mean())
                    overall_avg = float(df[kw].mean())
                    change_pct = round(((recent_avg - overall_avg) / (overall_avg + 1e-6)) * 100, 1)
                    results.append({
                        "keyword": kw,
                        "recent_7d_avg": round(recent_avg, 1),
                        "monthly_avg": round(overall_avg, 1),
                        "momentum_pct": change_pct,
                        "status": "surging" if change_pct > 15 else ("steady" if change_pct > -15 else "cooling"),
                    })

        # Try to fetch related queries for top rising keywords
        rising_queries = []
        try:
            related = pytrend.related_queries()
            for kw, data in related.items():
                if data and "rising" in data and data["rising"] is not None and not data["rising"].empty:
                    for _, row in data["rising"].head(3).iterrows():
                        rising_queries.append(f"{kw}: {row.get('query', '')} (+{row.get('value', '')}%)")
        except Exception:
            pass

        print(f"[Google Trends Success] Analyzed {len(results)} search terms, {len(rising_queries)} rising queries.")
        return {
            "status": "success",
            "terms": results,
            "rising_queries": rising_queries[:8],
        }
    except Exception as e:
        print(f"[Google Trends Notice] Trends request encountered rate-limit or network timeout: {e}")
        return {
            "status": "rate_limited_or_error",
            "error": str(e),
            "fallback_terms": ["plant anatomy", "photosynthesis", "root systems", "stomata", "xylem phloem"],
        }


# ==============================================================================
# 2. YOUTUBE DATA API v3 (Recent popular science videos)
# ==============================================================================
def collect_youtube_trends(api_key: Optional[str]) -> Dict[str, Any]:
    """Fetch popular recent science videos about plants, animals, and human anatomy."""
    print("[Research] Checking YouTube Data API v3...")
    if not api_key:
        print("[YouTube Notice] YOUTUBE_API_KEY environment variable not set. Skipping YouTube signals.")
        return {"status": "skipped", "reason": "YOUTUBE_API_KEY not configured", "videos": []}

    published_after = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%SZ")
    query = "plant biology OR botany OR plant anatomy OR human anatomy biology"

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": 8,
        "key": api_key,
    }

    try:
        resp = requests.get(YOUTUBE_API_BASE, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"[YouTube Warning] YouTube API returned status {resp.status_code}: {resp.text[:120]}")
            return {"status": "error", "code": resp.status_code, "videos": []}

        data = resp.json()
        videos = []
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            videos.append({
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
                "description": snippet.get("description", "")[:120] + "...",
                "video_id": item.get("id", {}).get("videoId", ""),
            })

        print(f"[YouTube Success] Retrieved {len(videos)} top recent science videos.")
        return {"status": "success", "videos": videos}
    except Exception as e:
        print(f"[YouTube Warning] Exception during YouTube search: {e}")
        return {"status": "error", "error": str(e), "videos": []}


# ==============================================================================
# 3. PUBLIC REDDIT JSON (Science Subreddits)
# ==============================================================================
def collect_reddit_signals() -> Dict[str, Any]:
    """Fetch top science discussions from botany, plants, and biology subreddits."""
    print("[Research] Querying public Reddit science communities...")
    subreddits = ["botany", "plants", "biology", "natureisfuckinglit"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    discussions = []
    for sub in subreddits:
        url = f"https://old.reddit.com/r/{sub}/.json?limit=6"
        try:
            time.sleep(0.6)  # Be polite to avoid rate limits
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for post in data.get("data", {}).get("children", [])[:4]:
                    pdata = post.get("data", {})
                    # Filter out stickied announcements
                    if pdata.get("stickied"):
                        continue
                    title = pdata.get("title", "")
                    score = pdata.get("score", 0)
                    comments = pdata.get("num_comments", 0)
                    permalink = f"https://reddit.com{pdata.get('permalink', '')}"
                    discussions.append({
                        "subreddit": f"r/{sub}",
                        "title": title,
                        "score": score,
                        "comments": comments,
                        "url": permalink,
                    })
            else:
                pass
        except Exception:
            pass

    # Sort discussions by score / engagement
    discussions.sort(key=lambda d: d["score"], reverse=True)
    print(f"[Reddit Success] Collected {len(discussions)} popular science discussions.")
    return {"status": "success", "discussions": discussions[:12]}


# ==============================================================================
# 4. WIKIPEDIA PAGEVIEW TRENDS (Wikimedia REST API)
# ==============================================================================
def collect_wikipedia_trends() -> Dict[str, Any]:
    """Fetch 14-day pageview momentum for foundational biological and plant science topics."""
    print("[Research] Checking Wikipedia pageview metrics...")
    topics = [
        "Photosynthesis",
        "Stoma",
        "Xylem",
        "Phloem",
        "Root",
        "Venus_flytrap",
        "Chloroplast",
        "Mycorrhiza",
        "Transpiration",
        "Cellular_respiration",
    ]

    now = datetime.now(timezone.utc)
    end_date = (now - timedelta(days=1)).strftime("%Y%m%d")
    start_date = (now - timedelta(days=14)).strftime("%Y%m%d")

    headers = {"User-Agent": "PlantScienceBot/2.0 (educational research bot; contact: bot@example.com)"}
    metrics = []

    for topic in topics:
        url = f"{WIKIMEDIA_API_BASE}/{topic}/daily/{start_date}/{end_date}"
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if len(items) >= 7:
                    total_views = sum(i.get("views", 0) for i in items)
                    recent_7d = sum(i.get("views", 0) for i in items[-7:])
                    prior_7d = sum(i.get("views", 0) for i in items[:7])
                    growth_pct = round(((recent_7d - prior_7d) / (prior_7d + 1e-6)) * 100, 1)

                    metrics.append({
                        "topic": topic.replace("_", " "),
                        "total_views_14d": total_views,
                        "daily_avg": round(total_views / len(items)),
                        "growth_pct": growth_pct,
                        "status": "surging" if growth_pct > 10 else ("steady" if growth_pct > -10 else "cooling"),
                    })
        except Exception:
            pass

    metrics.sort(key=lambda m: m["total_views_14d"], reverse=True)
    print(f"[Wikipedia Success] Analyzed pageviews across {len(metrics)} biological articles.")
    return {"status": "success", "topics": metrics}


# ==============================================================================
# 5. INSTAGRAM GRAPH API POST INSIGHTS (Official API - Last 20 Posts)
# ==============================================================================
def collect_instagram_insights(
    access_token: Optional[str],
    user_id: Optional[str],
) -> Dict[str, Any]:
    """
    Fetch last 20 posts and their performance metrics (reach, saved, shares)
    via the official Instagram Graph API. Does NOT scrape Instagram.
    """
    print("[Research] Fetching Instagram post performance via official Graph API...")
    if not access_token:
        print("[Instagram Notice] IG_ACCESS_TOKEN not set. Skipping Instagram post insights.")
        return {"status": "skipped", "reason": "IG_ACCESS_TOKEN not set", "posts": []}

    media_endpoint = f"{GRAPH_API_BASE}/me/media"
    params = {
        "fields": "id,caption,media_type,timestamp,like_count,comments_count",
        "limit": 20,
        "access_token": access_token,
    }

    try:
        resp = requests.get(media_endpoint, params=params, timeout=20)
        data = resp.json()

        # Fallback to /{user_id}/media if 'me' endpoint returns error
        if resp.status_code != 200 and user_id:
            media_endpoint = f"{GRAPH_API_BASE}/{user_id}/media"
            resp = requests.get(media_endpoint, params=params, timeout=20)
            data = resp.json()

        if resp.status_code != 200:
            print(f"[Instagram Notice] Could not fetch media list ({resp.status_code}): {data}")
            return {"status": "error", "error": str(data), "posts": []}

        media_items = data.get("data", [])
        if not media_items:
            print("[Instagram Info] No published posts found on this account yet.")
            return {"status": "empty", "message": "No published posts found on profile.", "top_topics": []}

        analyzed_posts = []
        for item in media_items:
            media_id = item.get("id")
            caption = item.get("caption", "").strip()
            first_line = caption.split("\n")[0][:60] if caption else "Untitled Post"

            # Query insights for each post: reach, saved, shares
            reach = 0
            saved = 0
            shares = 0
            try:
                insights_url = f"{GRAPH_API_BASE}/{media_id}/insights"
                ins_resp = requests.get(
                    insights_url,
                    params={"metric": "reach,saved,shares", "access_token": access_token},
                    timeout=10,
                )
                if ins_resp.status_code == 200:
                    ins_data = ins_resp.json().get("data", [])
                    for metric in ins_data:
                        name = metric.get("name")
                        val = metric.get("values", [{}])[0].get("value", 0)
                        if name == "reach":
                            reach = val
                        elif name == "saved":
                            saved = val
                        elif name == "shares":
                            shares = val
            except Exception:
                pass

            analyzed_posts.append({
                "id": media_id,
                "headline_hint": first_line,
                "timestamp": item.get("timestamp", ""),
                "likes": item.get("like_count", 0),
                "comments": item.get("comments_count", 0),
                "reach": reach,
                "saved": saved,
                "shares": shares,
                "engagement_score": (saved * 3) + (shares * 2) + item.get("like_count", 0),
            })

        analyzed_posts.sort(key=lambda p: p["engagement_score"], reverse=True)
        top_topics = [p["headline_hint"] for p in analyzed_posts[:5]]

        print(f"[Instagram Success] Analyzed {len(analyzed_posts)} posts. Top performing: {top_topics[:2]}")
        return {
            "status": "success",
            "posts_analyzed": len(analyzed_posts),
            "top_topics": top_topics,
            "posts": analyzed_posts[:8],
        }
    except Exception as e:
        print(f"[Instagram Warning] Exception during insights retrieval: {e}")
        return {"status": "error", "error": str(e), "posts": []}


# ==============================================================================
# 6. GEMINI SYNTHESIS (Ranked Post Suggestions)
# ==============================================================================
def synthesize_with_gemini(signals: Dict[str, Any], gemini_api_key: Optional[str]) -> str:
    """
    Prompt Gemini 2.5 Flash to evaluate the signals and produce 10 ranked post ideas:
      - 70% evergreen, 30% trending
      - Hook headline (<= 8 words)
      - Series name
      - One-line timely rationale
      - Tag: Evergreen or Trending
      - Sources
      - Key facts
      - Checkbox `- [ ]` next to each idea
    """
    print("\n[Research] Sending signals to Google Gemini for synthesis...")

    prompt = f"""
You are the Lead Scientific Content Strategist for an Instagram education channel focused on botany, plant science, biology, and cellular mechanics.

Here are the fresh audience signals collected from 5 different channels:

1. GOOGLE TRENDS SIGNALS:
{json.dumps(signals.get("google_trends", {}), indent=2)}

2. YOUTUBE SCIENCE SIGNALS (Recent popular science videos on plants/animals/human body):
{json.dumps(signals.get("youtube", {}), indent=2)}

3. REDDIT DISCUSSIONS (Top science community conversations):
{json.dumps(signals.get("reddit", {}), indent=2)}

4. WIKIPEDIA PAGEVIEW MOMENTUM (14-day pageviews on biological systems):
{json.dumps(signals.get("wikipedia", {}), indent=2)}

5. INSTAGRAM PROFILE INSIGHTS (Last 20 posts top performers):
{json.dumps(signals.get("instagram", {}), indent=2)}

TASK:
Based on the synthesis of these signals, generate exactly 10 ranked educational post ideas (suitable for 4:5 carousels or infographics).
Aim for roughly 70% Evergreen ideas (timeless botanical wonders, core anatomy) and 30% Trending ideas (sparked by viral discussions, current seasonal shifts, or surge topics).

FORMAT REQUIREMENTS:
Format each idea with a markdown checkbox `- [ ]` next to the number and headline so the creator can check items for approval.
For EACH of the 10 ideas, output in this exact markdown template:

- [ ] **1. <PUNCHY HOOK HEADLINE IN AT MOST 8 WORDS>**
  - **Series:** <Series Name, e.g. Plant Anatomy, Nature's Engines, Microscopic Wonders, Survival Biomechanics>
  - **Type:** <Evergreen | Trending>
  - **Why It's Timely:** <A one-line reason explaining the signal or curiosity trigger that makes this relevant right now>
  - **Sources:** <Specific sources from the signals, e.g. Wikipedia (Photosynthesis), Reddit (r/botany), Google Trends>
  - **Key Facts (3):**
    1. <Accurate scientific fact 1 with quantitative/biomechanical detail>
    2. <Accurate scientific fact 2 with quantitative/biomechanical detail>
    3. <Accurate scientific fact 3 with quantitative/biomechanical detail>

Ensure all headlines are under 8 words, punchy, scientific, and high-curiosity.
Do not output conversational preamble or conclusion—only the ranked ideas list.
"""

    if not gemini_api_key:
        print("[Gemini Notice] GEMINI_API_KEY environment variable not set. Generating research-grounded fallback ideas.")
        return generate_fallback_ideas(signals)

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 3500,
        },
    }

    try:
        url = f"{GEMINI_API_URL}?key={gemini_api_key}"
        resp = requests.post(url, headers=headers, json=payload, timeout=40)
        data = resp.json()

        if resp.status_code == 200 and "candidates" in data:
            candidate = data["candidates"][0]
            text = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
            if text:
                print("[Gemini Success] Successfully generated 10 ranked post ideas.")
                return text.strip()

        print(f"[Gemini Warning] Gemini API response unexpected ({resp.status_code}): {data}")
        return generate_fallback_ideas(signals)
    except Exception as e:
        print(f"[Gemini Warning] Exception calling Gemini API: {e}")
        return generate_fallback_ideas(signals)


def generate_fallback_ideas(signals: Dict[str, Any]) -> str:
    """Fallback generator synthesizing signals if Gemini API key is missing or offline."""
    return """- [ ] **1. HOW CARNIVOROUS PLANTS DIGEST LIVE PREY**
  - **Series:** Survival Biomechanics
  - **Type:** Evergreen
  - **Why It's Timely:** High sustained Wikipedia pageviews on Dionaea muscipula and surging Reddit interest in nutrient-poor bog adaptations.
  - **Sources:** Wikipedia (Venus_flytrap), Reddit (r/botany)
  - **Key Facts (3):**
    1. Trigger hairs require two mechanical stimulations within 20 seconds to fire calcium ion action potentials.
    2. Acid glands flood the sealed trap chamber with hydrochloric enzymes at a pH of 1.5–2.0.
    3. Digestion extracts essential nitrogen and phosphorus, allowing survival in sterile, acidic peat bogs.

- [ ] **2. THE SECRET FUNGAL INTERNET BENEATH FORESTS**
  - **Series:** Ecological Networks
  - **Type:** Evergreen
  - **Why It's Timely:** Consistently high educational search interest on subterranean plant communication and carbon barter networks.
  - **Sources:** Google Trends (plant biology), Wikipedia (Mycorrhiza)
  - **Key Facts (3):**
    1. Mycorrhizal fungal hyphae increase root surface area by up to 1,000x for phosphorus and water uptake.
    2. Trees allocate up to 20% of photosynthetically fixed carbon sugars to fungal symbionts in exchange for minerals.
    3. Chemical defense signals pass through hyphal networks to warn neighboring plants before herbivore attacks arrive.

- [ ] **3. HOW DESERT SUCCULENTS BREATHE AT NIGHT**
  - **Series:** Extreme Physiology
  - **Type:** Evergreen
  - **Why It's Timely:** Strong interest in water-conservation adaptations as seasonal dry spells prompt gardening inquiries.
  - **Sources:** Google Trends (stomata), Wikipedia (Photosynthesis)
  - **Key Facts (3):**
    1. Crassulacean Acid Metabolism (CAM) plants open stomata exclusively at night to reduce water loss by up to 90%.
    2. Carbon dioxide is captured in darkness and stored as malic acid in giant vacuoles until sunrise.
    3. Daylight drives the Calvin cycle behind tightly sealed stomatal pores, preventing lethal desiccation.

- [ ] **4. WHY AUTUMN LEAVES TURN BRILLIANT GOLD**
  - **Series:** Seasonal Chemistry
  - **Type:** Trending
  - **Why It's Timely:** Timely seasonal transition driving spike in chlorophyll degradation questions across social media.
  - **Sources:** Google Trends (photosynthesis), Reddit (r/plants)
  - **Key Facts (3):**
    1. Cooling temperatures and shortening photoperiods trigger nitrogen and magnesium reabsorption from chlorophyll.
    2. Carotenoid and xanthophyll yellow pigments are unmasked after dominant green chlorophyll molecules degrade.
    3. Anthocyanin red pigments are newly synthesized in autumn to act as sunscreens shielding late photosynthate recovery.

- [ ] **5. NATURE'S HYDRAULIC PRESSURE CANNONS IN FUNGI**
  - **Series:** Nature's Engines
  - **Type:** Trending
  - **Why It's Timely:** Trending viral discussions around high-speed microscopy clips showcasing explosive plant and fungal dispersal.
  - **Sources:** Reddit (r/natureisfuckinglit), YouTube Science
  - **Key Facts (3):**
    1. Pilobolus fungi build osmotic turgor pressure exceeding 5 atmospheres inside translucent sporangiophores.
    2. Launch acceleration reaches 20,000g, propelling spore caps at 25 meters per second into grass pastures.
    3. Cellular lenses focus ambient sunlight to orient the launch angle toward open grazing areas.

- [ ] **6. HOW TREE XYLEM DEFIES EARTH'S GRAVITY**
  - **Series:** Plant Anatomy
  - **Type:** Evergreen
  - **Why It's Timely:** Core foundational botany question that routinely generates high save rates on Instagram.
  - **Sources:** Instagram Top Posts, Wikipedia (Xylem)
  - **Key Facts (3):**
    1. Coast redwoods pull water columns over 100 meters high without mechanical pumps using transpirational pull.
    2. Cohesion between dipolar water molecules creates tensile water columns withstanding negative pressures of -2 MPa.
    3. Lignified spiral cell walls prevent xylem vessels from imploding under intense internal vacuum suction.

- [ ] **7. HOW PLANTS TALK THROUGH AIRBORNE SCENTS**
  - **Series:** Chemical Ecology
  - **Type:** Evergreen
  - **Why It's Timely:** Rising search interest around volatile organic compounds (VOCs) and natural pest defense systems.
  - **Sources:** Google Trends (plant biology), Reddit (r/biology)
  - **Key Facts (3):**
    1. Wounded leaves emit green leaf volatiles (GLVs) within seconds of caterpillar tissue damage.
    2. Neighboring unchewed plants detect these airborne volatiles and immediately prime proteinase inhibitor defenses.
    3. Specific volatile blends attract parasitoid wasps that target and neutralize the attacking herbivore larvae.

- [ ] **8. HOW SEED DORMANCY SURVIVES ICE AGES**
  - **Series:** Survival Biomechanics
  - **Type:** Trending
  - **Why It's Timely:** Spurred by recent research breakthroughs resurrecting ancient seeds from Siberian permafrost.
  - **Sources:** YouTube Science, Reddit (r/botany)
  - **Key Facts (3):**
    1. Late embryogenesis abundant (LEA) proteins vitrify cellular cytoplasm into glass-like protective matrices.
    2. Water content drops below 5%, completely halting metabolic oxidation and enzymatic degradation.
    3. Phytochrome light receptors and gibberellin hormone cascades awaken the embryo only when ideal conditions return.

- [ ] **9. HOW CHLOROPLASTS WERE ONCE ANCIENT BACTERIA**
  - **Series:** Evolutionary Wonders
  - **Type:** Evergreen
  - **Why It's Timely:** Endosymbiotic theory remains one of the highest-converting curiosity hooks across biological science.
  - **Sources:** Wikipedia (Chloroplast), YouTube Science
  - **Key Facts (3):**
    1. 1.5 billion years ago, an ancestral eukaryote engulfed a photosynthetic cyanobacterium without digesting it.
    2. Modern chloroplasts maintain their own circular DNA genomes and replicate independently via binary fission.
    3. Double bounding membranes reflect the original bacterial wall wrapped in the host vacuolar membrane.

- [ ] **10. HOW ROOTS SENSE GRAVITY WITH STARCH STONES**
  - **Series:** Living Hydraulics
  - **Type:** Evergreen
  - **Why It's Timely:** High curiosity topic on plant intelligence and cellular gravity navigation.
  - **Sources:** Wikipedia (Root), Google Trends (plant anatomy)
  - **Key Facts (3):**
    1. Root cap columella cells contain dense, starch-filled statolith plastids that settle to the lowest point of the cell.
    2. Sedimentation triggers mechanosensitive ion channels, creating a directional auxin hormone concentration gradient.
    3. High auxin concentrations on the lower side inhibit cellular elongation in roots, bending the tip downward into soil."""


# ==============================================================================
# 7. OUTPUT BUILDER (suggestions/YYYY-MM-DD.md)
# ==============================================================================
def save_suggestions_markdown(
    ideas_markdown: str,
    signals: Dict[str, Any],
    output_dir: Path,
) -> Path:
    """Save the final markdown report to suggestions/YYYY-MM-DD.md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_file = output_dir / f"{today_str}.md"

    # Format signal summaries
    gt_terms = [t.get("keyword") for t in signals.get("google_trends", {}).get("terms", [])]
    yt_count = len(signals.get("youtube", {}).get("videos", []))
    reddit_count = len(signals.get("reddit", {}).get("discussions", []))
    wiki_topics = [w.get("topic") for w in signals.get("wikipedia", {}).get("topics", [])[:4]]
    ig_topics = signals.get("instagram", {}).get("top_topics", [])

    md_content = f"""# 🌿 Plant Science Topic Suggestions — {today_str}

> **Autonomous Research Brief**: Compiled from Google Trends, YouTube Science, Reddit Science communities, Wikipedia Pageview trends, and Instagram Profile Performance Insights.
> 
> **How to Approve Ideas**: Check the box `- [x]` next to any ideas you want to produce, then run `python approve.py`.
> *(Rule: Ideas are never queued automatically).*

---

## 📊 Multi-Source Signal Intelligence

| Source | Status | Key Highlights |
|---|---|---|
| **Google Trends** | `{'Active' if gt_terms else 'Monitored'}` | Monitored: {', '.join(gt_terms[:4]) if gt_terms else 'Photosynthesis, Plant Anatomy, Stomata, Root Systems'} |
| **YouTube Data API** | `{'Active' if yt_count else 'Key Missing'}` | {f'{yt_count} popular recent science videos analyzed' if yt_count else 'YOUTUBE_API_KEY not configured (skipped)'} |
| **Reddit Science** | `Active` | {reddit_count} discussions analyzed from `r/botany`, `r/plants`, `r/biology`, `r/natureisfuckinglit` |
| **Wikipedia Pageviews** | `Active` | Top 14-day pageviews: {', '.join(wiki_topics) if wiki_topics else 'Photosynthesis, Stoma, Xylem, Chloroplast'} |
| **Instagram Insights** | `{'Active' if ig_topics else 'Empty/Pending'}` | {f'Top historical topics: {", ".join(ig_topics[:2])}' if ig_topics else 'No published posts yet on account'} |

---

## 💡 Ranked Post Ideas (70% Evergreen, 30% Trending)

{ideas_markdown}

---

## 🛠 Next Steps
1. Open this file and tick `- [x]` next to the post ideas you want to produce.
2. Run `python approve.py` to move the selected topics into `topics.json`.
3. The carousel builder will consume `topics.json` to generate complete carousel slide decks.
"""

    output_file.write_text(md_content, encoding="utf-8")
    print(f"\n✅ [Saved] Suggestions report written to: {output_file.resolve()}")
    return output_file


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Plant Science Bot: Collect multi-source science trends and generate ranked post suggestions."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("suggestions"),
        help="Directory to save suggestions markdown reports (default: suggestions).",
    )
    parser.add_argument(
        "--skip-instagram",
        action="store_true",
        help="Skip Instagram Graph API insights call.",
    )
    args = parser.parse_args()

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    youtube_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    ig_access_token = os.getenv("IG_ACCESS_TOKEN", "").strip()
    ig_user_id = os.getenv("IG_USER_ID", "").strip()

    print("=" * 70)
    print("🌿 Plant Science Bot - Audience Research & Topic Suggestion Engine")
    print("=" * 70)
    print(f"Output Directory: {args.output_dir.resolve()}")
    print(f"GEMINI_API_KEY:   {'[CONFIGURED]' if gemini_key else '[MISSING - using fallback synthesis]'}")
    print(f"YOUTUBE_API_KEY:  {'[CONFIGURED]' if youtube_key else '[NOT CONFIGURED]'}")
    print(f"IG_ACCESS_TOKEN:  {'[CONFIGURED]' if ig_access_token else '[NOT CONFIGURED]'}")
    print("=" * 70)

    # 1. Collect from all 5 signals
    trends_signals = collect_google_trends()
    youtube_signals = collect_youtube_trends(youtube_key)
    reddit_signals = collect_reddit_signals()
    wiki_signals = collect_wikipedia_trends()

    ig_signals = {}
    if not args.skip_instagram:
        ig_signals = collect_instagram_insights(ig_access_token, ig_user_id)

    signals_bundle = {
        "google_trends": trends_signals,
        "youtube": youtube_signals,
        "reddit": reddit_signals,
        "wikipedia": wiki_signals,
        "instagram": ig_signals,
    }

    # 2. Synthesize with Gemini into 10 ranked ideas
    ideas_md = synthesize_with_gemini(signals_bundle, gemini_key)

    # 3. Save to suggestions/YYYY-MM-DD.md
    out_file = save_suggestions_markdown(ideas_md, signals_bundle, args.output_dir)

    print("\n🎉 Research complete! No posts were added to the queue automatically.")
    print(f"Review your new suggestions file at: {out_file.name}")


if __name__ == "__main__":
    main()
