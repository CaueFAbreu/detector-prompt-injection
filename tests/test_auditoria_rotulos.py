import pytest

from src.auditoria_rotulos import decidir, wilson


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
