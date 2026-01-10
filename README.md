# Property Scanner

An agentic system for discovering, analyzing, and ranking real estate opportunities.

## Architecture

The system uses a multi-agent architecture:
- **Discovery Agent**: Finds new sources.
- **Crawler Agents**: Extracts raw data.
- **Normalization Agent**: Standardizes data schema.
- **Enrichment Agent**: Adds geo/market context.
- **Valuation Agent**: Estimates fair value.
- **Scoring Agent**: ranks opportunities.

## Getting Started

1. **Install Dependencies**:
   ```bash
   poetry install
   ```

2. **Run with Docker**:
   ```bash
   docker-compose up --build
   ```

3. **Run Locally**:
   ```bash
   python -m src.main
   ```

## Configuration

Edit `config/sources.yaml` to add property sources.
Edit `config/agents.yaml` to tune crawler behavior.
