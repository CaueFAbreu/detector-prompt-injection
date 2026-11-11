import hashlib
import json
from fnmatch import fnmatch
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.hf_api import RepoFile

from src.fontes import FONTES, Fonte

DESTINO = Path("data/raw")
TAMANHO_BLOCO = 1024 * 1024


def _resumir(caminho: Path, resumo) -> str:
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(TAMANHO_BLOCO), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


def calcular_sha256(caminho: Path) -> str:
    return _resumir(caminho, hashlib.sha256())


def calcular_blob_git(caminho: Path) -> str:
    # O Hugging Face só informa o SHA-256 de arquivos em LFS; os demais são conferidos
    # pelo identificador de blob do Git, que é o SHA-1 de "blob <tamanho>\0<conteúdo>".
    cabecalho = f"blob {caminho.stat().st_size}\0".encode()
    return _resumir(caminho, hashlib.sha1(cabecalho))


def listar_esperados(fonte: Fonte) -> list[RepoFile]:
    itens = HfApi().list_repo_tree(
        fonte.repositorio, repo_type="dataset", revision=fonte.revisao, recursive=True
    )
    return sorted(
        (
            item
            for item in itens
            if isinstance(item, RepoFile) and any(fnmatch(item.path, p) for p in fonte.padroes)
        ),
        key=lambda item: item.path,
    )


def conferir_arquivo(caminho: Path, esperado: RepoFile) -> str:
    sha256 = calcular_sha256(caminho)
    if esperado.lfs is not None:
        integro = sha256 == esperado.lfs.sha256
    else:
        integro = calcular_blob_git(caminho) == esperado.blob_id
    if caminho.stat().st_size != esperado.size or not integro:
        raise ValueError(f"Arquivo diferente do publicado na revisão: {caminho}")
    return sha256


def baixar_fonte(fonte: Fonte, destino: Path) -> list[dict]:
    esperados = listar_esperados(fonte)
    if not esperados:
        raise ValueError(f"Nenhum arquivo de {fonte.repositorio} casa com os padrões")

    pasta = destino / fonte.pasta
    snapshot_download(
        fonte.repositorio,
        repo_type="dataset",
        revision=fonte.revisao,
        allow_patterns=list(fonte.padroes),
        local_dir=pasta,
    )
    return [
        {
            "fonte": fonte.repositorio,
            "revisao": fonte.revisao,
            "arquivo": esperado.path,
            "tamanho": esperado.size,
            "sha256": conferir_arquivo(pasta / esperado.path, esperado),
        }
        for esperado in esperados
    ]


def gravar_manifesto(entradas: list[dict], caminho: Path) -> None:
    texto = json.dumps(entradas, ensure_ascii=False, indent=2)
    caminho.write_text(texto + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    entradas = []
    for fonte in FONTES:
        print(f"Baixando {fonte.repositorio}")
        entradas.extend(baixar_fonte(fonte, DESTINO))
    gravar_manifesto(entradas, DESTINO / "manifesto.json")
    print(f"{len(entradas)} arquivos conferidos; manifesto em {DESTINO / 'manifesto.json'}")


if __name__ == "__main__":
    main()
