import os
import re
import sys
import shutil
import yt_dlp


class MotorDescargaMovil:
    """
    Motor de extracción y descarga anti-bloqueo optimizado para Android 10+ y PC.
    """

    def __init__(self, ruta_datos_privados: str):
        self.ruta_datos_privados = ruta_datos_privados
        self.es_android = (
            "ANDROID_ARGUMENT" in os.environ
            or "ANDROID_ROOT" in os.environ
            or sys.platform == "linux" and os.path.exists("/storage/emulated/0")
        )

        self.ruta_descargas = self._configurar_carpeta_descargas()
        self.ruta_archivo_cookies = os.path.join(self.ruta_datos_privados, "cookies_youtube.txt")
        self.ruta_ffmpeg = self._localizar_ffmpeg()

    def _configurar_carpeta_descargas(self) -> str:
        if self.es_android:
            try:
                ruta_publica = "/storage/emulated/0/Download/YTPY"
                os.makedirs(ruta_publica, exist_ok=True)
                return ruta_publica
            except Exception:
                pass
        ruta_local = os.path.join(self.ruta_datos_privados, "descargas")
        os.makedirs(ruta_local, exist_ok=True)
        return ruta_local

    def _localizar_ffmpeg(self) -> str:
        if self.es_android and os.path.exists("/proc/self/maps"):
            try:
                with open("/proc/self/maps", "r", encoding="utf-8") as mapa:
                    for linea in mapa:
                        if "/lib/arm64" in linea and ".so" in linea:
                            ruta_so = linea.strip().split(" ")[-1]
                            posible_ffmpeg = os.path.join(os.path.dirname(ruta_so), "libffmpeg.so")
                            if os.path.exists(posible_ffmpeg):
                                return posible_ffmpeg
            except Exception:
                pass

        ruta_sistema = shutil.which("ffmpeg")
        if ruta_sistema:
            return ruta_sistema

        appdata = os.environ.get("LOCALAPPDATA", "")
        ruta_winget = os.path.join(appdata, "Microsoft", "WinGet", "Packages")
        if os.path.exists(ruta_winget):
            for raiz, _, archivos in os.walk(ruta_winget):
                if "ffmpeg.exe" in archivos:
                    return os.path.join(raiz, "ffmpeg.exe")
        return None

    def guardar_cookies_texto(self, contenido_netscape: str):
        with open(self.ruta_archivo_cookies, "w", encoding="utf-8") as archivo:
            archivo.write(contenido_netscape.strip())

    def tiene_cookies_configuradas(self) -> bool:
        return os.path.exists(self.ruta_archivo_cookies) and os.path.getsize(self.ruta_archivo_cookies) > 20

    def _limpiar_ansi(self, texto: str) -> str:
        return re.compile(r'\x1b\[[0-9;]*m').sub('', str(texto)).strip()

    def _obtener_opciones_base(self) -> dict:
        opciones = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'socket_timeout': 30,
            'retries': 15,
            'fragment_retries': 15,
            'nocheckcertificate': True,
            # Forzar cliente android_creator y web para evitar error 403 y restricciones de formato
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_creator', 'web', 'mweb']
                }
            }
        }
        if self.ruta_ffmpeg:
            opciones['ffmpeg_location'] = self.ruta_ffmpeg
        if self.tiene_cookies_configuradas():
            opciones['cookiefile'] = self.ruta_archivo_cookies
        return opciones

    def obtener_informacion_video(self, enlace_url: str) -> dict:
        opciones = self._obtener_opciones_base()
        opciones['extract_flat'] = False
        opciones['ignore_no_formats_error'] = True

        with yt_dlp.YoutubeDL(opciones) as extractor:
            info = extractor.extract_info(enlace_url, download=False)

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
        def gancho_progreso(datos):
            if datos['status'] == 'downloading':
                descargado = datos.get('downloaded_bytes', 0)
                total = datos.get('total_bytes') or datos.get('total_bytes_estimate', 0)
                porcentaje = (descargado / total) if total > 0 else 0.0
                velocidad = self._limpiar_ansi(datos.get('_speed_str', '...'))
                eta = self._limpiar_ansi(datos.get('_eta_str', '--:--'))
                funcion_progreso(porcentaje, velocidad, eta, "Descargando...")
            elif datos['status'] == 'finished':
                funcion_progreso(1.0, "---", "00:00", "Procesando archivo final con FFmpeg...")

        opciones = self._obtener_opciones_base()
        opciones['overwrites'] = True
        opciones['progress_hooks'] = [gancho_progreso]
        opciones['nocolor'] = True
        opciones['continuedl'] = True

        if modo_formato == "MP4":
            altura = int(valor_calidad)
            if self.ruta_ffmpeg:
                opciones['format'] = (
                    f"bestvideo[height={altura}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height={altura}]+bestaudio/"
                    f"best[height={altura}]/best"
                )
                opciones['merge_output_format'] = 'mp4'
            else:
                opciones['format'] = f"best[height<={altura}][ext=mp4]/best"

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
            with yt_dlp.YoutubeDL(opciones) as ydl:
                ydl.download([enlace_url])
            funcion_completado(self.ruta_descargas)
        except Exception as e:
            funcion_error(self._limpiar_ansi(str(e)))
