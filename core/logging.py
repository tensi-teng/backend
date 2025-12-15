import logging
from core.configs import settings

class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[1;91m",  # Bold Red
    }
    RESET = "\033[0m"

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


# Configure logger
logger = logging.getLogger("colored_logger")
handler = logging.StreamHandler()
handler.setFormatter(
    ColoredFormatter("%(levelname)s:     %(funcName)s:Line-%(lineno)d: %(message)s")
)
logger.addHandler(handler)

logger.setLevel(settings.DEBUG_MODE and logging.DEBUG or logging.INFO)