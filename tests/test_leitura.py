import json

import pandas as pd
import pytest

from src import leitura
from src.fontes import FONTES, Fonte


def _ler(repositorio, destino):
    fonte = Fonte(repositorio, "a" * 40, ())
    tabelas = list(leitura.ler_fonte(fonte, destino))
    for tabela in tabelas:
        assert list(tabela.columns) == leitura.COLUNAS
    return pd.concat(tabelas, ignore_index=True)


def _parquet(destino, pasta, arquivo, dados):
    caminho = destino / pasta / arquivo
    caminho.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(dados).to_parquet(caminho)


def test_toda_fonte_tem_leitor():
    assert {fonte.repositorio for fonte in FONTES} == set(leitura.LEITORES)


def test_ai_safety_brazil_usa_content_e_nao_o_prompt_completo(tmp_path):
    _parquet(
        tmp_path,
        "ai-safety-brazil__prompt-injection-br-synthetic",
        "data/train.parquet",
        {
            "id": ["x1"],
            "content": ["ignore as regras"],
            "text": ["[INSTRUÇÕES CONFIÁVEIS] ... ignore as regras"],
            "user_request": ["Estou trabalhando com..."],
            "label": [1],
            "kind": ["embedded_attack"],
            "family": ["falsa_autoridade"],
            "group_id": ["g1"],
            "language_detected": ["pt"],
        },
    )
    linha = _ler("ai-safety-brazil/prompt-injection-br-synthetic", tmp_path).iloc[0]

    assert linha["texto"] == "ignore as regras"
    assert linha["rotulo_fonte"] == "1"
    assert linha["familia_fonte"] == "falsa_autoridade"
    assert linha["grupo_fonte"] == "g1"
    assert linha["idioma_fonte"] == "pt"
    assert linha["arquivo"] == "data/train.parquet"


def test_parquet_simples_recebe_idioma_do_card_e_id_por_linha(tmp_path):
    _parquet(
        tmp_path,
        "Lakera__gandalf_ignore_instructions",
        "data/train.parquet",
        {"text": ["a", "b"], "similarity": [0.9, 0.8]},
    )
    tabela = _ler("Lakera/gandalf_ignore_instructions", tmp_path)

    assert tabela["texto"].tolist() == ["a", "b"]
    assert tabela["id_original"].tolist() == ["data/train.parquet:0", "data/train.parquet:1"]
    assert tabela["idioma_fonte"].tolist() == ["en", "en"]
    assert tabela["rotulo_fonte"].isna().all()


def test_notinject_ignora_copias_de_train_validation_test(tmp_path):
    pasta = "leolee99__NotInject"
    dados = {"prompt": ["p"], "word_list": [["ignore"]], "category": ["Common Queries"]}
    _parquet(tmp_path, pasta, "data/NotInject_one-00000-of-00001.parquet", dados)
    _parquet(tmp_path, pasta, "data/train-00000-of-00001.parquet", dados)

    tabela = _ler("leolee99/NotInject", tmp_path)

    assert len(tabela) == 1
    assert tabela.loc[0, "categoria_fonte"] == "Common Queries"


def test_trustairlab_usa_config_como_categoria(tmp_path):
    pasta = "TrustAIRLab__in-the-wild-jailbreak-prompts"
    _parquet(
        tmp_path,
        pasta,
        "jailbreak_2023_05_07/train-0.parquet",
        {"prompt": ["DAN"], "jailbreak": [True]},
    )
    _parquet(
        tmp_path,
        pasta,
        "regular_2023_05_07/train-0.parquet",
        {"prompt": ["oi"], "jailbreak": [False]},
    )

    tabela = _ler("TrustAIRLab/in-the-wild-jailbreak-prompts", tmp_path)

    assert tabela["categoria_fonte"].tolist() == ["jailbreak_2023_05_07", "regular_2023_05_07"]
    assert tabela["rotulo_fonte"].tolist() == ["True", "False"]


def test_llmail_unifica_tipos_do_rotulo_e_le_emails_benignos(tmp_path):
    pasta = tmp_path / "microsoft__llmail-inject-challenge" / "data"
    pasta.mkdir(parents=True)
    envios = {
        "Subject of the email: a. Body: b": {"attack_attempt": "True", "reason": "judge"},
        "Subject of the email: c. Body: d": {"attack_attempt": True, "reason": "judge"},
    }
    (pasta / "labelled_unique_submissions_phase2.json").write_text(json.dumps(envios))
    (pasta / "emails_for_fp_tests.json").write_text(json.dumps(["Subject of the email: e"]))

    tabela = _ler("microsoft/llmail-inject-challenge", tmp_path)

    assert tabela["rotulo_fonte"].tolist() == ["True", "True", "benigno"]
    assert tabela["categoria_fonte"].tolist()[:2] == ["judge", "judge"]
    assert tabela["texto"].iloc[0] == "Subject of the email: a. Body: b"


def test_oasst2_le_so_o_usuario_com_posicao_na_conversa(tmp_path):
    _parquet(
        tmp_path,
        "OpenAssistant__oasst2",
        "data/train.parquet",
        {
            "message_id": ["u1", "a1", "u2", "a2", "u3"],
            "parent_id": [None, "u1", "a1", "u2", "a2"],
            "message_tree_id": ["u1"] * 5,
            "text": ["oi", "olá", "e aí?", "tudo", "tchau"],
            "role": ["prompter", "assistant", "prompter", "assistant", "prompter"],
            "lang": ["pt-BR"] * 5,
            "deleted": [False, False, True, False, False],
        },
    )
    tabela = _ler("OpenAssistant/oasst2", tmp_path)

    assert tabela["texto"].tolist() == ["oi", "e aí?", "tchau"]
    assert tabela["posicao"].tolist() == [1, 2, 3]
    assert tabela["categoria_fonte"].tolist()[1] == "deleted"
    assert tabela["categoria_fonte"].isna().tolist() == [True, False, True]
    assert (tabela["grupo_fonte"] == "u1").all()


def test_wildchat_le_mensagens_do_usuario_com_idioma_proprio(tmp_path):
    def mensagem(papel, conteudo, idioma):
        return {"role": papel, "content": conteudo, "language": idioma}

    _parquet(
        tmp_path,
        "allenai__WildChat-1M",
        "data/train-00000-of-00014.parquet",
        {
            "conversation_hash": ["h1", "h2"],
            "conversation": [
                [
                    mensagem("user", "oi", "Portuguese"),
                    mensagem("assistant", "olá", "Portuguese"),
                    mensagem("user", "translate this", "English"),
                ],
                [mensagem("user", "hello", "English")],
            ],
            "language": ["Portuguese", "English"],
        },
    )
    tabela = _ler("allenai/WildChat-1M", tmp_path)

    assert tabela["texto"].tolist() == ["oi", "translate this", "hello"]
    assert tabela["idioma_fonte"].tolist() == ["Portuguese", "English", "English"]
    assert tabela["posicao"].tolist() == [1, 2, 1]
    assert tabela["grupo_fonte"].tolist() == ["h1", "h1", "h2"]


def test_wildchat_distingue_conversas_identicas_com_o_mesmo_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(leitura, "TAMANHO_LOTE", 1)
    arquivo = "data/train-00000-of-00014.parquet"
    conversa = [{"role": "user", "content": "oi", "language": "Portuguese"}]
    _parquet(
        tmp_path,
        "allenai__WildChat-1M",
        arquivo,
        {"conversation_hash": ["h1", "h1"], "conversation": [conversa, conversa]},
    )
    tabela = _ler("allenai/WildChat-1M", tmp_path)

    assert tabela["id_original"].tolist() == [f"{arquivo}:0:1", f"{arquivo}:1:1"]
    assert tabela["grupo_fonte"].tolist() == ["h1", "h1"]


@pytest.mark.parametrize(
    ("repositorio", "pasta", "dados"),
    [
        ("deepset/prompt-injections", "deepset__prompt-injections", {"text": ["x"], "label": [0]}),
        (
            "Lakera/mosscap_prompt_injection",
            "Lakera__mosscap_prompt_injection",
            {"level": ["Level 1"], "prompt": ["x"], "answer": ["senha"], "raw_answer": ["senha"]},
        ),
    ],
)
def test_parquets_sem_coluna_de_resposta_ou_idioma(tmp_path, repositorio, pasta, dados):
    _parquet(tmp_path, pasta, "data/train.parquet", dados)
    linha = _ler(repositorio, tmp_path).iloc[0]

    assert linha["texto"] == "x"
    assert "senha" not in linha.dropna().tolist()
