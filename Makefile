# Planwerk: one command per step. All steps run locally on DuckDB without cloud accounts.
PROFILE ?= dev
SEED ?= 42
export PLANWERK_RAW ?= $(CURDIR)/data/raw
export PLANWERK_DUCKDB ?= $(CURDIR)/data/warehouse/planwerk.duckdb
DBT_FLAGS = --project-dir $(CURDIR)/dbt --profiles-dir $(CURDIR)/dbt

.PHONY: install generate dbt test lint forecast backtest liquidity assistant mcp q1 sac eval reports all clean

install:
	pip install -e ".[dbt,reporting,assistant,dev]"

generate:            ## simulate Nordwerk GmbH (S/4HANA tables as Parquet)
	python -m planwerk.generator.run --profile $(PROFILE) --seed $(SEED) --out $(PLANWERK_RAW)

dbt:                 ## build and test the warehouse (staging -> core -> controlling -> semantic)
	mkdir -p data/warehouse
	dbt seed $(DBT_FLAGS) && dbt build $(DBT_FLAGS)

test:                ## unit, data and logic tests (CI profile)
	pytest

lint:
	ruff check src tests eval

forecast:            ## rolling forecast 3+9 / 6+6 / 9+3 for the main scenario
	python -m planwerk.forecast.rolling

backtest:            ## Q2: lead time of ML forecast vs straight-line over simulated scenarios
	python -m planwerk.forecast.backtest --scenarios 200

liquidity:           ## 13-week liquidity forecast from open items
	python -m planwerk.controlling.liquidity

assistant:           ## ask the assistant: make assistant Q="Warum liegt der DB II unter Plan?"
	python -m planwerk.assistant.graph "$(Q)"

mcp:                 ## run the MCP server (stdio)
	python -m planwerk.assistant.mcp_server

eval:                ## Q3: golden set and commentary evaluation of the AI assistant
	python -m planwerk.assistant.eval

q1:                  ## Q1: variance bridge evaluation against the injected ground truth
	python -m planwerk.controlling.q1_evaluation

sac:                 ## SAC Planning import files (dimensions, facts, driver basis)
	python -m planwerk.sac.export

reports: q1          ## German Excel month-end report and steering-committee deck
	python -m planwerk.reporting.excel_report
	python -m planwerk.reporting.deck

all: generate dbt forecast backtest liquidity q1 eval sac reports

clean:
	rm -rf data/raw data/warehouse dbt/target reports/out
