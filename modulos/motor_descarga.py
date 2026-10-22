import os
import re
import sys
import shutil
import yt_dlp


class MotorDescargaMovil:
    """
    Motor completo de extracción y descarga para Android 10+ y PC.
    Conecta automáticamente deno.exe en PC, libffmpeg.so en Android y
    ejecuta un escudo en cascada para garantizar 1080p/60FPS y 4K.
    """

    def __init__(self, ruta_datos_privados: str):
        self.ruta_datos_privados = ruta_datos_privados
        self.es_android = (
            "ANDROID_ARGUMENT" in os.environ
            or "ANDROID_ROOT" in os.environ
            or (sys.platform == "linux" and os.path.exists("/storage/emulated/0"))
        )

        # CRÍTICO EN PC: Inyectar la carpeta Scripts del .venv en el PATH para que yt-dlp
        # encuentre siempre a deno.exe y desbloquee 1080p/4K al ejecutar desde VS Code
        carpeta_scripts_venv = os.path.dirname(sys.executable)
        if carpeta_scripts_venv and carpeta_scripts_venv not in os.environ.get("PATH", ""):
            os.environ["PATH"] = carpeta_scripts_venv + os.pathsep + os.environ.get("PATH", "")

        self.ruta_descargas = self._configurar_carpeta_descargas()
        self.ruta_archivo_cookies = os.path.join(self.ruta_datos_privados, "cookies_youtube.txt")
        self.ruta_ffmpeg = self._localizar_ffmpeg()

    def _configurar_carpeta_descargas(self) -> str:
        """
        En Android intenta usar la carpeta pública Download/YTPY. Si el sistema
        restringe el acceso, verifica que realmente sea escribible.
        """
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

    def _localizar_ffmpeg(self) -> str:
        """
        En Android localiza libffmpeg.so en la carpeta nativa del APK y la añade al PATH.
        En PC localiza ffmpeg.exe en el sistema o en los paquetes de Winget.
        """
        if self.es_android and os.path.exists("/proc/self/maps"):
            try:
                with open("/proc/self/maps", "r", encoding="utf-8") as mapa:
                    for linea in mapa:
                        if "/lib/" in linea and ".so" in linea:
                            partes = linea.strip().split(" ")
                            ruta_so = partes[-1]
                            carpeta_nativa = os.path.dirname(ruta_so)
                            posible_ffmpeg = os.path.join(carpeta_nativa, "libffmpeg.so")
                            if os.path.exists(posible_ffmpeg):
                                if carpeta_nativa not in os.environ.get("PATH", ""):
                                    os.environ["PATH"] = carpeta_nativa + os.pathsep + os.environ.get("PATH", "")
                                return posible_ffmpeg
            except Exception:
                pass

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
        """
        Limpia parámetros de rastreo (?si=...) de los enlaces compartidos desde
        la app móvil de YouTube para evitar fallos de extracción.
        """
        enlace = enlace.strip()
        coincidencia_corta = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', enlace)
        if coincidencia_corta:
            video_id = coincidencia_corta.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"
        return enlace

    def guardar_cookies_texto(self, contenido_netscape: str):
        with open(self.ruta_archivo_cookies, "w", encoding="utf-8") as archivo:
            archivo.write(contenido_netscape.strip())

    def tiene_cookies_configuradas(self) -> bool:
        return os.path.exists(self.ruta_archivo_cookies) and os.path.getsize(self.ruta_archivo_cookies) > 20

    def _limpiar_ansi(self, texto: str) -> str:
        return re.compile(r'\x1b\[[0-9;]*m').sub('', str(texto)).strip()

    def _ejecutar_con_escudo_antibloqueo(self, enlace_url: str, opciones_base: dict, descargar: bool):
        """
        Ejecuta una cascada de estrategias verificando que realmente se desbloqueen
        las resoluciones de Alta Definición (720p / 1080p / 60FPS / 4K) y no solo 360p.
        """
        enlace_limpio = self._limpiar_enlace_youtube(enlace_url)

        estrategias = [
            # Estrategia 1: Cliente Android VR + Web (Desbloquea 1080p 60FPS en Android y PC sin PO Token)
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_vr', 'web', 'tv_embedded']
                    }
                }
            },
            # Estrategia 2: Cliente nativo por defecto (En PC usa Deno automáticamente)
            {},
            # Estrategia 3: Clientes alternativos para videos restringidos
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['tv', 'mweb', 'android_creator']
                    }
                }
            },
        ]

        # En PC, añadir como último respaldo las cookies de Firefox
        if not self.es_android:
            estrategias.append({'cookiesfrombrowser': ('firefox',)})

        ultimo_error = None
        info_respaldo_360p = None

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
                        # Comprobar si esta estrategia desbloqueó resoluciones HD (>= 720p)
                        tiene_hd = any(
                            (f.get('height') or 0) >= 720 and f.get('vcodec', 'none') != 'none'
                            for f in info.get('formats', [])
                        )
                        if tiene_hd:
                            return info
                        info_respaldo_360p = info
            except Exception as error:
                ultimo_error = error
                continue

        if info_respaldo_360p:
            return info_respaldo_360p
        raise ultimo_error or Exception("No se pudieron obtener los formatos del video.")

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
                funcion_progreso(1.0, "---", "00:00", "Uniendo y procesando archivo final...")

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
            if self.ruta_ffmpeg:
                opciones['format'] = (
                    f"bestvideo[height={altura}][ext=mp4]+bestaudio[ext=m4a]/"
                    f"bestvideo[height={altura}]+bestaudio/"
                    f"best[height={altura}]/"
                    f"bestvideo[height<={altura}]+bestaudio/best"
                )
                opciones['merge_output_format'] = 'mp4'
            else:
                opciones['format'] = f"best[height<={altura}][ext=mp4]/best[ext=mp4]/best"

            opciones['outtmpl'] = os.path.join(self.ruta_descargas, '%(title)s [%(height)sp].%(ext)s')

        elif modo_formato == "MP3":
            if self.ruta_ffmpeg:
                opciones['format'] = 'bestaudio/best'
                opciones['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': str(valor_calidad),
                }]
                opciones['outtmpl'] = os.path.join(self.ruta_descargas, f'%(title)s [MP3 {valor_calidad}kbps].%(ext)s')
            else:
                # Si en algún emulador no cargó FFmpeg, descarga el audio directo en m4a sin dar error
                opciones['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
                opciones['outtmpl'] = os.path.join(self.ruta_descargas, '%(title)s [Audio].%(ext)s')

        elif modo_formato == "FLAC":
            if self.ruta_ffmpeg:
                opciones['format'] = 'bestaudio/best'
                opciones['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'flac',
                }]
                opciones['outtmpl'] = os.path.join(self.ruta_descargas, '%(title)s [FLAC Lossless].%(ext)s')
            else:
                opciones['format'] = 'bestaudio/best'
                opciones['outtmpl'] = os.path.join(self.ruta_descargas, '%(title)s [Audio Lossless].%(ext)s')

        try:
            self._ejecutar_con_escudo_antibloqueo(enlace_url, opciones, descargar=True)
            funcion_completado(self.ruta_descargas)
        except Exception as e:
            funcion_error(self._limpiar_ansi(str(e)))
