import pandas as pd
import pytest
from openpyxl import load_workbook

from src import amostragem, leitura
from src.amostragem import (
    COLUNAS_ANOTACAO,
    ESTRATOS_FASE2,
    estrato,
    gravar_planilha,
    montar_fase,
    montar_fase1,
    montar_fase2,
    nota,
    selecionar,
    tornar_seguro,
)
from src.auditoria import chave_comparacao

FONTE = "autor/fonte"
TRUSTAIRLAB = "TrustAIRLab/in-the-wild-jailbreak-prompts"


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


def _amostra_sintetica(estratos=("a/x:0", "a/x:1", "b/y"), por_estrato=5):
    return {
        nome: [
            {
                "fonte": nome.split(":")[0],
                "id_original": f"{nome}-{i}",
                "rotulo_fonte": nome.split(":")[1] if ":" in nome else None,
                "texto": f"texto {nome} {i}",
                "nota": f"{i:064x}",
            }
            for i in range(por_estrato)
        ]
        for nome in estratos
    }


def test_planilha_da_fase1_nao_revela_fonte_nem_rotulo():
    planilha, _ = montar_fase1(_amostra_sintetica())

    assert list(planilha.columns) == ["id_amostra", "texto", *COLUNAS_ANOTACAO]
    assert (planilha[COLUNAS_ANOTACAO] == "").all().all()


def test_fase1_usa_as_primeiras_posicoes_de_cada_estrato():
    _, chave = montar_fase1(_amostra_sintetica(), tamanho=3)

    assert chave.groupby("estrato").size().to_dict() == {"a/x:0": 3, "a/x:1": 3, "b/y": 3}
    assert sorted(chave["posicao_na_fila"].unique()) == [1, 2, 3]
    primeiras = {f"{nome}-{i}" for nome in ("a/x:0", "a/x:1", "b/y") for i in range(3)}
    assert set(chave["id_original"]) == primeiras


def test_planilha_e_chave_se_correspondem_pelo_id_amostra():
    amostra = _amostra_sintetica()
    planilha, chave = montar_fase1(amostra)
    texto_por_id = {
        linha["id_original"]: linha["texto"] for linhas in amostra.values() for linha in linhas
    }

    assert list(planilha["id_amostra"]) == [f"A{i:04d}" for i in range(1, 16)]
    assert list(chave["id_amostra"]) == list(planilha["id_amostra"])
    assert list(planilha["texto"]) == [texto_por_id[i] for i in chave["id_original"]]


def test_fase1_embaralha_as_fontes_de_forma_deterministica():
    planilha, chave = montar_fase1(_amostra_sintetica())
    repetida, _ = montar_fase1(_amostra_sintetica())

    assert planilha.equals(repetida)
    assert list(chave["estrato"]) != sorted(chave["estrato"])


def _planilha(textos):
    planilha = pd.DataFrame({"id_amostra": [f"A{i:04d}" for i in range(1, len(textos) + 1)]})
    planilha["texto"] = textos
    for coluna in COLUNAS_ANOTACAO:
        planilha[coluna] = ""
    return planilha


def test_tornar_seguro_marca_caracteres_de_controle_e_preserva_quebras():
    texto = "a" + chr(7) + "b" + chr(0) + "\tc\nd"

    assert tornar_seguro(texto) == "a[U+0007]b[U+0000]\tc\nd"


def test_gravar_planilha_mantem_formulas_como_texto(tmp_path):
    caminho = tmp_path / "planilha.xlsx"
    textos = ["=1+1", '=HYPERLINK("http://exemplo.com")', "+SOMA(A1)", "texto comum"]

    gravar_planilha(_planilha(textos), caminho)

    folha = load_workbook(caminho)["anotacao"]
    celulas = [folha.cell(row=i, column=2) for i in range(2, 6)]
    assert [celula.value for celula in celulas] == textos
    assert {celula.data_type for celula in celulas} == {"s"}


def test_gravar_planilha_marca_caracteres_de_controle(tmp_path):
    caminho = tmp_path / "planilha.xlsx"

    gravar_planilha(_planilha(["a" + chr(7) + "b"]), caminho)

    assert load_workbook(caminho)["anotacao"].cell(row=2, column=2).value == "a[U+0007]b"


def test_gravar_planilha_tem_cabecalho_e_listas_suspensas(tmp_path):
    caminho = tmp_path / "planilha.xlsx"

    gravar_planilha(_planilha(["a", "b"]), caminho)

    folha = load_workbook(caminho)["anotacao"]
    cabecalho = [celula.value for celula in folha[1]]
    assert cabecalho == ["id_amostra", "texto", *COLUNAS_ANOTACAO]
    assert folha.cell(row=2, column=3).value is None
    listas = {str(v.sqref): v.formula1 for v in folha.data_validations.dataValidation}
    assert listas == {
        "C2:C3": '"ataque,sem_ataque,incerto"',
        "D2:D3": '"indireta,ofuscacao,persona,vazamento,sobrescrita"',
        "E2:E3": '"sim,nao"',
        "F2:F3": '"pt,en,misto,outro"',
    }


def test_gravar_planilha_nao_sobrescreve_arquivo_existente(tmp_path):
    caminho = tmp_path / "planilha.xlsx"
    caminho.write_bytes(b"anotacoes")

    with pytest.raises(FileExistsError):
        gravar_planilha(_planilha(["a"]), caminho)

    assert caminho.read_bytes() == b"anotacoes"


def test_fase2_usa_as_posicoes_21_a_50_dos_estratos_da_fase2():
    amostra = _amostra_sintetica((*ESTRATOS_FASE2, "b/y"), por_estrato=50)
    planilha, chave = montar_fase2(amostra)

    assert chave.groupby("estrato").size().to_dict() == {nome: 30 for nome in ESTRATOS_FASE2}
    assert sorted(chave["posicao_na_fila"].unique()) == list(range(21, 51))
    assert list(planilha["id_amostra"]) == [f"A{i:04d}" for i in range(341, 401)]
    assert list(planilha.columns) == ["id_amostra", "texto", *COLUNAS_ANOTACAO]


def test_fase2_mistura_os_rotulos_de_forma_deterministica():
    amostra = _amostra_sintetica(ESTRATOS_FASE2, por_estrato=50)
    planilha, chave = montar_fase2(amostra)
    repetida, _ = montar_fase2(amostra)

    assert planilha.equals(repetida)
    assert list(chave["estrato"]) != sorted(chave["estrato"])


def test_fase2_nao_repete_textos_da_fase1():
    amostra = _amostra_sintetica(ESTRATOS_FASE2, por_estrato=50)
    _, chave1 = montar_fase1(amostra)
    _, chave2 = montar_fase2(amostra)

    assert set(chave1["id_original"]).isdisjoint(chave2["id_original"])


def test_montar_fase_recusa_estrato_ausente():
    with pytest.raises(ValueError, match="ausentes"):
        montar_fase(_amostra_sintetica(), ["a/x:0", "z/w"], range(1, 3), primeiro_numero=1)


def _leitura_falsa(chamadas, tabela):
    def ler(repositorios=None):
        chamadas.append(repositorios)
        yield tabela

    return ler


def test_main_fase2_le_so_o_trustairlab_e_grava_os_arquivos(tmp_path, monkeypatch):
    chamadas = []
    textos = [f"prompt numero {i}" for i in range(100)]
    tabela = _tabela(textos, ["True"] * 50 + ["False"] * 50, fonte=TRUSTAIRLAB)
    monkeypatch.setattr(amostragem, "_ler", _leitura_falsa(chamadas, tabela))
    monkeypatch.setattr(amostragem, "PASTA_ANOTACAO", tmp_path)

    amostragem.main(["--fase", "2"])

    assert chamadas == [{TRUSTAIRLAB}]
    chave = pd.read_csv(tmp_path / "chave_fase2.csv")
    assert list(chave["id_amostra"]) == [f"A{i:04d}" for i in range(341, 401)]
    assert (tmp_path / "planilha_fase2.xlsx").exists()
    with pytest.raises(FileExistsError):
        amostragem.main(["--fase", "2"])


def test_main_sem_argumentos_gera_a_fase1_com_todas_as_fontes(tmp_path, monkeypatch):
    chamadas = []
    tabela = _tabela([f"mensagem {i}" for i in range(30)])
    monkeypatch.setattr(amostragem, "_ler", _leitura_falsa(chamadas, tabela))
    monkeypatch.setattr(amostragem, "PASTA_ANOTACAO", tmp_path)

    amostragem.main([])

    assert chamadas == [None]
    assert len(pd.read_csv(tmp_path / "chave_fase1.csv")) == 20
    assert not (tmp_path / "chave_fase2.csv").exists()


def test_fase1_mantem_a_permutacao_que_gerou_a_amostra_real():
    _, chave = montar_fase1(_amostra_sintetica())

    # Ordem registrada antes da generalização para montar_fase; mudá-la tornaria a fase 1
    # irreproduzível.
    assert list(chave["id_original"]) == [
        "a/x:1-3", "b/y-3", "a/x:1-2", "a/x:1-1", "b/y-4",
        "b/y-2", "a/x:1-0", "a/x:0-2", "a/x:1-4", "a/x:0-3",
        "a/x:0-4", "b/y-1", "a/x:0-0", "a/x:0-1", "b/y-0",
    ]  # fmt: skip


def test_ler_filtra_as_fontes_pelo_repositorio(monkeypatch, capsys):
    monkeypatch.setattr(amostragem, "ler_fonte", lambda fonte: iter([fonte.repositorio]))
    todas = [fonte.repositorio for fonte in amostragem.FONTES]

    assert list(amostragem._ler()) == todas
    assert list(amostragem._ler({TRUSTAIRLAB})) == [TRUSTAIRLAB]
    assert list(amostragem._ler(set())) == []
    capsys.readouterr()
