import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from src.fontes import Fonte
from src.obtencao import DESTINO

COLUNAS = [
    "fonte",
    "arquivo",
    "id_original",
    "texto",
    "rotulo_fonte",
    "categoria_fonte",
    "familia_fonte",
    "grupo_fonte",
    "idioma_fonte",
    "posicao",
]
TAMANHO_LOTE = 10_000


def _padronizar(dados: pd.DataFrame, fonte: str, arquivo: str) -> pd.DataFrame:
    dados = dados.reset_index(drop=True)
    dados["fonte"] = fonte
    dados["arquivo"] = arquivo
    if "id_original" not in dados:
        dados["id_original"] = [f"{arquivo}:{i}" for i in range(len(dados))]
    for coluna in COLUNAS:
        if coluna not in dados:
            dados[coluna] = None
    texto = [c for c in COLUNAS if c != "posicao"]
    dados[texto] = dados[texto].astype("string")
    dados["posicao"] = dados["posicao"].astype("Int64")
    return dados[COLUNAS]


def _ler_parquets(
    pasta: Path, fonte: str, padrao: str, mapa: dict[str, str], idioma: str | None
) -> Iterator[pd.DataFrame]:
    for caminho in sorted(pasta.glob(padrao)):
        dados = pd.read_parquet(caminho, columns=list(mapa)).rename(columns=mapa)
        dados["idioma_fonte"] = dados.get("idioma_fonte", idioma)
        yield _padronizar(dados, fonte, caminho.relative_to(pasta).as_posix())


def _ler_ai_safety_brazil(pasta: Path, fonte: str) -> Iterator[pd.DataFrame]:
    mapa = {
        "id": "id_original",
        "content": "texto",
        "label": "rotulo_fonte",
        "kind": "categoria_fonte",
        "family": "familia_fonte",
        "group_id": "grupo_fonte",
        "language_detected": "idioma_fonte",
    }
    yield from _ler_parquets(pasta, fonte, "data/*.parquet", mapa, None)


def _ler_trustairlab(pasta: Path, fonte: str) -> Iterator[pd.DataFrame]:
    mapa = {"prompt": "texto", "jailbreak": "rotulo_fonte"}
    for tabela in _ler_parquets(pasta, fonte, "*/train-*.parquet", mapa, "en"):
        tabela["categoria_fonte"] = tabela["arquivo"].str.split("/").str[0]
        yield tabela


def _ler_llmail(pasta: Path, fonte: str) -> Iterator[pd.DataFrame]:
    arquivo = "data/labelled_unique_submissions_phase2.json"
    envios = json.loads((pasta / arquivo).read_text(encoding="utf-8"))
    dados = pd.DataFrame(
        {
            "texto": list(envios),
            "rotulo_fonte": [str(v["attack_attempt"]) for v in envios.values()],
            "categoria_fonte": [v["reason"] for v in envios.values()],
            "idioma_fonte": "en",
        }
    )
    yield _padronizar(dados, fonte, arquivo)

    arquivo = "data/emails_for_fp_tests.json"
    emails = json.loads((pasta / arquivo).read_text(encoding="utf-8"))
    dados = pd.DataFrame({"texto": emails, "rotulo_fonte": "benigno", "idioma_fonte": "en"})
    yield _padronizar(dados, fonte, arquivo)


def _posicao_na_conversa(id_mensagem: str, pai: dict[str, str]) -> int:
    profundidade = 0
    while (id_mensagem := pai.get(id_mensagem)) is not None:
        profundidade += 1
    # Usuário e assistente se alternam a partir da raiz, que é sempre do usuário.
    return profundidade // 2 + 1


def _ler_oasst2(pasta: Path, fonte: str) -> Iterator[pd.DataFrame]:
    colunas = ["message_id", "parent_id", "message_tree_id", "text", "role", "lang", "deleted"]
    for caminho in sorted((pasta / "data").glob("*.parquet")):
        dados = pd.read_parquet(caminho, columns=colunas)
        respostas = dados.dropna(subset=["parent_id"])
        pai = dict(zip(respostas["message_id"], respostas["parent_id"], strict=True))
        usuario = dados[dados["role"] == "prompter"]
        tabela = pd.DataFrame(
            {
                "id_original": usuario["message_id"],
                "texto": usuario["text"],
                "categoria_fonte": usuario["deleted"].map({True: "deleted", False: None}),
                "grupo_fonte": usuario["message_tree_id"],
                "idioma_fonte": usuario["lang"],
                "posicao": [_posicao_na_conversa(m, pai) for m in usuario["message_id"]],
            }
        )
        yield _padronizar(tabela, fonte, caminho.relative_to(pasta).as_posix())


def _ler_wildchat(pasta: Path, fonte: str) -> Iterator[pd.DataFrame]:
    for caminho in sorted((pasta / "data").glob("*.parquet")):
        arquivo = caminho.relative_to(pasta).as_posix()
        lotes = pq.ParquetFile(caminho).iter_batches(
            batch_size=TAMANHO_LOTE, columns=["conversation_hash", "conversation"]
        )
        linha = 0
        for lote in lotes:
            linhas = []
            for conversa_hash, conversa in zip(
                lote.column("conversation_hash").to_pylist(),
                lote.column("conversation").to_pylist(),
                strict=True,
            ):
                usuario = [m for m in conversa if m["role"] == "user"]
                for posicao, mensagem in enumerate(usuario, start=1):
                    # O hash é do conteúdo: conversas idênticas o repetem, então não serve de ID.
                    linhas.append(
                        {
                            "id_original": f"{arquivo}:{linha}:{posicao}",
                            "texto": mensagem["content"],
                            "grupo_fonte": conversa_hash,
                            "idioma_fonte": mensagem["language"],
                            "posicao": posicao,
                        }
                    )
                linha += 1
            yield _padronizar(pd.DataFrame(linhas), fonte, arquivo)


LEITORES = {
    "ai-safety-brazil/prompt-injection-br-synthetic": _ler_ai_safety_brazil,
    "ai-safety-brazil/jailbreak-br-synthetic": _ler_ai_safety_brazil,
    "Lakera/gandalf_ignore_instructions": lambda pasta, fonte: _ler_parquets(
        pasta, fonte, "data/*.parquet", {"text": "texto"}, "en"
    ),
    "TrustAIRLab/in-the-wild-jailbreak-prompts": _ler_trustairlab,
    "Lakera/mosscap_prompt_injection": lambda pasta, fonte: _ler_parquets(
        pasta, fonte, "data/*.parquet", {"prompt": "texto", "level": "categoria_fonte"}, "en"
    ),
    "microsoft/llmail-inject-challenge": _ler_llmail,
    # O card não declara idioma; há textos em inglês e em alemão.
    "deepset/prompt-injections": lambda pasta, fonte: _ler_parquets(
        pasta, fonte, "data/*.parquet", {"text": "texto", "label": "rotulo_fonte"}, None
    ),
    # train, validation e test são cópias exatas de NotInject_one, _two e _three.
    "leolee99/NotInject": lambda pasta, fonte: _ler_parquets(
        pasta,
        fonte,
        "data/NotInject_*.parquet",
        {"prompt": "texto", "category": "categoria_fonte"},
        "en",
    ),
    "OpenAssistant/oasst2": _ler_oasst2,
    "allenai/WildChat-1M": _ler_wildchat,
}


def ler_fonte(fonte: Fonte, destino: Path = DESTINO) -> Iterator[pd.DataFrame]:
    yield from LEITORES[fonte.repositorio](destino / fonte.pasta, fonte.repositorio)
