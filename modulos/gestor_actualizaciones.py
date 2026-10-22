import os
import json
import shutil
import zipfile
from io import BytesIO
import requests


class GestorActualizacionesMovil:
    """
    Mantiene yt-dlp y yt-dlp-ejs actualizados para el siguiente inicio de la app
    sin interrumpir ni corromper las descargas en curso.
    """

    def __init__(self, ruta_datos_app: str):
        self.ruta_datos_app = ruta_datos_app
        self.ruta_librerias = os.path.join(self.ruta_datos_app, "herramientas", "librerias")
        self.ruta_temporal = os.path.join(self.ruta_datos_app, "herramientas", "temp_update")
        self.archivo_versiones = os.path.join(self.ruta_datos_app, "herramientas", "versiones.json")
        os.makedirs(self.ruta_librerias, exist_ok=True)

    def _leer_versiones(self) -> dict:
        if os.path.exists(self.archivo_versiones):
            try:
                with open(self.archivo_versiones, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"yt-dlp": "", "yt-dlp-ejs": ""}

    def _guardar_versiones(self, datos: dict):
        try:
            with open(self.archivo_versiones, "w", encoding="utf-8") as f:
                json.dump(datos, f, indent=4)
        except Exception:
            pass

    def verificar_y_actualizar_silenciosamente(self):
        versiones = self._leer_versiones()
        self._actualizar_paquete_pypi("yt-dlp", versiones)
        self._actualizar_paquete_pypi("yt-dlp-ejs", versiones)
        self._guardar_versiones(versiones)

    def _actualizar_paquete_pypi(self, nombre_paquete: str, registro: dict) -> bool:
        try:
            respuesta = requests.get(f"https://pypi.org/pypi/{nombre_paquete}/json", timeout=10)
            if respuesta.status_code != 200:
                return False

            datos = respuesta.json()
            version_remota = datos["info"]["version"]
            version_local = registro.get(nombre_paquete, "")

            carpeta_modulo = os.path.join(self.ruta_librerias, nombre_paquete.replace("-", "_"))
            if version_remota == version_local and os.path.exists(carpeta_modulo):
                return False

            url_wheel = None
            for archivo in datos.get("urls", []):
                if archivo.get("packagetype") == "bdist_wheel" and archivo.get("filename", "").endswith(".whl"):
                    url_wheel = archivo.get("url")
                    break

            if not url_wheel:
                return False

            descarga = requests.get(url_wheel, timeout=30)
            shutil.rmtree(self.ruta_temporal, ignore_errors=True)
            os.makedirs(self.ruta_temporal, exist_ok=True)

            with zipfile.ZipFile(BytesIO(descarga.content)) as zf:
                zf.extractall(self.ruta_temporal)

            for item in os.listdir(self.ruta_temporal):
                origen = os.path.join(self.ruta_temporal, item)
                destino = os.path.join(self.ruta_librerias, item)
                if os.path.isdir(origen):
                    shutil.rmtree(destino, ignore_errors=True)
                    shutil.move(origen, destino)
                else:
                    shutil.move(origen, destino)

            shutil.rmtree(self.ruta_temporal, ignore_errors=True)
            registro[nombre_paquete] = version_remota
            return True
        except Exception:
            return False
