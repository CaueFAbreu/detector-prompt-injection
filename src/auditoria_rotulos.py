from math import sqrt

from src.amostragem import TAMANHO_FASE1

Z_95 = 1.959963984540054
MINIMO_ACEITE = 19
MAXIMO_REJEICAO = 15
INCERTOS_FASE2 = 3


def wilson(sucessos: int, total: int) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("total precisa ser positivo")
    if not 0 <= sucessos <= total:
        raise ValueError("sucessos fora do intervalo [0, total]")

    p = sucessos / total
    z2 = Z_95**2
    denominador = 1 + z2 / total
    centro = (p + z2 / (2 * total)) / denominador
    meia_largura = Z_95 * sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / denominador
    # Em 0/n e n/n os limites são 0 e 1 exatos, mas a subtração em ponto flutuante deixa resíduos.
    inferior = 0.0 if sucessos == 0 else centro - meia_largura
    superior = 1.0 if sucessos == total else centro + meia_largura
    return inferior, superior


def decidir(concordantes: int, incertos: int) -> str:
    if concordantes < 0 or incertos < 0 or concordantes + incertos > TAMANHO_FASE1:
        raise ValueError(f"contagens inválidas para uma fase de {TAMANHO_FASE1} textos")

    if incertos >= INCERTOS_FASE2:
        return "fase2"
    if concordantes >= MINIMO_ACEITE:
        return "aceito"
    if concordantes <= MAXIMO_REJEICAO:
        return "rejeitado"
    return "fase2"
