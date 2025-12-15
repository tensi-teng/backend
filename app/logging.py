import logging


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[94m",
        "INFO": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[1;91m",
    }
    RESET = "\033[0m"

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


def init_logging(app):
    logger = logging.getLogger()
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            ColoredFormatter("%(levelname)s: %(name)s:%(funcName)s:L%(lineno)d: %(message)s")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
