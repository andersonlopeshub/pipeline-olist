"""Testes de pipeline/db.py. Spec: docstring do módulo (D1 a D4)."""

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pipeline import db

RAIZ = Path(__file__).resolve().parent.parent


def test_importar_db_nao_cria_arquivo_na_pasta_corrente(tmp_path):
    # Processo novo: o import já feito por este arquivo não serve de prova.
    ambiente = {**os.environ, "PYTHONPATH": str(RAIZ)}
    subprocess.run(
        [sys.executable, "-c", "import pipeline.db"],
        cwd=tmp_path,
        env=ambiente,
        check=True,
    )
    assert list(tmp_path.iterdir()) == []


def test_conectar_cria_o_banco_ao_lado_de_raw_e_nao_na_pasta_corrente(tmp_path, monkeypatch):
    projeto = tmp_path / "projeto"
    (projeto / "raw").mkdir(parents=True)
    outra = tmp_path / "outra"
    outra.mkdir()
    monkeypatch.setattr(db, "PASTA_RAW", projeto / "raw")
    monkeypatch.chdir(outra)

    con = db.conectar()
    con.close()

    assert (projeto / "olist.duckdb").is_file()
    assert list(outra.iterdir()) == []


def test_criar_schema_duas_vezes_nao_falha(tmp_path):
    con = duckdb.connect(tmp_path / "t.duckdb")
    db.criar_schema(con, "raw")
    db.criar_schema(con, "raw")
    schemas = con.execute(
        "SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'raw'"
    ).fetchall()[0][0]
    con.close()
    assert schemas == 1


def test_gravar_tres_linhas_devolve_tres_e_regravar_continua_tres(tmp_path):
    con = duckdb.connect(tmp_path / "t.duckdb")
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"a": ["x", "y", "z"]})  # três linhas quaisquer

    primeira = db.gravar(con, df, "raw", "t")
    segunda = db.gravar(con, df, "raw", "t")
    con.close()

    assert primeira == 3
    assert segunda == 3


def test_gravar_mantem_texto_como_varchar_e_nulo_como_null(tmp_path):
    con = duckdb.connect(tmp_path / "t.duckdb")
    db.criar_schema(con, "raw")
    df = pd.DataFrame(
        {
            "cep": ["01310", None],  # zero à esquerda; segunda linha sem CEP
        },
        dtype=str,
    )
    db.gravar(con, df, "raw", "t")
    tipo = con.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'raw' AND table_name = 't' AND column_name = 'cep'"
    ).fetchall()[0][0]
    linhas = con.execute("SELECT cep FROM raw.t ORDER BY cep NULLS LAST").fetchall()
    con.close()

    assert tipo == "VARCHAR"
    assert linhas == [("01310",), (None,)]


def test_gravar_nao_deixa_view_temporaria_nem_quando_falha(tmp_path):
    con = duckdb.connect(tmp_path / "t.duckdb")
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"a": ["x"]})

    db.gravar(con, df, "raw", "t")
    # Schema que não existe: o CREATE falha depois do register.
    with pytest.raises(duckdb.CatalogException):
        db.gravar(con, df, "nao_existe", "t")

    views = con.execute(
        "SELECT count(*) FROM duckdb_views() WHERE view_name = '__gravar_df'"
    ).fetchall()[0][0]
    con.close()
    assert views == 0
