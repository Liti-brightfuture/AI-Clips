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
- Prompts explicitly forbid structural labels in the `script` field: "The script field must contain ONLY the spoken words. Do NOT include any structural labels, timestamps, or markers like 'Hook', 'Problem', 'Demo', etc."
- Add `key_words` field: 5-8 words from the script that deserve yellow highlight (numbers, prices, power words, CTA triggers). Validated: list of 5-8 non-empty strings; raises `ScriptError` if outside range or wrong type.
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
- Enable `word_timestamps=True` in Whisper call: `model.transcribe(audio_path, word_timestamps=True)`
- Minimum `openai-whisper` version: `>=20231117` (preserve existing production floor). Update `requirements.txt`.
- Word data location in Whisper result: `result["segments"][i]["words"]` — each entry is `{"word": str, "start": float, "end": float, "probability": float}`
- Replace `_segments_to_srt()` with `_words_to_ass()` — outputs `.ass` format
- Return type changes from `str` to `tuple[str, list[dict]]`: `(ass_path, word_timings)`

**`word_timings` schema:**
```python
list[dict]  # each element:
{"word": str, "start": float, "end": float}
# example: {"word": "jasper", "start": 0.52, "end": 0.84}
```

**Fallback:** If `segments[i]["words"]` is missing or empty for any segment, fall back to segment-level timing — produce one entry per segment using the segment's `start`/`end` and the full segment text as a single "word". The `word_timings` list shape is identical in both cases; only granularity differs.

**ASS Caption Style:**
- Format: Advanced SubStation Alpha (ASS)
- Font: Arial Bold, 65px
- Alignment: `2` (bottom-center in ASS v4+)
- Color: white (`&H00FFFFFF`) with 3px black outline
- Key words: yellow (`&H0000FFFF` — ASS BGR format: B=0, G=255, R=255)
- Position: `MarginV=480` from bottom — places caption at y=1440 (75% down in 1920px frame), with `Alignment=2`
- Each word = one Dialogue line with its exact `start`/`end` timestamp
- Matching: compare each transcribed word (lowercase, strip punctuation) against `key_words` list (also lowercased)

**ASS file header:**
```
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,65,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,0,2,10,10,480,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
```

**Per-word Dialogue line:**
```
# Normal word (white):
Dialogue: 0,0:00:00.52,0:00:00.84,Default,,0,0,0,,word

# Key word (yellow):
Dialogue: 0,0:00:01.10,0:00:01.45,Default,,0,0,0,,{\c&H0000FFFF&}JASPER{\r}
```

**File output:** `subs.ass` replaces `subs.srt`

---

### 3. SFX Fetcher (`pipeline/sfx_fetcher.py`) — NEW

**Responsibility:** Download, cache, and schedule sound effects.

**SFX asset strategy:** The three SFX files (`whoosh.mp3`, `impact.mp3`, `ding.mp3`) are **committed to the repo** under `assets/sfx/`. The implementer selects CC0-licensed files from freesound.org once during development and commits them. No runtime Freesound download occurs — `sfx_fetcher.py` reads from the committed files only. This removes all runtime API dependency, makes the system deterministic, and eliminates the `FREESOUND_API_KEY` requirement entirely.

**Caching:** Not applicable — files are static repo assets. `assets/sfx/` is **not** gitignored. The `assets/sfx/` directory is created by `config.py` at startup as a safety net (in case of manual deletion), but files should always be present in the repo.

**SFX categories and triggers:**

| Category | File | Trigger |
|----------|------|---------|
| `transition` | `assets/sfx/whoosh.mp3` | At each clip transition: 0ms, 2500ms, 5000ms, ... up to audio_duration |
| `impact` | `assets/sfx/impact.mp3` | key_words that contain a digit or `$` sign |
| `ding` | `assets/sfx/ding.mp3` | key_words that match: `{"free", "now", "link", "click", "try"}` |

**Function signature:**
```python
def get_sfx_cues(
    word_timings: list[dict],   # {"word": str, "start": float, "end": float}
    key_words: list[str],
    audio_duration: float,
) -> list[tuple[int, str]]:
    """
    Returns list of (timestamp_ms, sfx_path) sorted by timestamp.
    Timestamp is the word's start time in milliseconds.
    Transition cues fire at 0, 2500, 5000, ... ms up to audio_duration*1000.
    Only includes cues for SFX files that exist in the local cache.
    """
```

**Volume:** SFX mixed at -12dB relative to voice. Implemented via ffmpeg `volume=-12dB` filter on each SFX input before mixing.

**No API key required** — SFX files are static repo assets.

---

### 4. Assembler (`pipeline/assembler.py`)

**Updated signature:**
```python
def assemble(
    raw_clips: list[str],
    audio_path: str,
    ass_path: Optional[str],       # was srt_path
    sfx_cues: list[tuple[int, str]], # new — pass [] when no SFX
    output_path: str,
    work_dir: Optional[str] = None,
) -> None:
```

**Step 1 — Faster cuts:**
Each clip trimmed to max **2.5 seconds** during scale/crop:
```
ffmpeg -y -i clip.mp4 -t 2.5 -vf scale=1080:1920:... -an clip_N_scaled.mp4
```

**Step 4.5 — SFX mixing (new, between mux and encode):**
Only runs if `sfx_cues` is non-empty AND all referenced SFX files exist.
```
ffmpeg -y
  -i muxed.mp4          # original voice audio
  -i whoosh.mp3         # SFX input 1
  -i impact.mp3         # SFX input 2 (if triggered)
  -filter_complex
    "[1:a]adelay=0|0,volume=-12dB[s1];
     [2:a]adelay=2500|2500,volume=-12dB[s2];
     [0:a][s1][s2]amix=inputs=3:normalize=0[aout]"
  -map 0:v -map "[aout]"
  -c:v copy -c:a aac
  audio_with_sfx.mp4
```
Output: `audio_with_sfx.mp4` (video+mixed audio). This replaces `muxed.mp4` as the input to Step 5.

**Step 5 — Encode with ASS captions:**
- Use `subs.ass` filename (same Windows `cwd` workaround as before — set `cwd=str(work)` and pass just the filename to ffmpeg `subtitles` filter, NOT the absolute path)
- When SFX exists, input is `audio_with_sfx.mp4`; when no SFX, input is `muxed.mp4`
- `-c:a copy` (audio already encoded to AAC in Step 4.5 when SFX exists)

**Updated `_build_encode_cmd`:**
```python
def _build_encode_cmd(input_path: str, ass_name: Optional[str], output: str) -> list[str]:
    # input_path = audio_with_sfx.mp4 if SFX, else muxed.mp4
    # ass_name = "subs.ass" (basename only — cwd workaround)
```

**`test_assembler.py` updated call sites:**
```python
# assemble() calls — add sfx_cues=[] as 4th positional arg:
assemble(raw_clips, str(audio), None, [], str(output), work_dir=str(tmp_path))

# _build_encode_cmd() — second arg is now ass_name (basename string), not full path:
_build_encode_cmd(str(muxed), "subs.ass", str(output))   # with ASS
_build_encode_cmd(str(muxed), None, str(output))          # without subtitles
```

---

### 5. Voice Generator (`pipeline/voice_generator.py`)

**Changes:**
- Model constant: `TTS_MODEL = "tts-1-hd"` (named constant, not a bare string literal)
- `/money` voice: `echo` (energetic, youthful)
- `/b2b` voice: `onyx` (unchanged, authoritative)
- Update `.env`: `OPENAI_VOICE_MONEY=echo`

---

### 6. `bot.py` — Updated call sites

**`_run_money_pipeline_sync`:**
```python
ass_path, word_timings = transcribe(voice_path, str(job_dir))
audio_duration = get_audio_duration(voice_path)   # see below
sfx_cues = get_sfx_cues(word_timings, script_data["key_words"], audio_duration)
assemble(raw_clips, voice_path, ass_path, sfx_cues, str(final_path))
```

**`audio_duration` source:** Use ffprobe via `_get_duration()` already in `assembler.py`. Expose it as a public function `get_audio_duration(path: str) -> float` at module level in `assembler.py` and import it in `bot.py`:
```python
from pipeline.assembler import get_audio_duration
```
Do NOT use a byte-estimate formula — it will produce incorrect SFX timing.

**`_run_b2b_pipeline_sync`:** identical pattern.

**Import:** `from pipeline.sfx_fetcher import get_sfx_cues`

---

### 7. Config & Env

**`config.py` changes:**
- Remove `FREESOUND_API_KEY` entirely — SFX files are static repo assets, no API needed
- `OPENAI_VOICE_MONEY=echo` (was `nova`)
- New directory safety-net at startup: `(BASE_DIR / "assets" / "sfx").mkdir(parents=True, exist_ok=True)`

**`openai-whisper` in `requirements.txt`:** `openai-whisper>=20231117`

**`test_transcriber.py` updated assertions:**
```python
# test_transcribe_returns_srt_path → renamed test_transcribe_returns_ass_path:
ass_path, word_timings = transcribe(audio_path, str(tmp_path))
assert ass_path.endswith(".ass")
assert isinstance(word_timings, list)
assert all("word" in w and "start" in w and "end" in w for w in word_timings)

# test_srt_format_is_valid → renamed test_ass_format_is_valid:
assert "[Script Info]" in Path(ass_path).read_text()
assert "Dialogue:" in Path(ass_path).read_text()

# test_raises_transcribe_error_on_failure — signature unchanged, still valid
```

---

## Data Flow

```
/money "topic"
  → generate_script()     → {script, pexels_keywords, hook_line, tool_benefit, key_words}
  → generate_voice()      → voice.mp3  [tts-1-hd, echo]
  → fetch_clips()         → raw_clips
  → transcribe()          → (subs.ass, word_timings)  [word_timestamps=True, fallback: segment-level]
  → get_sfx_cues()        → [(timestamp_ms, sfx_path), ...]  [[] if no key or no cache]
  → assemble()            → clips@2.5s + mux + sfx_mix + ASS_burn → final.mp4
```

---

## Files Changed

| File | Change Type |
|------|------------|
| `pipeline/script_generator.py` | Modify — fix labels, add key_words field + validation |
| `pipeline/transcriber.py` | Modify — word timestamps, ASS output, tuple return |
| `pipeline/sfx_fetcher.py` | New |
| `pipeline/assembler.py` | Modify — 2.5s cuts, SFX mixing step, ASS, new signature |
| `pipeline/voice_generator.py` | Modify — tts-1-hd constant |
| `bot.py` | Modify — transcribe destructuring, sfx_cues wiring |
| `config.py` | Modify — optional FREESOUND_API_KEY, assets/sfx/ mkdir |
| `.env` / `.env.example` | Modify |
| `requirements.txt` | Modify — openai-whisper>=20230314 |
| `assets/sfx/` | New directory — committed to repo with 3 CC0 SFX files |
| `tests/test_voice_generator.py` | Modify — tts-1-hd constant |
| `tests/test_transcriber.py` | Modify — ASS output, tuple return |
| `tests/test_sfx_fetcher.py` | New — see test scope below |
| `tests/test_assembler.py` | Modify — new 5-arg signature |

---

## Test Scope: `tests/test_sfx_fetcher.py`

- **File missing:** When `assets/sfx/whoosh.mp3` absent, that SFX type is skipped (no exception), cue not in output
- **`get_sfx_cues` output format:** Given `word_timings` + `key_words`, output is `list[tuple[int, str]]` sorted by timestamp
- **Transition cues:** Given `audio_duration=7.5`, transition cues at 0ms, 2500ms, 5000ms
- **Impact cue:** key_word containing digit (e.g. `"$47"`) produces an `impact` cue at that word's start time
- **Ding cue:** key_word `"free"` produces a `ding` cue

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| SFX file missing from `assets/sfx/` | Log warning, skip that SFX type, continue |
| Whisper word timestamps missing | Fall back to segment-level timing (same `word_timings` schema) |
| `TranscribeError` | Non-fatal — assembler called with `ass_path=None`, `sfx_cues=[]` |
| `AssembleError` | Fatal — job marked failed |
