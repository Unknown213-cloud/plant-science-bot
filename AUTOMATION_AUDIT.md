# Automation audit — 2026-10-16

Scope: generated-image handoff, infographic composition, queued publishing,
GitHub Actions, token persistence, and recovery from failed runs. Local data was
backed up outside the repository at `../audit_backups/before-automation-fixes/`.
No Instagram post was sent during this audit.

## Substantive findings and fixes

| Severity | Failure found | Resulting change |
| --- | --- | --- |
| Critical | The new 20-image folder was outside the Git checkout, and the compositor read a different, incomplete raw batch. | Copied the original PNGs into repository `codex_generate_raw/`; compositor defaults to that directory and validates all 20 before touching the queue. |
| Critical | Publisher handed PNG/WebP assets straight to Meta; dry-run only printed URLs. | Canonical compositor produces RGB JPEGs. Validation checks actual encoding, dimensions, size, caption length, and all queued posts. Live mode verifies anonymous hosted bytes before creating containers. |
| Critical | Polling returned success on unknown statuses and timeout; callers ignored failures. | Only `FINISHED` permits publication. Failed, expired, unknown, already-published, and timed-out containers stop publication. Oversized carousels are rejected instead of truncated. |
| Critical | A successful remote post followed by archive/commit failure could be posted again. | `publication.py` checkpoints the creation ID before `media_publish`, pushes that checkpoint in Actions, then records the confirmed media ID. A confirmed publication resumes archiving; an ambiguous outcome stops for reconciliation. No automatic retry of `media_publish`. |
| High | Concurrent scheduled/manual runs could select the same post; research and publishing could race on Git writes. | Both repository writers share a concurrency group with cancellation disabled. Archive persistence runs even after a failed publish step; a recovery artifact retains metadata if persistence fails. |
| High | Refreshed-token persistence checked a step-scoped `GH_PAT` as job environment, so its condition could never enable the step. Tokens were also refreshed twice per scheduled run. | One `refresh_ci_token.py` call refreshes and masks the new token, exports it to the current job, and updates the repository secret when `GH_PAT` is configured. Publisher skips the second refresh. |
| High | Rebuilding wrote directly into live post folders; failure could leave mixed old/new slides. Archive collisions deleted prior content. | Entire batch renders in staging and validates before replacement. Previous queue folders are retained in ignored `.build-backups/`. Published IDs cannot be rebuilt into the queue. Archive collisions and unreadable history stop without deleting data. |
| High | Compositor fonts only existed on Windows; several fixed-size CTA strings ran off the slide. | Added Linux DejaVu font paths and measured text fitting with readable minimum font size. |
| Medium | Every scheduled post installed pandas/pytrends although the publisher does not use them. | Added `requirements-publish.txt` for publishing and validation; research keeps its own full requirements. |
| Medium | Preview dates were fixed to one historical week. | Preview computes upcoming scheduled UTC slots at build time. These are scheduled estimates, not delivery confirmations. |
| High | Fact-check document claimed universal verification while captions contained clear errors. | Corrected neurotransmitter/vesicle transport, valve pressure descriptions, incorrect tennis-court comparison, unsupported eye-processing claims, and universal accuracy promises. Replaced the blanket verification declaration with scoped source notes. |

## Verification

- Regression tests use temporary directories and mocked HTTP; they do not touch Instagram.
- Tests cover failed and unknown containers, duplicate prevention after an ambiguous response,
  archive recovery, checkpoint failure, stale/private hosted images, encoding, layout fitting,
  incomplete inputs, captions, and archive preservation.
- Four carousels rebuilt from the 20 Codex originals; every publishing slide is RGB JPEG at
  1080 × 1350. Original generated PNGs remain unchanged.
- The validation workflow runs on push and pull requests without Instagram secrets.
- Source review and image rendering do not establish clinical accuracy of AI illustrations.

## Deployment observations and remaining boundaries

- The public GitHub repository is `Unknown213-cloud/plant-science-bot`, default branch `main`.
  Before deployment the GitHub API returned **no workflows and no runs**. Two existing local
  commits had not reached the remote. A local schedule file alone does not activate automation.
- Authenticated verification confirmed Actions is enabled and repository secrets named
  `IG_ACCESS_TOKEN`, `IG_USER_ID`, and `GEMINI_API_KEY` exist. Their values were not exposed.
  `GH_PAT` is absent. If token refresh returns a different value, persisting that replacement
  requires a token with repository secret-write permission; an ordinary `GITHUB_TOKEN` cannot
  replace it. If refresh returns the existing value, the configured secret needs no update.
- Local tests cannot prove a token is active, has publishing permissions, or targets the intended
  professional account. Use a hosted dry run after pushing; a real publish requires a live run.
- An interrupted `media_publish` can have an unknown remote outcome. Inspect the recorded
  `creation_id` and the Instagram account before changing its journal entry. Do not delete state
  and blindly retry. This deliberately favors avoiding duplicate posts.
- The queue contains four posts, not an unlimited content supply. Research produces suggestions;
  approval writes `topics.json`. New image generation and editorial review remain manual batch
  steps. Neither script currently turns arbitrary approved topics into finished infographics.
- Historical helper scripts (`build_human_batch.py`, `fetch_human_images.py`, and old raw batches)
  are not the supported publishing path. Use `build_carousel_batch.py` and the new raw directory.

## Source references

- [Meta content publishing](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing/).
  The documentation endpoint was rate-limited during this audit; no claim of live API acceptance
  is based solely on local validation.
- [GitHub workflow syntax and concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
- [OpenStax neural communication](https://openstax.org/books/introduction-behavioral-neuroscience/pages/2-1-neural-communication).
- [OpenStax cardiac cycle](https://openstax.org/books/anatomy-and-physiology-2e/pages/19-3-cardiac-cycle).
- [OpenStax respiratory system](https://openstax.org/books/fundamentals-nursing/pages/19-1-respiratory-system).
