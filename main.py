import sys
import os

if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))

from ping_tool.ui.app import PingApp
from ping_tool.logger import setup_logger

def main():
    logger = setup_logger()
    logger.info("应用启动")
    try:
        app = PingApp()
        app.mainloop()
    except Exception as e:
        logger.critical(f"应用异常退出: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
