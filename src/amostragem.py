import hashlib
from collections.abc import Iterable

import pandas as pd

from src.auditoria import LIMITE_CARACTERES, chave_comparacao

SEMENTE = "42"
TAMANHO_ESTRATO = 50
LIMITE_ACUMULADO = 1000


def nota(chave: str) -> str:
    return hashlib.sha256(f"{SEMENTE}:{chave}".encode("utf-8")).hexdigest()


def estrato(fonte: str, rotulo) -> str:
    if pd.isna(rotulo):
        return fonte
    return f"{fonte}:{rotulo}"


def _menores(linhas_por_nota: dict[str, dict], tamanho: int) -> dict[str, dict]:
    return {n: linhas_por_nota[n] for n in sorted(linhas_por_nota)[:tamanho]}


def selecionar(
    tabelas: Iterable[pd.DataFrame], tamanho: int = TAMANHO_ESTRATO
) -> dict[str, list[dict]]:
    candidatos: dict[str, dict[str, dict]] = {}

    for tabela in tabelas:
        for fonte, id_original, rotulo, texto in zip(
            tabela["fonte"],
            tabela["id_original"],
            tabela["rotulo_fonte"],
            tabela["texto"],
            strict=True,
        ):
            chave = chave_comparacao(texto)
            if chave == "" or len(texto) > LIMITE_CARACTERES:
                continue

            nota_linha = nota(chave)
            nome = estrato(fonte, rotulo)
            linha = {
                "fonte": fonte,
                "id_original": id_original,
                "rotulo_fonte": None if pd.isna(rotulo) else rotulo,
                "texto": texto,
                "nota": nota_linha,
            }

            linhas_por_nota = candidatos.setdefault(nome, {})
            atual = linhas_por_nota.get(nota_linha)
            if atual is None or id_original < atual["id_original"]:
                linhas_por_nota[nota_linha] = linha

            if len(linhas_por_nota) > LIMITE_ACUMULADO:
                candidatos[nome] = _menores(linhas_por_nota, tamanho)

    return {nome: list(_menores(linhas, tamanho).values()) for nome, linhas in candidatos.items()}
