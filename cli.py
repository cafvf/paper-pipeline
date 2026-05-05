#!/usr/bin/env python3
import sys
import argparse
import importlib

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    # try to delegate to package's CLI if present
    try:
        pkg_cli = importlib.import_module("paper_pipeline.cli")
        if hasattr(pkg_cli, "main"):
            return pkg_cli.main(argv)
    except Exception:
        pass

    parser = argparse.ArgumentParser(prog="paper-pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument("--version", action="store_true", help="Show version")
    if "--help" in sys.argv or "-h" in sys.argv:
        parser.print_help()
        return 0
    print("Erro: pacote 'paper_pipeline' não encontrado. Copie o diretório 'paper_pipeline' do vault para este repositório e rode novamente.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
