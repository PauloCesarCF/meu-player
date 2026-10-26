"""Módulo stats do Meu Player."""
from meu_player.constants import MIN_LISTEN_SECONDS
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

from meu_player.constants import MONTHS
from meu_player.metadata import format_time


def compute_streaks(history):
    """Devolve (sequência atual, maior sequência) em dias seguidos com música tocada."""
    days = sorted({date.fromisoformat(e["time"][:10]) for e in history
                   if e.get("time") and float(e.get("listened", 0) or 0) >= MIN_LISTEN_SECONDS})
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

    def __init__(self, history, on_summary=None, library_albums=None, playlists=None):
        super().__init__()
        self.history = history
        self.library_albums = library_albums or set()  # álbuns cadastrados na biblioteca
        self.playlists = playlists or {}              # nome da playlist -> caminhos das músicas
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

        self.album_note = QLabel("")
        self.album_note.setWordWrap(True)
        self.artist_note = QLabel("")
        self.artist_note.setWordWrap(True)
        self.tabs.addTab(self._page(self.album_note, self.album_tree), "Álbuns")
        self.tabs.addTab(self._page(self.artist_note, self.artist_tree), "Artistas")

        self.playlist_note = QLabel("")
        self.playlist_note.setWordWrap(True)
        self.playlist_tree = QTreeWidget()
        self.playlist_tree.setHeaderLabels(["#", "Playlist", "Músicas", "Reproduções", "Tempo"])
        self.playlist_tree.setRootIsDecorated(False)
        self.playlist_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.playlist_tree.header().setStretchLastSection(False)
        self.playlist_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.playlist_tree.setColumnWidth(0, 50)
        self.tabs.addTab(self._page(self.playlist_note, self.playlist_tree), "Playlists")

        layout.addWidget(self.tabs, 1)

        self._fill_years()

    @staticmethod
    def _page(note, tree):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(note)
        layout.addWidget(tree, 1)
        return page

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
        entries = [e for e in self.history
                   if e["time"].startswith(str(year))
                   and float(e.get("listened", 0) or 0) >= MIN_LISTEN_SECONDS]

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
        missing_artist = False
        for e in entries:
            length = float(e.get("listened", 0) or 0)
            album = (e.get("album") or "").strip()
            artist = (e.get("artist") or "").strip()
            if not artist:
                missing_artist = True
            if album:
                a = albums.setdefault((album, artist or "—"), {"count": 0, "seconds": 0.0})
                a["count"] += 1
                a["seconds"] += length
            if artist:
                r = artists.setdefault(artist, {"count": 0, "seconds": 0.0})
                r["count"] += 1
                r["seconds"] += length

        album_rank = sorted(albums.items(), key=lambda kv: (-kv[1]["count"], kv[0][0].lower()))
        artist_rank = sorted(artists.items(), key=lambda kv: (-kv[1]["count"], kv[0].lower()))

        # Aba Álbuns
        self.album_tree.clear()
        for position, ((album, artist), d) in enumerate(album_rank, start=1):
            item = QTreeWidgetItem([str(position), album, artist, str(d["count"]),
                                    format_time(int(d["seconds"] * 1000))])
            item.setTextAlignment(0, Qt.AlignCenter)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
            self.album_tree.addTopLevelItem(item)
        if album_rank:
            self.album_note.setVisible(False)
        elif self.library_albums:
            self.album_note.setText(f"Nenhum álbum foi escutado em {year}.")
            self.album_note.setVisible(True)
        else:
            self.album_note.setText(
                "Você ainda não tem álbuns. Para criar um, clique nos três pontinhos (⋮) de uma música, "
                "escolha Editar informações e preencha o campo Álbum."
            )
            self.album_note.setVisible(True)

        # Aba Artistas
        self.artist_tree.clear()
        for position, (artist, d) in enumerate(artist_rank, start=1):
            item = QTreeWidgetItem([str(position), artist, str(d["count"]),
                                    format_time(int(d["seconds"] * 1000))])
            item.setTextAlignment(0, Qt.AlignCenter)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            self.artist_tree.addTopLevelItem(item)
        if missing_artist:
            self.artist_note.setText(
                "Algumas músicas estão sem o nome do artista. Para corrigir, clique nos três pontinhos (⋮) "
                "da música, escolha Editar informações e preencha o campo Artista."
            )
            self.artist_note.setVisible(True)
        elif not artist_rank:
            self.artist_note.setText(f"Nenhum artista foi escutado em {year}.")
            self.artist_note.setVisible(True)
        else:
            self.artist_note.setVisible(False)

        # Aba Playlists: reproduções das músicas de cada playlist no ano
        self.playlist_tree.clear()
        playlist_rows = []
        for name, paths in self.playlists.items():
            wanted = set(paths)
            plays = [e for e in entries if e["path"] in wanted]
            if not plays:
                continue
            seconds = sum(float(e.get("listened", 0) or 0) for e in plays)
            playlist_rows.append((name, len(paths), len(plays), seconds))
        playlist_rows.sort(key=lambda row: (-row[2], row[0].lower()))
        for position, (name, songs, count, seconds) in enumerate(playlist_rows, start=1):
            item = QTreeWidgetItem([str(position), name, str(songs), str(count),
                                    format_time(int(seconds * 1000))])
            item.setTextAlignment(0, Qt.AlignCenter)
            item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(3, Qt.AlignRight | Qt.AlignVCenter)
            item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
            self.playlist_tree.addTopLevelItem(item)
        if playlist_rows:
            self.playlist_note.setVisible(False)
        elif self.playlists:
            self.playlist_note.setText(f"Nenhuma playlist foi escutada em {year}.")
            self.playlist_note.setVisible(True)
        else:
            self.playlist_note.setText(
                "Você ainda não tem playlists. Crie uma pelo botão + Criar playlist na coluna da direita."
            )
            self.playlist_note.setVisible(True)

        self._update_card(year, entries, ranking, album_rank, artist_rank, months)
        if album_rank:
            (album, artist), d = album_rank[0]
            self.summary.setText(self.summary.text() + f"\nÁlbum do ano: {album} ({d['count']} reproduções)")