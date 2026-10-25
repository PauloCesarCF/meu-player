"""
Meu Player - player de música para Windows feito com PySide6.

Funções principais:
- Lê pastas de músicas (com subpastas) e mostra título, artista e duração.
- Visualização por músicas ou por álbum, com a capa de cada álbum.
- Favoritos (★), com filtro para ver só os favoritos.
- Controles de tocar, pausar, anterior, próxima, aleatório, repetir e volume.
- Atalhos de teclado.
- Tema claro (padrão) e tema escuro.
- Lembra pastas, volume, tema, visualização, favoritos e a última música.
"""

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

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Extensões de arquivo que o programa considera música
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".wma", ".opus"}

# Arquivo com o histórico de reproduções (usado nas estatísticas)
HISTORY_FILE = Path.home() / ".meu_player" / "historico.json"
MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

# Cores dos dois temas. "accent" é a cor de destaque (azul).
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

# Modelo do estilo visual. As palavras entre @ são trocadas pelas cores de PALETTE.
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


# ---------------------------------------------------------------------------
# Funções de apoio: estilo, metadados, capas e tempo
# ---------------------------------------------------------------------------

def make_qss(palette):
    """Troca as palavras entre @ pelas cores do tema escolhido."""
    qss = QSS_TEMPLATE
    for key, value in palette.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


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


# ---------------------------------------------------------------------------
# Janela principal
# ---------------------------------------------------------------------------

def compute_streaks(history):
    """Devolve (sequência atual, maior sequência) em dias seguidos com música tocada."""
    days = sorted({date.fromisoformat(e["time"][:10]) for e in history if e.get("time")})
    if not days:
        return 0, 0
    best = run = 1
    for prev, cur in zip(days, days[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    current = 0
    if (date.today() - days[-1]).days <= 1:  # a sequência só vale se ouviu hoje ou ontem
        expected = days[-1]
        for d in reversed(days):
            if d == expected:
                current += 1
                expected = d - timedelta(days=1)
            elif d < expected:
                break
    return current, best


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


class MonthBars(QWidget):
    """Gráfico de barras com a quantidade de reproduções de cada mês."""

    def __init__(self):
        super().__init__()
        self.values = [0] * 12
        self.setMinimumHeight(170)

    def set_values(self, values):
        self.values = values
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        label_height, top_margin = 24, 22
        area = height - label_height - top_margin
        peak = max(self.values) or 1
        slot = width / 12
        bar_width = slot * 0.6
        text_color = self.palette().windowText().color()

        for i, value in enumerate(self.values):
            bar_height = area * value / peak
            x = i * slot + (slot - bar_width) / 2
            y = top_margin + area - bar_height
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#0a84ff"))
            painter.drawRoundedRect(QRectF(x, y, bar_width, bar_height), 4, 4)
            painter.setPen(text_color)
            if value:
                painter.drawText(QRectF(i * slot, y - 18, slot, 18), Qt.AlignCenter, str(value))
            painter.drawText(QRectF(i * slot, height - label_height, slot, label_height),
                             Qt.AlignCenter, MONTHS[i])
        painter.end()


class StatsWindow(QWidget):
    """Janela de estatísticas: ranking de músicas, total do ano e gráfico por mês."""

    def __init__(self, history, on_summary=None):
        super().__init__()
        self.history = history
        self.on_summary = on_summary   # abre o resumo do ano em página própria
        self.card_lines = []           # linhas do resumo do ano do ano selecionado
        self.setWindowTitle("Estatísticas de escuta")
        self.resize(780, 620)

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Ano:"))
        self.year_combo = QComboBox()
        self.year_combo.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.year_combo)
        top.addStretch(1)
        export = QPushButton("Exportar CSV")
        export.setToolTip("Salvar o ranking do ano em um arquivo para abrir no Excel")
        export.clicked.connect(self.export_csv)
        top.addWidget(export)
        summary_button = QPushButton("Resumo do ano")
        summary_button.setToolTip("Abrir o resumo do ano em uma página para tirar print")
        summary_button.clicked.connect(self.show_summary)
        top.addWidget(summary_button)
        layout.addLayout(top)

        self.summary = QLabel("")
        self.summary.setObjectName("title")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        self.month_bars = MonthBars()
        layout.addWidget(self.month_bars)

        self.rank = QTreeWidget()
        self.rank.setHeaderLabels(["#", "Música", "Artista", "Vezes", "Tempo"])
        self.rank.setRootIsDecorated(False)
        self.rank.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rank.header().setStretchLastSection(False)
        self.rank.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.rank.setColumnWidth(0, 50)
        self.history_tree = QTreeWidget()
        self.history_tree.setHeaderLabels(["Data", "Hora", "Música", "Artista"])
        self.history_tree.setRootIsDecorated(False)
        self.history_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_tree.header().setStretchLastSection(False)
        self.history_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.history_tree.setColumnWidth(0, 110)
        self.history_tree.setColumnWidth(1, 80)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.rank, "Ranking")
        self.tabs.addTab(self.history_tree, "Histórico por data")

        self.album_tree = QTreeWidget()
        self.album_tree.setHeaderLabels(["#", "Álbum", "Artista", "Reproduções", "Tempo"])
        self.album_tree.setRootIsDecorated(False)
        self.album_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.album_tree.header().setStretchLastSection(False)
        self.album_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.album_tree.setColumnWidth(0, 50)

        self.artist_tree = QTreeWidget()
        self.artist_tree.setHeaderLabels(["#", "Artista", "Reproduções", "Tempo"])
        self.artist_tree.setRootIsDecorated(False)
        self.artist_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.artist_tree.header().setStretchLastSection(False)
        self.artist_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.artist_tree.setColumnWidth(0, 50)

        self.tabs.addTab(self.album_tree, "Álbuns")
        self.tabs.addTab(self.artist_tree, "Artistas")

        layout.addWidget(self.tabs, 1)

        self._fill_years()

    def _update_card(self, year, entries, ranking, album_rank, artist_rank, months):
        """Monta a aba 'Resumo do ano' com os destaques do ano."""
        if not entries:
            self.card_lines = [f"Nenhuma reprodução em {year}."]
            return
        total_seconds = int(sum(float(e.get("listened", 0) or 0) for e in entries))
        hours, rest = divmod(total_seconds, 3600)
        best_month = MONTHS[months.index(max(months))]
        cur_streak, best_streak = compute_streaks(self.history)
        lines = [
            f"Resumo de {year}",
            f"Reproduções: {len(entries)}",
            f"Tempo ouvido: {hours} h {rest // 60} min",
            f"Mês mais ativo: {best_month}",
            f"Música do ano: {ranking[0]['title']} ({ranking[0]['count']} vezes)" if ranking else "",
            f"Álbum do ano: {album_rank[0][0][0]} ({album_rank[0][1]['count']} reproduções)" if album_rank else "",
            f"Artista do ano: {artist_rank[0][0]} ({artist_rank[0][1]['count']} reproduções)" if artist_rank else "",
            f"Maior sequência de dias seguidos: {best_streak}",
        ]
        self.card_lines = [line for line in lines if line]

    def show_summary(self):
        if self.on_summary:
            self.on_summary(self.card_lines)

    def export_csv(self):
        """Salva o ranking de músicas do ano em um arquivo CSV."""
        year = self.year_combo.currentData()
        entries = getattr(self, "_entries", [])
        if not entries:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar estatísticas", f"estatisticas_{year}.csv", "CSV (*.csv)")
        if not path:
            return
        totals = {}
        for e in entries:
            d = totals.setdefault(e["path"], {"title": e.get("title", ""), "artist": e.get("artist", ""),
                                              "album": e.get("album", ""), "count": 0, "seconds": 0.0})
            d["count"] += 1
            d["seconds"] += float(e.get("listened", 0) or 0)
        ranking = sorted(totals.values(), key=lambda d: (-d["count"], d["title"].lower()))
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["posicao", "musica", "artista", "album", "reproducoes", "tempo_segundos"])
            for position, d in enumerate(ranking, start=1):
                writer.writerow([position, d["title"], d["artist"], d["album"], d["count"], round(d["seconds"], 1)])

    def _fill_years(self):
        years = {int(e["time"][:4]) for e in self.history} | {datetime.now().year}
        self.year_combo.blockSignals(True)
        self.year_combo.clear()
        for year in sorted(years, reverse=True):
            self.year_combo.addItem(str(year), year)
        self.year_combo.setCurrentIndex(0)  # ano mais recente
        self.year_combo.blockSignals(False)
        self.refresh()

    def refresh(self):
        year = self.year_combo.currentData()
        if year is None:
            return
        entries = [e for e in self.history if e["time"].startswith(str(year))]

        # Ranking: quantas vezes e quanto tempo cada música foi tocada no ano
        totals = {}
        for e in entries:
            length = float(e.get("listened", 0) or 0)
            d = totals.setdefault(e["path"], {"title": e.get("title", ""), "artist": e.get("artist", ""),
                                              "count": 0, "seconds": 0.0})
            d["count"] += 1
            d["seconds"] += length
        ranking = sorted(totals.values(), key=lambda d: (-d["count"], d["title"].lower()))

        # Reproduções por mês
        months = [0] * 12
        for e in entries:
            months[int(e["time"][5:7]) - 1] += 1

        # Resumo do ano
        total_seconds = int(sum(float(e.get("listened", 0) or 0) for e in entries))
        hours, rest = divmod(total_seconds, 3600)
        summary = f"{len(entries)} reproduções em {year}  ·  {hours} h {rest // 60} min ouvindo"
        if ranking:
            top = ranking[0]
            summary += f"\nMúsica do ano: {top['title']} ({top['count']} vezes)"
        cur_streak, best_streak = compute_streaks(self.history)
        summary += f"\nSequência atual: {cur_streak} dia(s)  ·  Maior sequência: {best_streak} dia(s)"
        self._entries = entries
        self.summary.setText(summary)
        self.month_bars.set_values(months)

        self.rank.clear()
        for position, d in enumerate(ranking, start=1):
            item = QTreeWidgetItem([str(position), d["title"], d["artist"],
                                    str(d["count"]), format_time(int(d["seconds"] * 1000))])
            item.setTextAlignment(0, Qt.AlignCenter)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
            self.rank.addTopLevelItem(item)

        self.history_tree.clear()
        for e in reversed(entries):
            t = e["time"]  # formato AAAA-MM-DDTHH:MM:SS
            item = QTreeWidgetItem([f"{t[8:10]}/{t[5:7]}/{t[:4]}", t[11:16], e.get("title", ""), e.get("artist", "")])
            item.setTextAlignment(0, Qt.AlignCenter)
            item.setTextAlignment(1, Qt.AlignCenter)
            self.history_tree.addTopLevelItem(item)

        albums, artists = {}, {}
        for e in entries:
            length = float(e.get("listened", 0) or 0)
            album = e.get("album") or "Sem álbum"
            artist = e.get("artist") or "Sem artista"
            a = albums.setdefault((album, artist), {"count": 0, "seconds": 0.0})
            a["count"] += 1
            a["seconds"] += length
            r = artists.setdefault(artist, {"count": 0, "seconds": 0.0})
            r["count"] += 1
            r["seconds"] += length

        album_rank = sorted(albums.items(), key=lambda kv: (-kv[1]["count"], kv[0][0].lower()))
        self.album_tree.clear()
        for position, ((album, artist), d) in enumerate(album_rank, start=1):
            item = QTreeWidgetItem([str(position), album, artist, str(d["count"]),
                                    format_time(int(d["seconds"] * 1000))])
            item.setTextAlignment(0, Qt.AlignCenter)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
            self.album_tree.addTopLevelItem(item)

        artist_rank = sorted(artists.items(), key=lambda kv: (-kv[1]["count"], kv[0].lower()))
        self.artist_tree.clear()
        for position, (artist, d) in enumerate(artist_rank, start=1):
            item = QTreeWidgetItem([str(position), artist, str(d["count"]),
                                    format_time(int(d["seconds"] * 1000))])
            item.setTextAlignment(0, Qt.AlignCenter)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            self.artist_tree.addTopLevelItem(item)

        self._update_card(year, entries, ranking, album_rank, artist_rank, months)
        if album_rank:
            (album, artist), d = album_rank[0]
            self.summary.setText(self.summary.text() + f"\nÁlbum do ano: {album} ({d['count']} reproduções)")


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


class Player(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meu Player")
        self.resize(1000, 640)

        self.settings = QSettings("MeuPlayer", "MeuPlayer")

        # Biblioteca: as três listas andam sempre na mesma ordem
        self.tracks = []    # caminho de cada arquivo
        self.meta = []      # dados de cada música (título, artista, capa...)
        self.items = []     # linha correspondente na lista da tela (ou None se escondida)
        self.favorites = set(self.settings.value("favorites", [], type=list))
        self.playlists = self._load_playlists()
        self.playlist_covers = self._load_dict("playlist_covers")  # nome -> caminho da imagem
        self.track_covers = self._load_dict("track_covers")        # arquivo da música -> imagem escolhida
        self.track_info = self._load_dict("track_info")            # arquivo da música -> informações editadas
        self.current_playlist = None  # nome da playlist aberta, ou None para a biblioteca

        # Estado da reprodução
        self.current_index = -1
        self.shuffle = False
        self.repeat = False
        self.played_shuffle = set()  # músicas já tocadas na rodada aleatória
        self.up_next = []            # fila de reprodução (índices das músicas)
        self.shuffle_plan = []       # ordem já sorteada das próximas no modo aleatório
        self.history = self._load_history()  # reproduções registradas (para as estatísticas)
        self._last_pos = None                # última posição lida (para medir o tempo ouvido)
        self._listen_acc = 0.0               # segundos realmente ouvidos nesta reprodução
        self._last_save = time.monotonic()
        self.round_over = False      # True quando a rodada aleatória terminou
        self.dark = False
        self.album_color = False     # cor de destaque vinda da capa
        self._cover_color = None
        self._loading = False  # True enquanto as configurações são carregadas

        # Modo de exibição
        self.albums_view = False     # False = lista de músicas, True = agrupado por álbum
        self.favorites_only = False  # True = mostra só os favoritos

        # Áudio
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.playbackStateChanged.connect(self.on_state_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status)

        self._build_ui()
        self._build_shortcuts()
        self.on_theme_toggled(False)  # começa no tema claro
        self._load_settings()

    # ---------- Montagem da tela ----------

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # Coluna da esquerda: capa e informações da música atual
        left = QFrame()
        left.setObjectName("panel")
        left.setMinimumWidth(160)
        self.left_panel = left
        lv = QVBoxLayout(left)
        lv.setContentsMargins(20, 20, 20, 20)
        lv.setSpacing(6)
        head_left = QHBoxLayout()
        head_left.addStretch(1)
        self.btn_left = self._make_panel_toggle("◧", "Modo compacto do painel da esquerda", self.on_left_toggled)
        head_left.addWidget(self.btn_left)
        lv.addLayout(head_left)
        self.cover = QLabel("♪")
        self.cover.setObjectName("cover")
        self.cover.setAlignment(Qt.AlignCenter)
        self.lbl_title = QLabel("Nenhuma música tocando")
        self.lbl_title.setObjectName("title")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setMinimumHeight(48)
        self.lbl_artist = QLabel("")
        self.lbl_artist.setObjectName("muted")
        self.lbl_artist.setWordWrap(True)
        self.lbl_album = QLabel("")
        self.lbl_album.setObjectName("muted")
        self.lbl_album.setWordWrap(True)
        lv.addWidget(self.cover, alignment=Qt.AlignCenter)
        lv.addSpacing(10)
        lv.addWidget(self.lbl_title)
        lv.addWidget(self.lbl_artist)
        lv.addWidget(self.lbl_album)
        lv.addStretch(1)

        # Coluna da direita: barra de ferramentas, busca e lista
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        top = QHBoxLayout()
        self.btn_folder = QPushButton("Adicionar pasta")
        self.btn_folder.clicked.connect(self.choose_folder)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por título ou artista...  (Ctrl+F)")
        self.search.textChanged.connect(self.filter_list)

        self.btn_stats = QPushButton("📊 Estatísticas")
        self.btn_stats.setToolTip("Ver estatísticas de escuta")
        self.btn_stats.clicked.connect(self.open_stats)
        self.btn_albums = QPushButton("Álbuns")
        self.btn_albums.setObjectName("text_toggle")
        self.btn_albums.setCheckable(True)
        self.btn_albums.setToolTip("Mostrar agrupado por álbum")
        self.btn_albums.toggled.connect(self.on_view_toggled)

        self.btn_favs = QPushButton("★ Favoritos")
        self.btn_favs.setObjectName("text_toggle")
        self.btn_favs.setCheckable(True)
        self.btn_favs.setToolTip("Mostrar só os favoritos (tecla F marca/desmarca)")
        self.btn_favs.toggled.connect(self.on_favs_toggled)

        self.btn_theme = QPushButton("☾")
        self.btn_theme.setObjectName("toggle")
        self.btn_theme.setCheckable(True)
        self.btn_theme.setToolTip("Alternar tema claro/escuro")
        self.btn_theme.toggled.connect(self.on_theme_toggled)

        top.addWidget(self.btn_folder)
        top.addWidget(self.search, 1)
        top.addWidget(self.btn_stats)
        top.addWidget(self.btn_albums)
        top.addWidget(self.btn_favs)
        top.addWidget(self.btn_theme)
        right.addLayout(top)

        # Estatísticas da playlist aberta (aparece só dentro de uma playlist)
        self.stats_label = QLabel("")
        self.stats_label.setObjectName("muted")
        self.stats_label.setStyleSheet("font-size: 14px; padding: 4px 4px 0px 4px;")
        self.stats_label.setVisible(False)
        self.btn_album_color = QPushButton("🎨 Cor do álbum")
        self.btn_album_color.setObjectName("text_toggle")
        self.btn_album_color.setCheckable(True)
        self.btn_album_color.setToolTip("Usar a cor predominante da capa como destaque")
        self.btn_album_color.toggled.connect(self.on_album_color_toggled)
        self.playlist_bar = QWidget()
        bar_layout = QHBoxLayout(self.playlist_bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.addWidget(self.stats_label, 1)
        bar_layout.addWidget(self.btn_album_color)
        self.playlist_bar.setVisible(False)
        right.addWidget(self.playlist_bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Título", "Artista", "", "Duração"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(False)  # sem listras cinzas nas linhas
        self.tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree.setIconSize(QSize(40, 40))
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_tree_menu)
        self.tree.itemDoubleClicked.connect(self.on_double_click)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tree.setColumnWidth(2, 76)
        self.tree.setColumnWidth(1, 200)
        right.addWidget(self.tree, 1)

        # Coluna da direita: playlists, como no Spotify
        sidebar = QFrame()
        sidebar.setObjectName("panel")
        sidebar.setMinimumWidth(200)
        self.sidebar = sidebar
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(14, 14, 14, 14)
        sv.setSpacing(8)
        lbl_playlists = QLabel("Playlists")
        self.lbl_playlists = lbl_playlists
        lbl_playlists.setObjectName("title")
        self.btn_new_playlist = QPushButton("+ Criar playlist")
        self.btn_new_playlist.clicked.connect(self.on_new_playlist_clicked)
        self.playlist_list = QListWidget()
        self.playlist_list.setIconSize(QSize(40, 40))
        self.playlist_list.currentItemChanged.connect(self.on_playlist_selected)
        self.playlist_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self.on_playlist_menu)
        head_right = QHBoxLayout()
        head_right.addWidget(lbl_playlists)
        head_right.addStretch(1)
        self.btn_right = self._make_panel_toggle("◨", "Modo compacto das playlists", self.on_right_toggled)
        head_right.addWidget(self.btn_right)
        sv.addLayout(head_right)
        sv.addWidget(self.btn_new_playlist)
        sv.addWidget(self.playlist_list, 1)

        # Os três painéis ficam em um divisor: o usuário arrasta a borda com o mouse
        # Área central em pilha: página das músicas ou página das estatísticas
        center = QStackedWidget()
        library_page = QWidget()
        library_page.setLayout(right)
        center.addWidget(library_page)
        self.stack = center
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(sidebar)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 540, 300])
        splitter.splitterMoved.connect(lambda *args: self._update_cover_size())
        self.splitter = splitter
        splitter.setHandleWidth(4)
        outer.addWidget(splitter, 1)
        self._update_cover_size()

        # Barra inferior: progresso, controles e volume
        bottom = QFrame()
        bottom.setObjectName("panel")
        bv = QVBoxLayout(bottom)
        bv.setContentsMargins(20, 10, 20, 10)

        progress = QHBoxLayout()
        self.lbl_pos = QLabel("0:00")
        self.lbl_dur = QLabel("0:00")
        self.seek = ClickSeekSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player.setPosition)
        progress.addWidget(self.lbl_pos)
        progress.addWidget(self.seek, 1)
        progress.addWidget(self.lbl_dur)
        bv.addLayout(progress)

        controls = QHBoxLayout()
        self.btn_shuffle = QPushButton("⇄")
        self.btn_shuffle.setObjectName("toggle")
        self.btn_shuffle.setCheckable(True)
        self.btn_shuffle.setToolTip("Aleatório")
        self.btn_shuffle.toggled.connect(self.on_shuffle_toggled)
        self.btn_prev = QPushButton("⏮")
        self.btn_prev.setObjectName("icon")
        self.btn_prev.setToolTip("Anterior (Ctrl+←)")
        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("play")
        self.btn_play.setToolTip("Tocar / pausar (Espaço)")
        self.btn_next = QPushButton("⏭")
        self.btn_next.setObjectName("icon")
        self.btn_next.setToolTip("Próxima (Ctrl+→)")
        self.btn_repeat = QPushButton("↻")
        self.btn_repeat.setObjectName("toggle")
        self.btn_repeat.setCheckable(True)
        self.btn_repeat.setToolTip("Repetir")
        self.btn_repeat.toggled.connect(lambda v: setattr(self, "repeat", v))
        self.btn_prev.clicked.connect(self.previous)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next.clicked.connect(self.next)

        controls.addStretch(1)
        controls.addWidget(self.btn_shuffle)
        controls.addWidget(self.btn_prev)
        controls.addWidget(self.btn_play)
        controls.addWidget(self.btn_next)
        controls.addWidget(self.btn_repeat)
        controls.addStretch(1)

        self.btn_queue = QPushButton("☰ Fila")
        self.btn_queue.setToolTip("Ver e editar a fila de reprodução")
        self.btn_queue.clicked.connect(self.show_queue_window)
        controls.addWidget(self.btn_queue)

        controls.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(150)
        self.volume.valueChanged.connect(self.on_volume)
        controls.addWidget(self.volume)
        bv.addLayout(controls)

        outer.addWidget(bottom)
        self.on_volume(70)

    def _build_shortcuts(self):
        """Atalhos de teclado. Dentro da caixa de busca, as letras e o espaço digitam normalmente."""
        shortcuts = {
            "Space": self.toggle_play,
            "Ctrl+Right": self.next,
            "Ctrl+Left": self.previous,
            "Ctrl+Up": lambda: self.volume.setValue(min(100, self.volume.value() + 5)),
            "Ctrl+Down": lambda: self.volume.setValue(max(0, self.volume.value() - 5)),
            "F": self.toggle_favorite_selected,
            "Ctrl+F": self._focus_search,
        }
        for keys, action in shortcuts.items():
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(action)

    def _focus_search(self):
        self.search.setFocus()
        self.search.selectAll()

    # ---------- Tema ----------

    def on_theme_toggled(self, dark):
        """Aplica o tema escuro ou claro na janela inteira."""
        self.dark = dark
        self._apply_theme()

    def _apply_theme(self):
        """Aplica o tema claro/escuro. Com 'Cor do álbum' ligada, usa a cor da capa como destaque."""
        palette = dict(PALETTE["dark" if self.dark else "light"])
        if self.album_color and self._cover_color:
            palette["accent"] = self._cover_color
        self.setStyleSheet(make_qss(palette))

    def on_album_color_toggled(self, checked):
        self.album_color = checked
        self._apply_theme()
        self._save_settings()

    # ---------- Configurações salvas ----------

    def _load_settings(self):
        """Restaura volume, tema, modo de exibição, pastas e a última música."""
        self._loading = True
        self.volume.setValue(int(self.settings.value("volume", 70)))
        self.btn_theme.setChecked(self.settings.value("dark", False, type=bool))
        self.btn_albums.setChecked(self.settings.value("albums_view", False, type=bool))
        self.btn_favs.setChecked(self.settings.value("favorites_only", False, type=bool))
        self.btn_left.setChecked(self.settings.value("left_compact", False, type=bool))
        self.btn_right.setChecked(self.settings.value("right_compact", False, type=bool))
        self.btn_album_color.setChecked(self.settings.value("album_color", False, type=bool))
        splitter_state = self.settings.value("splitter")
        if splitter_state:
            self.splitter.restoreState(splitter_state)
        self._apply_left_mode()
        self._apply_right_mode()
        self._update_handles()

        folders = self.settings.value("folders", [], type=list)
        for folder in folders:
            self._scan_folder(folder, save=False)
        saved_playlist = self.settings.value("current_playlist", "", type=str)
        self.refresh_playlist_list(saved_playlist or None)

        last = self.settings.value("last_track", "")
        if last in self.tracks:
            index = self.tracks.index(last)
            self.current_index = index
            self.show_track(index)
            self._select_index(index)
            self.player.setSource(QUrl.fromLocalFile(last))
        self._loading = False

    def _save_settings(self):
        """Grava as preferências e a música atual."""
        if self._loading:
            return  # ainda carregando: não sobrescreve as configurações salvas
        self.settings.setValue("volume", self.volume.value())
        self.settings.setValue("dark", self.dark)
        self.settings.setValue("albums_view", self.albums_view)
        self.settings.setValue("left_compact", self.btn_left.isChecked())
        self.settings.setValue("right_compact", self.btn_right.isChecked())
        self.settings.setValue("favorites_only", self.favorites_only)
        self.settings.setValue("favorites", sorted(self.favorites))
        self.settings.setValue("current_playlist", self.current_playlist or "")
        self.settings.setValue("album_color", self.album_color)
        self.settings.setValue("track_info", json.dumps(self.track_info, ensure_ascii=False))
        self.settings.setValue("track_covers", json.dumps(self.track_covers, ensure_ascii=False))
        folders = sorted({str(Path(t).parent) for t in self.tracks})
        self.settings.setValue("folders", folders)
        if 0 <= self.current_index < len(self.tracks):
            self.settings.setValue("last_track", self.tracks[self.current_index])

    def closeEvent(self, event):
        self._save_settings()
        self._save_history()
        self.settings.setValue("splitter", self.splitter.saveState())
        super().closeEvent(event)

    # ---------- Biblioteca de músicas ----------

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Escolha a pasta de músicas")
        if folder:
            self._scan_folder(folder)

    def _scan_folder(self, folder, save=True):
        """Adiciona as músicas da pasta e das subpastas à biblioteca."""
        base = Path(folder)
        if not base.is_dir():
            return
        added = False
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() not in AUDIO_EXTS or str(path) in self.tracks:
                continue
            self.tracks.append(str(path))
            meta = read_metadata(path)
            self._apply_track_cover(meta, str(path))
            self._apply_track_info(meta, str(path))
            self.meta.append(meta)
            self.items.append(None)
            added = True
        if added:
            self.rebuild_tree()
        if save:
            self._save_settings()

    def rebuild_tree(self):
        """Redesenha a lista conforme o modo escolhido (músicas ou álbuns) e o filtro de favoritos."""
        self.tree.clear()
        self.items = [None] * len(self.tracks)

        playlist_mode = self.current_playlist is not None
        if playlist_mode:
            visible = self.playlist_indexes()
        else:
            visible = [
                i for i in range(len(self.tracks))
                if not self.favorites_only or self.tracks[i] in self.favorites
            ]

        if playlist_mode or not self.albums_view:
            for i in visible:
                item = self._make_track_item(i)
                self.tree.addTopLevelItem(item)
                self.items[i] = item
                self._attach_track_buttons(item, i)
        else:
            # Agrupa as músicas por álbum e artista, na ordem em que aparecem
            groups, order = {}, []
            for i in visible:
                key = (self.meta[i]["album"] or "Sem álbum", self.meta[i]["artist"])
                if key not in groups:
                    groups[key] = []
                    order.append(key)
                groups[key].append(i)

            for key in order:
                album, artist = key
                indexes = groups[key]
                year = next((self.meta[i]["year"] for i in indexes if self.meta[i]["year"]), "")
                title = f"{album} ({year})" if year and album != "Sem álbum" else album

                header = QTreeWidgetItem([title, artist, "", f"{len(indexes)} músicas"])
                font = header.font(0)
                font.setBold(True)
                header.setFont(0, font)
                header.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
                cover = next((self.meta[i]["cover"] for i in indexes if self.meta[i]["cover"]), None)
                if cover:
                    header.setIcon(0, make_icon(cover))
                self.tree.addTopLevelItem(header)

                for i in indexes:
                    child = self._make_track_item(i)
                    header.addChild(child)
                    self.items[i] = child
                    self._attach_track_buttons(child, i)
                header.setExpanded(True)

        self.filter_list()
        self._update_stats()

    def _update_stats(self):
        """Mostra quantidade de músicas e duração total da playlist aberta."""
        if self.current_playlist is None:
            self.playlist_bar.setVisible(False)
            return
        indexes = [self.tracks.index(p) for p in self.playlists.get(self.current_playlist, [])
                   if p in self.tracks]
        total_seconds = int(sum(self.meta[i]["length"] for i in indexes))
        hours, rest = divmod(total_seconds, 3600)
        minutes = rest // 60
        duration = f"{hours} h {minutes} min" if hours else f"{minutes} min"
        songs = "música" if len(indexes) == 1 else "músicas"
        self.stats_label.setText(f"{len(indexes)} {songs}  ·  {duration}")
        self.playlist_bar.setVisible(True)

    def _make_track_item(self, index):
        """Cria a linha de uma música na lista."""
        meta = self.meta[index]
        duration = format_time(int(meta["length"] * 1000)) if meta["length"] else ""
        item = QTreeWidgetItem([self._track_title(index), meta["artist"], "", duration])
        item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
        item.setData(0, Qt.UserRole, index)
        return item

    def _track_title(self, index):
        """Título com a estrela na frente, se a música for favorita."""
        star = "★ " if self.tracks[index] in self.favorites else ""
        return star + self.meta[index]["title"]

    def _update_row(self, index):
        item = self.items[index]
        if item is not None:
            item.setText(0, self._track_title(index))

    def _select_index(self, index):
        """Seleciona a música na lista, se ela estiver visível."""
        item = self.items[index]
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    # ---------- Filtro de busca ----------

    @staticmethod
    def _row_text(item):
        return " ".join(item.text(c) for c in range(item.columnCount())).lower()

    def filter_list(self, text=None):
        """Esconde as músicas (e os álbuns sem músicas) que não combinam com a busca."""
        query = (self.search.text() if text is None else text).lower()
        for top in range(self.tree.topLevelItemCount()):
            top_item = self.tree.topLevelItem(top)
            if top_item.data(0, Qt.UserRole) is not None:
                # Modo de músicas: a linha é a própria música
                top_item.setHidden(query not in self._row_text(top_item))
                continue
            # Modo de álbuns: o álbum aparece se alguma música dele combinar
            any_visible = False
            for c in range(top_item.childCount()):
                child = top_item.child(c)
                hidden = query not in self._row_text(child)
                child.setHidden(hidden)
                any_visible = any_visible or not hidden
            top_item.setHidden(not any_visible)

    # ---------- Playlists ----------

    def _load_playlists(self):
        """Lê as playlists salvas. Cada playlist é uma lista de caminhos de arquivos."""
        raw = self.settings.value("playlists", "{}", type=str)
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def _load_dict(self, key):
        raw = self.settings.value(key, "{}", type=str)
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    def _save_playlists(self):
        self.settings.setValue("playlists", json.dumps(self.playlists, ensure_ascii=False))
        self.settings.setValue("playlist_covers", json.dumps(self.playlist_covers, ensure_ascii=False))

    def playlist_indexes(self):
        """Índices das músicas da playlist aberta, na ordem da playlist."""
        indexes = []
        for path in self.playlists.get(self.current_playlist, []):
            if path not in self.tracks:
                continue
            if self.favorites_only and path not in self.favorites:
                continue
            indexes.append(self.tracks.index(path))
        return indexes

    def play_order(self):
        """Ordem de reprodução: a da playlist aberta ou a das músicas visíveis na lista."""
        if self.current_playlist is not None:
            return [self.tracks.index(p) for p in self.playlists.get(self.current_playlist, [])
                    if p in self.tracks]
        return self._visible_order()

    def _build_shuffle_plan(self):
        """Sorteia a ordem das músicas que ainda não tocaram nesta rodada."""
        order = self.play_order()
        candidates = [i for i in order if i not in self.played_shuffle and i != self.current_index]
        random.shuffle(candidates)
        return candidates

    def upcoming(self):
        """Devolve (fila, próximas): as da fila e as que tocam em seguida."""
        queued = list(self.up_next)
        order = self.play_order()
        if self.shuffle:
            if not self.shuffle_plan:
                self.shuffle_plan = self._build_shuffle_plan()
            following = [i for i in self.shuffle_plan
                         if i in order and i not in self.played_shuffle and i != self.current_index]
        elif self.current_index in order:
            following = order[order.index(self.current_index) + 1:]
        else:
            following = order
        return queued, following[:100]

    def _visible_order(self):
        """Músicas que aparecem na lista agora, na ordem em que aparecem (respeita busca e favoritos)."""
        order = []
        for top in range(self.tree.topLevelItemCount()):
            top_item = self.tree.topLevelItem(top)
            if top_item.isHidden():
                continue
            if top_item.data(0, Qt.UserRole) is not None:
                order.append(top_item.data(0, Qt.UserRole))
            else:
                for c in range(top_item.childCount()):
                    child = top_item.child(c)
                    if not child.isHidden():
                        order.append(child.data(0, Qt.UserRole))
        return order

    def refresh_playlist_list(self, select=None):
        """Recarrega a lista de playlists e abre a indicada (ou a biblioteca)."""
        self.playlist_list.blockSignals(True)
        self.playlist_list.clear()
        # No modo compacto, a Biblioteca aparece só como 📚 (o nome completo fica na dica)
        library = QListWidgetItem("📚" if self._right_compact() else "Biblioteca")
        library.setData(Qt.UserRole, None)
        library.setToolTip("Biblioteca")
        if self._right_compact():
            small = library.font()
            small.setPointSize(11)
            library.setFont(small)
        self.playlist_list.addItem(library)
        for name in sorted(self.playlists):
            compact_with_cover = self._right_compact() and self._has_cover(name)
            item = QListWidgetItem("" if compact_with_cover else name)
            item.setData(Qt.UserRole, name)
            item.setIcon(self._playlist_icon(name))
            self.playlist_list.addItem(item)

        # Mesmo tamanho para todos os itens: no modo compacto, cada um ocupa uma célula igual
        hint = QSize(72, 72) if self._right_compact() else QSize()
        for row in range(self.playlist_list.count()):
            self.playlist_list.item(row).setSizeHint(hint)
        if select not in self.playlists:
            select = None
        for row in range(self.playlist_list.count()):
            if self.playlist_list.item(row).data(Qt.UserRole) == select:
                self.playlist_list.setCurrentRow(row)
                break
        self.playlist_list.blockSignals(False)
        self.select_playlist(select)

    def on_playlist_selected(self, current, previous):
        if current is not None:
            self.select_playlist(current.data(Qt.UserRole))

    def select_playlist(self, name):
        """Abre a playlist indicada (None = biblioteca) e redesenha a lista de músicas."""
        self.current_playlist = name
        self.rebuild_tree()
        self._select_index(self.current_index)
        self._save_settings()

    def create_playlist(self):
        """Pede um nome e cria uma playlist vazia. Devolve o nome criado ou None."""
        name, ok = QInputDialog.getText(self, "Nova playlist", "Nome da playlist:")
        name = name.strip() if ok else ""
        if not name or name in self.playlists:
            return None
        self.playlists[name] = []
        self._save_playlists()
        return name

    def on_new_playlist_clicked(self):
        name = self.create_playlist()
        if name:
            self.refresh_playlist_list(select=name)

    def new_playlist_and_add(self, index):
        """Cria uma playlist pelo menu do clique direito e já adiciona a música."""
        name = self.create_playlist()
        if name:
            self.add_to_playlist(name, index)
            self.refresh_playlist_list(select=self.current_playlist)

    def add_to_playlist(self, name, index):
        path = self.tracks[index]
        songs = self.playlists.setdefault(name, [])
        if path not in songs:
            songs.append(path)
        self._save_playlists()
        if self.current_playlist == name:
            self.rebuild_tree()
            self._select_index(self.current_index)

    def remove_from_playlist(self, index):
        if self.current_playlist is None:
            return
        path = self.tracks[index]
        songs = self.playlists.get(self.current_playlist, [])
        if path in songs:
            songs.remove(path)
        self._save_playlists()
        self.rebuild_tree()
        self._select_index(self.current_index)

    def delete_playlist(self, name):
        """Apaga a playlist indicada. As músicas continuam na biblioteca."""
        answer = QMessageBox.question(
            self, "Excluir playlist",
            f"Excluir a playlist '{name}'? As músicas continuam na biblioteca.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.playlists.pop(name, None)
        self.playlist_covers.pop(name, None)
        self._save_playlists()
        self.refresh_playlist_list()

    def on_playlist_menu(self, position):
        """Menu do clique direito em uma playlist."""
        item = self.playlist_list.itemAt(position)
        if item is None or item.data(Qt.UserRole) is None:
            return  # a Biblioteca não pode ser editada
        name = item.data(Qt.UserRole)
        menu = QMenu(self)
        pick = menu.addAction("Escolher imagem...")
        pick.triggered.connect(lambda checked=False, n=name: self.choose_playlist_image(n))
        if name in self.playlist_covers:
            remove = menu.addAction("Remover imagem")
            remove.triggered.connect(lambda checked=False, n=name: self.remove_playlist_image(n))
        rename = menu.addAction("Renomear playlist")
        rename.triggered.connect(lambda checked=False, n=name: self.rename_playlist(n))
        menu.addSeparator()
        delete = menu.addAction("Excluir playlist")
        delete.triggered.connect(lambda checked=False, n=name: self.delete_playlist(n))
        menu.exec(self.playlist_list.viewport().mapToGlobal(position))

    def choose_playlist_image(self, name):
        """Escolhe uma imagem do computador para ser a capa da playlist."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Escolha a imagem da playlist", "",
            "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self.playlist_covers[name] = path
            self._save_playlists()
            self.refresh_playlist_list(select=self.current_playlist)

    def remove_playlist_image(self, name):
        self.playlist_covers.pop(name, None)
        self._save_playlists()
        self.refresh_playlist_list(select=self.current_playlist)

    def _has_cover(self, name):
        path = self.playlist_covers.get(name)
        return bool(path and Path(path).exists())

    def _playlist_icon(self, name):
        """Imagem da playlist, ou um ícone vazio se ela não tiver imagem."""
        path = self.playlist_covers.get(name)
        if path and Path(path).exists():
            return QIcon(path)
        return QIcon()

    def rename_playlist(self, old_name):
        """Pede um novo nome e troca o nome da playlist, mantendo músicas e imagem."""
        new_name, ok = QInputDialog.getText(
            self, "Renomear playlist", "Novo nome:", text=old_name
        )
        new_name = new_name.strip() if ok else ""
        if not new_name or new_name == old_name or new_name in self.playlists:
            return
        self.playlists[new_name] = self.playlists.pop(old_name)
        if old_name in self.playlist_covers:
            self.playlist_covers[new_name] = self.playlist_covers.pop(old_name)
        if self.current_playlist == old_name:
            self.current_playlist = new_name
        self._save_playlists()
        self.refresh_playlist_list(select=self.current_playlist)

    def on_tree_menu(self, position):
        """Menu do clique direito em uma música."""
        item = self.tree.itemAt(position)
        if item is None:
            return
        index = item.data(0, Qt.UserRole)
        if index is None:  # cabeçalho de álbum
            return

        menu = QMenu(self)
        next_action = menu.addAction("Tocar a seguir")
        next_action.triggered.connect(lambda checked=False, i=index: self.play_next_add(i))
        queue_action = menu.addAction("Adicionar à fila")
        queue_action.triggered.connect(lambda checked=False, i=index: self.add_to_queue(i))
        menu.addSeparator()
        submenu = menu.addMenu("Adicionar à playlist")
        for name in sorted(self.playlists):
            action = submenu.addAction(name)
            action.triggered.connect(lambda checked=False, n=name, i=index: self.add_to_playlist(n, i))
        submenu.addSeparator()
        new_action = submenu.addAction("Nova playlist...")
        new_action.triggered.connect(lambda checked=False, i=index: self.new_playlist_and_add(i))

        if self.current_playlist is not None:
            menu.addSeparator()
            remove_action = menu.addAction("Remover desta playlist")
            remove_action.triggered.connect(lambda checked=False, i=index: self.remove_from_playlist(i))

        menu.exec(self.tree.viewport().mapToGlobal(position))

    # ---------- Histórico e estatísticas ----------

    def _load_history(self):
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _record_play(self, index):
        """Guarda no histórico que uma música começou a tocar, com data e hora."""
        meta = self.meta[index]
        self._save_history()  # guarda a reprodução anterior com o tempo ouvido
        self._last_pos = None
        self._listen_acc = 0.0
        self.history.append({
            "path": self.tracks[index],
            "title": meta["title"],
            "artist": meta["artist"],
            "album": meta["album"],
            "length": round(meta["length"], 1),
            "listened": 0.0,  # tempo realmente ouvido, atualizado enquanto a música toca
            "time": datetime.now().isoformat(timespec="seconds"),
        })

    def _update_listened(self):
        """Atualiza o tempo ouvido da reprodução atual e grava de tempos em tempos."""
        if self.history:
            self.history[-1]["listened"] = round(self._listen_acc, 1)
        if time.monotonic() - self._last_save > 10:
            self._save_history()

    def _save_history(self):
        if not self.history:
            return
        self._last_save = time.monotonic()
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(json.dumps(self.history, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def open_stats(self):
        """Mostra as estatísticas no lugar da lista de músicas (esquerda e direita continuam)."""
        if getattr(self, "_stats_page", None) is not None:
            self.close_stats()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        top = QHBoxLayout()
        back = QPushButton("← Voltar")
        back.setToolTip("Voltar para as músicas")
        back.clicked.connect(self.close_stats)
        top.addWidget(back)
        top.addStretch(1)
        layout.addLayout(top)
        layout.addWidget(StatsWindow(self.history, on_summary=self.open_year_summary), 1)
        self._stats_page = page
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def open_year_summary(self, lines):
        """Mostra o resumo do ano em uma página cheia, própria para print."""
        self.close_stats()
        if getattr(self, "_summary_page", None) is not None:
            self._back_from_summary()
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(10, 10, 10, 10)
        top = QHBoxLayout()
        back = QPushButton("← Voltar")
        back.setToolTip("Voltar para as estatísticas")
        back.clicked.connect(self._back_from_summary)
        top.addWidget(back)
        top.addStretch(1)
        outer.addLayout(top)

        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(48, 48, 48, 48)
        panel_layout.setSpacing(20)
        for position, line in enumerate(lines):
            label = QLabel(line)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("font-size: 32px; font-weight: bold;" if position == 0 else "font-size: 19px;")
            panel_layout.addWidget(label)
        panel_layout.addStretch(1)
        outer.addWidget(panel, 1)

        self._summary_page = page
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def _back_from_summary(self):
        """Volta das páginas do resumo para as estatísticas."""
        page = getattr(self, "_summary_page", None)
        if page is not None:
            self.stack.setCurrentIndex(0)
            self.stack.removeWidget(page)
            page.deleteLater()
            self._summary_page = None
        self.open_stats()

    def close_stats(self):
        """Volta para a lista de músicas."""
        page = getattr(self, "_stats_page", None)
        if page is None:
            return
        self.stack.setCurrentIndex(0)
        self.stack.removeWidget(page)
        page.deleteLater()
        self._stats_page = None

    # ---------- Fila de reprodução ----------

    def add_to_queue(self, index):
        self.up_next.append(index)
        self._update_queue_button()

    def play_next_add(self, index):
        """Coloca a música para tocar logo depois da atual."""
        self.up_next.insert(0, index)
        self._update_queue_button()

    def remove_from_queue(self, position):
        if 0 <= position < len(self.up_next):
            del self.up_next[position]
        self._update_queue_button()

    def clear_queue(self):
        self.up_next = []
        self._update_queue_button()

    def _update_queue_button(self):
        count = len(self.up_next)
        self.btn_queue.setText(f"☰ Fila ({count})" if count else "☰ Fila")
        self._refresh_queue_window()

    def show_queue_window(self):
        """Abre o pop up da fila logo acima do botão ☰ Fila."""
        if getattr(self, "_queue_popup", None) is None:
            self._queue_popup = QueueWindow(self)
        popup = self._queue_popup
        origin = self.btn_queue.mapToGlobal(QPoint(0, 0))
        popup.move(origin.x() + self.btn_queue.width() - popup.width(),
                   origin.y() - popup.height() - 6)
        popup.show()
        popup.raise_()

    def _refresh_queue_window(self):
        window = getattr(self, "_queue_window", None)
        if window is not None and window.isVisible():
            window.refresh()

    # ---------- Botão + em cada música ----------

    def _attach_track_buttons(self, item, index):
        """Coloca a estrela (favorito) e os três pontinhos (mais opções) na coluna ao lado da duração."""
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        is_fav = self.tracks[index] in self.favorites
        star = QPushButton("★" if is_fav else "☆")
        star.setObjectName("star")
        star.setProperty("fav", "true" if is_fav else "false")
        star.setToolTip("Remover dos favoritos" if is_fav else "Marcar como favorito")
        star.setCursor(Qt.PointingHandCursor)
        star.clicked.connect(lambda checked=False, i=index: self.toggle_favorite(i))

        dots = QPushButton("⋮")
        dots.setObjectName("dots")
        dots.setToolTip("Mais opções")
        dots.setCursor(Qt.PointingHandCursor)
        dots.clicked.connect(lambda checked=False, i=index, b=dots: self.show_track_menu(i, b))

        row.addWidget(star)
        row.addWidget(dots)
        self.tree.setItemWidget(item, 2, container)

    def _apply_track_cover(self, meta, path):
        """Se o usuário escolheu uma capa para a música, ela substitui a capa do arquivo."""
        image = self.track_covers.get(path)
        if image and Path(image).exists():
            meta["cover"] = Path(image).read_bytes()

    def _apply_track_info(self, meta, path):
        """Aplica título, artista, álbum e ano editados pelo usuário."""
        info = self.track_info.get(path, {})
        for key in ("title", "artist", "album", "year"):
            if info.get(key):
                meta[key] = info[key]

    def edit_track_info(self, index):
        meta = self.meta[index]
        path = self.tracks[index]
        original = read_metadata(Path(path))
        dialog = TrackInfoDialog(meta, original, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.track_info[path] = dialog.values()
            self._apply_track_info(meta, path)
            self._after_info_change(index)

    def reset_track_info(self, index):
        """Volta título, artista, álbum e ano para os valores do arquivo."""
        path = self.tracks[index]
        self.track_info.pop(path, None)
        original = read_metadata(Path(path))
        for key in ("title", "artist", "album", "year"):
            self.meta[index][key] = original[key]
        self._after_info_change(index)

    def _after_info_change(self, index):
        self.settings.setValue("track_info", json.dumps(self.track_info, ensure_ascii=False))
        if index == self.current_index:
            self.show_track(index)
        self.rebuild_tree()
        self._select_index(self.current_index)

    def choose_track_cover(self, index):
        """Escolhe uma imagem do computador como capa desta música."""
        image, _ = QFileDialog.getOpenFileName(
            self, "Escolha a capa da música", "", "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not image:
            return
        path = self.tracks[index]
        self.track_covers[path] = image
        self._apply_track_cover(self.meta[index], path)
        self._after_cover_change(index)

    def remove_track_cover(self, index):
        """Remove a capa escolhida e volta para a capa que está no arquivo."""
        path = self.tracks[index]
        self.track_covers.pop(path, None)
        self.meta[index]["cover"] = read_metadata(Path(path))["cover"]
        self._after_cover_change(index)

    def _after_cover_change(self, index):
        self.settings.setValue("track_covers", json.dumps(self.track_covers, ensure_ascii=False))
        if index == self.current_index:
            self.show_track(index)
        self.rebuild_tree()
        self._select_index(self.current_index)

    def toggle_favorite(self, index):
        """Marca ou desmarca uma música como favorita e atualiza a lista."""
        path = self.tracks[index]
        if path in self.favorites:
            self.favorites.discard(path)
        else:
            self.favorites.add(path)
        self._save_settings()
        self.rebuild_tree()
        self._select_index(self.current_index)

    def show_track_menu(self, index, anchor):
        """Menu dos três pontinhos: tocar a seguir, fila, playlist e favorito."""
        menu = QMenu(self)
        next_action = menu.addAction("Tocar a seguir")
        next_action.triggered.connect(lambda checked=False, i=index: self.play_next_add(i))
        queue_action = menu.addAction("Adicionar à fila")
        queue_action.triggered.connect(lambda checked=False, i=index: self.add_to_queue(i))
        menu.addSeparator()

        submenu = menu.addMenu("Adicionar à playlist")
        for name in sorted(self.playlists):
            action = submenu.addAction(name)
            action.triggered.connect(lambda checked=False, n=name, i=index: self.add_to_playlist(n, i))
        if self.playlists:
            submenu.addSeparator()
        new_action = submenu.addAction("Nova playlist...")
        new_action.triggered.connect(lambda checked=False, i=index: self.new_playlist_and_add(i))

        menu.addSeparator()
        info_action = menu.addAction("Editar informações...")
        info_action.triggered.connect(lambda checked=False, i=index: self.edit_track_info(i))
        if self.tracks[index] in self.track_info:
            reset_info = menu.addAction("Restaurar informações originais")
            reset_info.triggered.connect(lambda checked=False, i=index: self.reset_track_info(i))
        cover_action = menu.addAction("Escolher capa...")
        cover_action.triggered.connect(lambda checked=False, i=index: self.choose_track_cover(i))
        if self.tracks[index] in self.track_covers:
            remove_cover = menu.addAction("Remover capa escolhida")
            remove_cover.triggered.connect(lambda checked=False, i=index: self.remove_track_cover(i))

        menu.exec(anchor.mapToGlobal(QPoint(0, anchor.height())))

    # ---------- Painéis laterais ----------

    def _make_panel_toggle(self, symbol, tooltip, slot):
        """Cria o botão do modo compacto de um painel (azul = compacto ligado)."""
        button = QPushButton(symbol)
        button.setObjectName("toggle")
        button.setCheckable(True)
        button.setChecked(False)
        button.setToolTip(tooltip)
        button.toggled.connect(slot)
        return button

    def on_left_toggled(self, visible):
        self._apply_left_mode(resize=True)
        self._save_settings()

    def on_right_toggled(self, visible):
        self._apply_right_mode(resize=True)
        self._update_handles()
        self.refresh_playlist_list(select=self.current_playlist)
        self._save_settings()

    def _left_compact(self):
        return self.btn_left.isChecked()

    def _right_compact(self):
        return self.btn_right.isChecked()

    def _apply_left_mode(self, resize=False):
        """Painel da esquerda: completo ou compacto (capa pequena e título)."""
        compact = self._left_compact()
        self.left_panel.setMinimumWidth(120 if compact else 200)
        self.lbl_artist.setVisible(not compact)
        self.lbl_album.setVisible(not compact)
        self.lbl_title.setAlignment(Qt.AlignCenter if compact else Qt.AlignLeft)
        if resize:
            sizes = self.splitter.sizes()
            sizes[0] = 120 if compact else 300
            self.splitter.setSizes(sizes)
        self._update_cover_size()

    def _apply_right_mode(self, resize=False):
        """Coluna de playlists: completa ou compacta (só capas, ou o nome quando não há capa)."""
        compact = self._right_compact()
        self.sidebar.setMinimumWidth(84 if compact else 200)
        self.lbl_playlists.setVisible(not compact)
        self.btn_new_playlist.setText("+" if compact else "+ Criar playlist")
        self.btn_new_playlist.setToolTip("Criar playlist")
        self.playlist_list.setIconSize(QSize(44, 44) if compact else QSize(40, 40))
        if compact:
            # Grade: a capa (ou o 📚) fica no centro e o nome embaixo, centralizados
            self.playlist_list.setViewMode(QListView.IconMode)
            self.playlist_list.setGridSize(QSize(72, 72))
            self.playlist_list.setSpacing(4)
        else:
            self.playlist_list.setViewMode(QListView.ListMode)
            self.playlist_list.setGridSize(QSize())
            self.playlist_list.setSpacing(0)
        # No modo compacto não aparece barra de rolagem: o conteúdo cabe na coluna
        self.playlist_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if compact else Qt.ScrollBarAsNeeded
        )
        margin = 6 if compact else 14
        self.sidebar.layout().setContentsMargins(margin, 14, margin, 14)
        if resize:
            sizes = self.splitter.sizes()
            sizes[2] = 84 if compact else 300
            self.splitter.setSizes(sizes)

    # ---------- Modos de exibição e favoritos ----------

    def on_view_toggled(self, checked):
        self.albums_view = checked
        self.rebuild_tree()
        self._select_index(self.current_index)
        self._save_settings()

    def on_favs_toggled(self, checked):
        self.favorites_only = checked
        self.rebuild_tree()
        self._select_index(self.current_index)
        self._save_settings()

    def selected_index(self):
        """Índice da música selecionada na lista (ou a que está tocando, se nada estiver selecionado)."""
        item = self.tree.currentItem()
        if item is not None and item.data(0, Qt.UserRole) is not None:
            return item.data(0, Qt.UserRole)
        return self.current_index

    def toggle_favorite_selected(self):
        """Marca ou desmarca como favorita a música selecionada (tecla F)."""
        index = self.selected_index()
        if 0 <= index < len(self.tracks):
            self.toggle_favorite(index)

    # ---------- Informações e capa da música atual ----------

    def show_track(self, index):
        """Mostra capa, título, artista e álbum da música."""
        meta = self.meta[index]
        self.lbl_title.setText(meta["title"])
        self.lbl_artist.setText(meta["artist"])
        album = meta["album"]
        if meta["year"]:
            album = f"{album} ({meta['year']})" if album else meta["year"]
        self.lbl_album.setText(album)
        self.set_cover(meta["cover"])

    def _update_handles(self):
        """Desativa o arrasto da borda do lado que está compacto."""
        self.splitter.handle(1).setEnabled(not self._left_compact())
        self.splitter.handle(2).setEnabled(not self._right_compact())

    def _update_cover_size(self):
        """Ajusta o tamanho da capa conforme a largura do painel da esquerda."""
        if self._left_compact():
            side = 96
        else:
            side = max(100, min(260, self.left_panel.width() - 40))
        self.cover.setFixedSize(side, side)
        self._render_cover()
        self._update_handles()

    def set_cover(self, data):
        """Guarda a capa da música atual e a mostra. Sem capa, mostra um ♪ em um quadrado branco."""
        self._cover_data = data
        self._render_cover()
        self._cover_color = None
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            pixel = pixmap.toImage().scaled(1, 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).pixelColor(0, 0)
            if pixel.lightness() < 90:  # cores muito escuras ficam ilegíveis no destaque
                pixel = pixel.lighter(140)
            self._cover_color = pixel.name()
        self._apply_theme()

    def _render_cover(self):
        data = getattr(self, "_cover_data", None)
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            self.cover.setText("")
            side = self.cover.width()
            self.cover.setPixmap(pixmap.scaled(side, side, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.cover.setPixmap(QPixmap())
            self.cover.setText("♪")

    # ---------- Reprodução ----------

    def play_index(self, index, keep_plan=False):
        """Toca a música de uma posição da biblioteca."""
        if not (0 <= index < len(self.tracks)):
            return
        if not keep_plan:
            # Troca manual (clique, fila, lista): a ordem aleatória será sorteada de novo
            self.shuffle_plan = []
        self.current_index = index
        self.round_over = False
        self.played_shuffle.add(index)
        self.player.setSource(QUrl.fromLocalFile(self.tracks[index]))
        self.player.play()
        self.show_track(index)
        self._record_play(index)
        self._refresh_queue_window()
        self._select_index(index)
        self._save_settings()

    def on_double_click(self, item, column):
        """Duplo clique em uma música toca ela. Em um álbum, toca a primeira música."""
        index = item.data(0, Qt.UserRole)
        if index is None and item.childCount():
            index = item.child(0).data(0, Qt.UserRole)
        if index is not None:
            self.play_index(index)

    def toggle_play(self):
        """Tocar ou pausar. Se a rodada aleatória acabou, começa uma nova."""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.shuffle and self.round_over:
            self.next()
        elif self.player.source().isEmpty():
            if self.tracks:
                self.play_index(0)
        else:
            self.player.play()

    def next(self):
        """Vai para a próxima música: primeiro a fila, depois a ordem da lista aberta."""
        if self.up_next:
            self.play_index(self.up_next.pop(0))
            self._update_queue_button()
            return
        order = self.play_order()
        if not order:
            return
        if self.shuffle:
            # Usa a ordem sorteada; quando ela acaba, sorteia uma nova rodada
            # A cada troca de música, sorteia uma nova ordem das próximas
            self.shuffle_plan = self._build_shuffle_plan()
            if not self.shuffle_plan:
                if not self.repeat:
                    # A rodada acabou: para e prepara uma nova para a próxima vez
                    self.player.stop()
                    self.played_shuffle = set()
                    self.shuffle_plan = []
                    self.round_over = True
                    return
                self.played_shuffle.clear()
                self.shuffle_plan = self._build_shuffle_plan() or list(order)
            index = self.shuffle_plan.pop(0)
        else:
            position = order.index(self.current_index) + 1 if self.current_index in order else 0
            if position >= len(order):
                if not self.repeat:
                    self.player.stop()
                    return
                position = 0
            index = order[position]
        self.play_index(index, keep_plan=self.shuffle)

    def previous(self):
        """Se a música passou de 3 segundos, volta ao início. Senão, vai para a anterior."""
        order = self.play_order()
        if not order:
            return
        if self.player.position() > 3000:
            self.player.setPosition(0)
            return
        position = order.index(self.current_index) - 1 if self.current_index in order else -1
        if position < 0:
            position = len(order) - 1 if self.repeat else 0
        self.play_index(order[position])

    def on_shuffle_toggled(self, checked):
        self.shuffle = checked
        self.shuffle_plan = []
        self.played_shuffle = {self.current_index} if self.current_index >= 0 else set()

    def on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.next()

    def on_state_changed(self, state):
        """Troca o ícone do botão e a cor dele quando a música toca ou pausa."""
        playing = state == QMediaPlayer.PlayingState
        if not playing:
            self._save_history()
        self.btn_play.setText("⏸" if playing else "▶")
        self.btn_play.setProperty("playing", "true" if playing else "false")
        self.btn_play.style().unpolish(self.btn_play)
        self.btn_play.style().polish(self.btn_play)

    def on_position_changed(self, position):
        if self.player.playbackState() == QMediaPlayer.PlayingState and self._last_pos is not None:
            delta = position - self._last_pos
            if 0 < delta <= 1500:  # só avanço normal; pulos na barra não contam
                self._listen_acc += delta / 1000
                self._update_listened()
        self._last_pos = position
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        self.lbl_pos.setText(format_time(position))

    def on_duration_changed(self, duration):
        self.seek.setRange(0, duration)
        self.lbl_dur.setText(format_time(duration))

    def on_volume(self, value):
        self.audio_output.setVolume(value / 100)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = Player()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()