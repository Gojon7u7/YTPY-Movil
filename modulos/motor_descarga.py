import os
import re
import sys
import shutil
import yt_dlp


class MotorDescargaMovil:
    """
    Motor de extracción y descarga para Android 10+ y PC.
    Enlaza libffmpeg.so y libdeno.so en Android y aísla los clientes
    para evitar el error 'The page needs to be reloaded'.
    """

    def __init__(self, ruta_datos_privados: str):
        self.ruta_datos_privados = ruta_datos_privados
        self.es_android = (
            "ANDROID_ARGUMENT" in os.environ
            or "ANDROID_ROOT" in os.environ
            or (sys.platform == "linux" and os.path.exists("/storage/emulated/0"))
        )

        # En PC: asegurar que la carpeta Scripts del entorno virtual esté en el PATH
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

    def _configurar_binarios_nativos(self) -> str:
        """
        En Android localiza la carpeta nativa (/data/app/.../lib/arm64) donde están
        libffmpeg.so y libdeno.so, y crea enlaces simbólicos llamados 'ffmpeg' y 'deno'
        para que yt-dlp los reconozca por su nombre estándar.
        """
        if self.es_android and os.path.exists("/proc/self/maps"):
            try:
                carpeta_nativa = None
                with open("/proc/self/maps", "r", encoding="utf-8") as mapa:
                    for linea in mapa:
                        if "/lib/" in linea and ".so" in linea:
                            ruta_so = linea.strip().split(" ")[-1]
                            posible_dir = os.path.dirname(ruta_so)
                            if os.path.exists(os.path.join(posible_dir, "libffmpeg.so")):
                                carpeta_nativa = posible_dir
                                break

                if carpeta_nativa:
                    # Crear carpeta puente con enlaces simbólicos llamados 'ffmpeg' y 'deno'
                    carpeta_puente = os.path.join(self.ruta_datos_privados, "bin_puente")
                    os.makedirs(carpeta_puente, exist_ok=True)

                    origen_ffmpeg = os.path.join(carpeta_nativa, "libffmpeg.so")
                    enlace_ffmpeg = os.path.join(carpeta_puente, "ffmpeg")
                    if os.path.exists(origen_ffmpeg):
                        if os.path.lexists(enlace_ffmpeg):
                            os.remove(enlace_ffmpeg)
                        os.symlink(origen_ffmpeg, enlace_ffmpeg)

                    origen_deno = os.path.join(carpeta_nativa, "libdeno.so")
                    enlace_deno = os.path.join(carpeta_puente, "deno")
                    if os.path.exists(origen_deno):
                        if os.path.lexists(enlace_deno):
                            os.remove(enlace_deno)
                        os.symlink(origen_deno, enlace_deno)

                    for dir_bin in [carpeta_puente, carpeta_nativa]:
                        if dir_bin not in os.environ.get("PATH", ""):
                            os.environ["PATH"] = dir_bin + os.pathsep + os.environ.get("PATH", "")

                    if os.path.exists(enlace_ffmpeg):
                        return enlace_ffmpeg
                    return origen_ffmpeg
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
        enlace = enlace.strip()
        coincidencia_corta = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', enlace)
        if coincidencia_corta:
            return f"https://www.youtube.com/watch?v={coincidencia_corta.group(1)}"
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
        Prueba cada cliente de forma individual y aislada (sin mezclar con tv_embedded)
        para que ningún cliente secundario dispare 'The page needs to be reloaded'.
        """
        enlace_limpio = self._limpiar_enlace_youtube(enlace_url)

        estrategias = [
            # Estrategia 1: android_vr en solitario (Desbloquea 1080p/60FPS directo en Android y PC)
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_vr']
                    }
                }
            },
            # Estrategia 2: Cliente nativo con Deno en segundo plano
            {},
            # Estrategia 3: Cliente Android Creator en solitario
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_creator']
                    }
                }
            },
            # Estrategia 4: Cliente Web Móvil (mweb) en solitario
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['mweb']
                    }
                }
            },
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
                        formatos_validos = [
                            f for f in info.get('formats', [])
                            if f.get('height') is not None and f.get('vcodec', 'none') != 'none'
                        ]
                        tiene_hd = any((f.get('height') or 0) >= 720 for f in formatos_validos)
                        if tiene_hd:
                            return info
                        if formatos_validos and not info_respaldo:
                            info_respaldo = info
            except Exception as error:
                ultimo_error = error
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
