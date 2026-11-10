from dataclasses import dataclass


@dataclass(frozen=True)
class Fonte:
    repositorio: str
    revisao: str
    padroes: tuple[str, ...]

    @property
    def pasta(self) -> str:
        return self.repositorio.replace("/", "__")


# Os repositórios da ai-safety-brazil também trazem código Python; só dados e documentação entram.
DOCUMENTACAO_AI_SAFETY_BRAZIL = (
    "README.md",
    "LICENSE",
    "TERMS.md",
    "manifest.json",
    "audit.json",
    "generation/*.json",
)

FONTES = (
    Fonte(
        "ai-safety-brazil/prompt-injection-br-synthetic",
        "73e244d89b5171f2372199a546617a49ac0f381a",
        ("data/*.parquet", *DOCUMENTACAO_AI_SAFETY_BRAZIL),
    ),
    Fonte(
        "ai-safety-brazil/jailbreak-br-synthetic",
        "1d74570f971dcc4f3c00ea90fc4600546b8bdd64",
        ("data/*.parquet", *DOCUMENTACAO_AI_SAFETY_BRAZIL),
    ),
    Fonte(
        "Lakera/gandalf_ignore_instructions",
        "04737b65e90a6794ec227012e4a255a7def6344b",
        ("data/*.parquet", "README.md"),
    ),
    Fonte(
        "TrustAIRLab/in-the-wild-jailbreak-prompts",
        "a10aab8eff1c73165a442d4464dce192bd28b9c5",
        ("*/train-*.parquet", "README.md"),
    ),
    Fonte(
        "Lakera/mosscap_prompt_injection",
        "b7e495ff63373ff7f7dabc1e9390cf62b5838570",
        ("data/*.parquet", "README.md"),
    ),
    Fonte(
        "microsoft/llmail-inject-challenge",
        "1063bdf01ec8762b812d5e06ee768a06faa5a6f7",
        (
            "data/labelled_unique_submissions_phase2.json",
            "data/emails_for_fp_tests.json",
            "data/levels_descriptions.json",
            "data/objectives_descriptions.json",
            "data/scenarios.json",
            "data/system_prompt.json",
            "README.md",
        ),
    ),
    Fonte(
        "deepset/prompt-injections",
        "4f61ecb038e9c3fb77e21034b22511b523772cdd",
        ("data/*.parquet", "README.md"),
    ),
    Fonte(
        "leolee99/NotInject",
        "847ae76cf8fea5ed325429e569ae8cfef022d2e0",
        ("data/*.parquet", "README.md"),
    ),
    Fonte(
        "OpenAssistant/oasst2",
        "179dd21fc55192153d94adb0e0ce8f69e222bf75",
        ("data/*.parquet", "README.md"),
    ),
    Fonte(
        "allenai/WildChat-1M",
        "7d6490e462285cf85d91eabea0f9a954fbddcd1f",
        ("data/*.parquet", "README.md", "LICENSE.md"),
    ),
)
