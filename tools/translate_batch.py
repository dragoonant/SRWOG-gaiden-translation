#!/usr/bin/env python3
"""AI translation pass through the Anthropic Message Batches API.

  submit FILE_GLOB... [--model claude-opus-5-5] [--effort medium] [--chunk 80] [--dry-run]
      Build one request per chunk of untranslated, non-kept entries in the
      matching worksheets (paths relative to the repo, e.g.
      worksheets/Logic/Dat/logic/talk/ls001.bin.json) and submit a batch.
      Strings already in the translation memory are filled without a request.
      State goes to translations/batches/<batch_id>.json.
  status BATCH_ID
  collect BATCH_ID      write results into the worksheets, update the
                        translation memory, print token usage and cost.
  retry                 clear every translation that fails fitcheck, keeping
                        the failure as feedback for the next submit.

Requires ANTHROPIC_API_KEY in the environment. Nothing is sent with
--dry-run; it prints the request count and a token estimate instead.

Per request the model sees: the project rules (cached system prompt built
from docs/style-guide.md), the chunk's lines with speaker names, the
glossary terms that occur in the chunk, the English the game will show for
each <keyword> tag, the previous lines for context, and the line-length
budget for the format. It returns JSON {"translations":[{"id","en"}]}.
"""
import glob
import json
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import fitcheck  # noqa: E402

WORK = r"C:\Users\antho\srw2og-work"
STATE_DIR = os.path.join(REPO, "translations", "batches")
TM_PATH = os.path.join(REPO, "translations", "tm.json")
# Batch prices, $ per million tokens (50% of standard). Cache writes are
# 1.25x input, cache reads 0.1x input.
PRICES = {
    "claude-opus-5-5": {"in": 2.0, "out": 10.0},
    "claude-sonnet-5-5": {"in": 1.0, "out": 5.0},
}
# Line-break marker per format. For FIXH/CSB/WTD it is a real newline
# character (JSON "\n"), which the build tools split on.
BREAK = {"LDBI": "@", "LOGO": "@", "ELF": "@", "BMD": "/", "FIXH": "\n", "CSB": "\n", "WTD": "\n"}
COST_PER_CHAR = 0.26 / 40944   # measured on chapter 1 (Opus 5.5, batch): $ per char of request text
SPENT_PATH = os.path.join(REPO, "translations", "spent.json")
AVG_PX = 17  # average advance of English text with the proportional font

SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "en": {"type": "string"}},
                "required": ["id", "en"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


def system_prompt():
    guide = open(os.path.join(REPO, "docs", "style-guide.md"), encoding="utf-8").read()
    return (
        "You translate the Japanese PS3 game 2nd Super Robot Wars OG into English for a fan "
        "translation. The project's style guide follows; apply it exactly.\n\n" + guide + "\n\n"
        "Working rules for every request:\n"
        "- Translate each item's jp into natural, idiomatic English that keeps the speaker's "
        "voice and the scene's tone. Do not add or drop information. No translator notes.\n"
        "- Use the glossary forms given in the request for every name and term, exactly.\n"
        "- Keyword tags like <ラ・ギアス> must be copied unchanged, Japanese inside, at the "
        "point in the sentence where that term belongs. The game replaces the tag with the "
        "English given for it in the request, so write the sentence around that English.\n"
        "- Keep other tags (<W=..>, </W>, etc.) and printf codes (%d, %s, %02d) exactly.\n"
        "- Never write ASCII < or > except inside copied tags.\n"
        "- Line breaks: use the break marker given in the request, at most the given number of "
        "lines, each line within the given length. Break at natural phrase boundaries.\n"
        "- Speaker-name items (short labels) get the short English name only.\n"
        "- Items with max_bytes must fit in that many UTF-8 bytes.\n"
        "- When the line break marker is a newline character, put real line breaks "
        "(\\n in the JSON string) between lines.\n"
        "- Return every id you were given, once, in the JSON format required."
    )


def load_spent():
    if os.path.exists(SPENT_PATH):
        return json.load(open(SPENT_PATH, encoding="utf-8"))
    return {"total": 0.0, "batches": {}}


def load_tm():
    return json.load(open(TM_PATH, encoding="utf-8")) if os.path.exists(TM_PATH) else {}


def save_tm(tm):
    os.makedirs(os.path.dirname(TM_PATH), exist_ok=True)
    json.dump(tm, open(TM_PATH, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=0)


def jp_of(e):
    return fitcheck.jp_of(e)


def speakers_for(rel, ws):
    """Speaker names for LDBI dialogue lines (index -> Japanese name)."""
    if ws.get("format") != "LDBI":
        return {}
    import script
    inner = rel.replace("\\", "/").split("/", 2)[2][:-5]          # strip worksheets/<Archive>/ and .json
    archive = rel.replace("\\", "/").split("/")[1]
    src = os.path.join(WORK, "ext", archive, *inner.split("/"))
    data = open(src, "rb").read()
    strings = ws["strings"]
    return {line: strings[spk]["jp"] for line, spk in script.ldbi_speakers(data).items()}


def budget_text(fmt, e, font):
    if fmt in fitcheck.DIALOGUE:
        lines, px = 3, {"LDBI": 832, "BMD": 704}[fmt]
    else:
        jl = fitcheck.split_lines(fmt, jp_of(e))
        lines, px = max(1, len(jl)), max(font.width(l) for l in jl)
    return lines, px


def build_requests(paths, model, effort, chunk, tm):
    font = fitcheck.Font(fitcheck.DEFAULT_FONT)
    glossary = fitcheck.load_glossary()
    kw_en = {jp: en for jp, en, _ in glossary}
    # Keyword tags display KeyWordData's names; once that table is translated,
    # its English is what the player sees in place of each <tag>.
    kwp = os.path.join(REPO, "worksheets", "Logic", "Dat", "FixedData", "KeyWordData.dat.json")
    if os.path.exists(kwp):
        for e in json.load(open(kwp, encoding="utf-8"))["strings"]:
            if e.get("en") and e.get("text"):
                kw_en[e["text"]] = e["en"]
    sysmsg = [{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}]
    requests, plan, prefilled = [], {}, 0
    queued = set()          # (format, jp) already in this submission
    for path in paths:
        rel = os.path.relpath(path, REPO)
        ws = json.load(open(path, encoding="utf-8"))
        fmt = fitcheck.fmt_of(ws)
        spk = speakers_for(rel, ws)
        todo = []
        for e in ws["strings"]:
            if e.get("keep") or e.get("en"):
                continue
            key = fmt + "\t" + jp_of(e)
            if key in tm:
                e["en"] = tm[key]
                prefilled += 1
                continue
            if key in queued:
                continue    # duplicate in this submission: filled from memory after collect
            queued.add(key)
            todo.append(e)
        if prefilled:
            json.dump(ws, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        for c in range(0, len(todo), chunk):
            part = todo[c:c + chunk]
            prev = [jp_of(x) for x in todo[max(0, c - 8):c]]
            items, terms, tags = [], {}, {}
            for e in part:
                jp = jp_of(e)
                lines, px = budget_text(fmt, e, font)
                item = {"id": e["id"], "jp": jp, "max_lines": lines,
                        "max_chars_per_line": max(4, px // AVG_PX)}
                if e["id"] in spk:
                    item["speaker"] = spk[e["id"]]
                if fmt == "ELF":
                    item["max_bytes"] = e["budget"]   # replaced in place in the executable
                if e.get("retry_note"):
                    item["previous_attempt"] = e["retry_note"]
                if e.get("kind") == "name":
                    item["type"] = "speaker-name or label"
                items.append(item)
                for gjp, gen, rx in glossary:
                    if gjp in jp and rx.search(jp):
                        terms[gjp] = gen
                for t in re.findall(r"<([^<>/=]+)>", jp):
                    tags["<%s>" % t] = kw_en.get(t, "(keyword; use the natural English term)")
                if item.get("speaker") and item["speaker"] in kw_en:
                    terms[item["speaker"]] = kw_en[item["speaker"]]
            payload = {
                "file": rel.replace("\\", "/"),
                "format": fmt,
                "line_break_marker": BREAK.get(fmt, "@"),
                "glossary": terms,
                "keyword_tags_display_as": tags,
                "previous_lines_for_context": prev,
                "items": items,
            }
            cid = "r%05d" % len(requests)
            requests.append({
                "custom_id": cid,
                "params": {
                    "model": model,
                    "max_tokens": 32000,
                    "system": sysmsg,
                    "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}},
                    "messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                },
            })
            plan[cid] = {"path": rel, "format": fmt, "ids": [e["id"] for e in part]}
    return requests, plan, prefilled


def client():
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic()


def cmd_submit(argv):
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d
    model, effort, chunk = opt("--model", "claude-opus-5-5"), opt("--effort", "medium"), int(opt("--chunk", "80"))
    pats = [a for a in argv[2:] if not a.startswith("--") and a not in (model, effort, str(chunk))]
    paths = sorted({p for pat in pats for p in glob.glob(os.path.join(REPO, pat), recursive=True)})
    tm = load_tm()
    requests, plan, prefilled = build_requests(paths, model, effort, chunk, tm)
    chars = sum(len(r["params"]["messages"][0]["content"]) for r in requests)
    estimate = chars * COST_PER_CHAR * (0.5 if model == "claude-sonnet-5-5" else 1.0)
    spent = load_spent()["total"]
    cap = float(opt("--cap", "75"))
    print("%d worksheet(s), %d request(s), %d entries prefilled from memory, ~%d chars of request text"
          % (len(paths), len(requests), prefilled, chars))
    print("estimated cost $%.2f; spent so far $%.2f; cap $%.2f" % (estimate, spent, cap))
    if "--dry-run" in argv or not requests:
        return 0
    if spent + estimate * 1.3 > cap:       # 30% safety margin on the estimate
        print("refusing: estimate with margin would exceed the cap")
        return 1
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    batch = client().messages.batches.create(requests=[
        Request(custom_id=r["custom_id"], params=MessageCreateParamsNonStreaming(**r["params"])) for r in requests])
    os.makedirs(STATE_DIR, exist_ok=True)
    json.dump({"batch_id": batch.id, "model": model, "effort": effort, "created": time.time(), "plan": plan},
              open(os.path.join(STATE_DIR, batch.id + ".json"), "w", encoding="utf-8"), indent=1)
    print("submitted batch", batch.id, batch.processing_status)
    return 0


def cmd_status(argv):
    b = client().messages.batches.retrieve(argv[2])
    print(b.processing_status, dict(b.request_counts))


def cmd_collect(argv):
    bid = argv[2]
    state = json.load(open(os.path.join(STATE_DIR, bid + ".json"), encoding="utf-8"))
    c = client()
    b = c.messages.batches.retrieve(bid)
    if b.processing_status != "ended":
        print("not finished:", b.processing_status, dict(b.request_counts))
        return 1
    tm = load_tm()
    usage = {"in": 0, "cw": 0, "cr": 0, "out": 0}
    sheets, filled, problems = {}, 0, []
    for res in c.messages.batches.results(bid):
        plan = state["plan"].get(res.custom_id)
        if res.result.type != "succeeded":
            problems.append("%s: %s" % (res.custom_id, res.result.type))
            continue
        msg = res.result.message
        u = msg.usage
        usage["in"] += u.input_tokens or 0
        usage["cw"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        usage["cr"] += getattr(u, "cache_read_input_tokens", 0) or 0
        usage["out"] += u.output_tokens or 0
        if msg.stop_reason != "end_turn":
            problems.append("%s: stop_reason %s" % (res.custom_id, msg.stop_reason))
            continue
        text = next((blk.text for blk in msg.content if blk.type == "text"), "")
        try:
            got = {t["id"]: t["en"] for t in json.loads(text)["translations"]}
        except (ValueError, KeyError) as ex:
            problems.append("%s: bad JSON (%s)" % (res.custom_id, ex))
            continue
        path = os.path.join(REPO, plan["path"])
        ws = sheets.setdefault(path, json.load(open(path, encoding="utf-8")))
        byid = {e["id"]: e for e in ws["strings"]}
        for i in plan["ids"]:
            en = got.get(i)
            if en is None:
                problems.append("%s: id %s missing" % (res.custom_id, i))
                continue
            e = byid[i]
            if not e.get("keep") and not e.get("en"):
                e["en"] = en
                e.pop("retry_note", None)
                tm[plan["format"] + "\t" + jp_of(e)] = en
                filled += 1
    for path, ws in sheets.items():
        json.dump(ws, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    save_tm(tm)
    pr = PRICES.get(state["model"], PRICES["claude-opus-5-5"])
    cost = (usage["in"] * pr["in"] + usage["cw"] * pr["in"] * 1.25 + usage["cr"] * pr["in"] * 0.1
            + usage["out"] * pr["out"]) / 1e6
    sp = load_spent()
    if bid not in sp["batches"]:
        sp["batches"][bid] = round(cost, 4)
        sp["total"] = round(sum(sp["batches"].values()), 4)
        json.dump(sp, open(SPENT_PATH, "w", encoding="utf-8"), indent=1)
    print("filled %d entries in %d worksheet(s)" % (filled, len(sheets)))
    print("total spent across batches: $%.2f" % sp["total"])
    print("tokens: input %d, cache write %d, cache read %d, output %d" % (usage["in"], usage["cw"], usage["cr"], usage["out"]))
    print("cost: $%.2f (batch prices for %s)" % (cost, state["model"]))
    for p in problems:
        print("problem:", p)
    return 0


def cmd_retry(argv):
    """Clear translations that fail fitcheck and note why, so the next submit
    re-translates them with that feedback. Kept entries are just cleared."""
    import subprocess
    out = os.path.join(REPO, "translations", "fit_failures.json")
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "fitcheck.py"), "--json", out, "--max", "0"],
                   capture_output=True, text=True, encoding="utf-8")
    fails = json.load(open(out, encoding="utf-8"))
    by_path = {}
    for f in fails:
        by_path.setdefault(f["path"], {})[f["id"]] = f
    tm = load_tm()
    n = 0
    for rel, items in by_path.items():
        path = os.path.join(REPO, rel)
        ws = json.load(open(path, encoding="utf-8"))
        fmt = fitcheck.fmt_of(ws)
        for e in ws["strings"]:
            f = items.get(e.get("id"))
            if not f:
                continue
            if not e.get("keep"):
                e["retry_note"] = "%s: %r failed (%s: %s)" % (fmt, e.get("en", ""), f["kind"], f["msg"])
                tm.pop(fmt + "\t" + jp_of(e), None)
            e["en"] = ""
            n += 1
        json.dump(ws, open(path, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
    save_tm(tm)
    print("cleared %d failing entries for re-translation" % n)
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "submit":
        return cmd_submit(argv)
    if cmd == "status":
        return cmd_status(argv)
    if cmd == "collect":
        return cmd_collect(argv)
    if cmd == "retry":
        return cmd_retry(argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv) or 0)
