import json

from paper_pipeline.cli import (
    _with_lm_timeout,
    _with_max_output_tokens,
    build_parser,
    main,
)
from paper_pipeline.config import default_config
from paper_pipeline.zotero_adapter import ZoteroItem


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


def test_cli_parser_supports_scan_obsidian():
    args = build_parser().parse_args(
        [
            "scan-obsidian",
            "--output",
            "data/projects.jsonl",
        ]
    )
    assert args.command == "scan-obsidian"
    assert args.vault_root is None
    assert args.output == "data/projects.jsonl"


def test_cli_parser_supports_scan_zotero_offline_fixture():
    args = build_parser().parse_args(
        [
            "scan-zotero",
            "--offline-fixture",
            "fixtures/zotero.json",
            "--output",
            "data/papers.jsonl",
            "--papers-root",
            "papers",
        ]
    )
    assert args.command == "scan-zotero"
    assert args.offline_fixture == "fixtures/zotero.json"
    assert args.output == "data/papers.jsonl"
    assert args.papers_root == "papers"


def test_cli_parser_supports_match_filters():
    args = build_parser().parse_args(
        [
            "match",
            "--projects",
            "data/projects.jsonl",
            "--papers",
            "data/papers.jsonl",
            "--output",
            "data/candidates.jsonl",
            "--top-n",
            "8",
            "--max-candidates-total",
            "8",
            "--paper-stages",
            ".ToLook,.To Revise",
            "--include-states",
            "on,ongoing",
        ]
    )
    assert args.command == "match"
    assert args.projects == "data/projects.jsonl"
    assert args.papers == "data/papers.jsonl"
    assert args.output == "data/candidates.jsonl"
    assert args.top_n == 8
    assert args.max_candidates_total == 8
    assert args.paper_stages == ".ToLook,.To Revise"
    assert args.include_states == "on,ongoing"


def test_cli_parser_supports_classify():
    args = build_parser().parse_args(
        [
            "classify",
            "--candidates",
            "data/candidates.jsonl",
            "--projects",
            "data/projects.jsonl",
            "--papers",
            "data/papers.jsonl",
            "--output",
            "data/classifications.jsonl",
            "--max-candidates",
            "8",
            "--paper-stages",
            ".ToLook,.ToDig",
            "--max-attempts",
            "3",
            "--lm-timeout-seconds",
            "600",
            "--max-output-tokens",
            "2048",
            "--save-llm-payloads",
        ]
    )
    assert args.command == "classify"
    assert args.candidates == "data/candidates.jsonl"
    assert args.projects == "data/projects.jsonl"
    assert args.papers == "data/papers.jsonl"
    assert args.output == "data/classifications.jsonl"
    assert args.max_candidates == 8
    assert args.paper_stages == ".ToLook,.ToDig"
    assert args.max_attempts == 3
    assert args.lm_timeout_seconds == 600
    assert args.max_output_tokens == 2048
    assert args.save_llm_payloads is True


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


def test_cli_run_loads_dotenv_without_vault_root_argument(
    tmp_path, monkeypatch, capsys
):
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


def test_cli_scan_obsidian_loads_dotenv_without_vault_root_argument(
    tmp_path, monkeypatch, capsys
):
    vault = tmp_path / "vault"
    (vault / "Efforts" / "On").mkdir(parents=True)
    (vault / "Efforts" / "On" / "Runnable.md").write_text(
        "# Runnable\n\n## Objectives\n- confirm CLI .env fallback works\n",
        encoding="utf-8",
    )
    (tmp_path / ".env").write_text(
        f"VAULT_ROOT={vault}\nOBSIDIAN_HUMAN_REVIEW_INBOX_DIR=Inbox/Human Review\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VAULT_ROOT", raising=False)
    monkeypatch.delenv("OBSIDIAN_HUMAN_REVIEW_INBOX_DIR", raising=False)

    output = tmp_path / "data" / "projects.jsonl"
    assert main(["scan-obsidian", "--output", str(output)]) == 0

    captured = capsys.readouterr()
    assert "projects=1" in captured.out
    assert output.exists()


def test_cli_scan_obsidian_prefers_cli_vault_root_over_dotenv(tmp_path, monkeypatch):
    env_vault = tmp_path / "env-vault"
    cli_vault = tmp_path / "cli-vault"
    (env_vault / "Efforts" / "On").mkdir(parents=True)
    (cli_vault / "Efforts" / "On").mkdir(parents=True)
    (env_vault / "Efforts" / "On" / "Env Note.md").write_text(
        "# Env Note\n", encoding="utf-8"
    )
    (cli_vault / "Efforts" / "On" / "CLI Note.md").write_text(
        "# CLI Note\n", encoding="utf-8"
    )
    (tmp_path / ".env").write_text(f"VAULT_ROOT={env_vault}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VAULT_ROOT", raising=False)

    output = tmp_path / "data" / "projects.jsonl"
    assert (
        main(["scan-obsidian", "--vault-root", str(cli_vault), "--output", str(output)])
        == 0
    )

    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "CLI Note" in lines[0]


def test_cli_scan_zotero_loads_dotenv_credentials_without_shell_exports(
    tmp_path, monkeypatch, capsys
):
    captured = {}
    (tmp_path / ".env").write_text(
        "ZOTERO_API_KEY=dotenv-key\nZOTERO_USER_ID=dotenv-user\nZOTERO_DATA_DIR=dotenv-data\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ZOTERO_API_KEY", raising=False)
    monkeypatch.delenv("ZOTERO_USER_ID", raising=False)
    monkeypatch.delenv("ZOTERO_DATA_DIR", raising=False)

    def fake_list_paper_items(self):
        captured["api_key"] = self.api_key
        captured["user_id"] = self.user_id
        captured["data_dir"] = self.data_dir
        return [
            ZoteroItem(
                key="Z1",
                citekey="dotenv2026",
                title="Dotenv Zotero Paper",
                collections=["Library"],
                tags=[],
            )
        ]

    monkeypatch.setattr(
        "paper_pipeline.zotero_api.ZoteroApiAdapter.list_paper_items",
        fake_list_paper_items,
    )

    output = tmp_path / "data" / "papers.jsonl"
    papers_root = tmp_path / "papers"
    assert (
        main(
            ["scan-zotero", "--output", str(output), "--papers-root", str(papers_root)]
        )
        == 0
    )

    assert captured == {
        "api_key": "dotenv-key",
        "user_id": "dotenv-user",
        "data_dir": "dotenv-data",
    }
    row = json.loads(output.read_text(encoding="utf-8"))
    assert row["citekey"] == "dotenv2026"
    assert "papers=1" in capsys.readouterr().out
