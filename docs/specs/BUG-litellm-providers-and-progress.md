I'm encountering several bugs while running the extraction pipeline. The output of my pipeline run is copied in the code block below. I see the following problems:
- "Provider List: ...." is printed in red: this makes me think that LiteLLM prints a message to stderr because something is going wrong with the provider router.
- it's unclear whether the first event was extracted successfully: i see a bullet point printed, but the pipeline still seemed to be displaying that it was working on Post 1/31 when i canceled it. It looks like the pipeline is hanging on this post.


```
luye@Lulupad:~/workspace/instacalendar$ uv run instacalendar run --from-cache --collection "Events Private" --ics-output ~/events-private.ics

Provider List: https://docs.litellm.ai/docs/providers


Provider List: https://docs.litellm.ai/docs/providers


Provider List: https://docs.litellm.ai/docs/providers

- @unknown (2026-04-09) - got event from text - 2026-08-07 at The Milton Keynes National Bowl - post est. $0.0007; run est. $0.0007; qwen/qwen3.5-9b: 4504 tokens ($0.0007)
Post 1/31: post est. $0.0007; run est. $0.0007; qwen/qwen3.5-9b: 4504 tokens ($0.0007) ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━? Diaspora Calling
Start: 2026-08-07 00:00:00+00:00
Location: The Milton Keynes National Bowl
Confidence: 0.95 (Y/n)

Cancelled by user

Post 1/31: post est. $0.0007; run est. $0.0007; qwen/qwen3.5-9b: 4504 tokens ($0.0007) ━╺━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 1/31 0:02:38
```

The contents of my config file is:

```json
{
  "instagram_username": "<hidden>",
  "openrouter_text_model": "qwen/qwen3.5-9b",
  "openrouter_vision_model": "google/gemini-3-flash-preview",
  "default_export": "ics",
  "google_calendar_id": null
}
```
