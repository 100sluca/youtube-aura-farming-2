"""Citations d'auteurs tirées de Wikiquote (docs/70) : seules les citations sourcées, recopiées mot pour mot et signées."""

from __future__ import annotations

from worker import quotes
from worker.models import ScriptV1
from worker.prompts import code_prompts
from worker.recipes import prompt_key
from worker.sources import wikiquote as wq
from worker.steps.ideate import pick_quote
from worker.steps.seo import attribution, quote_work

PAGE = """<div class="mw-content-ltr mw-parser-output">
<div class="mw-heading mw-heading2"><h2 id="Citations">Citations</h2></div>
<div class="mw-heading mw-heading3"><h3><i>Bel-Ami</i>, 1885</h3></div>
<div class="citation">La vie est une côte. Tant qu’on monte, on regarde le sommet, et on se sent heureux&#160;; mais,
lorsqu’on arrive en haut, on aperçoit tout d’un coup la descente.</div>
<ul><li><div class="ref"><i>Bel-Ami</i>&#160;(1885), Guy de Maupassant, éd. Ollendorf, 1901, p.&#160;159</div></li></ul>
<div class="citation">Une phrase sans aucune référence derrière elle, donc jamais gardée par le code.</div>
<div class="mw-heading mw-heading2"><h2 id="Citations_rapportées">Citations rapportées</h2></div>
<div class="citation">On prête souvent cette belle phrase à l'auteur sans aucune preuve sérieuse.</div>
<ul><li><div class="ref">Un site de citations, 2010</div></li></ul>
<div class="mw-heading mw-heading2"><h2 id="Voir">Citations sur Guy de Maupassant</h2></div>
<div class="citation">Maupassant écrivait vite, très vite, trop vite pour son propre bien selon certains.</div>
<ul><li><div class="ref">Un critique, 1900</div></li></ul>
</div>"""


def test_only_sourced_quotes_by_the_author_are_kept():
    qs = wq.parse_page(PAGE, "Guy de Maupassant", "Guy de Maupassant", "https://fr.wikiquote.org/wiki/Guy_de_Maupassant")
    assert len(qs) == 1  # sans référence, « rapportée » ou « sur » l'auteur : écartées
    q = qs[0]
    assert q.text.startswith("La vie est une côte. Tant qu’on monte") and "\xa0" not in q.text and "  " not in q.text
    assert q.ref.startswith("Bel-Ami (1885), Guy de Maupassant") and q.author == "Guy de Maupassant"
    assert q.to_ref().kind == "wikiquote" and [f.claim for f in q.facts()] == [q.text, q.ref]


def test_a_usable_quote_reads_alone_on_an_image():
    def quote(text: str) -> wq.Quote:
        return wq.Quote(text, "Victor Hugo", "Victor Hugo", "Les Misérables", "u")

    assert wq.usable(quote("Deux choses sont infinies : l'Univers et la bêtise humaine, mais je ne suis pas sûr."))
    assert not wq.usable(quote("Alceste : Je veux qu'on soit sincère, et qu'en homme d'honneur."))  # réplique de théâtre
    assert not wq.usable(quote("Le président Beaufort : Il y a une chose plus grave que la trahison."))
    assert not wq.usable(quote("[…] les femmes n’espèrent point toujours autre chose que ce qui est !"))
    assert not wq.usable(quote("Trop court ici."))
    assert not wq.usable(quote(" ".join(["mot"] * 41)))


def test_an_idea_keeps_the_exact_quote_of_the_bank_or_is_dropped():
    bank = [
        wq.Quote("On devrait toujours être légèrement improbable.", "Oscar Wilde", "Oscar Wilde", "The Chameleon", "u1"),
        wq.Quote("Le public pardonne tout, sauf le génie.", "Oscar Wilde", "Oscar Wilde", "De l'importance…", "u2"),
    ]
    assert pick_quote(bank, "On devrait toujours être légèrement improbable", [1]) is bank[0]  # point oublié
    assert pick_quote(bank, "Le public pardonne tout, sauf le génie.", [7]) is bank[1]  # mauvais numéro : par le texte
    assert pick_quote(bank, "Le public pardonne tout sauf les gens méchants et le génie.", [2]) is None  # réécrite
    assert {q.key for q in bank} == wq.used_keys([{"facts": [{"claim": q.text}]} for q in bank])


def test_the_writer_never_changes_an_authors_quote():
    prod = {
        "sources": [{"title": "Guy de Maupassant", "url": "u", "kind": "wikiquote"}],
        "facts": [{"claim": "La vie est une côte.", "source": 0}, {"claim": "Bel-Ami (1885)", "source": 0}],
    }
    assert quotes.author_quote(prod) == ("La vie est une côte.", "Guy de Maupassant")
    assert quotes.author_quote({"sources": [{"title": "t", "url": "u"}], "facts": [{"claim": "x"}]}) is None
    assert "Auteur : Guy de Maupassant" in quotes.author_brief(prod) and "Bel-Ami (1885)" in quotes.author_brief(prod)
    script = ScriptV1.model_validate(
        {
            "scenes": [{"index": 0, "duration_s": 10, "visual_prompt": "v", "on_screen_text": {"fr": "La vie, une côte ?"}}]
            + [{"index": i, "duration_s": 2, "visual_prompt": "v"} for i in range(1, 4)],
            "metadata": {"fr": {"title": "t", "description": "d"}},
        }
    )
    kept = quotes.keep_author_quote(quotes.normalize(script), quotes.author_quote(prod) or ("", ""))
    assert kept.scenes[0].on_screen_text["fr"] == "La vie est une côte.\n— Guy de Maupassant"
    assert quotes.split_author(kept.scenes[0].on_screen_text["fr"]) == ("La vie est une côte.", "Guy de Maupassant")


def test_the_author_variant_has_its_own_agents_and_credits_wikiquote():
    assert prompt_key("quote", "auteur") == "quote_auteur" and prompt_key("quote", None) == "quote"
    prompts = code_prompts()
    assert "MOT POUR MOT" in prompts["guide_quote_auteur"] and "JAMAIS le visage" in prompts["script_quote_auteur"]
    sources = [{"title": "Oscar Wilde", "url": "https://fr.wikiquote.org/wiki/Oscar_Wilde", "kind": "wikiquote"}]
    work = quote_work(sources, [{"claim": "q"}, {"claim": "Le Portrait de Dorian Gray (1891)"}])
    credit = attribution(sources, "fr", work)
    assert credit.startswith("Citation : Oscar Wilde, Le Portrait de Dorian Gray (1891)") and "Wikiquote" in credit
    assert attribution([{"title": "Zraoua", "url": "w"}], "fr").startswith("Sources (Wikipédia")
