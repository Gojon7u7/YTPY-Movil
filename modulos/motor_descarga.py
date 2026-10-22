import os
import re
import sys
import shutil
import yt_dlp


class MotorDescargaMovil:
    """
    Motor de extracción y descarga adaptado para Android 10+ y PC.
    Incluye evasión de bloqueos de YouTube y detección de libffmpeg.so.
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
        """
        Apunta a la carpeta pública 'Download/YTPY' en Android para que los videos
        y canciones aparezcan de inmediato en la Galería y reproductores del móvil.
        """
        if self.es_android:
            ruta_publica = "/storage/emulated/0/Download/YTPY"
            try:
                os.makedirs(ruta_publica, exist_ok=True)
                return ruta_publica
            except Exception:
                pass

        # Respaldo o modo prueba en PC
        ruta_local = os.path.join(self.ruta_datos_privados, "descargas")
        os.makedirs(ruta_local, exist_ok=True)
        return ruta_local

    def _localizar_ffmpeg(self) -> str:
        """
        En Android 10+, rastrea la carpeta nativa del APK (/data/app/.../lib/arm64/)
        usando /proc/self/maps para encontrar el binario 'libffmpeg.so'.
        """
        if self.es_android and os.path.exists("/proc/self/maps"):
            try:
                with open("/proc/self/maps", "r", encoding="utf-8") as mapa:
                    for linea in mapa:
                        if "/lib/arm64" in linea and ".so" in linea:
                            partes = linea.strip().split(" ")
                            ruta_so = partes[-1]
                            carpeta_nativa = os.path.dirname(ruta_so)
                            posible_ffmpeg = os.path.join(carpeta_nativa, "libffmpeg.so")
                            if os.path.exists(posible_ffmpeg):
                                return posible_ffmpeg
            except Exception:
                pass

        # En PC (durante pruebas locales) busca en el sistema o Winget
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
        """Guarda cookies en formato Netscape para desbloquear videos +18 o restringidos."""
        with open(self.ruta_archivo_cookies, "w", encoding="utf-8") as archivo:
            archivo.write(contenido_netscape.strip())

    def tiene_cookies_configuradas(self) -> bool:
        return os.path.exists(self.ruta_archivo_cookies) and os.path.getsize(self.ruta_archivo_cookies) > 20

    def _limpiar_ansi(self, texto: str) -> str:
        return re.compile(r'\x1b\[[0-9;]*m').sub('', str(texto)).strip()

    def _ejecutar_con_escudo_antibloqueo(self, enlace_url: str, opciones_base: dict, descargar: bool):
        """
        Prueba múltiples identidades de cliente para evitar 'Acceso Denegado',
        'Sign in to confirm you are not a bot' o el límite de 360p.
        """
        estrategias_clientes = [
            # Estrategia 1: Cliente Android VR + TV Embedded (desbloquea 1080p/4K sin PO Token)
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_vr', 'tv_embedded']
                    }
                }
            },
            # Estrategia 2: Clientes móviles iOS + MWeb
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['ios', 'mweb']
                    }
                }
            },
            # Estrategia 3: Cliente Android Creator / Web estándar
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_creator', 'web']
                    }
                }
            }
        ]

        ultimo_error = None
        info_respaldo = None

        for estrategia in estrategias_clientes:
            opciones = dict(opciones_base)
            opciones.update(estrategia)

            # Si el usuario cargó cookies para videos +18, inyectarlas
            if self.tiene_cookies_configuradas():
                opciones['cookiefile'] = self.ruta_archivo_cookies

            try:
                with yt_dlp.YoutubeDL(opciones) as extractor:
                    info = extractor.extract_info(enlace_url, download=descargar)
                    if descargar:
                        return info

                    if info and info.get('formats'):
                        hay_hd = any((f.get('height') or 0) >= 720 for f in info.get('formats', []))
                        if hay_hd:
                            return info
                        info_respaldo = info
            except Exception as error:
                ultimo_error = error
                continue

        if info_respaldo:
            return info_respaldo
        raise ultimo_error or Exception("No se pudo conectar con el video.")

    def obtener_informacion_video(self, enlace_url: str) -> dict:
        opciones = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'noplaylist': True,
            'ignore_no_formats_error': True,
            'socket_timeout': 30,
            'retries': 10,
            'nocheckcertificate': True,
        }

        if self.ruta_ffmpeg:
            opciones['ffmpeg_location'] = self.ruta_ffmpeg

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
            'continuedl': True,
        }

        if self.ruta_ffmpeg:
            opciones['ffmpeg_location'] = self.ruta_ffmpeg

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
            self._ejecutar_con_escudo_antibloqueo(enlace_url, opciones, descargar=True)
            funcion_completado(self.ruta_descargas)
        except Exception as e:
            funcion_error(self._limpiar_ansi(str(e)))
