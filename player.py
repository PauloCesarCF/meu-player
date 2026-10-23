import sys
import os
import random
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QSettings, QTimer
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QPushButton, QSlider, QVBoxLayout, QWidget,
)
from mutagen import File as MutagenFile

AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".ogg", ".aac", ".wma", ".opus"}


def read_metadata(path: Path):
    """Retorna (titulo, artista, duracao_em_segundos) lendo as tags do arquivo."""
    title, artist, length = path.stem, "", 0.0
    try:
        audio = MutagenFile(path)
        if audio is not None:
            if audio.info is not None:
                length = float(getattr(audio.info, "length", 0.0) or 0.0)
            tags = audio.tags or {}
            # Formatos diferentes guardam tags com nomes diferentes
            for key in ("title", "TIT2", "\xa9nam"):
                if key in tags:
                    value = tags[key]
                    title = str(value[0] if isinstance(value, list) else getattr(value, "text", [value])[0])
                    break
            for key in ("artist", "TPE1", "\xa9ART"):
                if key in tags:
                    value = tags[key]
                    artist = str(value[0] if isinstance(value, list) else getattr(value, "text", [value])[0])
                    break
    except Exception:
        pass
    return title, artist, length


def format_time(ms: int) -> str:
    seconds = max(0, ms // 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class Player(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meu Player")
        self.resize(900, 600)

        self.settings = QSettings("MeuPlayer", "MeuPlayer")
        self.tracks = []          # lista de caminhos
        self.current_index = -1
        self.shuffle = False
        self.repeat = False
        self.played_shuffle = set()  # índices já tocados no modo aleatório
        self.round_over = False      # True quando a rodada aleatória terminou

        # Audio
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.on_position_changed)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.playbackStateChanged.connect(self.on_state_changed)
        self.player.mediaStatusChanged.connect(self.on_media_status)

        self._build_ui()
        self._load_settings()

    # ---------- Interface ----------
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        self.btn_folder = QPushButton("Adicionar pasta")
        self.btn_folder.clicked.connect(self.choose_folder)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por título ou artista...")
        self.search.textChanged.connect(self.filter_list)
        top.addWidget(self.btn_folder)
        top.addWidget(self.search, 1)
        root.addLayout(top)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self.on_double_click)
        root.addWidget(self.list, 1)

        self.now_label = QLabel("Nenhuma música tocando")
        self.now_label.setAlignment(Qt.AlignCenter)
        self.now_label.setStyleSheet("font-size: 16px; font-weight: bold; padding: 6px;")
        root.addWidget(self.now_label)

        progress = QHBoxLayout()
        self.lbl_pos = QLabel("0:00")
        self.lbl_dur = QLabel("0:00")
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player.setPosition)
        progress.addWidget(self.lbl_pos)
        progress.addWidget(self.seek, 1)
        progress.addWidget(self.lbl_dur)
        root.addLayout(progress)

        controls = QHBoxLayout()
        self.btn_prev = QPushButton("⏮")
        self.btn_play = QPushButton("▶")
        self.btn_next = QPushButton("⏭")
        self.btn_shuffle = QPushButton("Aleatório")
        self.btn_shuffle.setCheckable(True)
        self.btn_shuffle.toggled.connect(self.on_shuffle_toggled)
        self.btn_repeat = QPushButton("Repetir")
        self.btn_repeat.setCheckable(True)
        self.btn_repeat.toggled.connect(lambda v: setattr(self, "repeat", v))
        for b in (self.btn_prev, self.btn_play, self.btn_next):
            b.setMinimumHeight(40)
            b.setMinimumWidth(60)
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

        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(150)
        self.volume.valueChanged.connect(self.on_volume)
        controls.addWidget(QLabel("Volume"))
        controls.addWidget(self.volume)
        root.addLayout(controls)

        self.setCentralWidget(central)
        self.on_volume(70)

    # ---------- Configurações ----------
    def _load_settings(self):
        volume = int(self.settings.value("volume", 70))
        self.volume.setValue(volume)
        folders = self.settings.value("folders", [], type=list)
        for folder in folders:
            self._scan_folder(folder, save=False)
        last = self.settings.value("last_track", "")
        if last in self.tracks:
            self.current_index = self.tracks.index(last)
            self.now_label.setText(Path(last).stem)
            self.player.setSource(QUrl.fromLocalFile(last))

    def _save_settings(self):
        self.settings.setValue("volume", self.volume.value())
        folders = sorted({str(Path(t).parent) for t in self.tracks})
        self.settings.setValue("folders", folders)
        if 0 <= self.current_index < len(self.tracks):
            self.settings.setValue("last_track", self.tracks[self.current_index])

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    # ---------- Biblioteca ----------
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Escolha a pasta de músicas")
        if folder:
            self._scan_folder(folder)

    def _scan_folder(self, folder, save=True):
        base = Path(folder)
        if not base.is_dir():
            return
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() in AUDIO_EXTS and str(path) not in self.tracks:
                self.tracks.append(str(path))
                title, artist, length = read_metadata(path)
                text = f"{title}  —  {artist}" if artist else title
                if length:
                    text += f"    [{format_time(int(length * 1000))}]"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, str(path))
                self.list.addItem(item)
        if save:
            self._save_settings()

    def filter_list(self, text):
        text = text.lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(text not in item.text().lower())

    # ---------- Reprodução ----------
    def play_index(self, index):
        if not (0 <= index < len(self.tracks)):
            return
        self.current_index = index
        self.round_over = False
        self.played_shuffle.add(index)
        path = self.tracks[index]
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        title, artist, _ = read_metadata(Path(path))
        self.now_label.setText(f"{title}  —  {artist}" if artist else title)
        self.list.setCurrentRow(index)
        self._save_settings()

    def on_shuffle_toggled(self, checked):
        self.shuffle = checked
        # Ao ligar o aleatório, a música atual conta como já tocada
        self.played_shuffle = {self.current_index} if self.current_index >= 0 else set()

    def on_double_click(self, item):
        self.play_index(self.list.row(item))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.shuffle and self.round_over:
            # A rodada aleatória já acabou: começa outra
            self.next()
        elif self.player.source().isEmpty():
            if self.tracks:
                self.play_index(0)
        else:
            self.player.play()

    def next(self):
        if not self.tracks:
            return
        if self.shuffle:
            remaining = [
                i for i in range(len(self.tracks))
                if i not in self.played_shuffle and i != self.current_index
            ]
            if not remaining:
                # Todas já tocaram
                if not self.repeat:
                    self.player.stop()
                    # Nova rodada começa limpa; a música atual só fica de fora
                    # da primeira escolha, para não repetir logo em seguida
                    self.played_shuffle = set()
                    self.round_over = True
                    return
                # Com repetir ligado, recomeça sem tocar a mesma música em seguida
                self.played_shuffle.clear()
                remaining = [i for i in range(len(self.tracks)) if i != self.current_index]
                if not remaining:  # só existe uma música na lista
                    remaining = list(range(len(self.tracks)))
            index = random.choice(remaining)
        else:
            index = self.current_index + 1
            if index >= len(self.tracks):
                if not self.repeat:
                    self.player.stop()
                    return
                index = 0
        self.play_index(index)

    def previous(self):
        if not self.tracks:
            return
        # Se passou de 3 segundos, volta ao início da faixa
        if self.player.position() > 3000:
            self.player.setPosition(0)
            return
        index = self.current_index - 1
        if index < 0:
            index = len(self.tracks) - 1 if self.repeat else 0
        self.play_index(index)

    def on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.next()

    def on_state_changed(self, state):
        self.btn_play.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def on_position_changed(self, position):
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