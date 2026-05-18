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
import sys
import json

import cv2

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


def obtener_ruta_imagen() -> str:
	"""Obtiene la ruta desde argv o stdin JSON/texto."""
	if len(sys.argv) > 1 and sys.argv[1]:
		return sys.argv[1]

	stdin_content = sys.stdin.read().strip()
	if not stdin_content:
		raise ValueError("No se recibió ruta de imagen")

	try:
		data = json.loads(stdin_content)
		if isinstance(data, str):
			return data
		if isinstance(data, dict):
			return data.get("img_path") or data.get("imagePath") or data.get("path")
	except json.JSONDecodeError:
		# Si no es JSON, asumimos que stdin trae la ruta en texto plano
		return stdin_content

	raise ValueError("No se pudo obtener la ruta de imagen")

if __name__ == '__main__':
	try:
		img_path = obtener_ruta_imagen()

		bgr = cv2.imread(img_path)
		if bgr is None:
			raise FileNotFoundError(f"No se pudo leer la imagen: {img_path}")

		image_rgb = recorte_inferior_izquierdo_rgb(bgr)

		qreader = QReader()
		text = qreader.detect_and_decode(image_rgb)

		if isinstance(text, list):
			text = next((item for item in text if item), "")

		print(text or "")
	except Exception as e:
		print("ERROR:", str(e), file=sys.stderr)
		sys.exit(1)
