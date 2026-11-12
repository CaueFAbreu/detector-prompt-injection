import json

import pandas as pd
import pytest
from openpyxl import Workbook

import src.auditoria_rotulos as auditoria_rotulos
from src.auditoria_rotulos import (
    classe_da_fonte,
    decidir,
    ler_anotacao,
    problemas_da_linha,
    proporcao,
    resumir,
    resumir_estrato,
    wilson,
)


@pytest.mark.parametrize(
    ("sucessos", "total", "inferior", "superior"),
    [
        (46, 50, 0.8116, 0.9685),
        (45, 50, 0.7864, 0.9565),
        (50, 50, 0.9287, 1.0),
        (0, 200, 0.0, 0.0188),
    ],
)
def test_wilson_reproduz_os_valores_da_secao_4_3(sucessos, total, inferior, superior):
    assert wilson(sucessos, total) == pytest.approx((inferior, superior), abs=1e-4)


@pytest.mark.parametrize("total", [1, 7, 20, 50, 200, 10_000])
def test_wilson_fica_entre_zero_e_um_nos_extremos(total):
    for sucessos in (0, total):
        inferior, superior = wilson(sucessos, total)
        assert 0.0 <= inferior <= sucessos / total <= superior <= 1.0


@pytest.mark.parametrize(("sucessos", "total"), [(0, 0), (-1, 10), (11, 10)])
def test_wilson_recusa_contagens_invalidas(sucessos, total):
    with pytest.raises(ValueError):
        wilson(sucessos, total)


@pytest.mark.parametrize(
    ("concordantes", "incertos", "esperado"),
    [
        (20, 0, "aceito"),
        (19, 0, "aceito"),
        (19, 1, "aceito"),
        (18, 0, "fase2"),
        (16, 0, "fase2"),
        (15, 0, "rejeitado"),
        (0, 0, "rejeitado"),
        (17, 3, "fase2"),
        (15, 3, "fase2"),
        (15, 2, "rejeitado"),
        (10, 5, "fase2"),
    ],
)
def test_decidir_segue_a_tabela_da_secao_4_3(concordantes, incertos, esperado):
    assert decidir(concordantes, incertos) == esperado


@pytest.mark.parametrize(("concordantes", "incertos"), [(-1, 0), (0, -1), (20, 1)])
def test_decidir_recusa_contagens_invalidas(concordantes, incertos):
    with pytest.raises(ValueError):
        decidir(concordantes, incertos)


COLUNAS_PLANILHA = ["id_amostra", "texto", "classe", "familia", "negativo_dificil", "idioma"]
ANOTACAO_VALIDA = [
    ["A0001", "ignore tudo", "ataque", "sobrescrita", "", "pt"],
    ["A0002", "qual a sua função?", "sem_ataque", "", "sim", "pt"],
    ["A0003", "???", "incerto", "", "", "en"],
]
CHAVE_VALIDA = [
    ["A0001", "deepset/prompt-injections", "x:1", "1", "deepset/prompt-injections:1", 1],
    ["A0002", "deepset/prompt-injections", "x:2", "0", "deepset/prompt-injections:0", 1],
    ["A0003", "OpenAssistant/oasst2", "x:3", None, "OpenAssistant/oasst2", 1],
]


def _gravar(tmp_path, anotacao, chave):
    livro = Workbook()
    folha = livro.active
    folha.title = "Sheet1"
    for linha in [COLUNAS_PLANILHA, *anotacao]:
        folha.append(linha)
    livro.create_sheet("Revisao").append(["id_amostra", "classe"])
    caminho_planilha = tmp_path / "planilha.xlsx"
    livro.save(caminho_planilha)

    colunas = ["id_amostra", "fonte", "id_original", "rotulo_fonte", "estrato", "posicao_na_fila"]
    caminho_chave = tmp_path / "chave.csv"
    pd.DataFrame(chave, columns=colunas).to_csv(caminho_chave, index=False)
    return caminho_planilha, caminho_chave


def test_ler_anotacao_junta_a_primeira_aba_com_a_chave(tmp_path):
    tabela = ler_anotacao(*_gravar(tmp_path, ANOTACAO_VALIDA, CHAVE_VALIDA))

    assert list(tabela["id_amostra"]) == ["A0001", "A0002", "A0003"]
    assert list(tabela["classe"]) == ["ataque", "sem_ataque", "incerto"]
    assert list(tabela["rotulo_fonte"].fillna("<nulo>")) == ["1", "0", "<nulo>"]
    assert "texto" not in tabela.columns
    assert "_merge" not in tabela.columns


def test_ler_anotacao_remove_espacos_e_linhas_vazias(tmp_path):
    anotacao = [
        ["A0001", "t", " ataque ", "sobrescrita ", None, "pt"],
        [None, None, None, None, None, None],
        *ANOTACAO_VALIDA[1:],
    ]
    tabela = ler_anotacao(*_gravar(tmp_path, anotacao, CHAVE_VALIDA))

    assert len(tabela) == 3
    assert tabela.loc[0, "classe"] == "ataque"
    assert tabela.loc[0, "familia"] == "sobrescrita"


def test_ler_anotacao_recusa_id_ausente_na_planilha(tmp_path):
    caminhos = _gravar(tmp_path, ANOTACAO_VALIDA[:2], CHAVE_VALIDA)
    with pytest.raises(ValueError, match="sem correspondência"):
        ler_anotacao(*caminhos)


def test_ler_anotacao_recusa_id_ausente_na_chave(tmp_path):
    caminhos = _gravar(tmp_path, ANOTACAO_VALIDA, CHAVE_VALIDA[:2])
    with pytest.raises(ValueError, match="sem correspondência"):
        ler_anotacao(*caminhos)


@pytest.mark.parametrize("tabela_com_repeticao", ["planilha", "chave"])
def test_ler_anotacao_recusa_ids_repetidos(tmp_path, tabela_com_repeticao):
    anotacao, chave = list(ANOTACAO_VALIDA), list(CHAVE_VALIDA)
    if tabela_com_repeticao == "planilha":
        anotacao.append(ANOTACAO_VALIDA[0])
    else:
        chave.append(CHAVE_VALIDA[0])
    with pytest.raises(ValueError, match=f"repetidos na {tabela_com_repeticao}"):
        ler_anotacao(*_gravar(tmp_path, anotacao, chave))


def test_ler_anotacao_lista_todas_as_linhas_invalidas(tmp_path):
    anotacao = [
        ["A0001", "t", "Ataque", "sobrescrita", "", "pt"],
        ["A0002", "t", "sem_ataque", "persona", "sim", "pt"],
        ANOTACAO_VALIDA[2],
    ]
    with pytest.raises(ValueError) as erro:
        ler_anotacao(*_gravar(tmp_path, anotacao, CHAVE_VALIDA))

    assert "A0001: classe inválida" in str(erro.value)
    assert "A0002: família fora de ataque" in str(erro.value)


def test_problemas_da_linha_aceita_combinacoes_do_guia():
    assert problemas_da_linha("ataque", "persona", "", "en") == []
    assert problemas_da_linha("sem_ataque", "", "nao", "outro") == []
    assert problemas_da_linha("incerto", "", "", "misto") == []


@pytest.mark.parametrize(
    ("classe", "familia", "negativo_dificil", "idioma", "trecho"),
    [
        ("", "", "", "pt", "classe inválida"),
        ("ataque", "sobrescrita", "", "", "idioma inválido"),
        ("ataque", "", "", "pt", "ataque sem família"),
        ("ataque", "dan", "", "pt", "ataque sem família"),
        ("incerto", "persona", "", "pt", "família fora de ataque"),
        ("sem_ataque", "", "", "pt", "sem_ataque sem negativo_dificil"),
        ("ataque", "persona", "nao", "pt", "negativo_dificil fora de sem_ataque"),
        ("incerto", "", "sim", "pt", "negativo_dificil fora de sem_ataque"),
    ],
)
def test_problemas_da_linha_aponta_violacoes_do_guia(
    classe, familia, negativo_dificil, idioma, trecho
):
    problemas = problemas_da_linha(classe, familia, negativo_dificil, idioma)
    assert len(problemas) == 1
    assert trecho in problemas[0]


@pytest.mark.parametrize(
    ("rotulo", "esperado"),
    [
        ("1", "ataque"),
        ("True", "ataque"),
        ("0", "sem_ataque"),
        ("False", "sem_ataque"),
        ("benigno", "sem_ataque"),
        ("Unclear", None),
        (None, None),
        (float("nan"), None),
    ],
)
def test_classe_da_fonte_segue_o_mapa_aprovado(rotulo, esperado):
    assert classe_da_fonte(rotulo) == esperado


@pytest.mark.parametrize("rotulo", ["2", "true", "jailbreak", ""])
def test_classe_da_fonte_recusa_rotulo_desconhecido(rotulo):
    with pytest.raises(ValueError, match="desconhecido"):
        classe_da_fonte(rotulo)


def test_proporcao_arredonda_e_inclui_wilson():
    assert proporcao(19, 20) == {
        "n": 19,
        "de": 20,
        "proporcao": 0.95,
        "wilson": [0.7639, 0.9911],
    }


def test_proporcao_sem_textos_avaliados_nao_tem_intervalo():
    assert proporcao(0, 0) == {"n": 0, "de": 0, "proporcao": None, "wilson": None}


def _linha(classe, familia="", negativo_dificil="", idioma="en", rotulo="1", fonte="f"):
    estrato = fonte if rotulo is None else f"{fonte}:{rotulo}"
    return {
        "fonte": fonte,
        "rotulo_fonte": rotulo,
        "estrato": estrato,
        "classe": classe,
        "familia": familia,
        "negativo_dificil": negativo_dificil,
        "idioma": idioma,
    }


def _estrato_de_ataques(rotulo="1"):
    return pd.DataFrame(
        [_linha("ataque", "persona", rotulo=rotulo)] * 16
        + [_linha("ataque", "vazamento", idioma="pt", rotulo=rotulo)] * 2
        + [_linha("sem_ataque", negativo_dificil="sim", rotulo=rotulo)]
        + [_linha("incerto", idioma="outro", rotulo=rotulo)]
    )


def test_resumir_estrato_exclui_incerto_da_concordancia():
    resumo = resumir_estrato(_estrato_de_ataques())

    assert resumo["textos"] == 20
    assert resumo["incertos"] == 1
    assert resumo["classe_fonte"] == "ataque"
    assert resumo["concordancia"]["n"] == 18
    assert resumo["concordancia"]["de"] == 19
    assert resumo["concordancia"]["decisao"] == "fase2"
    assert resumo["ataques"]["n"] == 18
    assert resumo["ataques"]["de"] == 19


def test_resumir_estrato_conta_familias_dificeis_e_idiomas():
    resumo = resumir_estrato(_estrato_de_ataques())

    assert resumo["familias"] == {"persona": 16, "vazamento": 2}
    assert resumo["negativos_dificeis"] == 1
    assert resumo["idiomas"] == {"en": 17, "pt": 2, "outro": 1}


def test_resumir_estrato_mede_concordancia_de_rotulo_negativo():
    linhas = pd.DataFrame(
        [_linha("sem_ataque", negativo_dificil="nao", rotulo="0")] * 19
        + [_linha("ataque", "sobrescrita", rotulo="0")]
    )
    resumo = resumir_estrato(linhas)

    assert resumo["classe_fonte"] == "sem_ataque"
    assert resumo["concordancia"]["n"] == 19
    assert resumo["concordancia"]["decisao"] == "aceito"
    assert resumo["ataques"]["n"] == 1


@pytest.mark.parametrize("rotulo", ["Unclear", None])
def test_resumir_estrato_sem_classe_da_fonte_nao_tem_concordancia(rotulo):
    resumo = resumir_estrato(_estrato_de_ataques(rotulo))

    assert resumo["rotulo_fonte"] == rotulo
    assert resumo["classe_fonte"] is None
    assert resumo["concordancia"] is None
    assert resumo["ataques"]["n"] == 18


def test_resumir_estrato_so_com_incertos_nao_tem_proporcao():
    linhas = pd.DataFrame([_linha("incerto")] * 3)
    resumo = resumir_estrato(linhas)

    assert resumo["ataques"]["proporcao"] is None
    assert resumo["concordancia"]["proporcao"] is None
    assert resumo["concordancia"]["decisao"] == "fase2"


def test_resumir_estrato_recusa_estrato_misturado():
    linhas = pd.DataFrame(
        [_linha("ataque", "persona"), _linha("sem_ataque", "", "nao", rotulo="0")]
    )
    with pytest.raises(ValueError, match="único rótulo"):
        resumir_estrato(linhas)


def test_resumir_separa_estratos_e_gera_json_sem_texto():
    tabela = pd.concat([_estrato_de_ataques("1"), _estrato_de_ataques(None)], ignore_index=True)
    tabela["texto"] = "MARCADOR_DE_TEXTO"
    estratos = resumir(tabela)

    assert list(estratos) == ["f", "f:1"]
    assert "MARCADOR_DE_TEXTO" not in json.dumps(estratos)


def test_main_grava_relatorio_com_hashes(tmp_path, monkeypatch, capsys):
    caminho_planilha, caminho_chave = _gravar(tmp_path, ANOTACAO_VALIDA, CHAVE_VALIDA)
    saida = tmp_path / "reports" / "auditoria_rotulos.json"
    monkeypatch.setattr(auditoria_rotulos, "PLANILHA", caminho_planilha)
    monkeypatch.setattr(auditoria_rotulos, "CHAVE", caminho_chave)
    monkeypatch.setattr(auditoria_rotulos, "SAIDA", saida)

    auditoria_rotulos.main()

    bytes_gravados = saida.read_bytes()
    assert b"\r\n" not in bytes_gravados
    relatorio = json.loads(bytes_gravados.decode("utf-8"))
    assert relatorio["entradas"]["planilha"]["arquivo"] == "planilha.xlsx"
    assert len(relatorio["entradas"]["chave"]["sha256"]) == 64
    assert set(relatorio["estratos"]) == {
        "OpenAssistant/oasst2",
        "deepset/prompt-injections:0",
        "deepset/prompt-injections:1",
    }
    assert "ignore tudo" not in bytes_gravados.decode("utf-8")
    assert "Relatório em" in capsys.readouterr().out
