"""Row localisation by the production reader, not by a second model.

The day oracle in `g4_build_dataset` runs `Qwen3-VL-2B-Instruct` ZERO-SHOT on a
narrow left crop and asks it, in Portuguese, for the first number on the line.
That works on lining figures and fails on the Annales, which set their dates in
old-style figures - 1 as a small-capital I, 10 as IO, 11 as II. 43 pages were
refused for it, all of them perfectly legible to a person.

The fine-tuned reader does not have that problem, because reading the day is
the first thing it was trained to do: the day is cell 0 of every row target it
ever saw. Measured on four of the refused pages, it reads 61-84% of their days
where the zero-shot oracle read too few to localise anything, and all four
clear their profile's bar.

Two findings shaped what is here, both measured rather than assumed:

* **Stop after ten tokens.** The day is the FIRST cell, so there is no reason
  to decode the other fifteen. Cutting `max_new_tokens` from 140 to 10 gave
  *identical* day sets on three pages (19/19, 24/24, 22/22) and was 3.7-4.8x
  faster - 456 s of localisation became 96 s.
* **Do not narrow the crop.** Showing the reader only the left 22% of the row,
  which is all the day occupies, made it *worse*: 35% where the full-width crop
  read 61%, and it disagreed with the full-width answer on 9 of 19 days. The
  model uses the rest of the row to know what it is looking at. This is the
  same lesson as the Radcliffe crop-scale test, where more pixels also hurt.

Reuses an already-loaded reader rather than loading its own copy. Two 2B models
resident at once is how this project last ran a laptop out of memory.
"""

from __future__ import annotations

import re

__all__ = ["first_printed_int", "AdapterDayOracle"]

# The chat template closes the assistant turn with <|im_end|> (248046); the
# model config declares no eos, so generate() would otherwise run past it.
STOP_IDS = (248046, 248044)


def first_printed_int(text: str) -> int | None:
    """The integer in the row's FIRST cell, or None.

    Deliberately not a search for any digit anywhere: `13 | 29.5 | ...` must
    give 13, and a row whose first cell is a marker or a rule must give
    nothing rather than reach into the barometer column for a number.
    """
    if not text:
        return None
    head = text.split("|")[0].strip().lstrip("·.")
    m = re.match(r"(\d+)", head)
    return int(m.group(1)) if m else None


class AdapterDayOracle:
    """`read_days(crops) -> [day | None]`, the contract `resolve_by_oracle` wants.

    Takes a model and processor that are already on the device. `max_new_tokens`
    is 10 because the day is cell 0; see the module docstring for the
    measurement behind that and behind the full-width crop.
    """

    def __init__(self, model, processor, device: str, *, instruction: str,
                 max_new_tokens: int = 10) -> None:
        self.model = model
        self.proc = processor
        self.device = device
        self.instruction = instruction
        self.max_new_tokens = max_new_tokens
        self.calls = 0

    def read_day(self, crop) -> int | None:
        return self.read_days([crop])[0]

    def read_days(self, crops: list) -> list[int | None]:
        import torch
        out: list[int | None] = []
        for crop in crops:
            msgs = [{"role": "user", "content": [
                {"type": "image", "image": crop},
                {"type": "text", "text": self.instruction}]}]
            inp = self.proc.apply_chat_template(
                msgs, add_generation_prompt=True, tokenize=True,
                return_dict=True, return_tensors="pt").to(self.device)
            n = inp["input_ids"].shape[1]
            with torch.no_grad():
                o = self.model.generate(**inp, max_new_tokens=self.max_new_tokens,
                                        do_sample=False, eos_token_id=list(STOP_IDS))
            text = self.proc.decode(o[0][n:], skip_special_tokens=True).split("<|im_end|>")[0]
            if self.device == "mps":
                torch.mps.empty_cache()
            self.calls += 1
            out.append(first_printed_int(text))
        return out
