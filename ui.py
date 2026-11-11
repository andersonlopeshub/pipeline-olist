"""Explorador do olist.duckdb no navegador, pela extensão `ui` do DuckDB.

Execução:
    uv run python ui.py

U1. O QUE FAZ
    Abre o olist.duckdb da raiz do projeto, instala e carrega a extensão ui
    (INSTALL ui; LOAD ui;) e chama CALL start_ui(), que sobe o servidor em
    http://localhost:4213 e abre o navegador.
    Por quê: explorar o banco pelo navegador em vez de ler tabela no
    terminal.

U2. FICA DE PÉ ATÉ CTRL+C
    A extensão serve enquanto a conexão estiver viva. O script mantém o
    processo rodando, imprime a URL e a instrução "Ctrl+C para encerrar", e
    no Ctrl+C fecha a conexão e sai limpo, sem traceback.
    Por quê: o .duckdb aceita um único processo escrevendo. Com este script
    de pé, a ingestão falha com "Could not set lock on file". Saber
    exatamente como desligar o servidor faz parte da ferramenta.

U3. NÃO CRIA BANCO
    Se olist.duckdb não existir, avisa que é preciso rodar a ingestão antes e
    encerra com sys.exit(1). Por isso NÃO usa conectar() de pipeline/db.py,
    que cria o arquivo quando ele falta.
    Por quê: um banco vazio aberto no navegador parece ingestão quebrada.

U4. SEPARAÇÃO
    Este arquivo não importa pipeline/ingestao.py, e a ingestão não importa
    este arquivo.
    Por quê: a ingestão não sobe servidor, não abre navegador e não depende
    da extensão ui para rodar.

U5. SAÍDA NA TELA
    stdout reconfigurado para utf-8.
    Por quê: o Prompt de Comando do Windows embaralha acento por padrão.

U6. BANCO EM USO
    Se outro processo estiver com o olist.duckdb aberto, o connect falha
    com IOException. O script mostra a mensagem do DuckDB (que traz o PID
    do processo dono do arquivo), diz como encerrá-lo e sai com
    sys.exit(1), sem traceback.
    Por quê: o caso mais comum é um ui.py esquecido aberto em outro
    terminal, e o traceback não diz isso.

Critérios de aceite:
- uv run python ui.py abre o navegador em localhost:4213 e o schema raw
  aparece com as nove tabelas.
- Ctrl+C devolve o terminal sem traceback, e logo depois a ingestão roda sem
  erro de lock.
- Renomear olist.duckdb faz o ui.py parar com a mensagem, sem criar arquivo
  novo.
- Com um ui.py já aberto, rodar outro para com a mensagem de banco em uso
  e o PID, sem traceback.
"""

import sys
import time
from pathlib import Path

import duckdb

# Mesmo critério do D1 em pipeline/db.py: caminho relativo a este arquivo,
# nunca ao diretório corrente. ui.py está na raiz do projeto.
BANCO = Path(__file__).resolve().parent / "olist.duckdb"
URL = "http://localhost:4213"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if not BANCO.is_file():
        print(f"Banco não encontrado: {BANCO}", file=sys.stderr)
        print(
            "Rode a ingestão antes: uv run python -m pipeline.ingestao",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        con = duckdb.connect(BANCO)
    except duckdb.IOException as e:
        # U6: outro processo (outro ui.py, a ingestão, o servidor MCP) está
        # com o arquivo aberto. A mensagem do DuckDB traz o PID dele.
        print(f"Banco em uso por outro processo: {BANCO}", file=sys.stderr)
        print(str(e).strip(), file=sys.stderr)
        print(
            "\nFeche esse processo (Ctrl+C no terminal dele, ou "
            "Stop-Process -Id <PID> no PowerShell) e rode de novo.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        con.execute("INSTALL ui").complete()
        con.execute("LOAD ui").complete()
        con.execute("CALL start_ui()").fetchall()
        print(f"DuckDB UI em {URL}")
        print("Ctrl+C para encerrar")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        con.close()
    print("Encerrado.")


if __name__ == "__main__":
    main()
