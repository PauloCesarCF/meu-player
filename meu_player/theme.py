"""Módulo theme do Meu Player."""
import csv
import json
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from mutagen import File as MutagenFile
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, QSettings, QTimer, QUrl
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QInputDialog, QListView, QStackedWidget, QStyle, QStyleOptionSlider, QTabWidget, QListWidget, QListWidgetItem, QMenu, QMessageBox, QSplitter,
    QAbstractItemView, QApplication, QFileDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QPushButton, QSlider, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from meu_player.constants import QSS_TEMPLATE


def make_qss(palette):
    """Troca as palavras entre @ pelas cores do tema escolhido."""
    qss = QSS_TEMPLATE
    for key, value in palette.items():
        qss = qss.replace(f"@{key}@", value)
    return qss