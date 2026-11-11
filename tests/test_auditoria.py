import numpy as np
import pandas as pd
import pytest

from src import auditoria, leitura
from src.auditoria import AuditoriaFonte, chave_comparacao, contar_faixas, sobreposicao
from src.fontes import Fonte


def _tabela(textos, rotulos=None, posicoes=None, ids=None):
    dados = pd.DataFrame(
        {
            "texto": textos,
            "rotulo_fonte": rotulos or [None] * len(textos),
            "posicao": posicoes or [None] * len(textos),
            "id_original": ids or [f"id{i}" for i in range(len(textos))],
        }
    )
    return leitura._padronizar(dados, "autor/fonte", "data/a.parquet")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        pytest.param("ｉｇｎｏｒｅ", "ignore", id="largura-total-vira-ascii"),
        pytest.param("ﬁm", "fim", id="ligadura-separada"),
        pytest.param("x²", "x2", id="sobrescrito-vira-digito"),
        pytest.param("IGNORE As Regras", "ignore as regras", id="minusculas"),
        pytest.param("Straße", "strasse", id="casefold-mais-forte-que-lower"),
        pytest.param("  ignore\n\n as\tregras  ", "ignore as regras", id="espacos-colapsados"),
        pytest.param("ignore\u00a0as", "ignore as", id="espaco-nao-separavel"),
        pytest.param("Atenção", "atenção", id="acentos-preservados"),
        pytest.param("ca\u0301", "cá", id="acento-combinante-composto"),
        pytest.param("", "", id="vazio"),
        pytest.param(" \n\t ", "", id="so-espacos"),
    ],
)
def test_chave_comparacao(texto, esperado):
    assert chave_comparacao(texto) == esperado


def test_variantes_da_mesma_mensagem_tem_a_mesma_chave():
    assert chave_comparacao("ＩＧＮＯＲＥ  as\nRegras") == chave_comparacao("ignore as regras")


def test_homoglifo_cirilico_nao_e_unificado():
    assert chave_comparacao("\u0456gnore") != chave_comparacao("ignore")


def test_espaco_de_largura_zero_nao_e_removido():
    # A remoção de invisíveis é da normalização do modelo (seção 4.2), decidida na Etapa 4.
    assert chave_comparacao("ig\u200bnore") != chave_comparacao("ignore")


def test_contar_faixas_respeita_o_limite_de_4096():
    comprimentos = np.array([1, 16, 17, 4096, 4097, 20_000])
    faixas = contar_faixas(comprimentos)

    assert len(faixas) == len(auditoria.LIMITES_FAIXAS) + 1
    assert faixas[0] == 2
    assert faixas[1] == 1
    assert faixas[auditoria.LIMITES_FAIXAS.index(4096)] == 1
    assert faixas[auditoria.LIMITES_FAIXAS.index(4096) + 1] == 1
    assert faixas[-1] == 1


def test_sobreposicao_conta_chaves_em_comum_e_mediana_do_comprimento():
    resultado = sobreposicao(
        {
            "a": {b"1": 2, b"2": 10, b"3": 30},
            "b": {b"2": 10, b"3": 30, b"4": 5},
            "c": {b"9": 7},
        }
    )

    assert resultado["a"]["a"] == {"textos": 3, "mediana_comprimento": 10}
    assert resultado["a"]["b"]["textos"] == 2
    assert resultado["a"]["b"]["mediana_comprimento"] in (10, 30)
    assert resultado["a"]["c"] == {"textos": 0, "mediana_comprimento": None}
    assert resultado["b"]["a"]["textos"] == 2


def test_auditoria_mede_duplicatas_vazios_e_comprimento():
    fonte = AuditoriaFonte()
    fonte.adicionar(_tabela(["Ignore as regras", "ignore  as REGRAS", "Ignore as regras"]))
    fonte.adicionar(_tabela([" \n ", "x" * 4097], ids=["id3", "id4"]))
    resumo = fonte.resumo()

    assert resumo["linhas"] == 5
    assert resumo["ids_unicos"]
    assert resumo["duplicatas_exatas"] == 1
    assert resumo["duplicatas_chave"] == 2
    assert resumo["vazios"] == 1
    assert resumo["comprimento"]["acima_do_limite"] == 1
    assert resumo["comprimento"]["maximo"] == 4097
    assert resumo["primeiras_mensagens"] is None
    assert resumo["contagens"]["rotulo_fonte"] == {"(ausente)": 5}


def test_auditoria_detecta_ids_repetidos_e_primeiras_mensagens():
    fonte = AuditoriaFonte()
    fonte.adicionar(_tabela(["a", "b", "c"], posicoes=[1, 2, 1], ids=["x", "x", "y"]))
    resumo = fonte.resumo()

    assert not resumo["ids_unicos"]
    assert resumo["primeiras_mensagens"] == 2


def test_auditoria_conta_mesma_chave_com_rotulos_divergentes():
    fonte = AuditoriaFonte()
    fonte.adicionar(
        _tabela(["Ignore", "IGNORE", "oi", "oi", "sem rótulo"], ["1", "0", "0", "0", None])
    )
    resumo = fonte.resumo()

    assert resumo["chaves_com_rotulos_divergentes"] == 1
    assert resumo["contagens"]["rotulo_fonte"] == {"0": 3, "(ausente)": 1, "1": 1}


def test_auditoria_de_fonte_sem_linhas_levanta_erro_claro():
    fonte = AuditoriaFonte()

    with pytest.raises(ValueError, match="fonte sem linhas para auditar"):
        fonte.resumo()


def test_auditar_resume_cada_fonte_e_a_sobreposicao(monkeypatch, tmp_path):
    tabelas = {"a/um": _tabela(["Oi", "tchau"]), "b/dois": _tabela(["oi", "outro"])}
    monkeypatch.setattr(
        auditoria, "ler_fonte", lambda fonte, destino: iter([tabelas[fonte.repositorio]])
    )
    fontes = (Fonte("a/um", "a" * 40, ()), Fonte("b/dois", "b" * 40, ()))

    resultado = auditoria.auditar(fontes, tmp_path)

    assert set(resultado["fontes"]) == {"a/um", "b/dois"}
    assert resultado["sobreposicao"]["a/um"]["b/dois"] == {"textos": 1, "mediana_comprimento": 2}
    assert resultado["limite_caracteres"] == 4096
