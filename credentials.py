"""Lettura centralizzata del token Notion: env -> file -> errore esplicito.

Unico punto di verita' per tutti i moduli che parlano con l'API Notion
(adapter_notion.py, notion_extract.py). Il valore non viene mai stampato.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class TokenError(RuntimeError):
    """Sollevato quando nessuna sorgente fornisce il token."""


@dataclass(frozen=True, slots=True)
class ResolvedToken:
    """Token risolto: valore e origine della sorgente usata ('env' o 'file').

    L'origine rende tracciabile, a runtime, quale sorgente e' stata consultata.
    """

    value: str
    origin: str


def get_token(name: str, file_fallback: str | None = None) -> ResolvedToken:
    """Risolve il token: prima la variabile d'ambiente, poi il file; altrimenti errore.

    `name` e' il nome della variabile d'ambiente da consultare per prima;
    `file_fallback` e' un percorso da cui leggere il token se la variabile
    e' assente o vuota. Il file deve contenere il solo token (con o senza
    whitespace finale). Nessuna sorgente -> TokenError, mai ritorno silenzioso.
    L'oggetto restituito include l'origine ('env' | 'file') per la tracciabilita'.
    """
    value = (os.environ.get(name) or "").strip()
    if value:
        return ResolvedToken(value=value, origin="env")

    if file_fallback:
        path = Path(file_fallback).expanduser()
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise TokenError(f"Token Notion non leggibile da {path}: {exc}") from exc
        if value:
            return ResolvedToken(value=value, origin="file")
        raise TokenError(f"Token Notion vuoto: {path}")

    raise TokenError(f"Nessuna sorgente configurata: {name} non impostato e nessun file di fallback.")