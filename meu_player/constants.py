"""Módulo constants do Meu Player."""
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



AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".wma", ".opus"}


HISTORY_FILE = Path.home() / ".meu_player" / "historico.json"


MIN_LISTEN_SECONDS = 30  # tempo mínimo ouvido para contar como reprodução
MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


PALETTE = {
    "light": {
        "bg": "#f5f5f7", "panel": "#ffffff", "text": "#1d1d1f", "muted": "#8e8e93",
        "accent": "#0a84ff", "border": "#d2d2d7", "hover": "#ececf0",
    },
    "dark": {
        "bg": "#1c1c1e", "panel": "#2c2c2e", "text": "#f5f5f7", "muted": "#8e8e93",
        "accent": "#0a84ff", "border": "#3a3a3c", "hover": "#3a3a3c",
    },
}


QSS_TEMPLATE = """
QMainWindow, QWidget#root { background: @bg@; }
QWidget { font-family: "Segoe UI"; font-size: 13px; color: @text@; }
QFrame#panel { background: @panel@; border-radius: 12px; }
QLabel#title { font-size: 16px; font-weight: bold; }
QLabel#muted { color: @muted@; }
QLabel#cover { background: #ffffff; border-radius: 12px; color: #1d1d1f; font-size: 72px; }
QLineEdit { background: @panel@; border: 1px solid @border@; border-radius: 8px; padding: 6px 10px; }
QPushButton { background: @panel@; border: 1px solid @border@; border-radius: 8px; padding: 6px 12px; }
QPushButton:hover { background: @hover@; }

/* Botão de tocar/pausar: só o ícone, sem fundo. Quando a música toca, fica laranja. */
QPushButton#play { background: transparent; border: none; color: @accent@; min-width: 48px; min-height: 48px; font-size: 28px; }
QPushButton#play:hover { background: transparent; }
QPushButton#play[playing="true"] { color: #ff9f0a; }

/* Anterior/próxima: só o ícone, sem fundo. */
QPushButton#icon { background: transparent; border: none; font-size: 18px; min-width: 36px; min-height: 36px; color: @text@; }
QPushButton#icon:hover { background: transparent; }

/* Aleatório, repetir e tema: cinza quando desligados, azul quando ligados. */
QPushButton#toggle { background: transparent; border: none; font-size: 20px; font-weight: bold; min-width: 36px; min-height: 36px; color: @muted@; }
QPushButton#toggle:hover { background: transparent; }
QPushButton#toggle:checked { background: transparent; color: @accent@; }

/* Botões com texto (Álbuns e Favoritos): cinza quando desligados, azuis quando ligados. */
QPushButton#text_toggle { background: transparent; border: none; color: @muted@; font-weight: bold; padding: 4px 8px; }
QPushButton#text_toggle:hover { background: transparent; }
QPushButton#text_toggle:checked { background: transparent; color: @accent@; }

QPushButton#add { background: transparent; border: none; color: @accent@; font-size: 18px; font-weight: bold; min-width: 24px; max-width: 24px; padding: 0px; }
QPushButton#add:hover { background: transparent; }
QPushButton#star, QPushButton#dots { background: transparent; border: none; font-size: 16px; min-width: 24px; max-width: 24px; padding: 0px; }
QPushButton#star:hover, QPushButton#dots:hover { background: transparent; }
QPushButton#star { color: @muted@; }
QPushButton#star[fav="true"] { color: #ff9f0a; }
QPushButton#dots { color: @muted@; font-size: 18px; font-weight: bold; }
QPushButton#dots:hover { color: @accent@; }
QListWidget { background: @panel@; border: none; }
QListWidget::item { padding: 8px; border-radius: 6px; }
QListWidget::item:selected { background: rgba(10, 132, 255, 0.18); color: @text@; }
QTreeWidget { background: @panel@; border: none; border-radius: 12px; alternate-background-color: @hover@; }
QTreeWidget::item { padding: 6px 4px; }
QTreeWidget::item:selected { background: rgba(10, 132, 255, 0.18); color: @text@; }
QHeaderView::section { background: @panel@; color: @muted@; border: none; padding: 6px; font-weight: bold; }
QSlider::groove:horizontal { height: 4px; background: @border@; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 2px; }
QSlider::handle:horizontal { background: @accent@; width: 12px; margin: -5px 0; border-radius: 6px; }
"""