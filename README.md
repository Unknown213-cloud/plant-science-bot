# 🌿 Plant Science Bot

Automated educational Instagram bot that publishes high-resolution plant anatomy infographics with scientifically validated captions and hashtags.

---

## 📋 Features

1. **Queued Publishing Architecture (`queue/` -> `posted/`)**:
   - Posts are prepared in `queue/` as an image (`.png`, `.jpg`, `.jpeg`, `.webp`) plus a matching caption in `captions.json`.
   - Each caption contains **3 accurate scientific facts** paired with structured botanic and educational hashtags.
   - The bot selects the **oldest image** in the queue based on file modification time.
   - Once posted, the image is archived to `posted/` and recorded in `posted/captions.json` with its Instagram Media ID and timestamp.

2. **Public Image Resolution via GitHub**:
   - Builds public `raw.githubusercontent.com` URLs directly from the active repository and branch (`main`).
   - Enables seamless image hosting without requiring external cloud storage (e.g. S3).

3. **Instagram Graph API with Instagram Login**:
   - Uses the official endpoints:
     1. `POST https://graph.instagram.com/me/media` (or `/{user_id}/media`) to create the media container.
     2. Polling `GET https://graph.instagram.com/{creation_id}` until processing is finished.
     3. `POST https://graph.instagram.com/me/media_publish` (or `/{user_id}/media_publish`) to publish the post.

4. **Automated Token Refresh**:
   - Refreshes long-lived Instagram user access tokens via `https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token={token}` before the 60-day expiration window.
   - Handles the Meta 24-hour refresh minimum gracefully.

5. **GitHub Actions Automation**:
   - Scheduled workflow (`.github/workflows/daily_post.yml`) running at `13:00 UTC` on **Monday, Wednesday, Friday, and Sunday**.
   - Supports manual execution (`workflow_dispatch`) with optional `--dry-run` simulation.
   - Automatically commits and pushes moved files (`queue/` and `posted/`) back to GitHub with `[skip ci]`.
   - Updates repository secret `IG_ACCESS_TOKEN` when `GH_PAT` is configured.

6. **Safety & Simulation**:
   - `--dry-run` flag lets you preview the exact image, public URL, caption, and simulated API payloads without publishing or altering files.

---

## 🗂 Project Structure

```
plant-science-bot/
├── .github/
│   └── workflows/
│       └── daily_post.yml        # Daily GitHub Actions workflow
├── queue/                        # Queued posts awaiting publication
│   ├── captions.json             # Keyed by image filename (3 facts + hashtags)
│   ├── leaf_cross_section.png    # Leaf anatomy diagram
│   ├── root_types.png            # Taproot vs. fibrous root systems
│   └── stomata_structure.png     # Guard cell turgor & stomatal mechanics
├── posted/                       # Published posts archive
│   └── captions.json             # Archived history with publication timestamps
├── .env.example                  # Environment variable template
├── .gitignore                    # Ignored local token files & environments
├── post_next.py                  # Core automation & Instagram publisher
├── requirements.txt              # Python dependencies
└── README.md
```

---

## 🚀 Quickstart & Local Usage

### 1. Installation

```bash
git clone https://github.com/Unknown213-cloud/plant-science-bot.git
cd plant-science-bot
pip install -r requirements.txt
```

### 2. Configure Credentials

Create a `.env` file (which is git-ignored):

```env
IG_ACCESS_TOKEN=your_long_lived_user_access_token
IG_USER_ID=your_instagram_user_id
```

### 3. Dry-Run Simulation

Test what would be posted without contacting the Instagram API or altering files:

```bash
python post_next.py --dry-run
```

Output preview:
```
=================================================================
🌿 Plant Science Bot - Daily Instagram Publisher
=================================================================
Repository:  Unknown213-cloud/plant-science-bot
Branch:      main
Queue Dir:   .../queue
Posted Dir:  .../posted
Dry Run:     YES (Simulation Mode)
=================================================================

[Selected Post]
  • Image File:    leaf_cross_section.png
  • Modified Time: 2026-10-16T...
  • Public URL:    https://raw.githubusercontent.com/Unknown213-cloud/plant-science-bot/main/queue/leaf_cross_section.png

[Caption Content]
----------------------------------------
🌿 Plant Anatomy: Leaf Cross-Section & Internal Architecture
...
----------------------------------------
✅ DRY RUN COMPLETE: No live requests made, no files modified.
```

### 4. Publish Next Queued Post

```bash
python post_next.py
```

### 5. Refresh Access Token Manually

```bash
python post_next.py --refresh-token
```

---

## ⚙️ GitHub Actions Setup

To enable daily automated posting, configure the following **Repository Secrets** under **Settings > Secrets and variables > Actions**:

| Secret Name | Required | Description |
|---|---|---|
| `IG_ACCESS_TOKEN` | **Yes** | Long-lived Instagram User Access Token (from Meta Developer Portal). |
| `IG_USER_ID` | **Yes** | Instagram Business or Creator Account ID. |
| `GH_PAT` | Optional | Personal Access Token with `secrets:write` and `repo` scopes. Allows GitHub Actions to persist refreshed access tokens back into `IG_ACCESS_TOKEN`. |

---

## 🎨 Sample Plant Anatomy Infographics

The initial queue includes 3 scientifically annotated infographics:

1. **`leaf_cross_section.png`**:
   - Cross-section displaying Cuticle, Upper/Lower Epidermis, Palisade Mesophyll with chloroplasts, Spongy Mesophyll with air spaces, Vascular Bundle (Xylem & Phloem), and Guard Cells.
2. **`root_types.png`**:
   - Comparative diagram illustrating Eudicot Taproot systems (primary root, lateral roots, root hairs, root cap) vs. Monocot Fibrous root systems and adventitious prop roots.
3. **`stomata_structure.png`**:
   - Detailed micro-anatomy of stomatal complexes showing open (turgid) vs. closed (flaccid) guard cells, ion influx ($K^+$ and $H_2O$), cell wall differentials, and ABA signaling.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
