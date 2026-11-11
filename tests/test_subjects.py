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


def test_ambiguous_numbered_subject_requires_clarification():
    chosen, options = resolve_subject("Matemática 1", OFFICIAL_SUBJECTS)
    assert chosen is None
    assert len(options) >= 2


def test_approximate_spelling_selects_the_only_clear_match():
    assert resolve_subject("Matemátca", OFFICIAL_SUBJECTS)[0] == "Matemática"


def test_portuguese_prefix_does_not_select_chefia():
    chosen, options = resolve_subject("Língua Portuguesa 2", OFFICIAL_SUBJECTS)
    assert chosen == "Língua Portuguesa e suas Literaturas"
    assert options == []
    chosen, options = resolve_subject("liderança", OFFICIAL_SUBJECTS)
    assert chosen is None
    assert options == []
