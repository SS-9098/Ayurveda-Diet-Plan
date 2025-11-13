import logging
import sys

def show_messages(label):
    logger = logging.getLogger()  # root logger
    print(f"\n--- {label} (level={logging.getLevelName(logger.level)}, handlers={len(logger.handlers)}) ---")
    logging.debug("debug message")
    logging.info("info message")
    logging.warning("warning message")

# 1) Default logging (no basicConfig): default level is WARNING
show_messages("default (no basicConfig)")

# 2) Configure once: sets root level to INFO and adds a StreamHandler
logging.basicConfig(level=logging.INFO)
show_messages("after basicConfig(level=INFO)")

# 3) Attempt to reconfigure to DEBUG -> has no effect because handlers already exist
logging.basicConfig(level=logging.DEBUG)  # no-op if handlers exist
show_messages("after basicConfig(level=DEBUG) again (no-op)")

# 4) If you remove handlers, you can reconfigure
for h in list(logging.getLogger().handlers):
    logging.getLogger().removeHandler(h)

logging.basicConfig(level=logging.DEBUG)
show_messages("after removing handlers and basicConfig(level=DEBUG)")