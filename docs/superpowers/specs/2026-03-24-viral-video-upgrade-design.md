# Viral Video Upgrade Design
**Date:** 2026-03-24
**Status:** Approved

---

## Overview

Upgrade the ClipBot video pipeline to produce TikTok/Reels-ready clips with word-by-word captions, contextual sound effects, faster cuts, and better voice quality. Current output is flat and unengaging; this design addresses all major retention problems.

---

## Problems Being Solved

| Problem | Root Cause |
|---------|-----------|
| AI reads structural labels (Hook, Problem 3-10s) | GPT includes structure markers in script field |
| Background clips change too slowly | Clips used at full duration (10-20s each) |
| Text appears suddenly, no animation | SRT subtitles at sentence level, small font |
| No sound effects | Not implemented |
| Text in middle of screen | Font size 18px, style misconfigured |
| Voice flat and lifeless | tts-1 model, nova voice |

---

## Components

### 1. Script Generator (`pipeline/script_generator.py`)

**Changes:**
- Prompts explicitly forbid structural labels in the `script` field
- Add `key_words` field: 5-8 words from the script that deserve yellow highlight (numbers, prices, power words, CTA triggers)
- Update JSON schemas for both money and b2b commands

**New schema:**
```
money: { script, pexels_keywords, hook_line, tool_benefit, key_words }
b2b:   { script, pexels_keywords, hook_line, data_point, key_words }
```

**Why GPT-selected key_words over auto-detect:** GPT understands context — knows "free trial" matters more than "the". Regex cannot replicate this.

---

### 2. Transcriber (`pipeline/transcriber.py`)

**Changes:**
- Enable `word_timestamps=True` in Whisper — gives exact per-word start/end times
- Replace `_segments_to_srt()` with `_words_to_ass()` — outputs `.ass` format
- Return `(ass_path, word_timings)` instead of just `srt_path`

**ASS Caption Style:**
- Format: Advanced SubStation Alpha (ASS)
- Font: Arial Bold, 65px
- Color: white (`&H00FFFFFF`) with 3px black outline
- Key words: yellow (`&H0000FFFF`)
- Position: center horizontal, 75% down vertically (MarginV=480 from bottom in 1920px)
- Each word = one Dialogue line with its exact start/end timestamp
- Matching: compare each transcribed word (lowercase, stripped punctuation) against `key_words` list

**File output:** `subs.ass` replaces `subs.srt`

---

### 3. SFX Fetcher (`pipeline/sfx_fetcher.py`) — NEW

**Responsibility:** Download, cache, and schedule sound effects.

**SFX categories and triggers:**

| Category | File | Trigger |
|----------|------|---------|
| `transition` | `assets/sfx/whoosh.mp3` | Each clip transition (~every 2.5s) |
| `impact` | `assets/sfx/impact.mp3` | key_words containing digits or `$` |
| `ding` | `assets/sfx/ding.mp3` | key_words: free, now, link, click, try |

**Caching:** Freesound API called once per SFX type on first run. Files persisted to `assets/sfx/`. Subsequent runs use local cache.

**API:** Freesound.org free API. Requires `FREESOUND_API_KEY` in `.env`.

**Output:** `list[tuple[int, str]]` — `(timestamp_ms, sfx_path)` for assembler.

**Volume:** SFX mixed at -12dB relative to voice to avoid overpowering audio.

---

### 4. Assembler (`pipeline/assembler.py`)

**Changes:**

**Step 1 — Faster cuts:**
- Each clip trimmed to max **2.5 seconds** during scale/crop step
- Result: hard cut every 2-3 seconds throughout the video

**Step 4.5 — SFX mixing (new step between mux and encode):**
- Input: `muxed.mp4` + list of `(timestamp_ms, sfx_path)`
- Build ffmpeg filter complex: `adelay` per SFX + `amix` for all inputs
- Output: `audio_with_sfx.mp3`
- Volume normalization: SFX at -12dB vs voice

**Step 5 — ASS captions:**
- `subtitles=subs.ass` instead of `subtitles=subs.srt`
- ffmpeg handles ASS styling automatically from the file

**Function signature update:**
```python
def assemble(raw_clips, audio_path, ass_path, sfx_cues, output_path, work_dir=None)
```

---

### 5. Voice Generator (`pipeline/voice_generator.py`)

**Changes:**
- Model: `tts-1-hd` (higher quality, ~$0.015/clip vs ~$0.008)
- `/money` voice: `echo` (energetic, youthful)
- `/b2b` voice: `onyx` (unchanged, authoritative)
- Update `.env`: `OPENAI_VOICE_MONEY=echo`

---

### 6. Config & Env

**New env var:** `FREESOUND_API_KEY`

**Updated env vars:**
- `OPENAI_VOICE_MONEY=echo` (was `nova`)

**New directory:** `assets/sfx/` (gitignored, populated at runtime)

---

## Data Flow

```
/money "topic"
  → generate_script()     → {script, pexels_keywords, hook_line, tool_benefit, key_words}
  → generate_voice()      → voice.mp3  [tts-1-hd, echo]
  → fetch_clips()         → raw_clips
  → transcribe()          → (subs.ass, word_timings)  [word_timestamps=True]
  → get_sfx_cues()        → [(timestamp_ms, sfx_path), ...]
  → assemble()            → clips@2.5s + mux + sfx_mix + ASS_burn → final.mp4
```

---

## Files Changed

| File | Change Type |
|------|------------|
| `pipeline/script_generator.py` | Modify — fix labels, add key_words field |
| `pipeline/transcriber.py` | Modify — word timestamps, ASS output |
| `pipeline/sfx_fetcher.py` | New |
| `pipeline/assembler.py` | Modify — 2.5s cuts, SFX mixing, ASS |
| `pipeline/voice_generator.py` | Modify — tts-1-hd |
| `bot.py` | Modify — wire sfx_fetcher into pipelines |
| `config.py` | Modify — FREESOUND_API_KEY |
| `.env` / `.env.example` | Modify |
| `assets/sfx/` | New directory (gitignored) |
| `tests/test_voice_generator.py` | Modify — tts-1-hd |
| `tests/test_transcriber.py` | Modify — ASS output |
| `tests/test_sfx_fetcher.py` | New |

---

## Error Handling

- SFX fetch failure: non-fatal, assembler proceeds without SFX (same pattern as TranscribeError)
- Freesound API down: use cached files if available; skip SFX if no cache
- Word timestamp failure: fall back to segment-level timestamps (no word-by-word, full line instead)
