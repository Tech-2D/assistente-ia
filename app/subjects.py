import re
import unicodedata
from difflib import SequenceMatcher

OFFICIAL_SUBJECTS = [
    "Desenvolvimento de Aplicativo Móvel",
    "Matemática 9-Banco de Dados",
    "Estatística",
    "Língua Inglesa",
    "Educação Física",
    "Engenharia e Qualidade de Software",
    "Língua Portuguesa e suas Literaturas",
    "Biologia 2-ESG-Environment, Social and Governance",
    "Matemática 10-Modelagem de Dados",
    "Desenvolvimento",
    "Desenvolvimento Aplicação Dinâmica",
    "Desenvolvimento e Operações Ágeis",
    "Sociologia",
    "Língua Portuguesa 2-Chefia e Liderança",
    "UX",
    "Matemática 14 - Inteligência Artificial",
    "Matemática",
    "Estatística 1-Business Intelligence",
]
ALIASES = {
    "desenvolvimento de aplicativo movel": ("mobile",),
    "matematica 9-banco de dados": ("banco",),
    "matematica 10-modelagem de dados": ("modelagem",),
    "matematica 14 - inteligencia artificial": ("ia",),
    "lingua inglesa": ("ingles",),
    "engenharia e qualidade de software": ("eqs", "engenharia"),
    "lingua portuguesa e suas literaturas": ("portugues", "literatura", "jj", "lingua portuguesa"),
    "biologia 2-esg-environment, social and governance": ("esg",),
    "desenvolvimento aplicacao dinamica": ("dad",),
    "desenvolvimento e operacoes ageis": ("devops", "carlinhos"),
    "desenvolvimento": ("ds", "spring"),
    "sociologia": ("historia",),
    "ux": ("design",),
    "estatistica 1-business intelligence": ("bi",),
    "lingua portuguesa 2-chefia e lideranca": ("chefia", "chefia e lideranca"),
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def resolve_subject(query: str | None, subjects: list[str]) -> tuple[str | None, list[str]]:
    if not query:
        return None, []
    q = norm(query)
    if q == "lideranca":
        return None, []
    if q in {"desenvolvimento do app", "desenvolvimento do aplicativo"}:
        return None, [
            s
            for s in subjects
            if norm(s)
            in {
                norm("Desenvolvimento de Aplicativo Móvel"),
                norm("Desenvolvimento Aplicação Dinâmica"),
            }
        ]
    exact = [s for s in subjects if norm(s) == q]
    if exact:
        return exact[0], []
    # A Portuguese-course number is only a catalogue prefix: never infer Chefia from it.
    if re.fullmatch(r"lingua portuguesa\s+\d+", q):
        q = "lingua portuguesa"
    numeric = re.fullmatch(r"(matematica|estatistica)\s+(\d+)", q)
    if numeric:
        prefix, number = numeric.groups()
        numbered = []
        for subject in subjects:
            match = re.match(rf"^{prefix}\s+(\d+)(?:\s|$)", norm(subject))
            if match and match.group(1).startswith(number):
                numbered.append(subject)
        if len(numbered) == 1:
            return numbered[0], []
        if len(numbered) > 1:
            return None, numbered
    hits = []
    for subject in subjects:
        n = norm(subject)
        aliases = [a for canonical, vals in ALIASES.items() if norm(canonical) == n for a in vals]
        if q in [norm(a) for a in aliases]:
            hits.append(subject)
    if len(hits) == 1:
        return hits[0], []
    if len(hits) > 1:
        return None, hits
    # Ignore numeric course prefixes but only when user's phrase identifies the suffix clearly.
    suffix_hits = [
        s for s in subjects if norm(s).split(" ", 1)[-1] == q or norm(s).endswith(" " + q)
    ]
    if len(suffix_hits) == 1:
        return suffix_hits[0], []
    variants_by_subject = {}
    for subject in subjects:
        n = norm(subject)
        aliases = [a for canonical, vals in ALIASES.items() if norm(canonical) == n for a in vals]
        variants = [n, *[norm(a) for a in aliases]]
        # Ignore the numbered course prefix when matching a meaningful suffix.
        suffix = n
        suffix = re.sub(r"^(?:matematica|lingua portuguesa|estatistica)\s+\d+\s*", "", suffix)
        suffix = suffix.strip()
        if suffix and suffix != n:
            variants.append(suffix)
        variants_by_subject[subject] = variants

    scores = []
    for subject, variants in variants_by_subject.items():
        best = max(SequenceMatcher(None, q, variant).ratio() for variant in variants)
        if any(q in variant or variant in q for variant in variants):
            best = max(best, 0.82)
        scores.append((best, subject))
    scores.sort(reverse=True)
    plausible = [subject for score, subject in scores if score >= 0.72]
    if not plausible:
        return None, []
    best_score = scores[0][0]
    best_subjects = [subject for score, subject in scores if score == best_score]
    second_score = next((score for score, _ in scores if score < best_score), 0.0)
    if len(best_subjects) == 1 and best_score >= 0.86 and best_score - second_score >= 0.08:
        return best_subjects[0], []
    return None, plausible
