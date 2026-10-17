# Instagram Publishing Cadence Guardrail

## Strict Single-Carousel Execution
When triggering, executing, or automating Instagram publications:
1. **Never Bundle or Chain Posts**: Never trigger, dispatch, or execute publication of multiple carousel posts in immediate succession or within the same session interaction.
2. **One Post Per Request**: When publishing on demand, publish strictly the single post at the front of the queue (`queue/`), verify and confirm its Instagram Media ID and slide count, and immediately stop.
3. **Queue Preservation**: All subsequent queued posts (e.g., `03-human-brain`, `04-human-lungs`) must remain untouched in the `queue/` folder, waiting either for their scheduled cron slot or for a separate, explicit user request.
4. **Mandatory Explicit Confirmation**: Even if multiple posts are ready in `queue/`, never proceed to publish a second post without an explicit, separate user command specifically directing the next post to go live.
