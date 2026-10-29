# SPDX-FileCopyrightText: 2026 EasyQM contributors
# SPDX-License-Identifier: BSD-3-Clause
import sys
from pathlib import Path

import EasyApplication
from EasyApplication.Logic.Logging import console
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

CURRENT_DIR = Path(__file__).parent  # path to qml components of the current project
# Path to the directory that *contains* the installed EasyApplication package, so that
# QML statements like `import EasyApplication.Gui.Style` can be resolved.
EASYAPP_IMPORT_DIR = Path(EasyApplication.__path__[0]).parent


if __name__ == '__main__':
    qInstallMessageHandler(console.qmlMessageHandler)
    console.debug('Custom Qt message handler defined')

    app = QApplication(sys.argv)
    console.debug(f'Qt Application created {app}')

    engine = QQmlApplicationEngine()
    console.debug(f'QML application engine created {engine}')

    engine.addImportPath(CURRENT_DIR)
    engine.addImportPath(str(EASYAPP_IMPORT_DIR))
    console.debug('Paths added where QML searches for components')

    engine.load(CURRENT_DIR / 'Gui' / 'ApplicationWindow.qml')
    console.debug('Main QML component loaded')

    if not engine.rootObjects():
        sys.exit(-1)
    sys.exit(app.exec())
