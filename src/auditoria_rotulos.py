from math import sqrt
from pathlib import Path

import pandas as pd

from src.amostragem import TAMANHO_FASE1, VALORES_ANOTACAO

Z_95 = 1.959963984540054
MINIMO_ACEITE = 19
MAXIMO_REJEICAO = 15
INCERTOS_FASE2 = 3
COLUNAS_LIDAS = ["id_amostra", *VALORES_ANOTACAO]


def wilson(sucessos: int, total: int) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("total precisa ser positivo")
    if not 0 <= sucessos <= total:
        raise ValueError("sucessos fora do intervalo [0, total]")

    p = sucessos / total
    z2 = Z_95**2
    denominador = 1 + z2 / total
    centro = (p + z2 / (2 * total)) / denominador
    meia_largura = Z_95 * sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / denominador
    # Em 0/n e n/n os limites são 0 e 1 exatos, mas a subtração em ponto flutuante deixa resíduos.
    inferior = 0.0 if sucessos == 0 else centro - meia_largura
    superior = 1.0 if sucessos == total else centro + meia_largura
    return inferior, superior


def decidir(concordantes: int, incertos: int) -> str:
    if concordantes < 0 or incertos < 0 or concordantes + incertos > TAMANHO_FASE1:
        raise ValueError(f"contagens inválidas para uma fase de {TAMANHO_FASE1} textos")

    if incertos >= INCERTOS_FASE2:
        return "fase2"
    if concordantes >= MINIMO_ACEITE:
        return "aceito"
    if concordantes <= MAXIMO_REJEICAO:
        return "rejeitado"
    return "fase2"


def problemas_da_linha(classe: str, familia: str, negativo_dificil: str, idioma: str) -> list[str]:
    problemas = []
    if classe not in VALORES_ANOTACAO["classe"]:
        problemas.append(f"classe inválida: {classe!r}")
    if idioma not in VALORES_ANOTACAO["idioma"]:
        problemas.append(f"idioma inválido: {idioma!r}")

    if classe == "ataque" and familia not in VALORES_ANOTACAO["familia"]:
        problemas.append(f"ataque sem família válida: {familia!r}")
    if classe != "ataque" and familia != "":
        problemas.append(f"família fora de ataque: {familia!r}")

    if classe == "sem_ataque" and negativo_dificil not in VALORES_ANOTACAO["negativo_dificil"]:
        problemas.append(f"sem_ataque sem negativo_dificil válido: {negativo_dificil!r}")
    if classe != "sem_ataque" and negativo_dificil != "":
        problemas.append(f"negativo_dificil fora de sem_ataque: {negativo_dificil!r}")
    return problemas


def _ids_repetidos(tabela: pd.DataFrame) -> list[str]:
    return sorted(set(tabela.loc[tabela["id_amostra"].duplicated(), "id_amostra"]))


def ler_anotacao(caminho_planilha: Path, caminho_chave: Path) -> pd.DataFrame:
    # A planilha voltou da anotação com a aba renomeada; a de anotação é sempre a primeira.
    planilha = pd.read_excel(caminho_planilha, sheet_name=0, usecols=COLUNAS_LIDAS, dtype=str)
    planilha = planilha.dropna(how="all").fillna("")
    planilha = planilha.apply(lambda coluna: coluna.str.strip())
    chave = pd.read_csv(caminho_chave, dtype={"id_amostra": str, "rotulo_fonte": str})

    for nome, tabela in (("planilha", planilha), ("chave", chave)):
        repetidos = _ids_repetidos(tabela)
        if repetidos:
            raise ValueError(f"ids repetidos na {nome}: {repetidos}")

    juncao = chave.merge(planilha, on="id_amostra", how="outer", indicator=True)
    sem_par = juncao.loc[juncao["_merge"] != "both", ["id_amostra", "_merge"]]
    if not sem_par.empty:
        raise ValueError(f"ids sem correspondência entre chave e planilha:\n{sem_par}")

    problemas = [
        f"{linha.id_amostra}: {problema}"
        for linha in juncao.itertuples(index=False)
        for problema in problemas_da_linha(
            linha.classe, linha.familia, linha.negativo_dificil, linha.idioma
        )
    ]
    if problemas:
        raise ValueError("anotação inválida:\n" + "\n".join(problemas))
    return juncao.drop(columns="_merge")
