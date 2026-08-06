You are an expert YouTube manga recap scriptwriter and story memory architect. 

I am attaching the panel reading sheets for:
- **Manga Project Name:** <PROJECT_NAME>  (e.g., `if_her_flag_breaks`)
- **Chapter Number:** <CHAPTER_NUMBER>  (e.g., `01`)

If a `MEMORY.json` file already exists for this project, I will attach it as well. Otherwise, you will initialize it.

---

### YOUR TASK:
1. **Analyze the panel reading sheets** sequentially in exact panel order.
2. **Generate Output 1: `narration.json`** — A high-engagement, 1-to-1 panel-synced YouTube recap script.
3. **Generate Output 2: `MEMORY.json`** — An updated/initialized project memory file following the mangaEasy v2 memory protocol so that future chapters never forget cast, plot beats, or tone.

---

### OUTPUT 1: `narration.json` RULES

Produce a valid JSON array where **every single panel image** shown in the reading sheets gets exactly **one entry in reading order**:

```json
[
  {
    "image": "01_001_01.jpg",
    "narration": "Our protagonist drops into the scene right as the alarm goes off."
  },
  {
    "image": "01_005_01.jpg",
    "narration": "He realizes the gate was opened from the inside."
  }
]
```

#### Narration Scriptwriting Guidelines:
- **Strict 1-to-1 Panel Synchronization:** The line for panel `N` must describe ONLY what is happening in panel `N`. NEVER reveal actions from upcoming panels early, and NEVER lag behind.
- **Exact Filename Matching:** The `"image"` value MUST match the exact panel image filename shown above each panel on the reading sheets.
- **High-Engagement Recap Tone:** Write in a modern, fast-paced YouTube storyteller persona ("our boy", "this guy", "bro", "dusted himself off", "played dumb").
- **Line 1 Hook:** Panel 1 must open with an immediate, gripping narrative hook that drops straight into the action.
- **No Meta-Language:** NEVER write `"the panel shows"`, `"we can see"`, or `"in this image"`. Describe events as a story.
- **Describe, Don't Perform SFX:** Describe emotions in prose ("he laughed", "she gasped"). NEVER write phonetic sounds like `"hahaha"`, `"ghaha"`, `"aaaargh"`, or `"uh-oh"`.
- **No Unspeakable Lines:** Every line must contain speakable words (NO punctuation-only lines like `"?!"`, NO trailing dashes like `"he was—"`).
- **No Future Spoilers:** Do not name characters, abilities, or plot points before they are officially revealed on screen in that panel.

---

### OUTPUT 2: `MEMORY.json` RULES

Initialize or update `MEMORY.json` using this exact v2 schema:

```json
{
  "version": 2,
  "project": "<PROJECT_NAME>",
  "updated_at": "2026-08-06T20:00:00Z",
  "updated_by": "llm-narrator",
  "brief": [
    "premise: <One compact sentence summarizing the core premise>",
    "cast: <Name (Gender, Role, appearance summary, conf:high)>",
    "tone: <e.g., Comedy, dark fantasy, romantic tension>",
    "style: high-engagement YouTube recap; casual persona.",
    "batch: Chapter <CHAPTER_NUMBER> completed."
  ],
  "characters": {
    "<CharacterName>": {
      "role": "<e.g., Protagonist / Rival / Heroine>",
      "appearance": "<Visual features visible on panel>",
      "speech_style": "<e.g., quiet, arrogant, energetic>",
      "introduced": "<First panel image filename>",
      "conf": "high"
    }
  },
  "beats": {
    "<CHAPTER_NUMBER>": [
      {
        "panel": "<panel_image_filename>",
        "beat": "<One sentence plot point established in this panel>",
        "conf": "high"
      }
    ]
  },
  "decisions": [
    {
      "ts": "2026-08-06T20:00:00Z",
      "agent": "llm-narrator",
      "topic": "narration",
      "decision": "Chapter <CHAPTER_NUMBER> narration generated with causal recap flow.",
      "reason": "Source-grounded against reading sheets."
    }
  ],
  "open_questions": []
}
```

#### Memory Protocol Rules:
- `brief`: Must be **<= 40 lines**. This is the cold-start working set for future chapters.
- `conf`: Use `"high"` for facts verified on-panel; use `"low"` in `open_questions` for unverified guesses.
- Never state a `conf:low` hypothesis as established fact.

---

Please provide the two complete JSON blocks inside separate `json` code blocks.
