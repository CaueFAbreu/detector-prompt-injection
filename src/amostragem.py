import argparse
import hashlib
import random
from collections.abc import Iterable, Iterator
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from src.auditoria import LIMITE_CARACTERES, chave_comparacao
from src.fontes import FONTES
from src.leitura import ler_fonte

SEMENTE = "42"
TAMANHO_ESTRATO = 50
TAMANHO_FASE1 = 20
LIMITE_ACUMULADO = 1000
# O `False` entra só para a anotação continuar às cegas; a decisão dele foi tomada na fase 1.
ESTRATOS_FASE2 = (
    "TrustAIRLab/in-the-wild-jailbreak-prompts:False",
    "TrustAIRLab/in-the-wild-jailbreak-prompts:True",
)
PRIMEIRO_NUMERO_FASE2 = 341
COLUNAS_ANOTACAO = ["classe", "familia", "negativo_dificil", "idioma", "observacao"]
VALORES_ANOTACAO = {
    "classe": ["ataque", "sem_ataque", "incerto"],
    "familia": ["indireta", "ofuscacao", "persona", "vazamento", "sobrescrita"],
    "negativo_dificil": ["sim", "nao"],
    "idioma": ["pt", "en", "misto", "outro"],
}
LARGURAS = {"id_amostra": 11, "texto": 100, "observacao": 40}
LARGURA_PADRAO = 18
PASTA_ANOTACAO = Path("data/anotacao")


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


def montar_fase(
    amostra: dict[str, list[dict]],
    estratos: Iterable[str],
    posicoes: range,
    primeiro_numero: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    faltando = sorted(set(estratos) - set(amostra))
    if faltando:
        raise ValueError(f"estratos ausentes da amostra: {faltando}")

    linhas = [
        {**linha, "estrato": nome, "posicao_na_fila": posicao}
        for nome in sorted(estratos)
        for posicao, linha in enumerate(amostra[nome], start=1)
        if posicao in posicoes
    ]
    random.Random(int(SEMENTE)).shuffle(linhas)
    ids = [f"A{i:04d}" for i in range(primeiro_numero, primeiro_numero + len(linhas))]

    planilha = pd.DataFrame({"id_amostra": ids, "texto": [linha["texto"] for linha in linhas]})
    for coluna in COLUNAS_ANOTACAO:
        planilha[coluna] = ""

    colunas_chave = ["fonte", "id_original", "rotulo_fonte", "estrato", "posicao_na_fila"]
    chave = pd.DataFrame(linhas, columns=colunas_chave)
    chave.insert(0, "id_amostra", ids)
    return planilha, chave


def montar_fase1(
    amostra: dict[str, list[dict]], tamanho: int = TAMANHO_FASE1
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return montar_fase(amostra, amostra, range(1, tamanho + 1), primeiro_numero=1)


def montar_fase2(amostra: dict[str, list[dict]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    posicoes = range(TAMANHO_FASE1 + 1, TAMANHO_ESTRATO + 1)
    return montar_fase(amostra, ESTRATOS_FASE2, posicoes, PRIMEIRO_NUMERO_FASE2)


def tornar_seguro(texto: str) -> str:
    return ILLEGAL_CHARACTERS_RE.sub(lambda m: f"[U+{ord(m.group()):04X}]", texto)


def gravar_planilha(planilha: pd.DataFrame, caminho: Path) -> None:
    if caminho.exists():
        raise FileExistsError(f"{caminho} já existe; apague-o à mão para gerar de novo")

    livro = Workbook()
    folha = livro.active
    folha.title = "anotacao"
    for coluna, nome in enumerate(planilha.columns, start=1):
        folha.cell(row=1, column=coluna, value=nome).font = Font(bold=True)
        folha.column_dimensions[get_column_letter(coluna)].width = LARGURAS.get(
            nome, LARGURA_PADRAO
        )
    for linha, valores in enumerate(planilha.itertuples(index=False), start=2):
        for coluna, valor in enumerate(valores, start=1):
            if valor == "":
                continue
            celula = folha.cell(row=linha, column=coluna, value=tornar_seguro(str(valor)))
            # Texto que começa com "=" viraria fórmula, executada pelo Excel ao abrir o arquivo.
            celula.data_type = "s"
            celula.alignment = Alignment(wrap_text=True, vertical="top")

    ultima = len(planilha) + 1
    for nome, valores in VALORES_ANOTACAO.items():
        letra = get_column_letter(list(planilha.columns).index(nome) + 1)
        validacao = DataValidation(type="list", formula1=f'"{",".join(valores)}"')
        validacao.add(f"{letra}2:{letra}{ultima}")
        folha.add_data_validation(validacao)
    folha.freeze_panes = "A2"

    caminho.parent.mkdir(parents=True, exist_ok=True)
    livro.save(caminho)


def _ler(repositorios: set[str] | None = None) -> Iterator[pd.DataFrame]:
    for fonte in FONTES:
        if repositorios is None or fonte.repositorio in repositorios:
            print(f"Lendo {fonte.repositorio}")
            yield from ler_fonte(fonte)


def main(argumentos: list[str] | None = None) -> None:
    analisador = argparse.ArgumentParser(description="Gera a planilha de anotação às cegas.")
    analisador.add_argument("--fase", type=int, choices=[1, 2], default=1)
    fase = analisador.parse_args(argumentos).fase

    caminho_planilha = PASTA_ANOTACAO / f"planilha_fase{fase}.xlsx"
    caminho_chave = PASTA_ANOTACAO / f"chave_fase{fase}.csv"
    for caminho in (caminho_planilha, caminho_chave):
        if caminho.exists():
            raise FileExistsError(f"{caminho} já existe; apague-o à mão para gerar de novo")

    if fase == 1:
        planilha, chave = montar_fase1(selecionar(_ler()))
    else:
        repositorios = {nome.rsplit(":", 1)[0] for nome in ESTRATOS_FASE2}
        planilha, chave = montar_fase2(selecionar(_ler(repositorios)))
    gravar_planilha(planilha, caminho_planilha)
    chave.to_csv(caminho_chave, index=False, mode="x", encoding="utf-8", lineterminator="\n")
    print(chave.groupby("estrato").size().to_string())
    print(f"{len(planilha)} textos em {caminho_planilha}")


if __name__ == "__main__":
    main()
