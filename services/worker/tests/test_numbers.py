import pytest

from worker.hooktitle import clean_hook
from worker.models import NarrationTimeline, SceneTiming, ScriptV1, WordTiming
from worker.montage import hook_text
from worker.numbers import NBSP, fr_cardinal, fr_ordinal, merge_timed, spoken, to_digits, tokens
from worker.recipes import normalize_script
from worker.steps.assemble import plan_from
from worker.storytelling import lint_script, normalize_story
from worker.subtitles import distribute_words
from worker.timeline import estimate_speech_s


@pytest.mark.parametrize(("n", "words"), [
    (21, "vingt et un"), (71, "soixante et onze"), (80, "quatre-vingts"), (81, "quatre-vingt-un"), (99, "quatre-vingt-dix-neuf"),
    (200, "deux cents"), (201, "deux cent un"), (852, "huit cent cinquante-deux"), (1350, "mille trois cent cinquante"),
    (1992, "mille neuf cent quatre-vingt-douze"), (80000, "quatre-vingt mille"), (2_500_000, "deux millions cinq cent mille"),
])
def test_fr_cardinal(n, words):
    assert fr_cardinal(n) == words


def test_fr_ordinal_and_feminine():
    assert [fr_ordinal(n) for n in (1, 2, 5, 9, 19, 21, 80, 100)] == [
        "premier", "deuxième", "cinquième", "neuvième", "dix-neuvième", "vingt et unième", "quatre-vingtième", "centième"]
    assert fr_cardinal(21, feminine=True) == "vingt et une" and fr_ordinal(1, feminine=True) == "première"


@pytest.mark.parametrize(("text", "said"), [
    ("852 morts en pleine mer", "huit cent cinquante-deux morts en pleine mer"),
    ("En 1992, 1 350 tonnes.", "En mille neuf cent quatre-vingt-douze, mille trois cent cinquante tonnes."),
    (f"10{NBSP}000 soldats", "dix mille soldats"),
    ("3 millions", "trois millions"),
    ("2,5 milliards", "deux virgule cinq milliards"),
    ("40 % des maisons", "quarante pour cent des maisons"),
    ("au 19e siècle, le 1er janvier", "au dix-neuvième siècle, le premier janvier"),
    ("21 personnes", "vingt et une personnes"),
    ("14 h 30", "quatorze heures trente"),
    ("1914-1918", "mille neuf cent quatorze à mille neuf cent dix-huit"),
    ("170 km, 14,5 M€", "cent soixante-dix kilomètres, quatorze virgule cinq millions d'euros"),
    ("L'A380 et la 3D", "L'A380 et la 3D"),  # un nombre collé à des lettres n'est pas lu
    ("Pas un seul chiffre.", "Pas un seul chiffre."),
])
def test_spoken_fr(text, said):
    assert spoken(text) == said


def test_spoken_en():
    assert spoken("In 1994, 852 died", "en") == "In nineteen ninety-four, eight hundred fifty-two died"
    assert spoken("the 21st of 1,350 ships, $5 million, 2.5 km", "en") == (
        "the twenty-first of one thousand three hundred fifty ships, five million dollars, two point five kilometers")


@pytest.mark.parametrize(("text", "shown"), [
    ("Huit cent cinquante-deux morts en pleine mer", "852 morts en pleine mer"),
    ("En dix-neuf cent quatre-vingt-douze, le canal ouvre.", "En 1992, le canal ouvre."),
    ("mille neuf cent quatre-vingt-quatorze", "1994"),
    ("des chalands de treize cent cinquante tonnes", f"des chalands de 1{NBSP}350 tonnes"),  # quantité : groupée
    ("de mille neuf cent quatorze à mille neuf cent dix-huit", "de 1914 à 1918"),  # années : collées
    ("trois millions de personnes", "3 millions de personnes"),
    ("deux virgule cinq milliards", "2,5 milliards"),
    ("soixante-dix ans, vingt et une victimes", "70 ans, 21 victimes"),
    ("trente pour cent", f"30{NBSP}%"),
    ("au dix-neuvième siècle", "au 19e siècle"),
    ("plus d'un million", "plus de 1 million"),
    ("deux cent mille", f"200{NBSP}000"),
    ("10000 morts", f"10{NBSP}000 morts"),
    ("neuf ans plus tard", "9 ans plus tard"),
    ("les années soixante", "les années 60"),
])
def test_to_digits(text, shown):
    assert to_digits(text) == shown


@pytest.mark.parametrize("text", [
    "Un homme seul", "l'un d'eux", "un navire neuf.", "tous les deux", "entre les deux, une ligne",
    "les Trois Mousquetaires", "Trois-Rivières", "partir de zéro", "des millions de personnes", "30 pour cent",
])
def test_to_digits_keeps_words_that_are_not_numbers(text):
    assert to_digits(text) == text


def test_to_digits_is_french_only_and_idempotent():
    assert to_digits("eight hundred people", "en") == "eight hundred people"
    once = to_digits("Huit cent cinquante-deux morts, en dix-neuf cent quatre-vingt-quatorze")
    assert to_digits(once) == once == "852 morts, en 1994"


def test_round_trip_digits_then_voice():
    assert spoken(to_digits("vingt et une personnes en dix-neuf cent quatre-vingt-douze")) == (
        "vingt et une personnes en mille neuf cent quatre-vingt-douze")


def _words(texts):
    return [WordTiming(text=t, start=i * 0.2, end=i * 0.2 + 0.18) for i, t in enumerate(texts)]


def test_merge_timed_joins_the_words_of_a_number():
    merged = merge_timed(_words(["Huit", "cent", "cinquante-deux", "morts", "en", "mille", "neuf", "cent", "quatre-vingt-quatorze."]))
    assert [(w.text, w.start, w.end) for w in merged] == [
        ("852", 0.0, pytest.approx(0.58)), ("morts", pytest.approx(0.6), pytest.approx(0.78)),
        ("en", pytest.approx(0.8), pytest.approx(0.98)), ("1994.", pytest.approx(1.0), pytest.approx(1.78))]
    assert merge_timed(_words(["one", "hundred"]), "en")[0].text == "one"


def test_tokens_and_timing_keep_a_number_whole_and_long_enough():
    assert tokens(f"En 1992, 1 350 tonnes et 30{NBSP}% de plus") == ["En", "1992,", "1 350", "tonnes", "et", f"30{NBSP}%", "de", "plus"]
    words = distribute_words("1992 marque", 0.0, 3.0)
    assert [w.text for w in words] == ["1992", "marque"]
    assert words[0].end - words[0].start > 3 * (words[1].end - words[1].start)  # « mille neuf cent quatre-vingt-douze »
    assert estimate_speech_s("En 1992") == pytest.approx(5 / 3, abs=1e-3)  # 5 mots dits, 3 mots par seconde


def _story(narrations, hook="Huit cent cinquante-deux morts en pleine mer"):
    roles = ["hook", "setup", "reveal", "escalation", "payoff", "loop"]
    return ScriptV1.model_validate({
        "scenes": [{"index": i, "role": roles[i], "duration_s": 5, "visual_prompt": "x", "narration": {"fr": t},
                    "on_screen_text": {"fr": "Deux mille ans"} if i == 1 else {}} for i, t in enumerate(narrations)],
        "metadata": {"fr": {"title": "Huit cent cinquante-deux morts", "description": "d"}},
        "hook_title": {"fr": hook}, "loop_note": "retour au ferry",
    })


def test_normalize_story_writes_numbers_in_digits():
    s = normalize_story(_story(["En mille neuf cent quatre-vingt-quatorze, le ferry coule."] + ["Une phrase de plus."] * 5))
    assert s.scenes[0].narration["fr"] == "En 1994, le ferry coule."
    assert s.scenes[1].on_screen_text["fr"] == f"2{NBSP}000 ans"
    assert s.hook_title["fr"] == "852 morts en pleine mer" and s.metadata["fr"].title == "852 morts"


def test_recipe_scripts_too():
    raw = ScriptV1.model_validate({
        "scenes": [{"index": i, "duration_s": 1.5, "visual_prompt": "x", "on_screen_text": {"fr": f"Jour {w}"}}
                   for i, w in enumerate(["un", "quatorze", "trente", "soixante"])],
        "metadata": {"fr": {"title": "t", "description": "d"}}, "hook_title": {"fr": "Cent vingt jours de chantier"},
    })
    s = normalize_script(raw, "timelapse")
    assert [sc.on_screen_text["fr"] for sc in s.scenes] == ["Jour 1", "Jour 14", "Jour 30", "Jour 60"]
    assert s.hook_title["fr"] == "120 jours de chantier"
    assert to_digits("un jour, un homme") == "un jour, un homme"  # « un » reste un article ailleurs


def test_lint_counts_the_words_the_voice_says():
    # 12 mots écrits, 22 dits : la voix déborderait d'une scène de 5 s
    long = "En 1992, 1 350 tonnes et 2 800 ouvriers traversent 171 km."
    issues = lint_script(_story([long] + ["Une phrase courte de dix mots pour remplir la scène ici."] * 5), ["fr"], 30)
    assert any("scène 1" in i and "mots pour 5 s" in i and "un nombre compte" in i for i in issues)


def test_montage_shows_digits_for_an_old_narration():
    script = _story(["x"] * 6)
    script.hook_title = {"fr": "Huit cent cinquante-deux morts en pleine mer"}  # script d'avant la règle, non normalisé
    timeline = NarrationTimeline(lang="fr", scenes=[
        SceneTiming(index=i, start=5.0 * i, duration=5.0, words=_words(["huit", "cent", "cinquante-deux", "morts."]) if i == 0 else [])
        for i in range(6)])
    _, words, titles = plan_from(script, "fr", timeline)
    assert [w.text for w in words[0]] == ["852", "morts."]
    assert titles == [(5.0, 10.0, f"2{NBSP}000 ans")]
    assert hook_text(script, "fr") == "852 morts en pleine mer"


def test_hook_title_keeps_the_non_breaking_space():
    assert clean_hook(f"10{NBSP}000 morts") == f"10{NBSP}000 morts"
