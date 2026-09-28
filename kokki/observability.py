import logging


def get_logger():
    logger = logging.getLogger("kokki")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.FileHandler("kokki.log")
        formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
