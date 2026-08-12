from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    base_dir: Path = Path(__file__).resolve().parent.parent
    input_dir: Path = base_dir / 'input'
    output_dir: Path = base_dir / 'output'
    templates_dir: Path = base_dir / 'templates'
    vectorstore_dir: Path = base_dir / 'vectorstore'
    input_pdf: Path = input_dir / 'AnnualReport.pdf'
    output_md: Path = output_dir / 'annual_report.md'
    output_json: Path = output_dir / 'annual_report.json'
    entities_json: Path = output_dir / 'entities.json'
    validated_json: Path = output_dir / 'validated_entities.json'
    output_excel: Path = output_dir / 'financial_output.xlsx'
    template_excel: Path = templates_dir / 'financial_template.xlsx'
    faiss_index_file: Path = vectorstore_dir / 'faiss_index.faiss'
    embeddings_file: Path = vectorstore_dir / 'embeddings.pkl'
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k: int = 10
    embedding_provider: str = 'huggingface'
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    llm_model: str = 'groq-3.5-mini'
    anthropic_api_key: str = ''

    def __post_init__(self) -> None:
        load_dotenv(self.base_dir / '.env')
        api_key = self._get_env('ANTHROPIC_API_KEY')
        object.__setattr__(self, 'anthropic_api_key', api_key)
        os.environ['ANTHROPIC_API_KEY'] = api_key
        object.__setattr__(self, 'embedding_provider', self._get_env('EMBEDDING_PROVIDER', self.embedding_provider))
        object.__setattr__(self, 'embedding_model', self._get_env('EMBEDDING_MODEL', self.embedding_model))
        object.__setattr__(self, 'llm_model', self._get_env('LLM_MODEL', self.llm_model))
        self._create_dirs()

    def _get_env(self, key: str, default: str | None = None) -> str:
        from os import getenv

        value = getenv(key, default)
        if key == 'ANTHROPIC_API_KEY' and not value:
            raise ValueError('ANTHROPIC_API_KEY missing')
        return value or ''

    def _create_dirs(self) -> None:
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)
