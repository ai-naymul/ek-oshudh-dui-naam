"""Bangla (and English) messages built ONLY from rule findings. The AI never writes warnings.

Every message ends by sending the family to a doctor or pharmacist. It never tells anyone to stop a medicine;
a test checks that no template contains such words.
"""
from __future__ import annotations

from .rules import Finding

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
ASK = "ডাক্তার বা ফার্মাসিস্টকে দেখান।"
ASK_EN = "Show this to your doctor or pharmacist."


def bn_num(x) -> str:
    return str(x).translate(BN_DIGITS)


def _and(items: list[str]) -> str:
    return " আর ".join(items) if len(items) <= 2 else "، ".join(items[:-1]) + " আর " + items[-1]


TITLES = {
    "DUP_INGREDIENT": ("একই ওষুধ দুইবার", "Same medicine twice"),
    "DUP_ASK_CURRENT": ("দুটোই কি এখন খাচ্ছেন?", "Are both taken now?"),
    "SAME_CLASS": ("একই ধরনের ওষুধ: আরও যাচাই দরকার", "Same family: needs checking"),
    "DOSE_OVER": ("দিনের মাত্রা সীমার বেশি", "Daily amount over the limit"),
    "RISKY_PAIR": ("একসাথে খেলে সমস্যা হতে পারে", "This combination needs checking"),
    "OTC_ONLY": ("প্রেসক্রিপশনে নেই", "Not on any prescription"),
    "CONFIRM_FIRST": ("নিশ্চিত করুন", "Please confirm"),
    "UNKNOWN": ("চেনা যায়নি", "Not found"),
}


def explain(f: Finding) -> dict:
    d = f.data
    title_bn, title_en = TITLES[f.rule]
    if f.rule in ("DUP_INGREDIENT", "DUP_ASK_CURRENT"):
        docs = d.get("doctors") or []
        who = f" ({bn_num(len(docs))} জন ডাক্তারের প্রেসক্রিপশন থেকে)" if len(docs) >= 2 else ""
        ings = _and([i.title() for i in d.get("ingredients") or [d["ingredient"]]])
        ings_en = " and ".join(i.title() for i in d.get("ingredients") or [d["ingredient"]])
        each = "দুটোতেই" if len(d["brands"]) == 2 else "সবগুলোতেই"
        each_en = "both" if len(d["brands"]) == 2 else "all"
        if f.rule == "DUP_INGREDIENT":
            bn = f"{_and(d['brands'])}{who}: {each} একই উপাদান {ings} আছে। {ASK}"
            en = f"{' and '.join(d['brands'])} {each_en} contain {ings_en}. {ASK_EN}"
        else:
            bn = f"{_and(d['brands'])}{who}: {each} একই উপাদান {ings} আছে। এগুলো কি এখন একসাথে খাচ্ছেন? প্রতিটি ওষুধে জানিয়ে দিন।"
            en = f"{' and '.join(d['brands'])} {each_en} contain {ings_en}. Are they being taken now? Mark each medicine."
    elif f.rule == "SAME_CLASS":
        bn = f"{_and(d['brands'])} দুটোই {d['group_bn']}। দুটোই দরকার কি না জেনে নিন। {ASK}"
        en = f"{' and '.join(d['brands'])} are both {d['group']}. Ask whether both are needed. {ASK_EN}"
    elif f.rule == "DOSE_OVER":
        joined = "মিলে" if len(d["brands"]) > 1 else "থেকে"
        bn = (f"{_and(d['brands'])} {joined} দিনে {bn_num(d['total_mg'])} মিলিগ্রাম {d['ingredient'].title()} হচ্ছে; "
              f"সীমা {bn_num(d['max_mg'])} মিলিগ্রাম। {ASK}")
        lead = f"Together {', '.join(d['brands'])} give" if len(d["brands"]) > 1 else f"{d['brands'][0]} gives"
        en = f"{lead} {d['total_mg']} mg of {d['ingredient'].title()} a day; the limit is {d['max_mg']} mg. {ASK_EN}"
    elif f.rule == "RISKY_PAIR":
        bn = f"{d['note_bn']}। {ASK}"
        en = f"{d['note_en'].capitalize()}. {ASK_EN}"
    elif f.rule == "OTC_ONLY":
        bn = f"{d['brand']} কোনো প্রেসক্রিপশনে নেই। ডাক্তার জানেন কি না নিশ্চিত হোন। {ASK}"
        en = f"{d['brand']} is not on any prescription. Make sure the doctor knows. {ASK_EN}"
    elif f.rule == "CONFIRM_FIRST":
        b, src = d["brand"], d.get("source")
        if src == "voice":
            bn = f"কথায় শোনা নামটি নিশ্চিত নয়: এটা কি {b}? তালিকা থেকে বেছে নিশ্চিত করুন।"
            en = f"The spoken name is not certain: is this {b}? Please pick it from the list to confirm."
        elif src == "text":
            bn = f"লেখা নামটি তালিকার সাথে পুরো মেলেনি: এটা কি {b}? বেছে নিশ্চিত করুন।"
            en = f"The typed name does not fully match the registry: is this {b}? Please confirm."
        elif d.get("handwritten", True):
            bn = f"হাতের লেখা পুরো পরিষ্কার নয়: এটা কি {b}? ছবির সাথে মিলিয়ে নিশ্চিত করুন।"
            en = f"The handwriting is unclear: is this {b}? Please confirm against the photo."
        else:
            bn = f"ছবির লেখা পুরো পরিষ্কার নয়: এটা কি {b}? ছবির সাথে মিলিয়ে নিশ্চিত করুন।"
            en = f"The text in the photo is unclear: is this {b}? Please confirm against the photo."
    else:
        bn = "এই ওষুধটি নিবন্ধিত তালিকায় পাওয়া যায়নি। স্ট্রিপ বা বাক্সের ছবি পাঠান।"
        en = "This medicine was not found in the registry. Please send a photo of the strip or box."
    return {"rule": f.rule, "severity": f.severity, "title_bn": title_bn, "title_en": title_en, "bn": bn, "en": en,
            "source": f.source, "meds": f.meds}


ALL_TEMPLATE_TEXT = " ".join([ASK] + [t[0] for t in TITLES.values()])
