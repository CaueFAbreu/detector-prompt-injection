import pandas as pd

from src import leitura
from src.amostragem import estrato, nota, selecionar
from src.auditoria import chave_comparacao

FONTE = "autor/fonte"


def _tabela(textos, rotulos=None, ids=None, fonte=FONTE):
    dados = pd.DataFrame(
        {
            "texto": textos,
            "rotulo_fonte": rotulos or [None] * len(textos),
            "id_original": ids or [f"id{i}" for i in range(len(textos))],
        }
    )
    return leitura._padronizar(dados, fonte, "data/a.parquet")


def _ids(amostra, nome=FONTE):
    return [linha["id_original"] for linha in amostra[nome]]


def test_selecionar_descarta_textos_invalidos():
    tabela = _tabela(
        ["", "  \n ", "a" * 4096, "b" * 4097, "oi"],
        ids=["vazio", "espacos", "limite", "acima", "oi"],
    )

    amostra = selecionar([tabela])

    assert sorted(_ids(amostra)) == ["limite", "oi"]


def test_selecionar_mantem_uma_linha_por_chave_com_o_menor_id():
    tabelas = [_tabela(["Oi"], ids=["b"]), _tabela(["oi", " OI "], ids=["a", "c"])]

    amostra = selecionar(tabelas)

    assert _ids(amostra) == ["a"]
    linha = amostra[FONTE][0]
    assert set(linha) == {"fonte", "id_original", "rotulo_fonte", "texto", "nota"}
    assert linha["texto"] == "oi"
    assert linha["nota"] == nota("oi")


def test_selecionar_separa_estratos_pelo_rotulo():
    rotulada = _tabela(["x", "y", "z"], rotulos=["1", "0", "1"], fonte="autor/rotulada")
    sem_rotulo = _tabela(["w"], fonte="autor/livre")

    amostra = selecionar([rotulada, sem_rotulo])

    assert {nome: len(linhas) for nome, linhas in amostra.items()} == {
        "autor/rotulada:1": 2,
        "autor/rotulada:0": 1,
        "autor/livre": 1,
    }
    assert estrato("autor/livre", pd.NA) == "autor/livre"
    assert estrato("autor/livre", None) == "autor/livre"


def test_selecionar_escolhe_as_menores_notas_sem_depender_da_ordem():
    textos = [f"mensagem {i}" for i in range(2500)]
    ids = [f"id{i:04d}" for i in range(2500)]
    tabelas = [_tabela(textos[:1200], ids=ids[:1200]), _tabela(textos[1200:], ids=ids[1200:])]
    invertidas = [
        _tabela(textos[1200:][::-1], ids=ids[1200:][::-1]),
        _tabela(textos[:1200][::-1], ids=ids[:1200][::-1]),
    ]
    por_nota = sorted(range(2500), key=lambda i: nota(chave_comparacao(textos[i])))
    esperado = [ids[i] for i in por_nota[:5]]

    assert _ids(selecionar(tabelas, tamanho=5)) == esperado
    assert _ids(selecionar(invertidas, tamanho=5)) == esperado


def test_segunda_fase_continua_a_fila_da_primeira():
    tabela = _tabela([f"texto {i}" for i in range(20)])

    primeira = _ids(selecionar([tabela], tamanho=2))
    ampliada = _ids(selecionar([tabela], tamanho=5))

    assert primeira == ampliada[:2]


def test_estrato_menor_que_o_tamanho_devolve_todas_as_linhas():
    tabela = _tabela(["a", "b", "c"])

    amostra = selecionar([tabela], tamanho=50)

    assert sorted(_ids(amostra)) == ["id0", "id1", "id2"]
    notas = [linha["nota"] for linha in amostra[FONTE]]
    assert notas == sorted(notas)
