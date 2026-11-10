"""Line icons (SVG, drawn in code) – no image files needed."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# 24x24 stroke icons
PATHS = {
    "open": '<path d="M3 7h6l2 2h10v10H3z"/><path d="M3 7V5h6"/>',
    "save": '<path d="M5 3h12l4 4v14H3V3z"/><path d="M7 3v6h9V3"/><rect x="7" y="13" width="10" height="6"/>',
    "connect": '<path d="M9 7V3M15 7V3"/><path d="M6 7h12v4a6 6 0 0 1-12 0z"/><path d="M12 17v4"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
    "blackout": '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    "fixtures": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "programmer": '<path d="M6 3v18M12 3v18M18 3v18"/><rect x="4" y="13" width="4" height="3" rx="1"/><rect x="10" y="6" width="4" height="3" rx="1"/><rect x="16" y="10" width="4" height="3" rx="1"/>',
    "effects": '<path d="M3 12c2-6 4-6 6 0s4 6 6 0 4-6 6 0"/><circle cx="12" cy="12" r="1"/>',
    "presets": '<circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><circle cx="12" cy="16" r="3"/>',
    "cues": '<path d="M4 6h16M4 12h16M4 18h10"/><path d="M17 16l4 2-4 2z"/>',
    "stage": '<path d="M2 20h20"/><path d="M4 20l3-12h10l3 12"/><path d="M7 4h10"/><path d="M9 4l-2 4M15 4l2 4"/>',
    "patch": '<circle cx="6" cy="6" r="2"/><circle cx="18" cy="18" r="2"/><path d="M8 6h4a4 4 0 0 1 4 4v6"/><circle cx="18" cy="6" r="2"/><path d="M6 8v10h10"/>',
    "dmx": '<path d="M4 20V10M9 20V4M14 20V13M19 20V7"/>',
    "go": '<path d="M7 4l12 8-12 8z"/>',
    "tap": '<path d="M12 3v10"/><circle cx="12" cy="17" r="4"/>',
    "cube": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    "top": '<rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="9" cy="9" r="1.5"/><circle cx="15" cy="13" r="1.5"/>',
    "front": '<path d="M3 20h18"/><path d="M6 20V8h12v12"/><path d="M9 8l-1-4h8l-1 4"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 3-6.2"/><path d="M4 4v4h4"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.8.4-1 1-1 1.7"/><circle cx="12" cy="17" r=".6"/>',
}


def icon(name: str, color: str = "#dfe1e8", size: int = 22) -> QIcon:
    body = PATHS.get(name, PATHS["help"])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for s in (size, size * 2):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        r.render(p, QRectF(0, 0, s, s))
        p.end()
        ic.addPixmap(pm)
    return ic
