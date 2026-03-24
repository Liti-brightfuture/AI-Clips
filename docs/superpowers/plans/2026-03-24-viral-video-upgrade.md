# Viral Video Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the ClipBot pipeline to produce TikTok-ready clips with word-by-word yellow-highlight captions, contextual SFX, 2.5s clip cuts, and better voice quality.

**Architecture:** Each pipeline stage is modified independently (script_generator → voice_generator → transcriber → sfx_fetcher → assembler → bot wiring). Tests for transcriber and assembler are already updated to the new interface; implement to make them pass. New component `sfx_fetcher.py` reads static SFX assets from `assets/sfx/`.

**Tech Stack:** Python 3.10+, OpenAI TTS (`tts-1-hd`), Whisper (`word_timestamps=True`), ffmpeg ASS subtitles filter, ffmpeg `amix`+`adelay` for SFX mixing.

**Spec:** `docs/superpowers/specs/2026-03-24-viral-video-upgrade-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pipeline/script_generator.py` | Modify | Add `key_words` field, forbid structural labels |
| `pipeline/voice_generator.py` | Modify | Use `tts-1-hd` as named constant |
| `pipeline/transcriber.py` | Modify | Word timestamps + ASS output + tuple return |
| `pipeline/sfx_fetcher.py` | Create | Compute SFX cues from word timings + static assets |
| `pipeline/assembler.py` | Modify | 2.5s cuts, SFX mix step, ASS captions, new signature |
| `bot.py` | Modify | Wire all new interfaces together |
| `config.py` | Modify | Add `assets/sfx/` mkdir at startup |
| `.env` | Modify | `OPENAI_VOICE_MONEY=echo` |
| `requirements.txt` | Modify | Remove `elevenlabs`, keep `openai-whisper>=20231117` |
| `tests/test_script_generator.py` | Modify | Add `key_words` to mock responses |
| `tests/test_voice_generator.py` | Modify | Reference `TTS_MODEL` constant |
| `tests/test_transcriber.py` | Already updated | — |
| `tests/test_sfx_fetcher.py` | Create | Tests for cue generation |
| `tests/test_assembler.py` | Already updated | — |
| `assets/sfx/` | Manual step | Add 3 CC0 MP3 files before running |

---

## Task 1: Add SFX assets (manual, do this first)

**Files:**
- Create: `assets/sfx/whoosh.mp3`
- Create: `assets/sfx/impact.mp3`
- Create: `assets/sfx/ding.mp3`

- [ ] **Step 1: Download 3 CC0 MP3 files from freesound.org**

  Search freesound.org (filter: CC0 license):
  - `whoosh.mp3` — search "whoosh swipe" → ~0.5-1s
  - `impact.mp3` — search "impact hit short" → ~0.3s
  - `ding.mp3` — search "notification ding" → ~0.5s

  Save to `D:\MoneyMaker\AIClips\assets\sfx\`

- [ ] **Step 2: Commit the SFX files**

  ```bash
  git add assets/sfx/whoosh.mp3 assets/sfx/impact.mp3 assets/sfx/ding.mp3
  git commit -m "assets: add CC0 SFX files for video pipeline"
  ```

---

## Task 2: Config — add assets/sfx mkdir

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add assets/sfx directory creation**

  In `config.py`, after the existing `OUTPUT_DIR.mkdir(...)` line, add a single block:

  ```python
  SFX_DIR: Path = BASE_DIR / "assets" / "sfx"
  SFX_DIR.mkdir(parents=True, exist_ok=True)
  ```

- [ ] **Step 1b: Verify FREESOUND_API_KEY is NOT in config.py**

  ```bash
  python -c "import config; assert not hasattr(config, 'FREESOUND_API_KEY'), 'Key still present'; print('OK — key absent')"
  ```
  Expected: `OK — key absent`

- [ ] **Step 2: Remove elevenlabs from requirements.txt**

  In `requirements.txt`, delete the line:
  ```
  elevenlabs>=1.3
  ```

- [ ] **Step 3: Verify bot starts without error**

  ```bash
  python -c "import config; print('OK')"
  ```
  Expected: `OK`

- [ ] **Step 4: Commit**

  ```bash
  git add config.py requirements.txt
  git commit -m "chore: add SFX_DIR to config, remove unused elevenlabs dep"
  ```

---

## Task 3: Voice Generator — tts-1-hd

**Files:**
- Modify: `pipeline/voice_generator.py`
- Modify: `tests/test_voice_generator.py`

- [ ] **Step 1: Update test to reference TTS_MODEL constant**

  In `tests/test_voice_generator.py`, update `test_generate_voice_writes_file` to assert the model used:

  ```python
  def test_generate_voice_writes_file(tmp_path):
      from pipeline.voice_generator import generate_voice, TTS_MODEL

      output_path = tmp_path / "voice.mp3"
      output_path.write_bytes(b"")

      mock_response = MagicMock()
      mock_client = MagicMock()
      mock_client.audio.speech.create.return_value = mock_response

      generate_voice("Hello world", str(output_path), client=mock_client, voice_name="nova")

      mock_client.audio.speech.create.assert_called_once_with(
          model=TTS_MODEL,
          voice="nova",
          input="Hello world",
      )
      mock_response.stream_to_file.assert_called_once_with(str(output_path))
  ```

- [ ] **Step 2: Run test — expect FAIL**

  ```bash
  pytest tests/test_voice_generator.py::test_generate_voice_writes_file -v
  ```
  Expected: FAIL — `ImportError: cannot import name 'TTS_MODEL'`

- [ ] **Step 3: Add TTS_MODEL constant to voice_generator.py**

  In `pipeline/voice_generator.py`, add at the top (after imports):
  ```python
  TTS_MODEL = "tts-1-hd"
  ```

  In the `generate_voice` function, change the API call from:
  ```python
  response = client.audio.speech.create(
      model="tts-1",
  ```
  to:
  ```python
  response = client.audio.speech.create(
      model=TTS_MODEL,
  ```

- [ ] **Step 4: Run tests — expect PASS**

  ```bash
  pytest tests/test_voice_generator.py -v
  ```
  Expected: all 3 tests PASS

- [ ] **Step 5: Update .env and .env.example**

  In `.env`, change `OPENAI_VOICE_MONEY=nova` to `OPENAI_VOICE_MONEY=echo`.

  In `.env.example`, change `OPENAI_VOICE_MONEY=nova` to `OPENAI_VOICE_MONEY=echo`.

- [ ] **Step 6: Commit**

  ```bash
  git add pipeline/voice_generator.py tests/test_voice_generator.py .env .env.example
  git commit -m "feat: voice generator uses tts-1-hd model, echo voice for /money"
  ```

---

## Task 4: Script Generator — key_words + no structural labels

**Files:**
- Modify: `pipeline/script_generator.py`
- Modify: `tests/test_script_generator.py`

- [ ] **Step 1: Update test mock responses to include key_words**

  In `tests/test_script_generator.py`, update both mock responses:

  ```python
  MOCK_MONEY_RESPONSE = {
      "script": "AI is changing everything. Most people waste 4 hours writing. Jasper writes it in 4 minutes. Try it free. Link in bio — free trial, no card needed.",
      "pexels_keywords": ["artificial intelligence", "laptop typing", "productivity"],
      "hook_line": "AI is changing everything.",
      "tool_benefit": "Jasper cuts your writing time from hours to minutes.",
      "key_words": ["free", "4 hours", "4 minutes", "Jasper", "trial"],
  }

  MOCK_B2B_RESPONSE = {
      "script": "HubSpot costs $800/month. Monday.com costs $200. Same features. Here is the breakdown. Full breakdown — link in bio.",
      "pexels_keywords": ["business meeting", "CRM software", "startup office"],
      "hook_line": "HubSpot costs $800/month.",
      "data_point": "Monday.com costs 75% less than HubSpot for teams under 50.",
      "key_words": ["$800", "$200", "75%", "HubSpot", "Monday.com"],
  }
  ```

  Add a new test for key_words validation:

  ```python
  def test_missing_key_words_raises_script_error():
      from pipeline.script_generator import generate_script
      from pipeline.exceptions import ScriptError
      incomplete = {**MOCK_MONEY_RESPONSE}
      del incomplete["key_words"]
      mock_client = make_mock_openai(incomplete)
      with pytest.raises(ScriptError):
          generate_script("test topic", command="money", client=mock_client)


  def test_key_words_too_few_raises_script_error():
      from pipeline.script_generator import generate_script
      from pipeline.exceptions import ScriptError
      bad = {**MOCK_MONEY_RESPONSE, "key_words": ["only_one"]}
      mock_client = make_mock_openai(bad)
      with pytest.raises(ScriptError, match="key_words"):
          generate_script("test topic", command="money", client=mock_client)


  def test_generate_money_script_has_key_words():
      from pipeline.script_generator import generate_script
      mock_client = make_mock_openai(MOCK_MONEY_RESPONSE)
      result = generate_script("Jasper AI review 2026", command="money", client=mock_client)
      assert "key_words" in result
      assert 5 <= len(result["key_words"]) <= 8
  ```

- [ ] **Step 2: Run new tests — expect FAIL**

  ```bash
  pytest tests/test_script_generator.py -v
  ```
  Expected: new tests FAIL — existing tests may also fail because mock response now has `key_words` which is not in the schema yet

- [ ] **Step 3: Update script_generator.py**

  **3a — Update prompts** (both MONEY and B2B). Add to the end of each:

  ```python
  MONEY_SYSTEM_PROMPT = """...existing content...
  The script field must contain ONLY the spoken words. Do NOT include any structural labels, timestamps, or markers like 'Hook', 'Problem', 'Demo', etc.
  Return 5-8 words or short phrases from the script as key_words — these will be highlighted yellow on screen. Pick numbers, prices, the tool name, power words (free, instant, best), and the CTA trigger word."""

  B2B_SYSTEM_PROMPT = """...existing content...
  The script field must contain ONLY the spoken words. Do NOT include any structural labels, timestamps, or markers like 'Hook', 'Problem', 'Solution', 'Data point', 'CTA', etc.
  Return 5-8 words or short phrases from the script as key_words — highlighted yellow on screen. Pick stats, prices, product names, and decisive words."""
  ```

  **3b — Add key_words to JSON schemas** in both `MONEY_SCHEMA` and `B2B_SCHEMA`:

  ```python
  # In MONEY_SCHEMA["json_schema"]["schema"]["properties"]:
  "key_words": {"type": "array", "items": {"type": "string"}},

  # In MONEY_SCHEMA["json_schema"]["schema"]["required"]:
  "key_words"  # add to the list
  ```

  Same for `B2B_SCHEMA`.

  **3c — Add key_words to required field sets:**
  ```python
  REQUIRED_MONEY_FIELDS = {"script", "pexels_keywords", "hook_line", "tool_benefit", "key_words"}
  REQUIRED_B2B_FIELDS = {"script", "pexels_keywords", "hook_line", "data_point", "key_words"}
  ```

  **3d — Add key_words validation** after the `pexels_keywords` validation block:

  ```python
  key_words = data.get("key_words")
  if (
      not isinstance(key_words, list)
      or not (5 <= len(key_words) <= 8)
      or not all(isinstance(k, str) and k for k in key_words)
  ):
      raise ScriptError("key_words must be a list of 5-8 non-empty strings")
  ```

- [ ] **Step 4: Run tests — expect PASS**

  ```bash
  pytest tests/test_script_generator.py -v
  ```
  Expected: all tests PASS

- [ ] **Step 5: Commit**

  ```bash
  git add pipeline/script_generator.py tests/test_script_generator.py
  git commit -m "feat: script generator adds key_words field, forbids structural labels in script"
  ```

---

## Task 5: Transcriber — word timestamps + ASS output

**Files:**
- Modify: `pipeline/transcriber.py`
- Tests are already written at `tests/test_transcriber.py` — implement to make them pass

- [ ] **Step 1: Run existing tests — expect FAIL**

  ```bash
  pytest tests/test_transcriber.py -v
  ```
  Expected: FAIL — tests expect tuple return and `.ass` output

- [ ] **Step 2: Rewrite transcriber.py**

  Replace the entire contents of `pipeline/transcriber.py` with:

  ```python
  import logging
  import re
  from pathlib import Path
  from typing import Optional

  from pipeline.exceptions import TranscribeError

  logger = logging.getLogger(__name__)

  ASS_HEADER = """\
  [Script Info]
  ScriptType: v4.00+
  PlayResX: 1080
  PlayResY: 1920

  [V4+ Styles]
  Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
  Style: Default,Arial,65,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,3,0,2,10,10,480,1

  [Events]
  Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
  """


  def _load_model():
      import whisper
      return whisper.load_model("base")


  def _ass_time(seconds: float) -> str:
      h = int(seconds // 3600)
      m = int((seconds % 3600) // 60)
      s = seconds % 60
      return f"{h}:{m:02}:{s:05.2f}"


  def _strip_punct(word: str) -> str:
      return re.sub(r"[^\w$]", "", word).lower()


  def _words_to_ass(word_timings: list[dict], key_words: list[str]) -> str:
      kw_set = {_strip_punct(kw) for kw in key_words}
      lines = [ASS_HEADER.rstrip()]
      for entry in word_timings:
          start = _ass_time(entry["start"])
          end = _ass_time(entry["end"])
          word = entry["word"].strip()
          if not word:
              continue
          if _strip_punct(word) in kw_set:
              text = f"{{\\c&H0000FFFF&}}{word}{{\\r}}"
          else:
              text = word
          lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
      return "\n".join(lines)


  def _extract_word_timings(segments: list) -> list[dict]:
      """Extract per-word timings from Whisper segments. Falls back to segment-level."""
      timings = []
      for seg in segments:
          words = seg.get("words") or []
          if words:
              for w in words:
                  timings.append({
                      "word": w.get("word", ""),
                      "start": float(w.get("start", seg["start"])),
                      "end": float(w.get("end", seg["end"])),
                  })
          else:
              # Fallback: treat entire segment text as one entry
              timings.append({
                  "word": seg["text"].strip(),
                  "start": float(seg["start"]),
                  "end": float(seg["end"]),
              })
      return timings


  def transcribe(audio_path: str, output_dir: str, key_words: Optional[list] = None) -> tuple[str, list[dict]]:
      """
      Transcribe audio with Whisper and write a .ass subtitle file.

      Args:
          audio_path: Path to the .mp3 file.
          output_dir: Directory to write subs.ass.
          key_words: Words to highlight yellow. Defaults to [].

      Returns:
          (ass_path, word_timings) — path to subs.ass and list of
          {"word": str, "start": float, "end": float} dicts.

      Raises:
          TranscribeError: On any failure. Caught by the queue worker (non-fatal).
      """
      if key_words is None:
          key_words = []
      try:
          model = _load_model()
          result = model.transcribe(audio_path, word_timestamps=True)
          segments = result.get("segments", [])
          word_timings = _extract_word_timings(segments)
          ass_content = _words_to_ass(word_timings, key_words)
          ass_path = Path(output_dir) / "subs.ass"
          ass_path.write_text(ass_content, encoding="utf-8")
          return str(ass_path), word_timings
      except Exception as e:
          raise TranscribeError(f"Whisper transcription failed: {e}") from e
  ```

- [ ] **Step 3: Run tests — expect PASS**

  ```bash
  pytest tests/test_transcriber.py -v
  ```
  Expected: all 4 tests PASS

- [ ] **Step 4: Commit**

  ```bash
  git add pipeline/transcriber.py
  git commit -m "feat: transcriber outputs word-by-word ASS captions with yellow key_words highlight"
  ```

---

## Task 6: SFX Fetcher — new component

**Files:**
- Create: `pipeline/sfx_fetcher.py`
- Create: `tests/test_sfx_fetcher.py`

- [ ] **Step 1: Write the tests**

  Create `tests/test_sfx_fetcher.py`:

  ```python
  import pytest
  from pathlib import Path
  from unittest.mock import patch

  from pipeline.sfx_fetcher import get_sfx_cues


  WORD_TIMINGS = [
      {"word": "Jasper", "start": 0.1, "end": 0.4},
      {"word": "is", "start": 0.4, "end": 0.5},
      {"word": "free", "start": 0.5, "end": 0.8},
      {"word": "$47", "start": 0.9, "end": 1.2},
      {"word": "now", "start": 1.3, "end": 1.5},
  ]
  KEY_WORDS = ["free", "$47", "Jasper", "now"]


  def make_sfx_dir(tmp_path: Path) -> Path:
      sfx_dir = tmp_path / "assets" / "sfx"
      sfx_dir.mkdir(parents=True)
      (sfx_dir / "whoosh.mp3").write_bytes(b"fake")
      (sfx_dir / "impact.mp3").write_bytes(b"fake")
      (sfx_dir / "ding.mp3").write_bytes(b"fake")
      return sfx_dir


  def test_transition_cues_fire_at_intervals(tmp_path):
      sfx_dir = make_sfx_dir(tmp_path)
      with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
          cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=7.5)
      transition_cues = [c for c in cues if "whoosh" in c[1]]
      timestamps = [c[0] for c in transition_cues]
      assert 0 in timestamps
      assert 2500 in timestamps
      assert 5000 in timestamps


  def test_impact_cue_on_digit_keyword(tmp_path):
      sfx_dir = make_sfx_dir(tmp_path)
      with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
          cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=5.0)
      impact_cues = [c for c in cues if "impact" in c[1]]
      assert len(impact_cues) == 1
      assert impact_cues[0][0] == 900  # $47 starts at 0.9s = 900ms


  def test_ding_cue_on_ding_keyword(tmp_path):
      sfx_dir = make_sfx_dir(tmp_path)
      with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
          cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=5.0)
      ding_cues = [c for c in cues if "ding" in c[1]]
      ding_timestamps = [c[0] for c in ding_cues]
      assert 500 in ding_timestamps   # "free" at 0.5s
      assert 1300 in ding_timestamps  # "now" at 1.3s


  def test_missing_sfx_file_skips_silently(tmp_path):
      sfx_dir = make_sfx_dir(tmp_path)
      (sfx_dir / "impact.mp3").unlink()  # remove impact
      with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
          cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=5.0)
      assert not any("impact" in c[1] for c in cues)


  def test_output_sorted_by_timestamp(tmp_path):
      sfx_dir = make_sfx_dir(tmp_path)
      with patch("pipeline.sfx_fetcher.SFX_DIR", sfx_dir):
          cues = get_sfx_cues(WORD_TIMINGS, KEY_WORDS, audio_duration=5.0)
      timestamps = [c[0] for c in cues]
      assert timestamps == sorted(timestamps)
  ```

- [ ] **Step 2: Run tests — expect FAIL**

  ```bash
  pytest tests/test_sfx_fetcher.py -v
  ```
  Expected: FAIL — `ModuleNotFoundError: pipeline.sfx_fetcher`

- [ ] **Step 3: Create pipeline/sfx_fetcher.py**

  ```python
  import logging
  import re
  from pathlib import Path

  logger = logging.getLogger(__name__)

  SFX_DIR = Path(__file__).parent.parent / "assets" / "sfx"

  DING_WORDS = {"free", "now", "link", "click", "try"}
  TRANSITION_INTERVAL_MS = 2500


  def _strip_punct(word: str) -> str:
      return re.sub(r"[^\w$]", "", word).lower()


  def get_sfx_cues(
      word_timings: list[dict],
      key_words: list[str],
      audio_duration: float,
  ) -> list[tuple[int, str]]:
      """
      Returns list of (timestamp_ms, sfx_path) sorted by timestamp.
      Only includes cues for SFX files that exist in assets/sfx/.
      Transition cues fire at 0, 2500, 5000, ... ms up to audio_duration*1000.
      """
      cues = []
      whoosh = SFX_DIR / "whoosh.mp3"
      impact = SFX_DIR / "impact.mp3"
      ding = SFX_DIR / "ding.mp3"

      # Transition cues every TRANSITION_INTERVAL_MS
      if whoosh.exists():
          t = 0
          limit = int(audio_duration * 1000)
          while t < limit:
              cues.append((t, str(whoosh)))
              t += TRANSITION_INTERVAL_MS
      else:
          logger.warning("SFX whoosh.mp3 not found in assets/sfx/ — skipping transitions")

      # Build word → start_ms lookup (first occurrence wins)
      word_map: dict[str, int] = {}
      for entry in word_timings:
          clean = _strip_punct(entry["word"])
          if clean and clean not in word_map:
              word_map[clean] = int(entry["start"] * 1000)

      # Impact cues — key words with digits or $
      if impact.exists():
          for kw in key_words:
              kw_clean = _strip_punct(kw)
              if any(c.isdigit() or c == "$" for c in kw_clean):
                  if kw_clean in word_map:
                      cues.append((word_map[kw_clean], str(impact)))
      else:
          logger.warning("SFX impact.mp3 not found in assets/sfx/ — skipping impact cues")

      # Ding cues — key words in DING_WORDS set
      if ding.exists():
          for kw in key_words:
              kw_clean = _strip_punct(kw)
              if kw_clean in DING_WORDS and kw_clean in word_map:
                  cues.append((word_map[kw_clean], str(ding)))
      else:
          logger.warning("SFX ding.mp3 not found in assets/sfx/ — skipping ding cues")

      return sorted(cues, key=lambda x: x[0])
  ```

- [ ] **Step 4: Run tests — expect PASS**

  ```bash
  pytest tests/test_sfx_fetcher.py -v
  ```
  Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

  ```bash
  git add pipeline/sfx_fetcher.py tests/test_sfx_fetcher.py
  git commit -m "feat: add sfx_fetcher — computes transition/impact/ding cues from static assets"
  ```

---

## Task 7: Assembler — 2.5s cuts + SFX mixing + ASS + new signature

**Files:**
- Modify: `pipeline/assembler.py`
- Tests already updated at `tests/test_assembler.py` — implement to pass them

- [ ] **Step 1: Run existing tests — expect FAIL**

  ```bash
  pytest tests/test_assembler.py -v
  ```
  Expected: FAIL — `assemble()` called with wrong number of arguments

- [ ] **Step 2: Rewrite assembler.py**

  Replace the entire contents of `pipeline/assembler.py` with:

  ```python
  import os
  import subprocess
  from pathlib import Path
  from typing import List, Optional

  from pipeline.exceptions import AssembleError


  def _run(cmd: List[str], cwd: Optional[str] = None) -> None:
      result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
      if result.returncode != 0:
          raise AssembleError(f"ffmpeg failed:\n{result.stderr[-1000:]}")


  def _get_duration(path: str) -> float:
      result = subprocess.run(
          ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
           "-of", "csv=p=0", path],
          capture_output=True, text=True,
      )
      if result.returncode != 0 or not result.stdout.strip():
          raise AssembleError(f"ffprobe failed on {path}")
      return float(result.stdout.strip())


  def get_audio_duration(path: str) -> float:
      """Public wrapper — returns duration in seconds via ffprobe."""
      return _get_duration(path)


  def _get_clip_duration(path: str) -> float:
      return _get_duration(path)


  def _build_concat_list(clips: List[str], clip_durations: dict, total_duration: float) -> List[str]:
      if not clips:
          raise AssembleError("No clips provided to concat list builder.")
      lines = []
      accumulated = 0.0
      i = 0
      while accumulated < total_duration:
          clip = clips[i % len(clips)]
          lines.append(f"file '{clip}'")
          accumulated += clip_durations[clip]
          i += 1
      return lines


  def _build_encode_cmd(input_path: str, ass_name: Optional[str], output: str) -> List[str]:
      """
      input_path: muxed.mp4 or audio_with_sfx.mp4
      ass_name: basename only (e.g. "subs.ass") — cwd workaround for Windows paths
      """
      if ass_name:
          vf = (
              f"subtitles={ass_name}:force_style="
              "'FontName=Arial,FontSize=65,Bold=1,"
              "PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
              "Outline=3,MarginV=480,Alignment=2'"
          )
          return [
              "ffmpeg", "-y", "-i", input_path,
              "-vf", vf,
              "-c:v", "libx264", "-crf", "23", "-preset", "fast",
              "-c:a", "copy", "-movflags", "+faststart",
              output,
          ]
      else:
          return [
              "ffmpeg", "-y", "-i", input_path,
              "-c:v", "libx264", "-crf", "23", "-preset", "fast",
              "-c:a", "copy", "-movflags", "+faststart",
              output,
          ]


  def _mix_sfx(muxed: str, sfx_cues: List[tuple], output: str) -> None:
      """Mix SFX into muxed video at specified timestamps. Output is a new .mp4."""
      cmd = ["ffmpeg", "-y", "-i", muxed]
      filter_parts = []
      for i, (ts_ms, sfx_path) in enumerate(sfx_cues):
          cmd += ["-i", sfx_path]
          idx = i + 1
          filter_parts.append(
              f"[{idx}:a]adelay={ts_ms}|{ts_ms},volume=-12dB[s{idx}]"
          )
      n = len(sfx_cues)
      inputs = "[0:a]" + "".join(f"[s{i+1}]" for i in range(n))
      filter_parts.append(f"{inputs}amix=inputs={n + 1}:normalize=0[aout]")
      cmd += [
          "-filter_complex", ";".join(filter_parts),
          "-map", "0:v", "-map", "[aout]",
          "-c:v", "copy", "-c:a", "aac",
          output,
      ]
      _run(cmd)


  def assemble(
      raw_clips: List[str],
      audio_path: str,
      ass_path: Optional[str],
      sfx_cues: List[tuple],
      output_path: str,
      work_dir: Optional[str] = None,
  ) -> None:
      """
      Assemble final video from stock clips, voice audio, optional captions and SFX.

      Args:
          raw_clips: Downloaded stock clip paths.
          audio_path: Path to .mp3 voice file.
          ass_path: Path to .ass subtitle file, or None.
          sfx_cues: List of (timestamp_ms, sfx_path). Pass [] for no SFX.
          output_path: Where to write final.mp4.
          work_dir: Directory for intermediates (defaults to output dir).

      Raises:
          AssembleError: If any ffmpeg step fails.
      """
      out = Path(output_path)
      work = Path(work_dir) if work_dir else out.parent
      work.mkdir(parents=True, exist_ok=True)

      intermediates = []

      try:
          # Step 1: Scale/crop each clip to 1080x1920, max 2.5 seconds
          scaled_clips = []
          for i, clip in enumerate(raw_clips):
              scaled = str(work / f"clip_{i}_scaled.mp4")
              _run([
                  "ffmpeg", "-y", "-i", clip,
                  "-t", "2.5",
                  "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30",
                  "-an", scaled,
              ])
              scaled_clips.append(scaled)
              intermediates.append(scaled)

          # Step 2: Get audio duration
          audio_duration = _get_duration(audio_path)

          # Step 3: Build concat list
          clip_durations = {c: _get_clip_duration(c) for c in scaled_clips}
          concat_lines = _build_concat_list(scaled_clips, clip_durations, audio_duration)
          concat_file = work / "concat.txt"
          concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
          intermediates.append(str(concat_file))

          video_raw = str(work / "video_raw.mp4")
          _run([
              "ffmpeg", "-y", "-f", "concat", "-safe", "0",
              "-i", str(concat_file),
              "-t", str(audio_duration),
              "-c", "copy", video_raw,
          ])
          intermediates.append(video_raw)

          # Step 4: Mux audio
          muxed = str(work / "muxed.mp4")
          _run([
              "ffmpeg", "-y", "-i", video_raw, "-i", audio_path,
              "-map", "0:v", "-map", "1:a",
              "-c:v", "copy", "-c:a", "aac", "-shortest", muxed,
          ])
          intermediates.append(muxed)

          # Step 4.5: Mix SFX (only if cues provided)
          if sfx_cues:
              sfx_mixed = str(work / "audio_with_sfx.mp4")
              _mix_sfx(muxed, sfx_cues, sfx_mixed)
              encode_input = sfx_mixed
              intermediates.append(sfx_mixed)
          else:
              encode_input = muxed

          # Step 5: Encode with optional ASS captions
          ass_name = Path(ass_path).name if ass_path else None
          cmd = _build_encode_cmd(encode_input, ass_name, str(out))
          _run(cmd, cwd=str(work))

      finally:
          if out.exists():
              for f in intermediates:
                  try:
                      os.remove(f)
                  except FileNotFoundError:
                      pass
  ```

- [ ] **Step 3: Run tests — expect PASS**

  ```bash
  pytest tests/test_assembler.py -v
  ```
  Expected: all 4 tests PASS

- [ ] **Step 4: Commit**

  ```bash
  git add pipeline/assembler.py
  git commit -m "feat: assembler — 2.5s cuts, SFX mixing, ASS captions, get_audio_duration export"
  ```

---

## Task 8: Wire everything in bot.py

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Update imports in bot.py**

  Add these imports at the top (with the existing pipeline imports):

  ```python
  from pipeline.sfx_fetcher import get_sfx_cues
  from pipeline.assembler import get_audio_duration
  ```

  Remove `DB_PATH` from the `generate_voice` imports section if it's there
  (it was already removed in a previous session).

- [ ] **Step 2: Update _run_money_pipeline_sync**

  Replace the current `transcribe` and `assemble` calls:

  ```python
  def _run_money_pipeline_sync(topic: str, job_dir: Path) -> tuple:
      script_data = generate_script(topic, command="money")
      script = script_data["script"]
      keywords = script_data["pexels_keywords"]

      voice_path = str(job_dir / "voice.mp3")
      warning = generate_voice(script, voice_path, voice_name=config.OPENAI_VOICE_MONEY)

      raw_clips = fetch_clips(keywords, str(job_dir), command="money")

      try:
          ass_path, word_timings = transcribe(voice_path, str(job_dir), script_data.get("key_words", []))
          audio_duration = get_audio_duration(voice_path)
          sfx_cues = get_sfx_cues(word_timings, script_data.get("key_words", []), audio_duration)
      except TranscribeError:
          ass_path = None
          sfx_cues = []

      final_path = job_dir / "final.mp4"
      assemble(raw_clips, voice_path, ass_path, sfx_cues, str(final_path))

      caption = generate_caption(script_data, command="money")
      return final_path, caption, warning
  ```

- [ ] **Step 3: Update _run_b2b_pipeline_sync** — identical pattern:

  ```python
  def _run_b2b_pipeline_sync(topic: str, job_dir: Path) -> tuple:
      from researcher import run_research

      research_text = run_research(topic, config.GPT_RESEARCHER_PATH)

      script_data = generate_script(topic, command="b2b", research_text=research_text)
      script = script_data["script"]
      keywords = script_data["pexels_keywords"]

      voice_path = str(job_dir / "voice.mp3")
      warning = generate_voice(script, voice_path, voice_name=config.OPENAI_VOICE_B2B)

      raw_clips = fetch_clips(keywords, str(job_dir), command="b2b")

      try:
          ass_path, word_timings = transcribe(voice_path, str(job_dir), script_data.get("key_words", []))
          audio_duration = get_audio_duration(voice_path)
          sfx_cues = get_sfx_cues(word_timings, script_data.get("key_words", []), audio_duration)
      except TranscribeError:
          ass_path = None
          sfx_cues = []

      final_path = job_dir / "final.mp4"
      assemble(raw_clips, voice_path, ass_path, sfx_cues, str(final_path))

      caption = generate_caption(script_data, command="b2b")
      return final_path, caption, warning
  ```

- [ ] **Step 4: Run full test suite**

  ```bash
  pytest -v
  ```
  Expected: all tests PASS

- [ ] **Step 5: Commit**

  ```bash
  git add bot.py
  git commit -m "feat: wire word-by-word captions, SFX cues, and get_audio_duration into bot pipelines"
  ```

---

## Task 9: Smoke test end-to-end

- [ ] **Step 1: Ensure SFX files exist**

  ```bash
  ls assets/sfx/
  ```
  Expected: `whoosh.mp3  impact.mp3  ding.mp3  README.md` (README.md is already committed from Task 1 setup)

- [ ] **Step 2: Start the bot**

  ```bash
  python bot.py
  ```

- [ ] **Step 3: Send a test command via Telegram**

  Send `/money "Jasper AI review 2026"` and verify:
  - No `ElevenLabs` errors in log
  - Log shows `POST /v1/audio/speech` (OpenAI TTS)
  - Log shows Whisper transcription running
  - Video arrives on Telegram with word-by-word captions visible
  - Clips change roughly every 2-3 seconds
  - SFX audible on key words

- [ ] **Step 4: Final commit**

  ```bash
  git add .
  git commit -m "feat: complete viral video upgrade — word-by-word captions, SFX, 2.5s cuts, tts-1-hd"
  ```
