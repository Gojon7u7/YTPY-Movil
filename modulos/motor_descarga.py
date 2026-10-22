import os
import re
import sys
import stat
import shutil
import subprocess
import yt_dlp


_POPEN_ORIGINAL = subprocess.Popen


class MotorDescargaMovil:
    """
    Motor de extracción y descarga para Android 10+ y PC.
    Incluye redirección de subprocesos en Android para ejecutar libffmpeg.so
    y libffprobe.so desde la partición nativa autorizada del APK.
    """

    def __init__(self, ruta_datos_privados: str):
        self.ruta_datos_privados = ruta_datos_privados
        self.es_android = (
            "ANDROID_ARGUMENT" in os.environ
            or "ANDROID_ROOT" in os.environ
            or (sys.platform == "linux" and os.path.exists("/storage/emulated/0"))
        )

        carpeta_scripts_venv = os.path.dirname(sys.executable)
        if carpeta_scripts_venv and carpeta_scripts_venv not in os.environ.get("PATH", ""):
            os.environ["PATH"] = carpeta_scripts_venv + os.pathsep + os.environ.get("PATH", "")

        self.ruta_descargas = self._configurar_carpeta_descargas()
        self.ruta_archivo_cookies = os.path.join(self.ruta_datos_privados, "cookies_youtube.txt")
        self.mapa_binarios_android = {}
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

    def _activar_interceptor_popen_android(self, ruta_real_ffmpeg: str, ruta_real_ffprobe: str):
        """
        En Android 10+, yt-dlp exige que los archivos se llamen 'ffmpeg' y 'ffprobe',
        pero Android solo permite ejecutar archivos llamados 'lib*.so' en la carpeta nativa.
        Este interceptor traduce en tiempo real cualquier llamada de 'ffmpeg' -> 'libffmpeg.so'
        y 'ffprobe' -> 'libffprobe.so'.
        """
        class PopenPuenteAndroid(_POPEN_ORIGINAL):
            def __init__(self_popen, args, *pargs, **kwargs):
                if isinstance(args, (list, tuple)) and len(args) > 0:
                    ejecutable = str(args[0])
                    nombre_base = os.path.basename(ejecutable).lower()
                    if nombre_base in ("ffmpeg", "libffmpeg.so") and os.path.exists(ruta_real_ffmpeg):
                        args = [ruta_real_ffmpeg] + list(args[1:])
                    elif nombre_base in ("ffprobe", "libffprobe.so") and os.path.exists(ruta_real_ffprobe):
                        args = [ruta_real_ffprobe] + list(args[1:])
                elif isinstance(args, str):
                    if "ffmpeg" in args and os.path.exists(ruta_real_ffmpeg):
                        args = args.replace("ffmpeg", ruta_real_ffmpeg, 1)
                super().__init__(args, *pargs, **kwargs)

        subprocess.Popen = PopenPuenteAndroid

        # Forzar permisos de lectura/ejecución para el detector os.access de yt-dlp
        acceso_original = os.access

        def acceso_puente(ruta, modo, *args, **kwargs):
            nombre = os.path.basename(str(ruta)).lower()
            if nombre in ("ffmpeg", "ffprobe", "libffmpeg.so", "libffprobe.so"):
                return True
            return acceso_original(ruta, modo, *args, **kwargs)

        os.access = acceso_puente

    def _configurar_binarios_nativos(self) -> str:
        """
        Localiza libffmpeg.so y libffprobe.so en Android y prepara la carpeta puente
        para que yt-dlp supere su validación y ejecute los binarios nativos.
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
                    origen_ffmpeg = os.path.join(carpeta_nativa, "libffmpeg.so")
                    origen_ffprobe = os.path.join(carpeta_nativa, "libffprobe.so")
                    if not os.path.exists(origen_ffprobe):
                        origen_ffprobe = origen_ffmpeg

                    # Crear archivos marcadores llamados exactamente 'ffmpeg' y 'ffprobe'
                    # (NO symlinks, para que os.path.realpath no les cambie el nombre a .so)
                    carpeta_puente = os.path.join(self.ruta_datos_privados, "bin_puente")
                    os.makedirs(carpeta_puente, exist_ok=True)

                    for nombre_bin in ("ffmpeg", "ffprobe"):
                        ruta_marcador = os.path.join(carpeta_puente, nombre_bin)
                        if os.path.lexists(ruta_marcador):
                            try:
                                os.remove(ruta_marcador)
                            except Exception:
                                pass
                        with open(ruta_marcador, "wb") as f:
                            f.write(b"#!/system/bin/sh\n")
                        try:
                            os.chmod(ruta_marcador, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
                        except Exception:
                            pass

                    self._activar_interceptor_popen_android(origen_ffmpeg, origen_ffprobe)

                    if carpeta_puente not in os.environ.get("PATH", ""):
                        os.environ["PATH"] = carpeta_puente + os.pathsep + os.environ.get("PATH", "")

                    return carpeta_puente
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
        enlace_limpio = self._limpiar_enlace_youtube(enlace_url)

        estrategias = [
            # Estrategia 1: android_vr (El cliente que desbloqueó tus 4 calidades en el video)
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_vr']
                    }
                }
            },
            # Estrategia 2: android_creator
            {
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_creator']
                    }
                }
            },
            # Estrategia 3: Cliente nativo por defecto
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
                texto_err = str(error).lower()
                # Si el error ocurrió en FFmpeg/Postprocesador (después de descargar),
                # NO repetir la descarga desde cero con otro cliente
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
