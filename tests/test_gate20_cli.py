from paper_pipeline.cli import _with_lm_timeout, _with_max_output_tokens, build_parser, main
from paper_pipeline.config import default_config


def test_cli_parser_supports_run_and_config_arguments():
    args = build_parser().parse_args(
        [
            "run",
            "--vault-root",
            ".",
            "--max-total",
            "3",
            "--dry-run",
            "--packet-max-chars",
            "1000",
            "--max-attempts",
            "1",
            "--lm-timeout-seconds",
            "600",
            "--max-output-tokens",
            "2048",
            "--stage",
            "todig",
            "--citekey",
            "paper2026",
            "--save-llm-payloads",
        ]
    )
    assert args.command == "run"
    assert args.max_total == 3
    assert args.dry_run is True
    assert args.packet_max_chars == 1000
    assert args.max_attempts == 1
    assert args.lm_timeout_seconds == 600
    assert args.max_output_tokens == 2048
    assert args.stage == "todig"
    assert args.citekey == "paper2026"
    assert args.save_llm_payloads is True


def test_cli_parser_supports_zotero_dry_run():
    args = build_parser().parse_args(["zotero-dry-run", "--max-total", "2"])
    assert args.command == "zotero-dry-run"
    assert args.max_total == 2


def test_cli_parser_supports_pilot_run():
    args = build_parser().parse_args(
        [
            "pilot-run",
            "--max-total",
            "1",
            "--packet-max-chars",
            "1000",
            "--max-attempts",
            "1",
            "--lm-timeout-seconds",
            "600",
            "--max-output-tokens",
            "2048",
            "--stage",
            "tolook",
            "--citekey",
            "paper2026",
            "--save-llm-payloads",
        ]
    )
    assert args.command == "pilot-run"
    assert args.max_total == 1
    assert args.packet_max_chars == 1000
    assert args.max_attempts == 1
    assert args.lm_timeout_seconds == 600
    assert args.max_output_tokens == 2048
    assert args.stage == "tolook"
    assert args.citekey == "paper2026"
    assert args.save_llm_payloads is True


def test_cli_lm_overrides_apply_to_stage_specific_budgets(tmp_path):
    cfg = default_config(tmp_path)
    cfg = _with_lm_timeout(cfg, 600)
    assert cfg.lmstudio.timeout_seconds == 600
    assert cfg.lmstudio.tolook_timeout_seconds == 600
    assert cfg.lmstudio.deep_stage_timeout_seconds == 600

    cfg = _with_max_output_tokens(cfg, 2048)
    assert cfg.lmstudio.max_output_tokens == 2048
    assert cfg.lmstudio.tolook_max_output_tokens == 2048
    assert cfg.lmstudio.deep_stage_max_output_tokens == 2048


def test_cli_run_loads_dotenv_without_vault_root_argument(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    inbox = vault / "Inbox" / "Human Review"
    inbox.mkdir(parents=True)
    (tmp_path / ".env").write_text(
        f"VAULT_ROOT={vault}\nOBSIDIAN_HUMAN_REVIEW_INBOX_DIR=Inbox/Human Review\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VAULT_ROOT", raising=False)
    monkeypatch.delenv("OBSIDIAN_HUMAN_REVIEW_INBOX_DIR", raising=False)
    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    monkeypatch.delenv("ZOTERO_USER_ID", raising=False)

    assert main(["run", "--dry-run", "--max-total", "1"]) == 0

    assert "dry-run" in capsys.readouterr().out
