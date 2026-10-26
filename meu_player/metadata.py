"""Módulo metadata do Meu Player."""
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



def tag_text(tags, keys):
    """Procura a primeira tag existente entre as chaves informadas e devolve o texto.

    Cada formato de arquivo (mp3, m4a, flac) guarda as tags com nomes diferentes,
    por isso a função recebe várias opções.
    """
    for key in keys:
        if key in tags:
            value = tags[key]
            if isinstance(value, list):
                value = value[0] if value else ""
            if hasattr(value, "text"):
                value = value.text[0] if value.text else ""
            return str(value)
    return ""


def read_cover(audio):
    """Devolve os bytes da imagem de capa guardada dentro do arquivo, ou None."""
    tags = audio.tags
    if tags:
        for key in tags.keys():
            if str(key).startswith("APIC"):      # mp3
                return tags[key].data
        if "covr" in tags:                       # m4a / aac
            return bytes(tags["covr"][0])
    pictures = getattr(audio, "pictures", None)  # flac
    if pictures:
        return pictures[0].data
    return None


def read_metadata(path: Path):
    """Lê título, artista, álbum, ano, duração e capa de um arquivo de música."""
    info = {
        "title": path.stem, "artist": "", "album": "", "year": "",
        "length": 0.0, "cover": None,
    }
    try:
        audio = MutagenFile(path)
        if audio is None:
            return info
        if audio.info is not None:
            info["length"] = float(getattr(audio.info, "length", 0.0) or 0.0)
        tags = audio.tags or {}
        info["title"] = tag_text(tags, ["title", "TIT2", "\xa9nam"]) or info["title"]
        info["artist"] = tag_text(tags, ["artist", "TPE1", "\xa9ART"])
        info["album"] = tag_text(tags, ["album", "TALB", "\xa9alb"])
        info["year"] = tag_text(tags, ["date", "TDRC", "\xa9day"])[:4]
        info["cover"] = read_cover(audio)
    except Exception:
        # Arquivo corrompido ou formato não reconhecido: usa o nome do arquivo
        pass
    return info


def make_icon(data, size=40):
    """Cria um ícone pequeno a partir dos bytes de uma imagem."""
    pixmap = QPixmap()
    if data and pixmap.loadFromData(data):
        return QIcon(pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return QIcon()


def format_time(ms: int) -> str:
    """Converte milissegundos em texto, como 3:45 ou 1:02:10."""
    seconds = max(0, ms // 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"