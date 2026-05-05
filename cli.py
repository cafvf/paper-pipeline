#!/usr/bin/env python3
import sys
import argparse
import importlib

def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    try:
        pkg_cli = importlib.import_module("paper_pipeline.cli")
    except ImportError:
        parser = argparse.ArgumentParser(prog="paper-pipeline")
        parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
        parser.add_argument("--version", action="store_true", help="Show version")
        if "--help" in sys.argv or "-h" in sys.argv:
            parser.print_help()
            return 0
        print("Erro: pacote 'paper_pipeline' nao encontrado. Instale o projeto com `uv sync` e rode novamente.")
        return 1

    return pkg_cli.main(argv)

if __name__ == "__main__":
    sys.exit(main())
