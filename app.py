#!/usr/bin/env python3
from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import sensors

UPDATE_MS = 1000
HISTORY_OPTIONS = [("1분", 60), ("3분", 180), ("5분", 300), ("10분", 600), ("30분", 1800)]

COLORS = {
    "orange": "#E95420",
    "purple": "#77216F",
    "blue": "#3584E4",
    "green": "#26A269",
    "red": "#E01B24",
    "yellow": "#F6D32D",
    "fg": "#DAD7D2",
    "muted": "#9A9996",
    "title": "#F2EDE7",
    "bg": "#1B1B1B",
    "card": "#242424",
    "grid": "#4A4A4A",
}


class Card(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 8, 10, 9)
        self.layout.setSpacing(4)
        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        self.layout.addWidget(self.title)


class HistoryPlot(Card):
    def __init__(self, title: str, color: str, y_max: float = 100.0, unit: str = "%", dynamic_y: bool = False):
        super().__init__(title)
        self.unit = unit
        self.y_max = y_max
        self.dynamic_y = dynamic_y
        self.value_label = QLabel("--")
        self.value_label.setObjectName("valueLabel")
        self.layout.addWidget(self.value_label)
        self.plot = pg.PlotWidget()
        self.plot.setBackground(COLORS["card"])
        self.plot.showGrid(x=True, y=True, alpha=0.18)
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setYRange(-2 if unit == "%" else 0, y_max + (2 if unit == "%" else 0), padding=0)
        self.plot.getAxis("left").setPen(pg.mkPen(COLORS["muted"], width=1))
        self.plot.getAxis("bottom").setPen(pg.mkPen(COLORS["muted"], width=1))
        self.plot.getAxis("left").setTextPen(COLORS["muted"])
        self.plot.getAxis("bottom").setTextPen(COLORS["muted"])
        self.plot.showAxis("bottom", False)
        self.plot.setMinimumHeight(78)
        # 축 제목은 공간을 많이 먹어서 카드가 작아질 때 잘림을 유발한다.
        # 대신 값 라벨에 단위를 표시하고, 축은 눈금만 남긴다.
        self.plot.getAxis("left").setWidth(48)
        self.plot.setContentsMargins(2, 0, 2, 0)
        self.plot.getPlotItem().layout.setContentsMargins(6, 3, 8, 3)
        self.plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.plot.getAxis("left").setStyle(tickFont=QFont("Ubuntu", 8), textFillLimits=[(0, 0.8)])
        self.plot.getAxis("bottom").setStyle(tickFont=QFont("Ubuntu", 8), textFillLimits=[(0, 0.8)])
        self.default_color = color
        self.curves: Dict[str, pg.PlotDataItem] = {}
        self.layout.addWidget(self.plot, stretch=1)

    def _clean(self, xs: List[float], ys: List[Optional[float]]):
        clean_x = []
        clean_y = []
        for x, y in zip(xs, ys):
            if y is None:
                continue
            clean_x.append(x)
            clean_y.append(y)
        return clean_x, clean_y

    def adjust_y_range(self, series: Dict[str, dict]):
        if not self.dynamic_y:
            if self.unit == "%":
                self.plot.setYRange(-2, 102, padding=0)
            return
        vals = []
        for item in series.values():
            vals.extend([v for v in item.get("ys", []) if v is not None])
        if not vals:
            self.plot.setYRange(0, self.y_max, padding=0)
            return
        lo = min(vals)
        hi = max(vals)
        if hi == lo:
            lo -= 3
            hi += 3
        pad = max(3.0, (hi - lo) * 0.18)
        bottom = max(0.0, lo - pad)
        top = hi + pad
        # 온도 그래프가 너무 납작하거나 과하게 확대되지 않게 최소 범위를 보장.
        if top - bottom < 12:
            mid = (top + bottom) / 2
            bottom = max(0.0, mid - 6)
            top = mid + 6
        self.plot.setYRange(bottom, top, padding=0)

    def set_data(self, xs: List[float], ys: List[Optional[float]], current: Optional[float], subtitle: str = ""):
        self.set_series({"main": {"xs": xs, "ys": ys, "current": current, "color": self.default_color, "width": 2.8}}, current, subtitle)

    def set_series(self, series: Dict[str, dict], current: Optional[float], subtitle: str = ""):
        self.adjust_y_range(series)
        for name in list(self.curves):
            if name not in series:
                self.plot.removeItem(self.curves.pop(name))
        for name, item in series.items():
            if name not in self.curves:
                color = QColor(item.get("color", self.default_color))
                alpha = item.get("alpha")
                if alpha is not None:
                    color.setAlpha(alpha)
                self.curves[name] = self.plot.plot([], [], pen=pg.mkPen(color, width=item.get("width", 2.0)))
            clean_x, clean_y = self._clean(item["xs"], item["ys"])
            self.curves[name].setData(clean_x, clean_y)
        if current is None:
            self.value_label.setText("감지 안 됨" + (f" · {subtitle}" if subtitle else ""))
        else:
            self.value_label.setText(f"{current:.1f}{self.unit}" + (f" · {subtitle}" if subtitle else ""))


class DonutWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.percent = 0.0
        self.label = "-"
        self.detail = ""
        self.setMinimumSize(118, 118)
        self.setMaximumSize(138, 138)

    def set_usage(self, percent: float, label: str, detail: str):
        self.percent = max(0.0, min(100.0, percent))
        self.label = label
        self.detail = detail
        self.update()

    def paintEvent(self, event):
        rect = self.rect().adjusted(14, 14, -14, -14)
        size = min(rect.width(), rect.height())
        x = rect.center().x() - size // 2
        y = rect.center().y() - size // 2
        square = rect.__class__(x, y, size, size)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen_bg = QPen(QColor("#454545"), 12, Qt.SolidLine, Qt.RoundCap)
        pen_fg = QPen(QColor(COLORS["orange"]), 12, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen_bg)
        painter.drawArc(square, 0, 360 * 16)
        painter.setPen(pen_fg)
        painter.drawArc(square, 90 * 16, int(-360 * 16 * self.percent / 100.0))
        painter.setPen(QColor(COLORS["fg"]))
        f = painter.font()
        f.setPointSize(15)
        f.setBold(True)
        painter.setFont(f)
        painter.drawText(square, Qt.AlignCenter, f"{self.percent:.0f}%")
        f.setPointSize(8)
        f.setBold(False)
        painter.setFont(f)
        painter.setPen(QColor(COLORS["muted"]))
        painter.drawText(square.adjusted(0, size // 3, 0, size // 2), Qt.AlignCenter, self.label)


class StorageCard(Card):
    def __init__(self):
        super().__init__("스토리지 용량")
        row = QHBoxLayout()
        self.combo = QComboBox()
        self.refresh_btn = QPushButton("새로고침")
        row.addWidget(QLabel("마운트"))
        row.addWidget(self.combo, stretch=1)
        row.addWidget(self.refresh_btn)
        self.layout.addLayout(row)
        body = QHBoxLayout()
        self.donut = DonutWidget()
        self.info = QLabel("--")
        self.info.setObjectName("storageInfo")
        self.info.setWordWrap(True)
        self.info.setStyleSheet("font-size: 8.5pt;")
        body.addWidget(self.donut)
        body.addWidget(self.info, stretch=1)
        self.layout.addLayout(body, stretch=1)
        self.items: List[dict] = []
        self.refresh_btn.clicked.connect(self.refresh)
        self.combo.currentIndexChanged.connect(self.update_view)
        self.refresh()

    def refresh(self):
        current = self.combo.currentData()
        self.items = sensors.storage_usages()
        self.combo.blockSignals(True)
        self.combo.clear()
        for item in self.items:
            self.combo.addItem(f"{item['mountpoint']}  ({item['device']})", item["mountpoint"])
        if current:
            idx = self.combo.findData(current)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        self.update_view()

    def update_view(self):
        idx = self.combo.currentIndex()
        if idx < 0 or idx >= len(self.items):
            self.donut.set_usage(0, "감지 안 됨", "")
            self.info.setText("표시할 스토리지 마운트가 없습니다.")
            return
        item = self.items[idx]
        self.donut.set_usage(item["percent"], item["mountpoint"], "")
        self.info.setText(
            f"마운트: {item['mountpoint']}\n"
            f"장치: {item['device']}\n"
            f"파일시스템: {item['fstype']}\n"
            f"사용: {item['used_gb']:.1f} GiB / {item['total_gb']:.1f} GiB\n"
            f"여유: {item['free_gb']:.1f} GiB"
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ubuntu System Monitor")
        self.resize(1120, 720)
        self.setMinimumSize(960, 640)
        self.history_seconds = 60
        self.t = 0
        self.buffers: Dict[str, deque] = {}
        self.cpu_core_count = psutil_cpu_count()
        self.last_cpu_cores: List[float] = []
        self.last_cpu_temps: List[sensors.SensorValue] = []
        self.last_nvme_temps: List[sensors.SensorValue] = []

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 8, 10, 10)
        root_layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Ubuntu System Monitor")
        title.setObjectName("appTitle")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(QLabel("기록 길이"))
        self.history_combo = QComboBox()
        for label, seconds in HISTORY_OPTIONS:
            self.history_combo.addItem(label, seconds)
        self.history_combo.currentIndexChanged.connect(self.change_history)
        header.addWidget(self.history_combo)
        self.status_label = QLabel("1초마다 업데이트")
        self.status_label.setObjectName("muted")
        header.addWidget(self.status_label)
        root_layout.addLayout(header)

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        self.cpu_plot = HistoryPlot("CPU 사용량", COLORS["orange"], 100, "%")
        self.cpu_plot.plot.setMinimumHeight(92)
        self.cpu_combo = QComboBox()
        self.cpu_combo.addItem("전체", "total")
        self.cpu_combo.addItem("모든 코어", "all")
        for i in range(self.cpu_core_count):
            self.cpu_combo.addItem(f"Core {i}", i)
        self.cpu_plot.layout.insertWidget(1, self.cpu_combo)

        self.mem_plot = HistoryPlot("메모리 사용량", COLORS["blue"], 100, "%")

        self.cpu_temp_plot = HistoryPlot("CPU 온도", COLORS["red"], 95, "°C", dynamic_y=True)
        self.cpu_temp_combo = QComboBox()
        self.cpu_temp_combo.addItem("전체 평균", "avg")
        self.cpu_temp_combo.addItem("모든 센서", "all")
        self.cpu_temp_plot.layout.insertWidget(1, self.cpu_temp_combo)

        self.nvme_temp_plot = HistoryPlot("NVMe SSD 온도", COLORS["yellow"], 85, "°C", dynamic_y=True)
        self.nvme_combo = QComboBox()
        self.nvme_combo.addItem("전체 평균", "avg")
        self.nvme_combo.addItem("모든 NVMe", "all")
        self.nvme_temp_plot.layout.insertWidget(1, self.nvme_combo)

        self.storage_card = StorageCard()

        # 한 화면 대시보드: CPU만 전체 폭, 나머지는 2열로 압축한다.
        grid.addWidget(self.cpu_plot, 0, 0, 1, 2)
        grid.addWidget(self.mem_plot, 1, 0)
        grid.addWidget(self.cpu_temp_plot, 1, 1)
        grid.addWidget(self.nvme_temp_plot, 2, 0)
        grid.addWidget(self.storage_card, 2, 1)
        grid.setRowStretch(0, 2)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        root_layout.addWidget(content, stretch=1)
        self.setCentralWidget(root)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(UPDATE_MS)
        self.tick()

    def change_history(self):
        self.history_seconds = int(self.history_combo.currentData())
        for key, old in list(self.buffers.items()):
            self.buffers[key] = deque(old, maxlen=self.history_seconds)

    def buffer(self, key: str) -> deque:
        if key not in self.buffers:
            self.buffers[key] = deque(maxlen=self.history_seconds)
        return self.buffers[key]

    def append(self, key: str, value: Optional[float]):
        self.buffer(key).append(value)

    def xs(self, key: str) -> List[float]:
        n = len(self.buffer(key))
        return list(range(-n + 1, 1))

    def selected_cpu_value(self, total: float, cores: List[float]) -> tuple[float, str, str]:
        data = self.cpu_combo.currentData()
        if data == "total":
            return total, "cpu_total", f"{len(cores)} cores"
        idx = int(data)
        val = cores[idx] if idx < len(cores) else None
        return val, f"cpu_core_{idx}", f"Core {idx}"

    def sync_sensor_combo(self, combo: QComboBox, values: List[sensors.SensorValue], first_label: str, all_label: str):
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(first_label, "avg")
        combo.addItem(all_label, "all")
        for i, v in enumerate(values):
            combo.addItem(v.name, i)
        if current is not None:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def selected_sensor(self, combo: QComboBox, values: List[sensors.SensorValue], key_prefix: str) -> tuple[Optional[float], str, str]:
        data = combo.currentData()
        if data == "avg" or data is None:
            val = sensors.average(values)
            return val, f"{key_prefix}_avg", "평균" if val is not None else "센서 없음"
        idx = int(data)
        if idx < len(values):
            return values[idx].value, f"{key_prefix}_{idx}", values[idx].name
        return None, f"{key_prefix}_missing", "센서 없음"

    def palette_color(self, idx: int) -> str:
        palette = ["#E95420", "#3584E4", "#33D17A", "#F6D32D", "#C061CB", "#62A0EA", "#FF7800", "#1ABC9C", "#DC8ADD", "#A51D2D", "#B5835A", "#99C1F1"]
        return palette[idx % len(palette)]

    def render_cpu(self, total: float, cores: List[float]):
        mode = self.cpu_combo.currentData()
        if mode == "all":
            series = {
                "cpu_total": {"xs": self.xs("cpu_total"), "ys": list(self.buffer("cpu_total")), "current": total, "color": COLORS["orange"], "width": 3.2}
            }
            for i, val in enumerate(cores):
                key = f"cpu_core_{i}"
                series[key] = {"xs": self.xs(key), "ys": list(self.buffer(key)), "current": val, "color": self.palette_color(i), "width": 1.25, "alpha": 150}
            avg = sum(cores) / len(cores) if cores else total
            maxv = max(cores) if cores else total
            self.cpu_plot.set_series(series, total, f"전체 굵은선 · {len(cores)} cores · avg {avg:.1f}% · max {maxv:.1f}%")
            return
        cpu_val, cpu_key, cpu_sub = self.selected_cpu_value(total, cores)
        self.cpu_plot.set_data(self.xs(cpu_key), list(self.buffer(cpu_key)), cpu_val, cpu_sub)

    def render_sensors(self, plot: HistoryPlot, combo: QComboBox, values: List[sensors.SensorValue], key_prefix: str, label: str):
        mode = combo.currentData()
        avg = sensors.average(values)
        if mode == "all":
            if not values:
                plot.set_data(self.xs(f"{key_prefix}_avg"), list(self.buffer(f"{key_prefix}_avg")), None, f"{label} 없음")
                return
            series = {}
            if avg is not None:
                series[f"{key_prefix}_avg"] = {"xs": self.xs(f"{key_prefix}_avg"), "ys": list(self.buffer(f"{key_prefix}_avg")), "current": avg, "color": COLORS["red"] if key_prefix == "cpu_temp" else COLORS["yellow"], "width": 3.0}
            for i, v in enumerate(values):
                key = f"{key_prefix}_{i}"
                series[key] = {"xs": self.xs(key), "ys": list(self.buffer(key)), "current": v.value, "color": self.palette_color(i), "width": 1.5, "alpha": 170}
            maxv = max([v.value for v in values if v.value is not None], default=avg)
            plot.set_series(series, avg, f"평균 굵은선 · {len(values)}개 {label} · max {maxv:.1f}°C")
            return
        sensor_val, sensor_key, sensor_sub = self.selected_sensor(combo, values, key_prefix)
        plot.set_data(self.xs(sensor_key), list(self.buffer(sensor_key)), sensor_val, sensor_sub)

    def tick(self):
        self.t += 1
        total, cores = sensors.cpu_usage()
        mem_percent, mem_used, mem_total = sensors.memory_usage()
        cpu_temps = sensors.cpu_temperature_values()
        nvme_temps = sensors.nvme_temperature_values()

        self.sync_sensor_combo(self.cpu_temp_combo, cpu_temps, "전체 평균", "모든 센서")
        self.sync_sensor_combo(self.nvme_combo, nvme_temps, "전체 평균", "모든 NVMe")

        self.append("cpu_total", total)
        for i, val in enumerate(cores):
            self.append(f"cpu_core_{i}", val)
        self.render_cpu(total, cores)

        self.append("mem", mem_percent)
        self.mem_plot.set_data(self.xs("mem"), list(self.buffer("mem")), mem_percent, f"{mem_used:.1f}/{mem_total:.1f} GiB")

        cpu_avg = sensors.average(cpu_temps)
        self.append("cpu_temp_avg", cpu_avg)
        for i, v in enumerate(cpu_temps):
            self.append(f"cpu_temp_{i}", v.value)
        self.render_sensors(self.cpu_temp_plot, self.cpu_temp_combo, cpu_temps, "cpu_temp", "센서")

        nvme_avg = sensors.average(nvme_temps)
        self.append("nvme_temp_avg", nvme_avg)
        for i, v in enumerate(nvme_temps):
            self.append(f"nvme_temp_{i}", v.value)
        self.render_sensors(self.nvme_temp_plot, self.nvme_combo, nvme_temps, "nvme_temp", "NVMe")

        if self.t % 30 == 0:
            self.storage_card.refresh()


def psutil_cpu_count() -> int:
    import psutil
    return psutil.cpu_count(logical=True) or 1


def apply_style(app: QApplication):
    app.setStyleSheet(f"""
        QMainWindow, QWidget {{
            background: {COLORS['bg']};
            color: {COLORS['fg']};
            font-family: Ubuntu, Cantarell, Noto Sans, sans-serif;
            font-size: 8.5pt;
        }}
        QLabel#appTitle {{
            font-size: 14pt;
            font-weight: 700;
            color: {COLORS['orange']};
        }}
        QLabel#cardTitle {{
            font-size: 10pt;
            font-weight: 700;
            color: {COLORS['title']};
        }}
        QLabel#valueLabel {{
            font-size: 11pt;
            font-weight: 700;
            color: #E6DED8;
        }}
        QLabel#muted, QLabel#storageInfo {{
            color: {COLORS['muted']};
        }}
        QFrame#card {{
            background: {COLORS['card']};
            border: 1px solid #343434;
            border-radius: 13px;
        }}
        QScrollArea {{
            border: none;
            background: {COLORS['bg']};
        }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: #1F1F1F;
            border: none;
            margin: 0px;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: #55514E;
            border-radius: 6px;
            min-height: 34px;
            min-width: 34px;
        }}
        QComboBox, QPushButton {{
            background: #3A3A3A;
            color: {COLORS['fg']};
            border: 1px solid #555;
            border-radius: 9px;
            padding: 3px 7px;
        }}
        QPushButton:hover, QComboBox:hover {{
            background: #454545;
        }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
    """)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Ubuntu System Monitor")
    pg.setConfigOptions(antialias=True)
    apply_style(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
