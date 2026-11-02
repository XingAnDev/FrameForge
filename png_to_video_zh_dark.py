#!/usr/bin/env python3

 # -*- coding: utf-8 -*-

"""

png_to_video.py  -  PNG sequence  ->  lossless video (for DaVinci Resolve)



GUI: PyQt5      Encoder: ffmpeg (default folder D:\\\ffmpeg\\\bin)



Run:

    pip install PyQt5

    python png_to_video.py



Highlights

  * Auto-detects the numbering pattern (0001.png / 00001.png / 1.png / shot_0100.png ...)

  * Choose input folder, frame range (all / start+count / start+end), fps, output file

  * 编码器s: QuickTime PNG (.mov, default) | FFV1 (.mkv) | ProRes 4444 (.mov)

  * Optional alpha, 16-bit PNG support, colour-tag options

  * Checks that every frame has the same resolution before encoding

  * Encodes to a temporary file and only renames it on success (no partial files left behind)

  * Validates the result with ffprobe (frames, resolution, codec, pix_fmt, alpha, fps)

  * Writes a log file (png_to_video.log) next to this script

"""

from __future__ import annotations



import json

import logging

import os

import re

import shutil

import struct

import sys

import time

from collections import deque

from dataclasses import dataclass

from datetime import datetime

from fractions import Fraction

from pathlib import Path

from subprocess import list2cmdline



from PyQt5.QtCore import QObject, QProcess, QSettings, Qt, QUrl, pyqtSignal

from PyQt5.QtGui import QDesktopServices, QFont, QPixmap, QTransform

from PyQt5.QtWidgets import (

    QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QGroupBox,

    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,

    QPushButton, QSpinBox, QVBoxLayout, QWidget,

)



import sys
import os
from PyQt5.QtGui import QIcon, QPixmap

def resource_path(relative_path):
    """ 兼容 PyInstaller 单文件打包的路径获取函数 """
    try:
        base_path = sys._MEIPASS  # 打包后的临时目录
    except AttributeError:
        base_path = os.path.abspath(".")  # 开发环境目录
    return os.path.join(base_path, relative_path)

 # --------------------------------------------------------------------------- #

 # Constants

 # --------------------------------------------------------------------------- #

DEFAULT_FFMPEG_DIR = r"D:\ffmpeg\bin"

EXE = ".exe" if os.name == "nt" else ""

LOG_NAME = "png_to_video.log"


DARK_QSS = """
QWidget { background: #101722; color: #E6EDF7; font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 10pt; }
QGroupBox { background: #151F2E; border: 1px solid #29394F; border-radius: 10px; margin-top: 14px; padding: 16px 12px 12px 12px; font-weight: 600; color: #F2F6FC; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #B8C9E2; }
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit { background: #0B111B; color: #E6EDF7; border: 1px solid #304056; border-radius: 6px; padding: 7px 9px; selection-background-color: #356AC3; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus { border: 1px solid #609BFF; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: #172337; color: #E6EDF7; selection-background-color: #294C7B; border: 1px solid #304056; }
QPushButton { background: #202D40; color: #EAF1FC; border: 1px solid #35465E; border-radius: 7px; padding: 8px 14px; }
QPushButton:hover { background: #2A3D57; border-color: #5476A5; }
QPushButton:pressed { background: #152237; }
QPushButton:disabled { color: #77869A; background: #182231; border-color: #273447; }
QPushButton#primaryButton { background: #285AA0; border: 1px solid #477AC8; font-weight: 600; }
QPushButton#primaryButton:hover { background: #346DB8; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QProgressBar { background: #0B111B; border: 1px solid #304056; border-radius: 6px; height: 14px; text-align: center; color: #F4F7FC; }
QProgressBar::chunk { background: #4C8DFA; border-radius: 5px; }
QScrollBar:vertical { background: #101722; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #35465E; min-height: 24px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #1A2638; color: #F4F7FC; border: 1px solid #405875; padding: 5px; }
QMessageBox { background: #151F2E; }
"""




PNG_SIG = b"\x89PNG\r\n\x1a\n"

FRAME_RE = re.compile(r"^(.*?)(\d+)(\.png)$", re.IGNORECASE)



FPS_PRESETS = ["23.976", "24", "25", "29.97", "30", "48", "50", "59.94", "60"]

NTSC_FRACTIONS = {"23.976": "24000/1001", "29.97": "30000/1001",

                  "47.952": "48000/1001", "59.94": "60000/1001"}



CODEC_ORDER = ["mov_png", "mkv_ffv1", "mov_prores"]

CODECS = {

    "mov_png": {

        "label": "QuickTime PNG（.mov）— 无损，推荐",

        "ext": ".mov", "probe_codec": "png",

        "note": ("Mathematically lossless (PNG compression inside a QuickTime container). "

                 "Supports alpha and 16-bit. Files are large, but Resolve normally imports it. "

                 "If your Resolve build refuses it, use ProRes 4444 or import the PNG "

                 "sequence directly."),

    },

    "mkv_ffv1": {

        "label": "FFV1（.mkv）— 无损，适合归档",

        "ext": ".mkv", "probe_codec": "ffv1",

        "note": ("Mathematically lossless and usually smaller than PNG-in-MOV. "

                 "DaVinci Resolve generally CANNOT import FFV1/MKV - use this for archiving "

                 "or re-encode it before editing."),

    },

    "mov_prores": {

        "label": "ProRes 4444（.mov）— 高画质，支持透明通道",

        "ext": ".mov", "probe_codec": "prores",

        "note": ("NOT mathematically lossless (10-bit 4:4:4 with very high quality). "

                 "Supports alpha and is the safest choice for Resolve compatibility."),

    },

}



 # colour tag -> (primaries, transfer)

COLOR_TAGS = {

    "srgb": ("bt709", "iec61966-2-1"),

    "rec709": ("bt709", "bt709"),

    "none": None,

}



log = logging.getLogger("png2video")





class UserError(Exception):

    """An error whose message is meant to be shown to the user."""





 # --------------------------------------------------------------------------- #

 # Logging

 # --------------------------------------------------------------------------- #

class LogBridge(QObject):

    message = pyqtSignal(str)





class QtLogHandler(logging.Handler):

    def __init__(self, bridge: LogBridge):

        super().__init__()

        self.bridge = bridge



    def emit(self, record):

        try:

            self.bridge.message.emit(self.format(record))

        except Exception:  # never let logging break the app

            pass





def app_dir() -> Path:

    if getattr(sys, "frozen", False):

        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent





def setup_logging(bridge: LogBridge) -> Path | None:

    if log.handlers:

        return None

    log.setLevel(logging.DEBUG)

    file_fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")

    gui_fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")

    log_path = None

    for folder in (app_dir(), Path.home()):

        try:

            fh = logging.FileHandler(folder / LOG_NAME, encoding="utf-8")

        except OSError:

            continue

        fh.setFormatter(file_fmt)

        log.addHandler(fh)

        log_path = folder / LOG_NAME

        break

    qh = QtLogHandler(bridge)

    qh.setFormatter(gui_fmt)

    log.addHandler(qh)

    return log_path





 # --------------------------------------------------------------------------- #

 # Helpers: ffmpeg, fps, formatting

 # --------------------------------------------------------------------------- #

def tools_in(folder: str):

    """Return (ffmpeg, ffprobe_or_None) if ffmpeg exists in folder, else None."""

    if not folder:

        return None

    d = Path(folder)

    ff, fp = d / f"ffmpeg{EXE}", d / f"ffprobe{EXE}"

    if not ff.is_file():

        return None

    return str(ff), (str(fp) if fp.is_file() else None)





def parse_fps(text: str):

    """Return (ffmpeg_arg, float_value). Accepts '24', '23.976', '24000/1001'."""

    t = text.strip().lower().replace("fps", "").strip()

    if not t:

        raise UserError("请输入帧率。")

    t = NTSC_FRACTIONS.get(t, t)

    try:

        value = float(Fraction(t))

    except (ValueError, ZeroDivisionError):

        raise UserError(f"'{text}' is not a valid frame rate (examples: 24, 23.976, 30000/1001).")

    if not (0 < value <= 1000):

        raise UserError("帧率必须大于 0 且不超过 1000。")

    return t, value





def has_alpha_fmt(pix_fmt: str) -> bool:

    p = (pix_fmt or "").lower()

    return p.startswith(("yuva", "gbrap", "ya", "ayuv", "pal8a")) or any(

        k in p for k in ("rgba", "bgra", "argb", "abgr"))





def fmt_bytes(n: float) -> str:

    for unit in ("B", "KB", "MB", "GB"):

        if n < 1024:

            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"

        n /= 1024

    return f"{n:.2f} TB"





def fmt_time(seconds: float) -> str:

    seconds = int(seconds)

    h, rem = divmod(seconds, 3600)

    m, s = divmod(rem, 60)

    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"





def force_ext(path: Path, ext: str) -> Path:

    suffix = path.suffix.lower()

    if suffix == ext:

        return path

    if suffix in (".mov", ".mkv", ".mp4", ".avi", ".mxf", ""):

        return path.with_suffix(ext)

    return path.with_name(path.name + ext)





 # --------------------------------------------------------------------------- #

 # PNG sequence detection and inspection

 # --------------------------------------------------------------------------- #

@dataclass

class Sequence:

    folder: Path

    prefix: str

    ext: str

    width: int          # zero-padding width; 0 = not padded (1.png, 2.png, ...)

    numbers: list       # sorted frame numbers found on disk



    @property

    def first(self) -> int:

        return self.numbers[0]



    @property

    def last(self) -> int:

        return self.numbers[-1]



    def name(self, n: int) -> str:

        num = f"{n:0{self.width}d}" if self.width else str(n)

        return f"{self.prefix}{num}{self.ext}"



    def path(self, n: int) -> Path:

        return self.folder / self.name(n)



    def pattern_label(self) -> str:

        fmt = f"%0{self.width}d" if self.width else "%d"

        return f"{self.prefix}{fmt}{self.ext}"



    def ffmpeg_pattern(self) -> str:

        """Absolute image2 pattern; literal '%' characters are escaped as '%%'."""

        esc = lambda s: s.replace("%", "%%")

        fmt = f"%0{self.width}d" if self.width else "%d"

        return esc(str(self.folder)) + os.sep + esc(self.prefix) + fmt + esc(self.ext)



    def missing(self, start: int, end: int, limit: int = 10) -> list:

        have = set(self.numbers)

        out = []

        for n in range(start, end + 1):

            if n not in have:

                out.append(n)

                if len(out) >= limit:

                    break

        return out





def scan_sequence(folder: Path):

    """Find the largest numbered PNG sequence in folder (or None)."""

    groups: dict = {}

    for entry in os.scandir(folder):

        if not entry.is_file():

            continue

        m = FRAME_RE.match(entry.name)

        if not m:

            continue

        prefix, digits, ext = m.groups()

        n = int(digits)

        padded = len(digits) > 1 and digits[0] == "0"

        groups.setdefault((prefix, ext, len(digits)), []).append(n)   # fixed-width candidate

        if not padded:

            groups.setdefault((prefix, ext, 0), []).append(n)         # un-padded candidate

    if not groups:

        return None

    (prefix, ext, width), numbers = max(

        groups.items(), key=lambda kv: (len(kv[1]), kv[0][2] > 0))

    others = {(p, e) for (p, e, _w) in groups} - {(prefix, ext)}

    if others:

        log.info("Other numbered PNG series found in the folder were ignored: %s",

                 ", ".join(sorted(f"{p}#{e}" for p, e in others)[:6]))

    return Sequence(folder, prefix, ext, width, sorted(set(numbers)))





@dataclass

class PngInfo:

    width: int

    height: int

    bit_depth: int

    color_type: int

    has_alpha: bool





def read_png_info(path: Path, probe_trns: bool = False) -> PngInfo:

    """Read the PNG header only (fast, no decoding)."""

    with open(path, "rb") as f:

        head = f.read(33)

        if len(head) < 33 or head[:8] != PNG_SIG or head[12:16] != b"IHDR":

            raise ValueError("not a valid PNG file")

        width, height = struct.unpack(">II", head[16:24])

        bit_depth, color_type = head[24], head[25]

        has_alpha = color_type in (4, 6)

        if probe_trns and not has_alpha:          # palette/gray/RGB with a tRNS chunk

            while True:

                hdr = f.read(8)

                if len(hdr) < 8:

                    break

                length, ctype = struct.unpack(">I4s", hdr)

                if ctype == b"tRNS":

                    has_alpha = True

                    break

                if ctype in (b"IDAT", b"IEND"):

                    break

                f.seek(length + 4, os.SEEK_CUR)

    return PngInfo(width, height, bit_depth, color_type, has_alpha)





def check_frames(seq: Sequence, start: int, count: int, on_progress):

    """Read every header in the range. Returns a dict with the findings."""

    ref = None

    mismatches, unreadable = [], []

    total_bytes = 0

    for i in range(count):

        p = seq.path(start + i)

        try:

            info = read_png_info(p)

            total_bytes += p.stat().st_size

        except (OSError, ValueError) as e:

            unreadable.append((p.name, str(e)))

            continue

        size = (info.width, info.height)

        if ref is None:

            ref = size

        elif size != ref:

            mismatches.append((p.name, size))

        if i % 100 == 0:

            on_progress(i + 1)

    return {"ref": ref, "mismatches": mismatches, "unreadable": unreadable,

            "bytes": total_bytes}





 # --------------------------------------------------------------------------- #

 # ffmpeg argument builder

 # --------------------------------------------------------------------------- #

def build_encode_args(codec: str, alpha: bool, bit16: bool, color: str):

    """Return (video_filter_or_None, output_args, pix_fmt)."""

    vf = None

    if codec == "mov_png":

        if alpha:

            pix = "rgba64be" if bit16 else "rgba"

        else:

            pix = "rgb48be" if bit16 else "rgb24"

        args = ["-c:v", "png"]

    elif codec == "mkv_ffv1":

        if alpha:

            pix = "gbrap16le" if bit16 else "bgra"

        else:

            pix = "gbrp16le" if bit16 else "bgr0"

        args = ["-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1",

                "-g", "1", "-slices", "4", "-slicecrc", "1"]

    elif codec == "mov_prores":

        pix = "yuva444p10le" if alpha else "yuv444p10le"

        args = ["-c:v", "prores_ks", "-profile:v", "4444", "-vendor", "apl0",

                "-bits_per_mb", "8000"]

        # RGB -> YUV must use the BT.709 matrix (ffmpeg's default would be BT.601)

        vf = "scale=out_color_matrix=bt709:out_range=tv"

    else:

        raise ValueError(codec)

    args += ["-pix_fmt", pix]

    tag = COLOR_TAGS.get(color)

    if tag:

        args += ["-color_primaries", tag[0], "-color_trc", tag[1]]

    if codec == "mov_prores":

        args += ["-colorspace", "bt709"]

    return vf, args, pix





 # --------------------------------------------------------------------------- #

 # Main window

 # --------------------------------------------------------------------------- #

class MainWindow(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("PNG 序列转无损视频")
        self.setWindowIcon(QIcon(resource_path("app.ico")))
        self.resize(1000, 780)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.top() + 10
        )
        logo_path = resource_path("XADLogo2.png") 
        pixmap = QPixmap(logo_path)
        self.settings = QSettings("Png2VideoTool", "Png2Video")



        self.tools = None            # (ffmpeg, ffprobe|None)

        self.seq: Sequence | None = None

        self.src: PngInfo | None = None

        self.proc: QProcess | None = None

        self.probe: QProcess | None = None

        self.job: dict = {}

        self.cancelled = False

        self._out_auto = True

        self._out_buf = ""

        self._err_buf = ""

        self._err_tail = deque(maxlen=40)

        self._prog: dict = {}



        self.bridge = LogBridge()

        self._build_ui()

        self.bridge.message.connect(self.log_view.appendPlainText)

        log_path = setup_logging(self.bridge)

        log.info("PNG sequence encoder started. Log file: %s", log_path or "(none)")

        self._load_settings()



    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        ########################

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        logo_label = QLabel()
        logo_label.setFixedWidth(340)
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("background: #0B111B; border-radius: 8px;")
        ###############################################################
        pixmap = QPixmap(resource_path("XADLogo2.png"))

        if not pixmap.isNull():
            pixmap = pixmap.transformed(
                QTransform().rotate(90),
                Qt.SmoothTransformation
            )
            logo_label.setPixmap(
                pixmap.scaled(
                    500, 1200,
                    Qt.IgnoreAspectRatio,
                    Qt.SmoothTransformation
                )
            )
        else:
            logo_label.setText("XAD")

        outer.addWidget(logo_label)

        panel = QWidget()
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        outer.addWidget(panel, 1)




        # 1. ffmpeg

        g = QGroupBox("01  ·  FFmpeg 工具")

        gl = QGridLayout(g)

        self.ed_ffmpeg = QLineEdit()

        b = QPushButton("浏览…")

        b.clicked.connect(self._browse_ffmpeg)

        self.lbl_ffmpeg = QLabel()

        gl.addWidget(self.ed_ffmpeg, 0, 0)

        gl.addWidget(b, 0, 1)

        gl.addWidget(self.lbl_ffmpeg, 1, 0, 1, 2)

        self.ed_ffmpeg.textChanged.connect(self._check_ffmpeg)

        root.addWidget(g)



        # 2. input

        g = QGroupBox("02  ·  PNG 序列来源")

        gl = QGridLayout(g)

        self.ed_in = QLineEdit()

        self.ed_in.editingFinished.connect(lambda: self.load_folder(self.ed_in.text()))

        b = QPushButton("浏览…")

        b.clicked.connect(self._browse_input)

        self.lbl_in = QLabel("尚未选择文件夹")

        self.lbl_in.setWordWrap(True)

        gl.addWidget(self.ed_in, 0, 0)

        gl.addWidget(b, 0, 1)

        gl.addWidget(self.lbl_in, 1, 0, 1, 2)

        root.addWidget(g)



        # 3. range

        g = QGroupBox("03  ·  帧范围")

        gl = QGridLayout(g)

        self.cb_mode = QComboBox()

        self.cb_mode.addItems(["全部帧", "起始帧 + 帧数",

                               "起始帧 + 结束帧"])

        self.sp_start, self.sp_count, self.sp_end = QSpinBox(), QSpinBox(), QSpinBox()

        for sp in (self.sp_start, self.sp_count, self.sp_end):

            sp.setRange(0, 999_999_999)

        gl.addWidget(QLabel("范围模式"), 0, 0)

        gl.addWidget(self.cb_mode, 0, 1, 1, 5)

        gl.addWidget(QLabel("起始帧"), 1, 0)

        gl.addWidget(self.sp_start, 1, 1)

        gl.addWidget(QLabel("帧数"), 1, 2)

        gl.addWidget(self.sp_count, 1, 3)

        gl.addWidget(QLabel("结束帧"), 1, 4)

        gl.addWidget(self.sp_end, 1, 5)

        self.lbl_range = QLabel()

        self.lbl_range.setWordWrap(True)

        gl.addWidget(self.lbl_range, 2, 0, 1, 6)

        self.cb_mode.currentIndexChanged.connect(lambda _: self._sync("mode"))

        self.sp_start.valueChanged.connect(lambda _: self._sync("start"))

        self.sp_count.valueChanged.connect(lambda _: self._sync("count"))

        self.sp_end.valueChanged.connect(lambda _: self._sync("end"))

        root.addWidget(g)



        # 4. output

        g = QGroupBox("04  ·  输出设置")

        gl = QGridLayout(g)

        self.cb_codec = QComboBox()

        for k in CODEC_ORDER:

            self.cb_codec.addItem(CODECS[k]["label"], k)

        self.lbl_codec = QLabel()

        self.lbl_codec.setWordWrap(True)

        self.cb_fps = QComboBox()

        self.cb_fps.setEditable(True)

        self.cb_fps.addItems(FPS_PRESETS)

        self.cb_fps.setCurrentText("24")

        self.chk_alpha = QCheckBox("保留透明通道（Alpha）")

        self.cb_depth = QComboBox()

        self.cb_depth.addItems(["位深度：跟随 PNG（自动）", "位深度：强制 8 位"])

        self.cb_color = QComboBox()

        self.cb_color.addItem("色彩标签：sRGB", "srgb")

        self.cb_color.addItem("色彩标签：Rec.709", "rec709")

        self.cb_color.addItem("色彩标签：不指定", "none")

        self.ed_out = QLineEdit()

        self.ed_out.textEdited.connect(self._on_out_edited)

        b = QPushButton("另存为…")

        b.clicked.connect(self._browse_output)



        gl.addWidget(QLabel("编码格式"), 0, 0)

        gl.addWidget(self.cb_codec, 0, 1, 1, 2)

        gl.addWidget(self.lbl_codec, 1, 1, 1, 2)

        gl.addWidget(QLabel("帧率 (FPS)"), 2, 0)

        gl.addWidget(self.cb_fps, 2, 1)

        gl.addWidget(self.chk_alpha, 3, 1)

        gl.addWidget(self.cb_depth, 3, 2)

        gl.addWidget(self.cb_color, 4, 1, 1, 2)

        gl.addWidget(QLabel("输出文件"), 5, 0)

        gl.addWidget(self.ed_out, 5, 1)

        gl.addWidget(b, 5, 2)

        gl.setColumnStretch(1, 1)

        self.cb_codec.currentIndexChanged.connect(self._on_codec_changed)

        self.cb_fps.editTextChanged.connect(lambda _: self._refresh_summary())

        root.addWidget(g)



        # run row

        row = QHBoxLayout()

        self.btn_start = QPushButton("开始转换")

        self.btn_start.setObjectName("primaryButton")
        self.btn_start.setMinimumHeight(38)

        self.btn_start.clicked.connect(self._on_start)

        self.btn_cancel = QPushButton("取消转换")

        self.btn_cancel.setMinimumHeight(34)

        self.btn_cancel.setEnabled(False)

        self.btn_cancel.clicked.connect(self._on_cancel)

        row.addWidget(self.btn_start, 3)

        row.addWidget(self.btn_cancel, 1)

        root.addLayout(row)



        self.bar = QProgressBar()

        self.bar.setRange(0, 1)

        self.lbl_status = QLabel("就绪")

        self.log_view = QPlainTextEdit()

        self.log_view.setReadOnly(True)

        mono = QFont("Consolas")

        mono.setStyleHint(QFont.Monospace)

        self.log_view.setFont(mono)

        self.log_view.setMaximumBlockCount(5000)

        root.addWidget(self.bar)

        root.addWidget(self.lbl_status)

        root.addWidget(self.log_view, 1)



        self._on_codec_changed()

        self._update_widgets()



    # ------------------------------------------------------------ settings --

    def _load_settings(self):

        s = self.settings

        self.ed_ffmpeg.setText(s.value("ffmpeg_dir", DEFAULT_FFMPEG_DIR, str))

        idx = self.cb_codec.findData(s.value("codec", "mov_png", str))

        self.cb_codec.setCurrentIndex(max(idx, 0))

        self.cb_fps.setCurrentText(s.value("fps", "24", str))

        idx = self.cb_color.findData(s.value("color", "srgb", str))

        self.cb_color.setCurrentIndex(max(idx, 0))

        self._check_ffmpeg()

        last = s.value("input_dir", "", str)

        if last and Path(last).is_dir():

            self.ed_in.setText(last)

            self.load_folder(last)



    def _save_settings(self):

        s = self.settings

        s.setValue("ffmpeg_dir", self.ed_ffmpeg.text().strip())

        s.setValue("input_dir", self.ed_in.text().strip())

        s.setValue("codec", self.cb_codec.currentData())

        s.setValue("fps", self.cb_fps.currentText().strip())

        s.setValue("color", self.cb_color.currentData())



    # -------------------------------------------------------------- ffmpeg --

    def _check_ffmpeg(self):

        text = self.ed_ffmpeg.text().strip()

        self.tools = tools_in(text)

        if self.tools is None and not text:

            found = shutil.which("ffmpeg")

            if found:

                self.tools = tools_in(str(Path(found).parent))

        if self.tools is None:

            self.lbl_ffmpeg.setText(

                f"<span style='color:#c0392b'>ffmpeg{EXE} not found in this folder. "

                "请选择正确的文件夹。</span>")

        else:

            fp = "ffprobe found" if self.tools[1] else "ffprobe NOT found (output validation disabled)"

            colour = "#27ae60" if self.tools[1] else "#d68910"

            self.lbl_ffmpeg.setText(f"<span style='color:{colour}'>ffmpeg found - {fp}.</span>")

        self._update_widgets()



    def _browse_ffmpeg(self):

        d = QFileDialog.getExistingDirectory(self, "选择包含 FFmpeg 的文件夹",

                                             self.ed_ffmpeg.text() or "")

        if d:

            self.ed_ffmpeg.setText(os.path.normpath(d))



    def _ensure_ffmpeg(self):

        if self.tools is None:

            QMessageBox.warning(

                self, "未找到 FFmpeg",

                f"Could not find ffmpeg{EXE} in:\n{self.ed_ffmpeg.text() or '(empty)'}\n\n"

                "请选择包含 ffmpeg.exe 的文件夹。")

            self._browse_ffmpeg()

        if self.tools is None:

            raise UserError("ffmpeg was not found. Select the folder containing ffmpeg.exe.")



    # --------------------------------------------------------------- input --

    def _browse_input(self):

        d = QFileDialog.getExistingDirectory(self, "选择 PNG 序列文件夹",

                                             self.ed_in.text() or "")

        if d:

            d = os.path.normpath(d)

            self.ed_in.setText(d)

            self.load_folder(d)



    def load_folder(self, folder: str):

        folder = folder.strip()

        self.seq = None

        self.src = None

        err = lambda msg: self.lbl_in.setText(f"<span style='color:#c0392b'>{msg}</span>")

        if not folder:

            self.lbl_in.setText("尚未选择文件夹")

            self._update_widgets()

            return

        if not Path(folder).is_dir():

            err("文件夹不存在。")

            self._update_widgets()

            return

        try:

            seq = scan_sequence(Path(folder))

        except OSError as e:

            err(f"无法读取文件夹： {e}")

            self._update_widgets()

            return

        if seq is None:

            err("此文件夹中没有找到带编号的 PNG 文件。")

            self._update_widgets()

            return

        try:

            src = read_png_info(seq.path(seq.first), probe_trns=True)

        except (OSError, ValueError) as e:

            err(f"无法读取 {seq.name(seq.first)}： {e}")

            self._update_widgets()

            return



        # configure spin boxes (signals blocked, seq still None -> _sync is a no-op)

        first, last = seq.first, seq.last

        for sp in (self.sp_start, self.sp_count, self.sp_end):

            sp.blockSignals(True)

        self.sp_start.setRange(first, last)

        self.sp_end.setRange(first, last)

        self.sp_count.setRange(1, last - first + 1)

        self.sp_start.setValue(first)

        self.sp_end.setValue(last)

        self.sp_count.setValue(last - first + 1)

        for sp in (self.sp_start, self.sp_count, self.sp_end):

            sp.blockSignals(False)



        self.seq, self.src = seq, src

        self.chk_alpha.setChecked(src.has_alpha)

        self.cb_depth.setCurrentIndex(0)



        gaps = len(seq.numbers) != (last - first + 1)

        kind = "RGBA" if src.has_alpha else "RGB"

        info = (f"序列格式 <b>{seq.pattern_label()}</b> — 共 <b>{len(seq.numbers)}</b> 个文件，"

                f"帧范围 {first}–{last}，首帧分辨率：{src.width}×{src.height}，"

                f"{src.bit_depth}-bit, {kind}")

        if gaps:

            info += ("<br><span style='color:#d68910'>警告：帧编号不连续，"

                     "（存在缺帧）。选择包含缺失帧的范围将无法编码。</span>")

        self.lbl_in.setText(info)

        log.info("Folder loaded: %s | pattern %s | %d files (%d-%d) | %dx%d %d-bit %s",

                 folder, seq.pattern_label(), len(seq.numbers), first, last,

                 src.width, src.height, src.bit_depth, kind)

        if self._out_auto or not self.ed_out.text().strip():

            self._default_output()

        self._sync("mode")

        self._update_widgets()



    # --------------------------------------------------------------- range --

    def _sync(self, source: str):

        if not self.seq:

            self._refresh_summary()

            return

        first, last = self.seq.first, self.seq.last

        s, c, e = self.sp_start.value(), self.sp_count.value(), self.sp_end.value()

        mode = self.cb_mode.currentIndex()

        if mode == 0:

            s, e = first, last

            c = e - s + 1

        elif source == "end" or (source in ("start", "mode") and mode == 2):

            e = max(e, s)

            c = e - s + 1

        else:

            c = max(1, min(c, last - s + 1))

            e = s + c - 1

        for sp in (self.sp_start, self.sp_count, self.sp_end):

            sp.blockSignals(True)

        self.sp_start.setValue(s)

        self.sp_count.setValue(c)

        self.sp_end.setValue(e)

        for sp in (self.sp_start, self.sp_count, self.sp_end):

            sp.blockSignals(False)

        self.sp_start.setEnabled(mode != 0)

        self.sp_count.setEnabled(mode == 1)

        self.sp_end.setEnabled(mode == 2)

        self._refresh_summary()



    def _compute_range(self):

        """Return (start, count). Raises UserError when invalid."""

        seq = self.seq

        if seq is None:

            raise UserError("请先选择包含 PNG 序列的文件夹。")

        mode = self.cb_mode.currentIndex()

        if mode == 0:

            start, end = seq.first, seq.last

        elif mode == 1:

            start = self.sp_start.value()

            end = start + self.sp_count.value() - 1

        else:

            start, end = self.sp_start.value(), self.sp_end.value()

        if end < start:

            raise UserError("结束帧不能早于起始帧。")

        if start < seq.first or end > seq.last:

            avail = max(0, seq.last - start + 1)

            raise UserError(

                f"请求的帧范围为 {start}–{end}，但序列实际范围为 "

                f"{seq.first}-{seq.last}. 从第 {start} 帧开始仅有 {avail} 帧可用。")

        missing = seq.missing(start, end)

        if missing:

            names = ", ".join(seq.name(n) for n in missing[:5])

            raise UserError(

                f"所选范围内存在缺帧（例如：{names}"

                f"{' ...' if len(missing) > 5 else ''}). ffmpeg needs a continuous sequence - "

                "请补齐缺失文件，或选择没有缺帧的范围。")

        return start, end - start + 1



    def _refresh_summary(self):

        if not self.seq:

            self.lbl_range.setText("")

            return

        try:

            start, count = self._compute_range()

            text = f"将转换 <b>{count}</b> 帧：第 {start} 帧至第 {start + count - 1} 帧"

            try:

                _, fps = parse_fps(self.cb_fps.currentText())

                text += f"  -  duration {count / fps:.2f} s at {fps:g} fps"

            except UserError:

                pass

            self.lbl_range.setText(text)

        except UserError as e:

            self.lbl_range.setText(f"<span style='color:#c0392b'>{e}</span>")



    # -------------------------------------------------------------- output --

    def _on_codec_changed(self):

        key = self.cb_codec.currentData()

        self.lbl_codec.setText(f"<i>{CODECS[key]['note']}</i>")

        text = self.ed_out.text().strip()

        if text:

            self.ed_out.setText(str(force_ext(Path(text), CODECS[key]["ext"])))



    def _on_out_edited(self, _text):

        self._out_auto = False



    def _default_output(self):

        if not self.seq:

            return

        ext = CODECS[self.cb_codec.currentData()]["ext"]

        folder = self.seq.folder

        parent = folder.parent if folder.parent != folder else folder

        self.ed_out.setText(str(parent / f"{folder.name or 'sequence'}{ext}"))

        self._out_auto = True



    def _browse_output(self):

        ext = CODECS[self.cb_codec.currentData()]["ext"]

        start = self.ed_out.text().strip() or str(Path.home() / f"output{ext}")

        path, _ = QFileDialog.getSaveFileName(

            self, "保存视频文件", start, f"Video (*{ext})", options=QFileDialog.DontConfirmOverwrite)

        if path:

            self.ed_out.setText(str(force_ext(Path(path), ext)))

            self._out_auto = False



    # ----------------------------------------------------------- UI state --

    def _update_widgets(self):

        busy = self.proc is not None or self.probe is not None or self.job.get("checking", False)

        has_seq = self.seq is not None

        self.btn_start.setEnabled(has_seq and not busy)

        self.btn_cancel.setEnabled(self.proc is not None)

        for w in (self.ed_ffmpeg, self.ed_in, self.cb_mode, self.cb_codec, self.cb_fps,

                  self.cb_color, self.ed_out):

            w.setEnabled(not busy)

        alpha_ok = bool(has_seq and self.src and self.src.has_alpha)

        self.chk_alpha.setEnabled(alpha_ok and not busy)

        if not alpha_ok:

            self.chk_alpha.setChecked(False)

        self.cb_depth.setEnabled(bool(has_seq and self.src and self.src.bit_depth == 16) and not busy)

        if has_seq and not busy:

            mode = self.cb_mode.currentIndex()

            self.sp_start.setEnabled(mode != 0)

            self.sp_count.setEnabled(mode == 1)

            self.sp_end.setEnabled(mode == 2)

        else:

            for sp in (self.sp_start, self.sp_count, self.sp_end):

                sp.setEnabled(False)



    def _status(self, text: str):

        self.lbl_status.setText(text)



    # --------------------------------------------------------------- start --

    def _on_start(self):

        try:

            job = self._prepare_job()

        except UserError as e:

            self.job = {}

            self._update_widgets()

            log.error("Cannot start: %s", e)

            QMessageBox.warning(self, "无法开始转换", str(e))

            return

        if job is None:      # cancelled by the user (e.g. declined overwrite)

            self.job = {}

            self._update_widgets()

            return

        self.job = job

        self._launch()



    def _prepare_job(self):

        self._ensure_ffmpeg()

        ffmpeg, ffprobe = self.tools

        start, count = self._compute_range()

        seq = self.seq

        fps_arg, fps_val = parse_fps(self.cb_fps.currentText())

        codec = self.cb_codec.currentData()

        ext = CODECS[codec]["ext"]



        text = self.ed_out.text().strip()

        if not text or not Path(text).name:

            raise UserError("请选择输出文件（使用“另存为…”）。")

        out = force_ext(Path(text), ext)

        self.ed_out.setText(str(out))

        try:

            out.parent.mkdir(parents=True, exist_ok=True)

        except OSError as e:

            raise UserError(f"无法创建输出文件夹：\n{e}")

        if out.exists():

            r = QMessageBox.question(self, "确认覆盖", f"{out}\n\n文件已存在。是否覆盖？",

                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if r != QMessageBox.Yes:

                return None



        # --- check that every frame has the same resolution ---------------

        self.job = {"checking": True}

        self._update_widgets()

        self.bar.setRange(0, count)

        self._status("正在检查帧信息…")

        QApplication.setOverrideCursor(Qt.WaitCursor)

        try:

            def prog(i):

                self.bar.setValue(i)

                QApplication.processEvents()

            res = check_frames(seq, start, count, prog)

        finally:

            QApplication.restoreOverrideCursor()

            self.bar.setValue(0)

            self._status("就绪")

        if res["unreadable"]:

            lines = "\n".join(f"  {n}: {why}" for n, why in res["unreadable"][:8])

            raise UserError(f"{len(res['unreadable'])} frame(s) could not be read:\n{lines}")

        ref = res["ref"]

        if res["mismatches"]:

            lines = "\n".join(f"  {n}: {w}x{h}" for n, (w, h) in res["mismatches"][:8])

            raise UserError(

                f"分辨率 mismatch! {len(res['mismatches'])} frame(s) differ from the "

                f"first frame ({ref[0]}x{ref[1]}):\n{lines}\n\n"

                "所有帧的分辨率必须一致。")

        try:

            free = shutil.disk_usage(out.parent).free

            if free < res["bytes"]:

                r = QMessageBox.question(

                    self, "磁盘空间不足",

                    f"源 PNG 文件总计 {fmt_bytes(res['bytes'])}, 但输出磁盘仅剩 "

                    f"{fmt_bytes(free)} 可用空间。无损视频文件可能与 PNG 序列一样大。\n\n"

                    "仍要继续吗？", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

                if r != QMessageBox.Yes:

                    return None

        except OSError:

            pass



        alpha = bool(self.chk_alpha.isChecked() and self.src.has_alpha)

        bit16 = bool(self.src.bit_depth == 16 and self.cb_depth.currentIndex() == 0)

        color = self.cb_color.currentData()

        vf, enc_args, pix = build_encode_args(codec, alpha, bit16, color)



        tmp = out.with_name(f".{out.stem}.partial{ext}")

        if tmp.exists():

            try:

                tmp.unlink()

            except OSError as e:

                raise UserError(f"无法删除旧的临时文件 {tmp}：\n{e}")



        cmd = [ffmpeg, "-hide_banner", "-loglevel", "info", "-nostats",

               "-progress", "pipe:1", "-y",

               "-framerate", fps_arg, "-start_number", str(start),

               "-i", seq.ffmpeg_pattern()]

        if vf:

            cmd += ["-vf", vf]

        cmd += enc_args + ["-frames:v", str(count), "-an", str(tmp)]



        return {"ffmpeg": ffmpeg, "ffprobe": ffprobe, "cmd": cmd, "tmp": tmp, "out": out,

                "start": start, "count": count, "size": ref, "fps_arg": fps_arg,

                "fps_val": fps_val, "codec": codec, "alpha": alpha, "bit16": bit16,

                "pix": pix, "color": color, "folder": seq.folder, "checking": False}



    def _launch(self):

        j = self.job

        log.info("=" * 72)

        log.info("Job started : %s", datetime.now().isoformat(timespec="seconds"))

        log.info("Input folder: %s", j["folder"])

        log.info("Frames      : %d (%d to %d), %dx%d", j["count"], j["start"],

                 j["start"] + j["count"] - 1, *j["size"])

        log.info("Format      : %s | pix_fmt %s | alpha=%s | %s fps | colour tag=%s",

                 CODECS[j["codec"]]["label"], j["pix"], j["alpha"], j["fps_arg"], j["color"])

        log.info("Output      : %s  (temp: %s)", j["out"], j["tmp"].name)

        log.info("Command     : %s", list2cmdline(j["cmd"]))



        self.cancelled = False

        self._out_buf = self._err_buf = ""

        self._err_tail.clear()

        self._prog = {}

        self.t0 = time.time()

        self.bar.setRange(0, j["count"])

        self.bar.setValue(0)



        p = QProcess(self)

        self.proc = p

        p.readyReadStandardOutput.connect(self._on_stdout)

        p.readyReadStandardError.connect(self._on_stderr)

        p.finished.connect(self._on_finished)

        p.errorOccurred.connect(self._on_proc_error)

        p.start(j["cmd"][0], j["cmd"][1:])

        self._status("正在编码…")

        self._update_widgets()



    def _on_cancel(self):

        if self.proc is not None:

            self.cancelled = True

            log.warning("Cancel requested - stopping ffmpeg.")

            self.proc.kill()



    # --------------------------------------------------- process handlers --

    def _on_stdout(self):

        if self.proc is None:

            return

        self._out_buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")

        *lines, self._out_buf = self._out_buf.split("\n")

        for line in lines:

            key, _, val = line.strip().partition("=")

            if not key:

                continue

            self._prog[key] = val

            if key == "progress":

                try:

                    n = int(self._prog.get("frame", "0"))

                except ValueError:

                    n = 0

                total = self.job["count"]

                self.bar.setValue(min(n, total))

                self._status(

                    f"Encoding... {n}/{total} frames ({100 * n // max(total, 1)}%)  |  "

                    f"{self._prog.get('fps', '0')} fps  |  speed {self._prog.get('speed', '?')}  |  "

                    f"elapsed {fmt_time(time.time() - self.t0)}")



    def _on_stderr(self):

        if self.proc is None:

            return

        self._err_buf += bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")

        parts = re.split(r"[\r\n]", self._err_buf)

        self._err_buf = parts.pop()

        for line in parts:

            line = line.strip()

            if line:

                self._err_tail.append(line)

                log.info("[ffmpeg] %s", line)



    def _on_proc_error(self, err):

        if err == QProcess.FailedToStart and self.proc is not None:

            self.proc = None

            self._cleanup_tmp()

            self._fail("ffmpeg could not be started. Check the ffmpeg folder.")



    def _on_finished(self, code, status):

        if self.proc is None:

            return

        self._on_stdout()

        self._on_stderr()

        if self._err_buf.strip():

            self._err_tail.append(self._err_buf.strip())

            log.info("[ffmpeg] %s", self._err_buf.strip())

        proc, self.proc = self.proc, None

        proc.deleteLater()

        elapsed = time.time() - self.t0

        self.job["elapsed"] = elapsed



        if self.cancelled:

            self._cleanup_tmp()

            log.warning("Job cancelled by user. Temporary file removed.")

            self._status("已取消。")

            self.bar.setValue(0)

            self._update_widgets()

            return

        if status != QProcess.NormalExit or code != 0:

            tail = "\n".join(list(self._err_tail)[-15:])

            self._cleanup_tmp()

            self._fail(f"ffmpeg failed (exit code {code}).", tail)

            return



        tmp, out = self.job["tmp"], self.job["out"]

        try:

            os.replace(tmp, out)

        except OSError as e:

            self._cleanup_tmp()

            self._fail("无法写入最终文件：\n"

                       f"{e}\n\n如果文件正被 DaVinci Resolve 或其他程序占用，"

                       "请关闭占用程序后重试。")

            return

        log.info("Encoding finished in %s -> %s (%s)", fmt_time(elapsed), out,

                 fmt_bytes(out.stat().st_size))

        self.bar.setValue(self.job["count"])

        self._run_probe()



    def _fail(self, message: str, details: str = ""):

        log.error("%s", message)

        if details:

            log.error("Last ffmpeg output:\n%s", details)

        self._status("失败。")

        self.bar.setValue(0)

        self._update_widgets()

        box = QMessageBox(self)

        box.setIcon(QMessageBox.Critical)

        box.setWindowTitle("编码失败")

        box.setText(message + "\n\nNo partial output file was kept.")

        if details:

            box.setDetailedText(details)

        box.exec_()



    def _cleanup_tmp(self):

        tmp = self.job.get("tmp")

        if tmp and Path(tmp).exists():

            try:

                Path(tmp).unlink()

                log.info("Removed temporary file %s", tmp)

            except OSError as e:

                log.warning("Could not remove temporary file %s: %s", tmp, e)



    # --------------------------------------------------- ffprobe validation --

    def _run_probe(self):

        j = self.job

        if not j.get("ffprobe"):

            log.warning("ffprobe not found - output validation skipped.")

            self._finish(None)

            return

        self._status("Validating the output with ffprobe...")

        args = ["-v", "error", "-count_packets", "-select_streams", "v:0",

                "-show_entries",

                "stream=codec_name,width,height,pix_fmt,r_frame_rate,nb_read_packets,"

                "color_space,color_transfer,color_primaries:format=duration,size",

                "-of", "json", str(j["out"])]

        p = QProcess(self)

        self.probe = p

        p.finished.connect(lambda *_: self._on_probe_done())

        p.errorOccurred.connect(lambda e: self._on_probe_error(e))

        p.start(j["ffprobe"], args)



    def _on_probe_error(self, err):

        if err == QProcess.FailedToStart and self.probe is not None:

            self.probe.deleteLater()

            self.probe = None

            log.warning("ffprobe could not be started - validation skipped.")

            self._finish(None)



    def _on_probe_done(self):

        p, self.probe = self.probe, None

        if p is None:

            return

        raw = bytes(p.readAllStandardOutput()).decode("utf-8", "replace")

        err = bytes(p.readAllStandardError()).decode("utf-8", "replace").strip()

        p.deleteLater()

        try:

            data = json.loads(raw)

            report = self._make_report(data)

        except (ValueError, KeyError, IndexError, TypeError) as e:

            log.warning("ffprobe validation failed: %s %s", e, err)

            report = (False, [f"ffprobe could not read the output file: {err or e}"])

        self._finish(report)



    def _make_report(self, data):

        j = self.job

        st = (data.get("streams") or [{}])[0]

        frames = int(st.get("nb_read_packets") or 0)

        w, h = int(st.get("width") or 0), int(st.get("height") or 0)

        pix = st.get("pix_fmt", "?")

        codec = st.get("codec_name", "?")

        try:

            fps_out = float(Fraction(st.get("r_frame_rate", "0/1")))

        except (ValueError, ZeroDivisionError):

            fps_out = 0.0

        alpha_out = has_alpha_fmt(pix)

        checks = [

            ("帧数", f"{frames} (expected {j['count']})", frames == j["count"]),

            ("分辨率", f"{w}x{h} (expected {j['size'][0]}x{j['size'][1]})",

             (w, h) == tuple(j["size"])),

            ("编码器", f"{codec} (expected {CODECS[j['codec']]['probe_codec']})",

             codec == CODECS[j["codec"]]["probe_codec"]),

            ("帧率", f"{fps_out:.3f} (expected {j['fps_val']:.3f})",

             abs(fps_out - j["fps_val"]) < 0.01),

            ("透明通道", f"{'yes' if alpha_out else 'no'} (expected "

                              f"{'yes' if j['alpha'] else 'no'})", alpha_out == j["alpha"]),

        ]

        lines = [f"{'OK  ' if ok else 'FAIL'} {name}: {val}" for name, val, ok in checks]

        lines.append(f"INFO Pixel format: {pix}")

        tags = ", ".join(f"{k}={st.get(k)}" for k in ("color_primaries", "color_transfer", "color_space")

                         if st.get(k))

        if tags:

            lines.append(f"INFO Colour tags: {tags}")

        return all(c[2] for c in checks), lines



    # ------------------------------------------------------------- finish --

    def _finish(self, report):

        j = self.job

        out = j["out"]

        fps = j["fps_arg"]

        fps_txt = f"{j['fps_val']:.3f}".rstrip("0").rstrip(".")

        if report:

            for line in report[1]:

                (log.info if line.startswith(("确定", "INFO")) else log.error)("[validate] %s", line)

        self._status("完成。" if (report is None or report[0]) else "已完成，但校验发现问题。")

        self._update_widgets()



        summary = (

            f"输出文件：\n{out}\n\n"

            f"Format: {CODECS[j['codec']]['label']}\n"

            f"Frames: {j['count']}   分辨率: {j['size'][0]}x{j['size'][1]}   "

            f"帧率: {fps_txt} fps   Alpha: {'yes' if j['alpha'] else 'no'}\n"

            f"File size: {fmt_bytes(out.stat().st_size)}   Time: {fmt_time(j.get('elapsed', 0))}\n"

        )

        if report:

            summary += "\nffprobe validation:\n" + "\n".join(report[1]) + "\n"

        else:

            summary += "\n(ffprobe validation was skipped.)\n"

        summary += (

            f"\nDaVinci Resolve 提示：请将项目/时间线帧率设置为 {fps_txt} fps "

            "(Project Settings > Master Settings > Timeline frame rate) BEFORE adding this clip "

            "to a timeline. A mismatched frame rate makes the video play at the wrong speed. "

            "如果颜色异常，请检查 Resolve 中片段的输入色彩空间。"

        )

        log.info("Job complete.\n%s", summary)



        box = QMessageBox(self)

        ok = report is None or report[0]

        box.setIcon(QMessageBox.Information if ok else QMessageBox.Warning)

        box.setWindowTitle("转换完成" if ok else "转换完成，但存在警告")

        box.setText(summary)

        open_btn = box.addButton("打开输出文件夹", QMessageBox.ActionRole)

        box.addButton(QMessageBox.Ok)

        box.exec_()

        if box.clickedButton() is open_btn:

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out.parent)))

        self.job = {}

        self._status("就绪")

        self._update_widgets()



    # -------------------------------------------------------------- close --

    def closeEvent(self, event):

        if self.proc is not None:

            r = QMessageBox.question(self, "正在编码",

                                     "Encoding is still running. Stop it and quit?",

                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

            if r != QMessageBox.Yes:

                event.ignore()

                return

            self.cancelled = True

            self.proc.kill()

            self.proc.waitForFinished(3000)

            self._cleanup_tmp()

        self._save_settings()

        event.accept()






def main():
    # 强制告诉 Windows 这是一个独立的应用，让任务栏正确读取图标！
    try:
        import ctypes
        myappid = 'XingAnDev.PngToVideo.2026' # 这个 ID 保证唯一即可
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)

    win = MainWindow()
    win.showMaximized()
    
    # 这行代码执行后，整个程序就在事件循环里了，后面的代码都不会执行
    sys.exit(app.exec_()) 


if __name__ == "__main__":
    main()