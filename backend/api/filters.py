"""MeiliSearch filter helpers shared across endpoints."""

from __future__ import annotations


def ms_escape(v: str) -> str:
    """Escape a string value for use inside a MeiliSearch double-quoted filter."""
    return v.replace("\\", "\\\\").replace('"', '\\"')


def build_filters(
    *,
    level: str | None = None,
    level_excl: str | None = None,
    ead_id: str | None = None,
    date_from: int | None = None,
    date_to: int | None = None,
    lang: str | None = None,
    pers_name_role: str | None = None,
    subject_norm: str | None = None,
    subject_norm_excl: str | None = None,
    geo_name_norm: str | None = None,
    geo_name_norm_excl: str | None = None,
    genre_form_norm: str | None = None,
    genre_form_norm_excl: str | None = None,
    gff_norm: str | None = None,
    gff_norm_excl: str | None = None,
    tdd_norm: str | None = None,
    tdd_norm_excl: str | None = None,
    technique_norm: str | None = None,
    technique_norm_excl: str | None = None,
    corp_name_norm: str | None = None,
    repository_id: str | None = None,
    repository: str | None = None,
    repository_excl: str | None = None,
    century: str | None = None,
    century_excl: str | None = None,
) -> list[str]:
    """Build a list of MeiliSearch filter expressions from common search parameters."""
    f: list[str] = []
    if level:                 f.append(f'level = "{ms_escape(level)}"')
    if level_excl:            f.append(f'NOT (level = "{ms_escape(level_excl)}")')
    if ead_id:                f.append(f'ead_id = "{ms_escape(ead_id)}"')
    if date_from is not None: f.append(f"date_end >= {date_from}")
    if date_to is not None:   f.append(f"date_start <= {date_to}")
    if lang:                  f.append(f'languages = "{ms_escape(lang)}"')
    if pers_name_role:        f.append(f'pers_name_roles = "{ms_escape(pers_name_role)}"')
    if subject_norm:          f.append(f'subjects_norm = "{ms_escape(subject_norm)}"')
    if subject_norm_excl:     f.append(f'NOT (subjects_norm = "{ms_escape(subject_norm_excl)}")')
    if geo_name_norm:         f.append(f'geo_names_norm = "{ms_escape(geo_name_norm)}"')
    if geo_name_norm_excl:    f.append(f'NOT (geo_names_norm = "{ms_escape(geo_name_norm_excl)}")')
    if genre_form_norm:       f.append(f'genre_forms_norm = "{ms_escape(genre_form_norm)}"')
    if genre_form_norm_excl:  f.append(f'NOT (genre_forms_norm = "{ms_escape(genre_form_norm_excl)}")')
    if gff_norm:              f.append(f'gff_norm = "{ms_escape(gff_norm)}"')
    if gff_norm_excl:         f.append(f'NOT (gff_norm = "{ms_escape(gff_norm_excl)}")')
    if tdd_norm:              f.append(f'tdd_norm = "{ms_escape(tdd_norm)}"')
    if tdd_norm_excl:         f.append(f'NOT (tdd_norm = "{ms_escape(tdd_norm_excl)}")')
    if technique_norm:        f.append(f'technique_norm = "{ms_escape(technique_norm)}"')
    if technique_norm_excl:   f.append(f'NOT (technique_norm = "{ms_escape(technique_norm_excl)}")')
    if corp_name_norm:        f.append(f'corp_names_norm = "{ms_escape(corp_name_norm)}"')
    if repository_id:         f.append(f'repository_id = "{ms_escape(repository_id)}"')
    elif repository:          f.append(f'repository = "{ms_escape(repository)}"')
    elif repository_excl:     f.append(f'NOT (repository = "{ms_escape(repository_excl)}")')
    if century:               f.append(f'century = "{ms_escape(century)}"')
    if century_excl:          f.append(f'NOT (century = "{ms_escape(century_excl)}")')
    return f
