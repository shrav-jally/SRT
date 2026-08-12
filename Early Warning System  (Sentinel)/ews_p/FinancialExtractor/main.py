from src.config import Config
from src.parser import DoclingParser
from src.loader import MarkdownLoader
from src.chunker import Chunker
from src.vectordb import VectorDB
from src.retriever import Retriever
from src.extractor import FinancialExtractor
from src.validator import JsonValidator
from src.excel_writer import ExcelWriter
from src.utils import setup_logging


def main() -> None:
    logger = setup_logging()
    config = Config()

    logger.info('===========================================')
    logger.info('Financial Entity Extraction')
    logger.info('===========================================')

    parser = DoclingParser(config)
    loader = MarkdownLoader(config)
    chunker = Chunker(config)
    vectordb = VectorDB(config)
    retriever = Retriever(config, vectordb)
    extractor = FinancialExtractor(config)
    validator = JsonValidator(config)
    excel_writer = ExcelWriter(config)

    try:
        logger.info('Parsing PDF...')
        parser.parse_pdf()

        logger.info('Loading Documents...')
        documents = loader.load_markdown()

        logger.info('Chunking...')
        chunks = chunker.split_documents(documents)

        logger.info('Creating Embeddings...')
        vectordb.build_index(chunks)

        logger.info('Retrieving Relevant Chunks...')
        relevant_chunks = retriever.get_relevant_chunks()

        logger.info('Calling GPT...')
        entities = extractor.extract_entities(relevant_chunks)

        logger.info('Saving extracted JSON...')
        from src.utils import save_json

        save_json(config.entities_json, entities)

        logger.info('Validating Results...')
        validated_entities = validator.validate(entities)

        logger.info('Writing Excel...')
        excel_writer.write(validated_entities)

        logger.info('Done!')
        logger.info('Files saved inside output/')
    except Exception as error:
        logger.exception('Pipeline failed')
        raise SystemExit(1) from error


if __name__ == '__main__':
    main()
