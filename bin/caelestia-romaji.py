"""Romanise timed lyrics while keeping karaoke timing.

stdin:  {"lines": [{"text", "syllabus": [{"time", "duration", "text"}], "bg": {...}|null, ...}]}
stdout: the same document with text and syllables romanised.

Japanese uses cutlet over MeCab/UniDic, which reads kanji in context rather
than character by character. Readings are produced per word, so a word's
timing is rebuilt from the syllables (usually single kana or kanji in Apple's
TTML) that it covers. Chinese becomes tone-marked pinyin and Korean follows
the Revised Romanization. The language is decided once per song: Han
characters in a song with any kana are Japanese, otherwise Chinese.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

KANA = re.compile(r"[぀-ヿㇰ-ㇿｦ-ﾟ]")
HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "caelestia" / "romaji"
VERSION = 2

_katsu = None


def katsu():
    global _katsu
    if _katsu is None:
        import cutlet

        _katsu = cutlet.Cutlet()
        _katsu.use_foreign_spelling = False
    return _katsu


# ---- Korean (Revised Romanization) ---------------------------------------

INITIALS = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
MEDIALS = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
           "yu", "eu", "ui", "i"]
FINALS = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
          "ng", "t", "t", "k", "t", "p", "t"]
# Final consonants re-pronounced as the next syllable's initial when it starts
# with a silent ieung (연음), e.g. 사랑이 -> sarang-i, 먹어 -> meogeo.
LIAISON = {1: "g", 4: "n", 7: "d", 8: "r", 16: "m", 17: "b", 19: "s", 21: "ng", 22: "j", 23: "ch", 24: "k",
           25: "t", 26: "p", 27: ""}


def romanise_korean(text: str) -> str:
    out = []
    chars = list(text)
    carry = None
    for index, ch in enumerate(chars):
        code = ord(ch) - 0xAC00
        if not 0 <= code < 11172:
            out.append(ch)
            carry = None
            continue
        initial, medial, final = code // 588, (code % 588) // 28, code % 28
        nxt = ord(chars[index + 1]) - 0xAC00 if index + 1 < len(chars) else -1
        next_silent = 0 <= nxt < 11172 and nxt // 588 == 11
        head = INITIALS[initial]
        if initial == 11 and carry:
            head = carry
        carry = None
        tail = FINALS[final]
        if final and next_silent and final in LIAISON:
            carry = LIAISON[final]
            tail = ""
        out.append(head + MEDIALS[medial] + tail)
    return "".join(out)


# ---- Chinese ---------------------------------------------------------------

def pinyin_tokens(text: str) -> list[tuple[int, int, str, bool]]:
    from pypinyin import Style, pinyin

    tokens = []
    index = 0
    while index < len(text):
        ch = text[index]
        if HAN.match(ch):
            reading = pinyin(ch, style=Style.TONE, heteronym=False)[0][0]
            tokens.append((index, index + 1, reading, True))
            index += 1
        else:
            start = index
            while index < len(text) and not HAN.match(text[index]):
                index += 1
            chunk = text[start:index]
            tokens.append((start, index, chunk, False))
    return tokens


# ---- Japanese --------------------------------------------------------------

def japanese_tokens(text: str) -> list[tuple[int, int, str, bool]]:
    k = katsu()
    words = k.tagger(text)
    romaji = k.romaji_tokens(words, capitalize=False)
    tokens = []
    cursor = 0
    for word, token in zip(words, romaji):
        surface = word.surface
        start = text.find(surface, cursor)
        if start < 0:
            continue
        end = start + len(surface)
        tokens.append((start, end, token.surface, bool(token.space)))
        cursor = end
    return tokens


def plain(text: str, language: str) -> str:
    if language == "ko":
        return romanise_korean(text)
    if language == "ja" and (KANA.search(text) or HAN.search(text)):
        return katsu().romaji(text, capitalize=False)
    if language == "zh" and HAN.search(text):
        return render(pinyin_tokens(text))
    return text


def render(tokens) -> str:
    out = ""
    for _, _, reading, spaced in tokens:
        if out and spaced and not out.endswith(" "):
            out += " "
        out += reading
        if spaced:
            out += " "
    return re.sub(r"\s+", " ", out).strip()


def tokens_for(text: str, language: str):
    if language == "ja":
        return japanese_tokens(text)
    if language == "zh":
        return pinyin_tokens(text)
    return None


def retime(syllables: list[dict], language: str) -> list[dict]:
    """Rebuild syllables as romanised words carrying the right timing."""
    if language == "ko":
        return [{**s, "text": romanise_korean(s.get("text", ""))} for s in syllables]

    full = "".join(s.get("text", "") for s in syllables)
    if not (KANA.search(full) or HAN.search(full)):
        return syllables

    # Per-character timing, spreading each syllable evenly over its characters.
    starts, ends = [], []
    for s in syllables:
        text = s.get("text", "")
        time, duration = float(s.get("time", 0)), float(s.get("duration", 0))
        n = max(1, len(text))
        for k in range(len(text)):
            starts.append(time + duration * k / n)
            ends.append(time + duration * (k + 1) / n)

    stripped = full.rstrip()
    tokens = tokens_for(stripped, language) or []
    out = []
    for start, end, reading, spaced in tokens:
        reading = reading if language != "zh" else reading
        if not reading.strip():
            if out and reading and not out[-1]["text"].endswith(" "):
                out[-1]["text"] += " "
            continue
        if language == "zh" and not spaced:
            spaced = bool(re.search(r"\s$", reading))
            reading = reading.strip()
        if not reading:
            continue
        first, last = start, max(start, end - 1)
        out.append({
            "time": starts[first],
            "duration": max(0.0, ends[last] - starts[first]),
            "text": reading + (" " if spaced or language == "zh" else ""),
        })
    return out or syllables


def detect_language(document: dict) -> str:
    texts = []
    for line in document.get("lines", []):
        texts.append(line.get("text", ""))
        if line.get("bg"):
            texts.append(line["bg"].get("text", ""))
    sample = "\n".join(texts)
    if KANA.search(sample):
        return "ja"
    if HANGUL.search(sample):
        return "ko"
    if HAN.search(sample):
        return "zh"
    return ""


def convert_part(part: dict, language: str) -> dict:
    syllables = part.get("syllabus") or []
    if syllables:
        rebuilt = retime(syllables, language)
        text = re.sub(r"\s+", " ", "".join(s["text"] for s in rebuilt)).strip()
        return {**part, "syllabus": rebuilt, "text": text}
    return {**part, "text": plain(part.get("text", ""), language)}


def main() -> int:
    raw = sys.stdin.read()
    document = json.loads(raw or "{}")
    language = detect_language(document)
    if not language:
        print(json.dumps({"language": "", "lines": document.get("lines", [])}, ensure_ascii=False))
        return 0

    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{VERSION}\n{raw}".encode()).hexdigest()[:32]
    cached = CACHE / f"{key}.json"
    if cached.is_file():
        sys.stdout.write(cached.read_text())
        return 0

    lines = []
    for line in document.get("lines", []):
        converted = convert_part(line, language)
        if line.get("bg"):
            converted["bg"] = convert_part(line["bg"], language)
        lines.append(converted)
    payload = json.dumps({"language": language, "lines": lines}, ensure_ascii=False)
    tmp = cached.with_suffix(".tmp")
    tmp.write_text(payload)
    tmp.replace(cached)
    sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
