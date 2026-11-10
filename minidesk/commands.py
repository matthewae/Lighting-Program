"""dot2-style command line.

Examples::

    fixture 1 thru 8 at 50
    f 1 + 3 + 5 at full
    group 2 at 75
    group 2 red 255
    at 0 / full / clear
    go 3   back 3   off 3   goto 3 2   flash ... (use the executor buttons)
    store 5            (add step to executor 5, creates it if needed)
    store 5 /merge     store 5 /overwrite
    blackout           highlight
"""
from __future__ import annotations

import re

from .engine import Engine
from .model import Playback

ALIASES = {
    "f": "fixture", "fix": "fixture", "fixture": "fixture",
    "g": "group", "gr": "group", "group": "group",
    "t": "thru", "thru": "thru", "through": "thru",
    "@": "at", "at": "at",
    "c": "clear", "clr": "clear", "clear": "clear",
    "go": "go", "back": "back", "b": "back", "off": "off", "stop": "off", "goto": "goto",
    "st": "store", "store": "store", "full": "full", "blackout": "blackout", "bo": "blackout",
    "highlight": "highlight", "hl": "highlight", "exec": "executor", "executor": "executor",
    "e": "executor", "page": "page", "+": "+", "-": "-",
}


def _tokens(text: str) -> list[str]:
    text = text.replace("@", " @ ").replace("+", " + ")
    return [t for t in re.split(r"\s+", text.strip()) if t]


class CommandLine:
    def __init__(self, engine: Engine):
        self.engine = engine

    def _pb(self, num: int) -> Playback | None:
        for pb in self.engine.show.playbacks:
            if pb.number == num:
                return pb
        return None

    def run(self, text: str) -> str:
        toks = _tokens(text)
        if not toks:
            return ""
        eng = self.engine
        words = [ALIASES.get(t.lower(), t) for t in toks]
        i = 0
        msgs = []
        selection: list[int] | None = None
        while i < len(words):
            w = words[i]
            if w in ("fixture", "group"):
                ids, i = self._id_list(words, i + 1)
                if w == "fixture":
                    sel = [f for f in ids if eng.show.fixture(f)]
                else:
                    sel = []
                    for g in ids:
                        if 1 <= g <= len(eng.show.groups):
                            sel += [f for f in eng.show.groups[g - 1].fixtures if f not in sel]
                selection = (selection or []) + [f for f in sel if f not in (selection or [])]
                eng.select(selection)
                msgs.append(f"{len(selection)} fixture(s) selected")
                continue
            if w == "at":
                if i + 1 >= len(words):
                    return "At needs a value"
                v = words[i + 1].lower()
                pct = 100.0 if v in ("full", "f") else float(v)
                eng.set_intensity(pct)
                msgs.append(f"intensity {pct:g}%")
                i += 2
                continue
            if w == "full":
                eng.set_intensity(100)
                msgs.append("intensity full")
                i += 1
                continue
            if w == "clear":
                eng.clear_programmer(True)
                msgs.append("programmer cleared")
                i += 1
                continue
            if w == "blackout":
                eng.blackout = not eng.blackout
                msgs.append("BLACKOUT " + ("ON" if eng.blackout else "off"))
                i += 1
                continue
            if w == "highlight":
                eng.highlight = not eng.highlight
                msgs.append("highlight " + ("on" if eng.highlight else "off"))
                i += 1
                continue
            if w in ("go", "back", "off", "goto"):
                j = i + 1
                if j < len(words) and words[j] == "executor":
                    j += 1
                if j >= len(words) or not words[j].isdigit():
                    return f"{w} needs an executor number"
                pb = self._pb(int(words[j]))
                if not pb:
                    return f"Executor {words[j]} does not exist"
                st = eng.state_for(pb)
                if w == "go":
                    eng.go(st)
                elif w == "back":
                    eng.back(st)
                elif w == "off":
                    eng.stop(st)
                    st.level = 0
                else:
                    if j + 1 >= len(words) or not words[j + 1].isdigit():
                        return "goto <executor> <step>"
                    eng.goto(st, int(words[j + 1]) - 1)
                    j += 1
                msgs.append(f"{w} executor {pb.number} ({pb.name})")
                i = j + 1
                continue
            if w == "store":
                j = i + 1
                if j < len(words) and words[j] == "executor":
                    j += 1
                if j >= len(words) or not words[j].isdigit():
                    return "store <executor number> [/merge|/overwrite]"
                num = int(words[j])
                mode = "add"
                for opt in words[j + 1:]:
                    if opt.lower() in ("/merge", "/m"):
                        mode = "merge"
                    elif opt.lower() in ("/overwrite", "/o"):
                        mode = "overwrite"
                if not eng.programmer:
                    return "Programmer is empty – nothing to store"
                pb = self._pb(num)
                if pb is None:
                    pb = Playback(name=f"Playback {num}", number=num, bank="User", mode="cuelist")
                    eng.show.playbacks.append(pb)
                    eng.rebuild_patch()
                st = eng.store(pb, mode)
                msgs.append(f"stored to executor {num} ({pb.name}) step {pb.steps.index(st) + 1}")
                return "; ".join(msgs)
            # attribute value  e.g.  "red 255" / "pan 128"
            if i + 1 < len(words) and re.fullmatch(r"\d+", words[i + 1]):
                eng.set_attr(w.lower(), int(words[i + 1]))
                msgs.append(f"{w.lower()} = {words[i + 1]}")
                i += 2
                continue
            return f"Unknown command near '{toks[i]}'"
        return "; ".join(msgs)

    @staticmethod
    def _id_list(words: list[str], i: int) -> tuple[list[int], int]:
        ids: list[int] = []
        mode = "+"
        while i < len(words):
            w = words[i]
            if w.isdigit():
                n = int(w)
                if mode == "thru" and ids:
                    a = ids[-1]
                    step = 1 if n >= a else -1
                    ids += list(range(a + step, n + step, step))
                elif mode == "-":
                    ids = [x for x in ids if x != n]
                else:
                    ids.append(n)
                mode = "+"
            elif w in ("thru", "+", "-"):
                mode = w
            else:
                break
            i += 1
        return ids, i
