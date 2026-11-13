"""Clean Cohere Transcribe Arabic output: cut decoder loops, drop text invented on silence."""
import re

# Text the model invents on silence or noise (seen on the 20 Oct recordings).
JUNK = re.compile(r"(موقع الدراسة|موسيقى|ضوضاء|فراغ|تمتمة|%20|ترجمة|اشتركوا|شكرا للمشاهدة)")
TOKEN = re.compile(r"\S+")


def collapse(text):
    """Cut a decoder loop: a word or a 2-6 word phrase repeated more than 3 times in a row."""
    words = TOKEN.findall(text)
    key = [w.strip("،,.؟?!") for w in words]
    out, i, cut = [], 0, 0
    while i < len(words):
        for n in range(1, 7):
            unit = key[i:i + n]
            reps = 1
            while len(unit) == n and key[i + reps * n:i + (reps + 1) * n] == unit:
                reps += 1
            if reps > 3:
                out += words[i:i + 3 * n] + ["[…]"]
                i += reps * n
                cut += 1
                break
        else:
            out.append(words[i])
            i += 1
    return " ".join(out), cut


def clean(text):
    """Return (clean text, number of loops cut). Empty text means nothing worth keeping."""
    text = re.sub(r"<hesitation>|[#*@_]+|ـ{3,}", " ", text).replace("<laugh>", "(rire)")
    text = re.sub(r"<[^>]{1,20}>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text, cut = collapse(text)
    if JUNK.search(text) and len(text.split()) <= 6:
        return "", cut
    return text, cut
