from app.subjects import OFFICIAL_SUBJECTS, resolve_subject


def test_exact_short_names_and_user_aliases():
    assert resolve_subject("matemática", OFFICIAL_SUBJECTS)[0] == "Matemática"
    assert (
        resolve_subject("português", OFFICIAL_SUBJECTS)[0] == "Língua Portuguesa e suas Literaturas"
    )
    assert resolve_subject("banco", OFFICIAL_SUBJECTS)[0] == "Matemática 9-Banco de Dados"
    assert resolve_subject("DAD", OFFICIAL_SUBJECTS)[0] == "Desenvolvimento Aplicação Dinâmica"
    assert resolve_subject("Carlinhos", OFFICIAL_SUBJECTS)[0] == "Desenvolvimento e Operações Ágeis"
    assert resolve_subject("história", OFFICIAL_SUBJECTS)[0] == "Sociologia"


def test_app_development_phrase_requires_clarification():
    chosen, options = resolve_subject("desenvolvimento do app", OFFICIAL_SUBJECTS)
    assert chosen is None
    assert set(options) == {
        "Desenvolvimento de Aplicativo Móvel",
        "Desenvolvimento Aplicação Dinâmica",
    }


def test_numbered_prefix_does_not_select_specialization():
    for query in ("Matemática 1", "Matemática 9", "Matemática 10", "Matemática 14"):
        assert resolve_subject(query, OFFICIAL_SUBJECTS) == ("Matemática", [])
    assert resolve_subject("Estatística 1", OFFICIAL_SUBJECTS) == ("Estatística", [])
    assert resolve_subject("Matemática 10", ["Matemática 10-Modelagem de Dados"]) == (None, [])


def test_meaningful_suffix_takes_precedence_over_numeric_prefix():
    assert resolve_subject("Matemática 10 Banco de Dados", OFFICIAL_SUBJECTS) == (
        "Matemática 9-Banco de Dados",
        [],
    )
    assert resolve_subject("Matemática 9 Inteligência Artificial", OFFICIAL_SUBJECTS) == (
        "Matemática 14 - Inteligência Artificial",
        [],
    )
    assert resolve_subject("Língua Portuguesa 2 liderança", OFFICIAL_SUBJECTS) == (None, [])
    assert resolve_subject("Língua Portuguesa 2 Chefia e Liderança", OFFICIAL_SUBJECTS) == (
        "Língua Portuguesa 2-Chefia e Liderança",
        [],
    )


def test_approximate_spelling_selects_the_only_clear_match():
    assert resolve_subject("Matemátca", OFFICIAL_SUBJECTS)[0] == "Matemática"


def test_portuguese_prefix_does_not_select_chefia():
    chosen, options = resolve_subject("Língua Portuguesa 2", OFFICIAL_SUBJECTS)
    assert chosen == "Língua Portuguesa e suas Literaturas"
    assert options == []
    chosen, options = resolve_subject("liderança", OFFICIAL_SUBJECTS)
    assert chosen is None
    assert options == []
