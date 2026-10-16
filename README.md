# 🌿 Plant Science Bot

Automated educational Instagram bot that researches audience science trends, generates high-resolution plant anatomy infographics & carousels (4:5, 1080x1350), and publishes them via the official Instagram Graph API.

---

## 📋 Core Systems

### 1. 🔍 Research & Topic Suggestion Engine (`research.py`)
Collects emerging scientific interest and audience engagement signals across 5 channels (without scraping Instagram):
- **Google Trends** (`pytrends`): Identifies search momentum and rising search queries across botany, plant anatomy, and biology.
- **YouTube Data API v3**: Analyzes recent popular science videos on plants, animals, and human anatomy.
- **Public Reddit JSON**: Gathers top community discussions from `r/botany`, `r/plants`, `r/biology`, and `r/natureisfuckinglit`.
- **Wikipedia Pageview Trends**: Queries 14-day pageview momentum from the Wikimedia REST API across foundational biological systems.
- **Instagram Graph API Insights**: Retrieves the last 20 published posts, calculating saves, shares/sends, and reach to surface top-performing topics.
- **Gemini AI Synthesis**: Sends all collected signals to Google Gemini (`gemini-2.5-flash`) to generate **10 ranked post ideas** (roughly 70% evergreen, 30% trending) with hook headlines (≤ 8 words), series names, timely rationales, sources, and 3 key facts.
- **Output**: Saves to `suggestions/YYYY-MM-DD.md` with interactive markdown checkboxes `- [ ]`.
- *Rule: Ideas are never queued automatically.*

### 2. ✅ Human-in-the-Loop Approval Manager (`approve.py`)
- Reads the newest suggestions file in `suggestions/`.
- Scans for ticked checkboxes (`- [x]`).
- Appends approved topics into `topics.json` with structured facts and metadata for the carousel generator.

### 3. 🎞 Queued Publishing & Carousel Architecture (`post_next.py`)
- **Carousels**: Post folders inside `queue/` (e.g. `queue/2026-plant-anatomy-carousel/`) containing `slide_01.png` to `slide_05.png` and `caption.txt`.
- **Single Posts**: Standalone image files in `queue/` with captions in `queue/captions.json`.
- **4:5 Layout (1080x1350)**:
  - Slide 1: Hook headline (≤ 8 words) + cinematic biological visual.
  - Slides 2–4: One big idea per slide, short title, and ≤ 25 words of text added in code with Pillow.
  - Slide 5: Call to action ("Send this to someone who loves plants", "Follow for more") and an "AI illustration" footnote.
- **Instagram Login Graph API Flow**:
  1. `POST /me/media` with `image_url` and `is_carousel_item=true` for each slide.
  2. Polling status until containers report `FINISHED`.
  3. `POST /me/media` with `media_type=CAROUSEL` and `children=id1,id2,...` and caption.
  4. `POST /me/media_publish` with `creation_id`.
- **Archiving**: Moves published post folders or files to `posted/` and updates `posted/captions.json`.

### 4. ⏰ Automation Workflows
- **`weekly_research.yml`**: Runs `research.py` every Monday at `08:00 UTC` and commits the new suggestions file with `[skip ci]`.
- **`daily_post.yml`**: Runs `post_next.py` at `13:00 UTC` on **Monday, Wednesday, Friday, and Sunday**, refreshes the access token, and archives moved files.

---

## 🗂 Project Structure

```
plant-science-bot/
├── .github/
│   └── workflows/
│       ├── daily_post.yml        # Mon/Wed/Fri/Sun publishing workflow
│       └── weekly_research.yml   # Weekly Monday research workflow
├── queue/                        # Queued posts awaiting publication
│   ├── 2026-plant-anatomy-carousel/
│   │   ├── slide_01.png          # Slide 1: The Hook (4:5, 1080x1350)
│   │   ├── slide_02.png          # Slide 2: Fact 1 (Leaf Palisade)
│   │   ├── slide_03.png          # Slide 3: Fact 2 (Stomatal Valves)
│   │   ├── slide_04.png          # Slide 4: Fact 3 (Root Biomechanics)
│   │   ├── slide_05.png          # Slide 5: Call to Action + AI note
│   │   └── caption.txt           # Post caption with facts & hashtags
│   ├── leaf_cross_section.png    # Standalone single image
│   ├── root_types.png            # Standalone single image
│   ├── stomata_structure.png     # Standalone single image
│   └── captions.json             # Captions for single images
├── suggestions/                  # Weekly research reports
│   └── 2026-10-16.md             # Ranked ideas with checkboxes (- [ ])
├── topics.json                   # Approved topics for generation
├── posted/                       # Published posts archive
│   └── captions.json             # Publication history with media IDs
├── research.py                   # Multi-source research engine
├── approve.py                    # Approval manager (moves [x] to topics.json)
├── post_next.py                  # Core Instagram publisher (carousels & singles)
├── .env.example                  # Credentials template
├── .gitignore                    # Ignored local token files & environments
├── requirements.txt              # Python dependencies
└── README.md
```

---

## 🔑 Required API Keys & Where to Get Them

Configure these in your local `.env` file and as **GitHub Repository Secrets** (**Settings > Secrets and variables > Actions**):

| Secret / Env Variable | Required For | Where to Get It |
|---|---|---|
| `GEMINI_API_KEY` | `research.py` | **Google AI Studio** ([aistudio.google.com](https://aistudio.google.com/)). Free API key for Gemini 2.5 Flash model. |
| `YOUTUBE_API_KEY` | `research.py` | **Google Cloud Console** ([console.cloud.google.com](https://console.cloud.google.com/)). Create a project, enable the **YouTube Data API v3**, and generate an API key under **Credentials**. |
| `IG_ACCESS_TOKEN` | `post_next.py`, `research.py` | **Meta for Developers** ([developers.facebook.com](https://developers.facebook.com/)). Register your app with **Instagram Graph API with Instagram Login**. Generate a Long-Lived User Access Token with `instagram_basic`, `instagram_content_publish`, and `instagram_manage_insights` permissions. |
| `IG_USER_ID` | `post_next.py`, `research.py` | **Meta for Developers / Instagram Graph API Explorer**. The numeric User ID of your connected Instagram Creator or Business account. |
| `GH_PAT` | Optional Token Refresh | **GitHub Settings > Developer Settings > Personal Access Tokens**. Token with `repo` and `secrets:write` scopes to automatically persist refreshed tokens back into GitHub Actions secrets. |

---

## 🚀 Quickstart & Workflow Guide

### Current supported batch workflow

The canonical original images are `codex_generate_raw/raw_*.png` (20 files).
Keep these PNG originals; Instagram publishing uses the composed JPEG slides.

```bash
pip install -r requirements-publish.txt
python build_carousel_batch.py
python post_next.py --validate-all
python -m unittest discover -s tests -v
python publish_batch.py --push
```

The compositor validates the complete input batch, renders in staging, and backs up
replaced queue folders in ignored `.build-backups/`. It refuses to requeue IDs
with publication history. `preview.html` shows the resulting JPEG carousels.

After pushing, use Actions → Scheduled Instagram Post → Run workflow with
`dry_run` enabled to verify hosted images without posting or refreshing tokens.
The regular schedule remains Monday, Wednesday, Friday and Sunday at 13:00 UTC.
Publishing installs only `requirements-publish.txt`; research uses `requirements.txt`.

Publication state is stored in `posted/publication_state.json`. A confirmed post
resumes archiving after failure; an uncertain publish response requires checking
Instagram and the recorded container ID before retrying. Preserve this journal.
Configure `GH_PAT` with repository secret-write permission if refreshed tokens
should persist across runs. See [AUTOMATION_AUDIT.md](AUTOMATION_AUDIT.md) for
findings, verification limits, and the manual content-generation boundary.

### 1. Run Autonomous Research
```bash
python research.py
```
This fetches signals across Google Trends, YouTube, Reddit, Wikipedia, and Instagram, prompts Gemini, and generates `suggestions/YYYY-MM-DD.md`.

### 2. Approve Selected Ideas
Open `suggestions/YYYY-MM-DD.md`, mark your chosen ideas with `[x]`:
```markdown
- [x] **1. HOW CARNIVOROUS PLANTS DIGEST LIVE PREY**
```
Then run:
```bash
python approve.py
```
The approved ideas are extracted and stored in `topics.json`.

### 3. Dry-Run the Next Post (Simulation Mode)
```bash
python post_next.py --dry-run
```
To test a specific carousel:
```bash
python post_next.py --dry-run --post 2026-plant-anatomy-carousel
```

### 4. Publish to Instagram
```bash
python post_next.py
```

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
