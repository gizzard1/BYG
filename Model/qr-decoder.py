"""Decodificador QR (qreader) con soporte macOS/Homebrew.

Requisitos:
  - brew install zbar
  - pip install qreader opencv-python

Nota macOS:
  pyzbar usa ctypes.util.find_library('zbar'). En Homebrew (Apple Silicon)
  la librería queda en /opt/homebrew/opt/zbar/lib y find_library no la ve
  si DYLD_LIBRARY_PATH está vacío. Por eso la añadimos antes del import.
"""

import os
import platform
from ctypes.util import find_library

import cv2

import time

def _ensure_zbar_on_dyld_path() -> None:
	if platform.system() != "Darwin":
		return

	# Si ya la encuentra, no tocamos nada
	if find_library("zbar"):
		return

	candidatos = [
		"/opt/homebrew/opt/zbar/lib",  # Apple Silicon
		"/usr/local/opt/zbar/lib",  # Intel
	]

	for libdir in candidatos:
		if os.path.isdir(libdir):
			actual = os.environ.get("DYLD_LIBRARY_PATH", "")
			paths = [p for p in actual.split(":") if p]
			if libdir not in paths:
				os.environ["DYLD_LIBRARY_PATH"] = ":".join([libdir] + paths)
			break


_ensure_zbar_on_dyld_path()

from qreader import QReader  # noqa: E402


def recorte_inferior_izquierdo_rgb(bgr: "cv2.Mat"):
	"""Devuelve el cuadrante inferior izquierdo en RGB."""
	h, w = bgr.shape[:2]
	mx, my = w // 2, h // 2
	crop_bgr = bgr[my:h, 0:mx]
	return cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)


paths = ["../dataset/IMG_1225.png","../dataset/IMG_1210.png","../dataset/IMG_1221.png","../dataset/IMG_1216.png"]

for img_path in paths:
    start = time.time()
    bgr = cv2.imread(img_path)
    if bgr is None:
        raise FileNotFoundError(f"No se pudo leer la imagen: {img_path}")

    image_rgb = recorte_inferior_izquierdo_rgb(bgr)

    qreader = QReader()
    text = qreader.detect_and_decode(image_rgb)
    end = time.time()

    print(f"Contenido del QR: {text} de la imagen. Tiempo: {end - start:.2f}")
