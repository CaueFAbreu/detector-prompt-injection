import hashlib
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from src.fontes import FONTES, Fonte
from src.leitura import ler_fonte
from src.obtencao import DESTINO

COLUNAS_CONTADAS = ["arquivo", "rotulo_fonte", "categoria_fonte", "familia_fonte", "idioma_fonte"]
LIMITE_CARACTERES = 4096
LIMITES_FAIXAS = [16, 32, 64, 128, 256, 512, 1024, 2048, LIMITE_CARACTERES, 8192, 16384]
AUSENTE = "(ausente)"
SAIDA = Path("reports/auditoria_fontes.json")


def chave_comparacao(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto)
    texto = texto.casefold()
    texto = " ".join(texto.split())
    return texto


def resumir(texto: str) -> bytes:
    return hashlib.sha1(texto.encode("utf-8")).digest()


def contar_faixas(comprimentos: np.ndarray) -> list[int]:
    # A faixa i conta comprimentos em (LIMITES_FAIXAS[i-1], LIMITES_FAIXAS[i]]; a última, o resto.
    indices = np.searchsorted(LIMITES_FAIXAS, comprimentos, side="left")
    return np.bincount(indices, minlength=len(LIMITES_FAIXAS) + 1).tolist()


def _em_comum(chaves_a: dict[bytes, int], chaves_b: dict[bytes, int]) -> dict:
    comuns = chaves_a.keys() & chaves_b.keys()
    comprimentos = [chaves_a[chave] for chave in comuns]
    mediana = int(np.percentile(comprimentos, 50, method="nearest")) if comuns else None
    return {"textos": len(comuns), "mediana_comprimento": mediana}


def sobreposicao(chaves_por_fonte: dict[str, dict[bytes, int]]) -> dict[str, dict[str, dict]]:
    return {
        fonte_a: {
            fonte_b: _em_comum(chaves_a, chaves_b) for fonte_b, chaves_b in chaves_por_fonte.items()
        }
        for fonte_a, chaves_a in chaves_por_fonte.items()
    }


def _ordenar(contagem: Counter) -> dict[str, int]:
    return dict(sorted(contagem.items(), key=lambda item: (-item[1], item[0])))


class AuditoriaFonte:
    def __init__(self) -> None:
        self.linhas = 0
        self.vazios = 0
        self.com_posicao = 0
        self.primeiras_mensagens = 0
        self.contagens = {coluna: Counter() for coluna in COLUNAS_CONTADAS}
        self.comprimentos: list[np.ndarray] = []
        self.textos: set[bytes] = set()
        self.chaves: dict[bytes, int] = {}
        self.ids: set[bytes] = set()
        self.rotulos_por_chave: defaultdict[bytes, set[str]] = defaultdict(set)

    def adicionar(self, tabela: pd.DataFrame) -> None:
        textos = tabela["texto"].tolist()
        chaves = [chave_comparacao(texto) for texto in textos]
        resumos_chave = [resumir(chave) for chave in chaves]

        self.linhas += len(tabela)
        self.vazios += sum(chave == "" for chave in chaves)
        self.com_posicao += int(tabela["posicao"].notna().sum())
        self.primeiras_mensagens += int((tabela["posicao"] == 1).sum())
        for coluna in COLUNAS_CONTADAS:
            self.contagens[coluna].update(tabela[coluna].fillna(AUSENTE).tolist())
        self.comprimentos.append(tabela["texto"].str.len().to_numpy(dtype=np.int64))
        self.textos.update(resumir(texto) for texto in textos)
        self.chaves.update(zip(resumos_chave, map(len, chaves), strict=True))
        self.ids.update(resumir(id_original) for id_original in tabela["id_original"].tolist())
        for resumo, rotulo in zip(resumos_chave, tabela["rotulo_fonte"].tolist(), strict=True):
            if not pd.isna(rotulo):
                self.rotulos_por_chave[resumo].add(rotulo)

    def resumo(self) -> dict:
        if self.linhas == 0:
            raise ValueError("fonte sem linhas para auditar")
        comprimentos = np.concatenate(self.comprimentos)
        p50, p95 = np.percentile(comprimentos, [50, 95], method="nearest")
        return {
            "linhas": self.linhas,
            "ids_unicos": len(self.ids) == self.linhas,
            "vazios": self.vazios,
            "primeiras_mensagens": self.primeiras_mensagens if self.com_posicao else None,
            "comprimento": {
                "p50": int(p50),
                "p95": int(p95),
                "maximo": int(comprimentos.max()),
                "acima_do_limite": int((comprimentos > LIMITE_CARACTERES).sum()),
                "faixas": contar_faixas(comprimentos),
            },
            "duplicatas_exatas": self.linhas - len(self.textos),
            "duplicatas_chave": self.linhas - len(self.chaves),
            "chaves_com_rotulos_divergentes": sum(
                len(rotulos) > 1 for rotulos in self.rotulos_por_chave.values()
            ),
            "contagens": {coluna: _ordenar(c) for coluna, c in self.contagens.items()},
        }


def auditar(fontes: tuple[Fonte, ...] = FONTES, destino: Path = DESTINO) -> dict:
    resultado = {
        "limite_caracteres": LIMITE_CARACTERES,
        "limites_faixas": LIMITES_FAIXAS,
        "fontes": {},
    }
    chaves_por_fonte = {}
    for fonte in fontes:
        print(f"Auditando {fonte.repositorio}")
        auditoria = AuditoriaFonte()
        for tabela in ler_fonte(fonte, destino):
            auditoria.adicionar(tabela)
        resultado["fontes"][fonte.repositorio] = auditoria.resumo()
        chaves_por_fonte[fonte.repositorio] = auditoria.chaves
    resultado["sobreposicao"] = sobreposicao(chaves_por_fonte)
    return resultado


def main() -> None:
    resultado = auditar()
    SAIDA.parent.mkdir(exist_ok=True)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    SAIDA.write_text(texto + "\n", encoding="utf-8", newline="\n")
    print(f"Auditoria gravada em {SAIDA}")


if __name__ == "__main__":
    main()
