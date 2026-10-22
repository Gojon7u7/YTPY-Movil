import os
import re
import sys
import shutil
import subprocess

# =============================================================================
# INTERCEPTOR DE SUBPROCESOS (ANTES DE IMPORTAR YT-DLP)
# =============================================================================
_POPEN_ORIGINAL = subprocess.Popen
_ACCESO_ORIGINAL = os.access
_MAPA_BINARIOS_ANDROID = {
    "ffmpeg": None,
    "ffprobe": None,
}


class _PopenPuenteGlobal(_POPEN_ORIGINAL):
    def __init__(self, args, *pargs, **kwargs):
        if isinstance(args, (list, tuple)) and len(args) > 0:
            ejecutable = str(args[0])
            nombre_base = os.path.basename(ejecutable).lower()
            if nombre_base in ("ffmpeg", "libffmpeg.so") and _MAPA_BINARIOS_ANDROID.get("ffmpeg"):
                args = [_MAPA_BINARIOS_ANDROID["ffmpeg"]] + list(args[1:])
            elif nombre_base in ("ffprobe", "libffprobe.so") and _MAPA_BINARIOS_ANDROID.get("ffprobe"):
                args = [_MAPA_BINARIOS_ANDROID["ffprobe"]] + list(args[1:])
        super().__init__(args, *pargs, **kwargs)


def _acceso_puente_global(ruta, modo, *args, **kwargs):
    nombre = os.path.basename(str(ruta)).lower()
    if nombre in ("ffmpeg", "ffprobe", "libffmpeg.so", "libffprobe.so"):
        return True
    return _ACCESO_ORIGINAL(ruta, modo, *args, **kwargs)


subprocess.Popen = _PopenPuenteGlobal
os.access = _acceso_puente_global

# Importar yt_dlp DESPUÉS de asignar subprocess.Popen para que herede el puente
# manteniendo intacto su método interno Popen.run()
import yt_dlp


class MotorDescargaMovil:
    """
    Motor de extracción y descarga para Android 10+ (ARM64 y Emulador x86_64) y PC.
    """

    def __init__(self, ruta_datos_privados: str):
        self.ruta_datos_privados = ruta_datos_privados
        self.es_android = (
            "ANDROID_ARGUMENT" in os.environ
            or "ANDROID_ROOT" in os.environ
            or (sys.platform == "linux" and os.path.exists("/data/user/0"))
        )

        if not self.es_android:
            carpeta_scripts_venv = os.path.dirname(sys.executable)
            if carpeta_scripts_venv and carpeta_scripts_venv not in os.environ.get("PATH", ""):
                os.environ["PATH"] = carpeta_scripts_venv + os.pathsep + os.environ.get("PATH", "")

        self.ruta_descargas = self._configurar_carpeta_descargas()
        self.ruta_archivo_cookies = os.path.join(self.ruta_datos_privados, "cookies_youtube.txt")
        self.ruta_ffmpeg = self._configurar_binarios_nativos()

    def _configurar_carpeta_descargas(self) -> str:
        if self.es_android:
            rutas_candidatas = [
                "/storage/emulated/0/Download/YTPY",
                "/sdcard/Download/YTPY",
            ]
            for ruta in rutas_candidatas:
                try:
                    os.makedirs(ruta, exist_ok=True)
                    archivo_prueba = os.path.join(ruta, ".test_escritura")
                    with open(archivo_prueba, "w", encoding="utf-8") as f:
                        f.write("ok")
                    os.remove(archivo_prueba)
                    return ruta
                except Exception:
                    continue

        ruta_local = os.path.join(self.ruta_datos_privados, "descargas")
        os.makedirs(ruta_local, exist_ok=True)
        return ruta_local

    def _buscar_carpeta_lib_android(self) -> str:
        """
        Rastrea la carpeta de instalación de la app en /data/app/ para encontrar
        libffmpeg.so sin importar si es ARM64 (celular) o x86_64 (emulador LDPlayer).
        """
        raices_app = set()

        if os.path.exists("/proc/self/maps"):
            try:
                with open("/proc/self/maps", "r", encoding="utf-8") as mapa:
                    for linea in mapa:
                        if "/data/app/" in linea:
                            partes = linea.strip().split(" ")
                            ruta = partes[-1].split("!")[0]
                            # Subir hasta encontrar la carpeta que contiene base.apk o lib
                            actual = os.path.dirname(ruta)
                            for _ in range(4):
                                if os.path.basename(actual).startswith("com.flet") or os.path.exists(os.path.join(actual, "lib")):
                                    raices_app.add(actual)
                                actual = os.path.dirname(actual)
            except Exception:
                pass

        for raiz in raices_app:
            for dir_actual, _, archivos in os.walk(raiz):
                if "libffmpeg.so" in archivos:
                    return dir_actual
        return None

    def _configurar_binarios_nativos(self) -> str:
        if self.es_android:
            try:
                carpeta_puente = os.path.join(self.ruta_datos_privados, "bin_puente")
                shutil.rmtree(carpeta_puente, ignore_errors=True)
                os.makedirs(carpeta_puente, exist_ok=True)

                carpeta_nativa = self._buscar_carpeta_lib_android()
                if carpeta_nativa:
                    origen_ffmpeg = os.path.join(carpeta_nativa, "libffmpeg.so")
                    origen_ffprobe = os.path.join(carpeta_nativa, "libffprobe.so")
                    if not os.path.exists(origen_ffprobe):
                        origen_ffprobe = origen_ffmpeg

                    _MAPA_BINARIOS_ANDROID["ffmpeg"] = origen_ffmpeg
                    _MAPA_BINARIOS_ANDROID["ffprobe"] = origen_ffprobe

                    enlace_ffmpeg = os.path.join(carpeta_puente, "ffmpeg")
                    enlace_ffprobe = os.path.join(carpeta_puente, "ffprobe")

                    os.symlink(origen_ffmpeg, enlace_ffmpeg)
                    os.symlink(origen_ffprobe, enlace_ffprobe)

                    if carpeta_puente not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = carpeta_puente + os.pathsep + os.environ.get("PATH", "")

                    return carpeta_puente
            except Exception:
                pass
            return None

        ruta_sistema = shutil.which("ffmpeg")
        if ruta_sistema:
            return os.path.dirname(ruta_sistema)

        appdata = os.environ.get("LOCALAPPDATA", "")
        ruta_winget = os.path.join(appdata, "Microsoft", "WinGet", "Packages")
        if os.path.exists(ruta_winget):
            for raiz, _, archivos in os.walk(ruta_winget):
                if "ffmpeg.exe" in archivos:
                    if raiz not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = raiz + os.pathsep + os.environ.get("PATH", "")
                    return raiz
        return None

    def _limpiar_enlace_youtube(self, enlace: str) -> str:
        enlace = enlace.strip()
        coincidencia = re.search(r'(?:v=|youtu\.be/|shorts/|embed/)([a-zA-Z0-9_-]{11})', enlace)
        if coincidencia:
            return f"https://www.youtube.com/watch?v={coincidencia.group(1)}"
        return enlace

    def guardar_cookies_texto(self, contenido_netscape: str):
        with open(self.ruta_archivo_cookies, "w", encoding="utf-8") as archivo:
            archivo.write(contenido_netscape.strip())

    def tiene_cookies_configuradas(self) -> bool:
        return os.path.exists(self.ruta_archivo_cookies) and os.path.getsize(self.ruta_archivo_cookies) > 20

    def _limpiar_ansi(self, texto: str) -> str:
        return re.compile(r'\x1b\[[0-9;]*m').sub('', str(texto)).strip()

    def _ejecutar_con_escudo_antibloqueo(self, enlace_url: str, opciones_base: dict, descargar: bool):
        enlace_limpio = self._limpiar_enlace_youtube(enlace_url)

        estrategias = [
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_vr']
                    }
                }
            },
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['ios']
                    }
                }
            },
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_creator']
                    }
                }
            },
            {},
        ]

        if not self.es_android:
            estrategias.append({'cookiesfrombrowser': ('firefox',)})

        ultimo_error = None
        info_respaldo = None

        for config_extra in estrategias:
            opciones = dict(opciones_base)
            opciones.update(config_extra)

            if self.tiene_cookies_configuradas():
                opciones['cookiefile'] = self.ruta_archivo_cookies

            try:
                with yt_dlp.YoutubeDL(opciones) as extractor:
                    info = extractor.extract_info(enlace_limpio, download=descargar)
                    if descargar:
                        return info

                    if info and info.get('formats'):
                        formatos_video = [
                            f for f in info.get('formats', [])
                            if (f.get('height') is not None or f.get('resolution'))
                            and f.get('vcodec', 'none') != 'none'
                            and not str(f.get('vcodec', '')).startswith('images')
                        ]
                        tiene_hd = any((f.get('height') or 0) >= 720 for f in formatos_video)
                        if tiene_hd:
                            return info
                        if formatos_video and not info_respaldo:
                            info_respaldo = info
            except Exception as error:
                ultimo_error = error
                texto_err = str(error).lower()
                if "postprocessing" in texto_err or "ffmpeg" in texto_err or "ffprobe" in texto_err:
                    raise error
                continue

        if info_respaldo:
            return info_respaldo
        raise ultimo_error or Exception("No se pudieron obtener los formatos del video.")

    def obtener_informacion_video(self, enlace_url: str) -> dict:
        opciones = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 10,
            'nocheckcertificate': True,
        }

        info = self._ejecutar_con_escudo_antibloqueo(enlace_url, opciones, descargar=False)
        formatos = info.get('formats', [])
        mapa_resoluciones = {}

        for f in formatos:
            vcodec = f.get('vcodec', 'none')
            altura = f.get('height')
            fps = f.get('fps') or 30

            if altura is None and f.get('resolution'):
                m = re.search(r'x(\d+)', str(f.get('resolution')))
                if m:
                    altura = int(m.group(1))

            if (
                altura is not None
                and vcodec != 'none'
                and not str(vcodec).startswith('images')
                and f.get('resolution') != 'audio only'
                and f.get('ext') != 'mhtml'
            ):
                etiqueta = f"{altura}p ({int(fps)} FPS)" if fps > 30 else f"{altura}p"
                mapa_resoluciones[etiqueta] = altura

        etiquetas_ordenadas = sorted(
            mapa_resoluciones.keys(),
            key=lambda x: (mapa_resoluciones[x], "60 FPS" in x),
            reverse=True
        )

        return {
            'titulo': info.get('title', 'Video sin título'),
            'autor': info.get('uploader', 'Canal desconocido'),
            'duracion_segundos': info.get('duration', 0),
            'url_miniatura': info.get('thumbnail', ''),
            'resoluciones': mapa_resoluciones,
            'lista_etiquetas': etiquetas_ordenadas
        }

    def descargar_multimedia(
        self,
        enlace_url: str,
        modo_formato: str,
        valor_calidad,
        funcion_progreso,
        funcion_completado,
        funcion_error
    ):
        # Reintentar actualizar carpeta de descargas por si el usuario acaba de dar permisos en Ajustes
        self.ruta_descargas = self._configurar_carpeta_descargas()

        def gancho_progreso(datos):
            if datos['status'] == 'downloading':
                descargado = datos.get('downloaded_bytes', 0)
                total = datos.get('total_bytes') or datos.get('total_bytes_estimate', 0)
                porcentaje = (descargado / total) if total > 0 else 0.0
                velocidad = self._limpiar_ansi(datos.get('_speed_str', '...'))
                eta = self._limpiar_ansi(datos.get('_eta_str', '--:--'))
                funcion_progreso(porcentaje, velocidad, eta, "Descargando...")
            elif datos['status'] == 'finished':
                funcion_progreso(1.0, "---", "00:00", "Uniendo y convirtiendo con FFmpeg...")

        opciones = {
            'noplaylist': True,
            'overwrites': True,
            'progress_hooks': [gancho_progreso],
            'quiet': True,
            'no_warnings': True,
            'nocolor': True,
            'nocheckcertificate': True,
            'socket_timeout': 30,
            'retries': 15,
            'fragment_retries': 15,
            'file_access_retries': 5,
            'continuedl': True,
        }

        if self.ruta_ffmpeg:
            opciones['ffmpeg_location'] = self.ruta_ffmpeg

        if modo_formato == "MP4":
            altura = int(valor_calidad)
            opciones['format'] = (
                f"bestvideo[height={altura}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height={altura}]+bestaudio/"
                f"best[height={altura}]/"
                f"bestvideo[height<={altura}]+bestaudio/best"
            )
            opciones['merge_output_format'] = 'mp4'
            opciones['outtmpl'] = os.path.join(self.ruta_descargas, '%(title)s [%(height)sp].%(ext)s')

        elif modo_formato == "MP3":
            opciones['format'] = 'bestaudio/best'
            opciones['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': str(valor_calidad),
            }]
            opciones['outtmpl'] = os.path.join(self.ruta_descargas, f'%(title)s [MP3 {valor_calidad}kbps].%(ext)s')

        elif modo_formato == "FLAC":
            opciones['format'] = 'bestaudio/best'
            opciones['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'flac',
            }]
            opciones['outtmpl'] = os.path.join(self.ruta_descargas, '%(title)s [FLAC Lossless].%(ext)s')

        try:
            self._ejecutar_con_escudo_antibloqueo(enlace_url, opciones, descargar=True)
            funcion_completado(self.ruta_descargas)
        except Exception as e:
            funcion_error(self._limpiar_ansi(str(e)))
