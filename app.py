import sys
from PySide6.QtWidgets import QApplication
from src.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    # Conservamos el nombre interno anterior para no perder QSettings ni
    # el perfil persistente de ChatGPT de versiones previas.
    app.setApplicationName("Consultor Bíblico")
    app.setApplicationDisplayName("Consultor App")
    app.setOrganizationName("TraduccionBiblica")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
