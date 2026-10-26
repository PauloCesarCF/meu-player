"""Módulo widgets do Meu Player."""
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



class TrackInfoDialog(QDialog):
    """Janela para corrigir título, artista, álbum e ano de uma música."""

    FIELDS = [("title", "Título"), ("artist", "Artista"), ("album", "Álbum"), ("year", "Ano")]

    def __init__(self, current, original, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar informações")
        self.original = original  # valores do arquivo, usados se um campo ficar vazio
        form = QFormLayout(self)
        self.edits = {}
        for key, label in self.FIELDS:
            edit = QLineEdit(current.get(key, ""))
            form.addRow(label, edit)
            self.edits[key] = edit
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        return {key: (edit.text().strip() or self.original.get(key, "")) for key, edit in self.edits.items()}


class ClickSeekSlider(QSlider):
    """Barra de progresso que vai direto para o ponto clicado (não anda só uma página)."""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            handle = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)
            value = QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(),
                int(event.position().x()) - handle.width() // 2,
                self.width() - handle.width(),
            )
            self.setValue(value)
            self.sliderMoved.emit(value)
        super().mousePressEvent(event)  # depois disso o arrasto continua normalmente


class QueueWindow(QWidget):
    """Janela da fila: música atual, fila (escolhida por você) e as próximas que vão tocar."""

    def __init__(self, player):
        super().__init__(player, Qt.Popup)  # pop up: fecha ao clicar fora dele
        self.player = player
        self.resize(380, 440)
        self.timer = QTimer(self)  # atualiza a lista enquanto o pop up está aberto
        self.timer.setInterval(300)
        self.timer.timeout.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tocando agora"))
        self.now_label = QLabel("")
        self.now_label.setObjectName("title")
        self.now_label.setWordWrap(True)
        layout.addWidget(self.now_label)

        self.list = QListWidget()
        self.list.setToolTip("Clique duas vezes em uma música para tocar agora")
        self.list.itemDoubleClicked.connect(self._play_item)
        layout.addWidget(self.list, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        clear = QPushButton("Limpar fila")
        clear.clicked.connect(self.player.clear_queue)
        bottom.addWidget(clear)
        layout.addLayout(bottom)

        self.refresh()

    def showEvent(self, event):
        self.timer.start()
        self.refresh()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _title(self, index):
        meta = self.player.meta[index]
        return f"{meta['title']}  —  {meta['artist']}" if meta["artist"] else meta["title"]

    def _section(self, text):
        item = QListWidgetItem(text)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        item.setFlags(Qt.NoItemFlags)
        self.list.addItem(item)

    def refresh(self):
        p = self.player
        if 0 <= p.current_index < len(p.tracks):
            self.now_label.setText(self._title(p.current_index))
        else:
            self.now_label.setText("Nada tocando")

        queued, following = p.upcoming()
        self.list.clear()
        self._section("Na fila")
        if not queued:
            self.list.addItem(QListWidgetItem("Fila vazia (clique com o botão direito em uma música)"))
        for position, index in enumerate(queued):
            item = QListWidgetItem(f"{position + 1}. {self._title(index)}")
            item.setData(Qt.UserRole, ("queued", position))
            self.list.addItem(item)

        self._section("A seguir" + (" (modo aleatório)" if p.shuffle else ""))
        if not following:
            self.list.addItem(QListWidgetItem("Nada a seguir"))
        for index in following:
            item = QListWidgetItem(self._title(index))
            item.setData(Qt.UserRole, ("upcoming", index))
            self.list.addItem(item)

    def _play_item(self, item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        kind, value = data
        if kind == "queued":
            index = self.player.up_next.pop(value)
            self.player._update_queue_button()
            self.player.play_index(index)
        else:
            self.player.play_index(value)