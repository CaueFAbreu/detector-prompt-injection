import hashlib
import json
import re
from fnmatch import fnmatch
from types import SimpleNamespace

import pytest
from huggingface_hub.hf_api import RepoFile, RepoFolder

from src import obtencao
from src.fontes import FONTES, Fonte

REVISAO = "a" * 40
CONTEUDO_LFS = b"dados de teste"
SHA256_LFS = hashlib.sha256(CONTEUDO_LFS).hexdigest()
CONTEUDO_README = b"hello\n"
BLOB_README = "ce013625030ba8dba906f756967f9e9ca394464a"


def test_calcular_sha256_de_conteudo_conhecido(tmp_path):
    caminho = tmp_path / "abc.txt"
    caminho.write_bytes(b"abc")
    esperado = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert obtencao.calcular_sha256(caminho) == esperado


def test_calcular_blob_git_igual_ao_git_hash_object(tmp_path):
    caminho = tmp_path / "README.md"
    caminho.write_bytes(CONTEUDO_README)
    assert obtencao.calcular_blob_git(caminho) == BLOB_README


def test_fontes_tem_revisao_fixa_e_repositorio_unico():
    assert all(re.fullmatch(r"[0-9a-f]{40}", fonte.revisao) for fonte in FONTES)
    assert len({fonte.repositorio for fonte in FONTES}) == len(FONTES)


@pytest.mark.parametrize("caminho", ["scripts/gerar.py", "src/pacote/modulo.py", "setup.py"])
def test_padroes_nao_permitem_codigo(caminho):
    assert not any(fnmatch(caminho, padrao) for fonte in FONTES for padrao in fonte.padroes)


@pytest.fixture
def hub_falso(monkeypatch):
    hub = SimpleNamespace(
        arvore=[
            RepoFolder(path="data", oid="0"),
            RepoFile(
                path="data/train.parquet",
                size=len(CONTEUDO_LFS),
                oid="1",
                lfs={"size": len(CONTEUDO_LFS), "oid": SHA256_LFS, "pointerSize": 1},
            ),
            RepoFile(path="README.md", size=len(CONTEUDO_README), oid=BLOB_README),
            RepoFile(path="scripts/gerar.py", size=1, oid="2"),
        ],
        conteudo_lfs=CONTEUDO_LFS,
        chamadas=[],
    )

    class ApiFalsa:
        def list_repo_tree(self, *args, **kwargs):
            return hub.arvore

    def download_falso(repositorio, **kwargs):
        hub.chamadas.append((repositorio, kwargs))
        pasta = kwargs["local_dir"]
        (pasta / "data").mkdir(parents=True)
        (pasta / "data" / "train.parquet").write_bytes(hub.conteudo_lfs)
        (pasta / "README.md").write_bytes(CONTEUDO_README)

    monkeypatch.setattr(obtencao, "HfApi", ApiFalsa)
    monkeypatch.setattr(obtencao, "snapshot_download", download_falso)
    return hub


FONTE_FALSA = Fonte("autor/dataset", REVISAO, ("data/*.parquet", "README.md"))


def test_baixar_fonte_fixa_revisao_e_registra_hashes(hub_falso, tmp_path):
    entradas = obtencao.baixar_fonte(FONTE_FALSA, tmp_path)

    repositorio, argumentos = hub_falso.chamadas[0]
    assert repositorio == "autor/dataset"
    assert argumentos["revision"] == REVISAO
    assert argumentos["allow_patterns"] == ["data/*.parquet", "README.md"]
    assert argumentos["local_dir"] == tmp_path / "autor__dataset"
    assert [e["arquivo"] for e in entradas] == ["README.md", "data/train.parquet"]
    assert entradas[1]["sha256"] == SHA256_LFS
    assert entradas[1]["revisao"] == REVISAO


def test_baixar_fonte_falha_com_arquivo_lfs_corrompido(hub_falso, tmp_path):
    hub_falso.conteudo_lfs = b"dados de tesTe"

    with pytest.raises(ValueError, match="diferente do publicado"):
        obtencao.baixar_fonte(FONTE_FALSA, tmp_path)


def test_baixar_fonte_falha_com_arquivo_sem_lfs_corrompido(hub_falso, tmp_path):
    hub_falso.arvore[2] = RepoFile(path="README.md", size=len(CONTEUDO_README), oid="0" * 40)

    with pytest.raises(ValueError, match="diferente do publicado"):
        obtencao.baixar_fonte(FONTE_FALSA, tmp_path)


def test_baixar_fonte_falha_quando_nenhum_arquivo_casa(hub_falso, tmp_path):
    fonte = Fonte("autor/dataset", REVISAO, ("inexistente/*.csv",))

    with pytest.raises(ValueError, match="Nenhum arquivo"):
        obtencao.baixar_fonte(fonte, tmp_path)
    assert hub_falso.chamadas == []


def test_gravar_manifesto_preserva_entradas(tmp_path):
    entradas = [{"fonte": "autor/dataset", "arquivo": "README.md", "sha256": "f" * 64}]
    caminho = tmp_path / "manifesto.json"

    obtencao.gravar_manifesto(entradas, caminho)

    assert json.loads(caminho.read_text(encoding="utf-8")) == entradas
    assert b"\r\n" not in caminho.read_bytes()
