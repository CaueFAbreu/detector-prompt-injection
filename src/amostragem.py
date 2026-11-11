import hashlib
import random
from collections.abc import Iterable

import pandas as pd

from src.auditoria import LIMITE_CARACTERES, chave_comparacao

SEMENTE = "42"
TAMANHO_ESTRATO = 50
TAMANHO_FASE1 = 20
LIMITE_ACUMULADO = 1000
COLUNAS_ANOTACAO = ["classe", "familia", "negativo_dificil", "idioma", "observacao"]


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


def montar_fase1(
    amostra: dict[str, list[dict]], tamanho: int = TAMANHO_FASE1
) -> tuple[pd.DataFrame, pd.DataFrame]:
    linhas = [
        {**linha, "estrato": nome, "posicao_na_fila": posicao}
        for nome in sorted(amostra)
        for posicao, linha in enumerate(amostra[nome][:tamanho], start=1)
    ]
    random.Random(int(SEMENTE)).shuffle(linhas)
    ids = [f"A{i:04d}" for i in range(1, len(linhas) + 1)]

    planilha = pd.DataFrame({"id_amostra": ids, "texto": [linha["texto"] for linha in linhas]})
    for coluna in COLUNAS_ANOTACAO:
        planilha[coluna] = ""

    colunas_chave = ["fonte", "id_original", "rotulo_fonte", "estrato", "posicao_na_fila"]
    chave = pd.DataFrame(linhas, columns=colunas_chave)
    chave.insert(0, "id_amostra", ids)
    return planilha, chave
