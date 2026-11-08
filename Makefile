# Planwerk: one command per step. All steps run locally on DuckDB without cloud accounts.
PROFILE ?= dev
SEED ?= 42
export PLANWERK_RAW ?= $(CURDIR)/data/raw
export PLANWERK_DUCKDB ?= $(CURDIR)/data/warehouse/planwerk.duckdb
DBT = cd dbt && dbt

.PHONY: install generate dbt test lint forecast backtest liquidity assistant eval reports all clean

install:
	pip install -e ".[dbt,reporting,assistant,dev]"

generate:            ## simulate Nordwerk GmbH (S/4HANA tables as Parquet)
	python -m planwerk.generator.run --profile $(PROFILE) --seed $(SEED) --out $(PLANWERK_RAW)

dbt:                 ## build and test the warehouse (staging -> core -> controlling -> semantic)
	mkdir -p data/warehouse
	$(DBT) seed --profiles-dir . && $(DBT) build --profiles-dir .

test:                ## unit, data and logic tests (CI profile)
	pytest

lint:
	ruff check src tests

forecast:            ## rolling forecast 3+9 / 6+6 / 9+3 for the main scenario
	python -m planwerk.forecast.rolling

backtest:            ## Q2: lead time of ML forecast vs straight-line over simulated scenarios
	python -m planwerk.forecast.backtest --scenarios 200

liquidity:           ## 13-week liquidity forecast from open items
	python -m planwerk.controlling.liquidity

eval:                ## Q3: golden set and commentary evaluation of the AI assistant
	python -m planwerk.assistant.eval

reports:             ## German Excel month-end report and steering-committee deck
	python -m planwerk.reporting.excel_report
	python -m planwerk.reporting.deck

all: generate dbt forecast backtest liquidity eval reports

clean:
	rm -rf data/raw data/warehouse dbt/target reports/out
