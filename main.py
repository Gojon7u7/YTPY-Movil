import os
import sys
import threading
import flet as ft


def obtener_directorio_datos() -> str:
    ruta_flet = os.environ.get("FLET_APP_STORAGE_DATA")
    if ruta_flet:
        os.makedirs(ruta_flet, exist_ok=True)
        return ruta_flet
    return os.path.dirname(os.path.abspath(__file__))


def configurar_librerias_autoactualizables(ruta_datos: str):
    ruta_lib = os.path.join(ruta_datos, "herramientas", "librerias")
    os.makedirs(ruta_lib, exist_ok=True)
    if ruta_lib not in sys.path:
        sys.path.insert(0, ruta_lib)


def main(pagina: ft.Page):
    ruta_datos = obtener_directorio_datos()
    configurar_librerias_autoactualizables(ruta_datos)

    from modulos.motor_descarga import MotorDescargaMovil
    from modulos.gestor_actualizaciones import GestorActualizacionesMovil

    motor = MotorDescargaMovil(ruta_datos)

    pagina.title = "YTPY Studio Mobile"
    pagina.theme_mode = ft.ThemeMode.DARK
    pagina.bgcolor = "#0f0f14"
    pagina.padding = 16
    pagina.scroll = ft.ScrollMode.ADAPTIVE
    pagina.window.width = 420
    pagina.window.height = 820

    estado_app = {
        "datos_video": None,
        "modo_formato": "MP4",
    }

    calidades_mp3 = {
        "320 kbps (Máxima calidad)": "320",
        "256 kbps (Alta calidad)": "256",
        "192 kbps (Estándar)": "192",
        "128 kbps (Ligero)": "128",
    }

    def actualizar_en_segundo_plano():
        try:
            gestor = GestorActualizacionesMovil(ruta_datos)
            gestor.verificar_y_actualizar_silenciosamente()
        except Exception:
            pass

    threading.Thread(target=actualizar_en_segundo_plano, daemon=True).start()

    # =========================================================================
    # MODAL DE COOKIES
    # =========================================================================
    campo_cookies = ft.TextField(
        multiline=True,
        min_lines=5,
        max_lines=8,
        hint_text="Pega aquí el contenido de tu archivo cookies.txt (formato Netscape) si necesitas descargar videos con restricción de edad...",
        text_size=12,
        bgcolor="#101017",
        border_color="#2e2e42",
    )

    def guardar_cookies_modal(e):
        motor.guardar_cookies_texto(campo_cookies.value or "")
        dialogo_cookies.open = False
        texto_estado.value = "Cookies guardadas correctamente en el escudo."
        texto_estado.color = "#2a9d8f"
        pagina.update()

    dialogo_cookies = ft.AlertDialog(
        title=ft.Text("Escudo Anti-Bloqueo (Cookies)", size=18, weight=ft.FontWeight.BOLD),
        content=campo_cookies,
        actions=[
            ft.TextButton("Cancelar", on_click=lambda _: setattr(dialogo_cookies, 'open', False) or pagina.update()),
            ft.ElevatedButton("Guardar Cookies", bgcolor="#2a9d8f", color="#ffffff", on_click=guardar_cookies_modal),
        ],
    )
    pagina.overlay.append(dialogo_cookies)

    # =========================================================================
    # CONTROLES DE LA INTERFAZ
    # =========================================================================
    encabezado = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ft.Column(
                spacing=2,
                controls=[
                    ft.Text("YTPY Studio", size=26, weight=ft.FontWeight.BOLD, color="#ffffff"),
                    ft.Text("Descargador 1080p/4K • MP4 / MP3 / FLAC", size=12, color="#8a8a9e"),
                ],
            ),
            ft.IconButton(
                icon=ft.icons.SHIELD_OUTLINED,
                icon_color="#3a86ff",
                tooltip="Configurar Cookies",
                on_click=lambda _: setattr(dialogo_cookies, 'open', True) or pagina.update(),
            ),
        ],
    )

    entrada_url = ft.TextField(
        hint_text="Pega el enlace de YouTube aquí...",
        bgcolor="#101017",
        border_color="#2e2e42",
        border_radius=10,
        text_size=14,
        expand=True,
        content_padding=ft.padding.symmetric(horizontal=14, vertical=12),
    )

    async def pegar_portapapeles(e):
        texto = await pagina.get_clipboard_async()
        if texto:
            entrada_url.value = texto.strip()
            pagina.update()

    boton_pegar = ft.ElevatedButton(
        text="Pegar",
        bgcolor="#262638",
        color="#ffffff",
        height=46,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
        on_click=pegar_portapapeles,
    )

    boton_analizar = ft.ElevatedButton(
        text="Analizar Video",
        bgcolor="#e63946",
        color="#ffffff",
        height=46,
        width=400,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
    )

    imagen_miniatura = ft.Image(
        src="https://via.placeholder.com/320x180.png?text=YTPY",
        width=360,
        height=180,
        fit=ft.ImageFit.COVER,
        border_radius=10,
        visible=False,
    )

    placeholder_miniatura = ft.Container(
        width=360,
        height=160,
        bgcolor="#101017",
        border_radius=10,
        alignment=ft.alignment.center,
        content=ft.Text("Vista previa del video", color="#555568", size=13),
    )

    texto_titulo_video = ft.Text(
        "Esperando enlace de YouTube...",
        size=15,
        weight=ft.FontWeight.BOLD,
        color="#e0e0e0",
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    texto_metadatos = ft.Text(
        "Canal: ---   |   Duración: --:--",
        size=12,
        color="#8a8a9e",
    )

    menu_calidades = ft.Dropdown(
        label="Resolución / Calidad original",
        bgcolor="#101017",
        border_color="#2e2e42",
        border_radius=10,
        disabled=True,
        options=[ft.dropdown.Option(key="Analiza un video primero", text="Analiza un video primero")],
        value="Analiza un video primero",
    )

    boton_descargar = ft.ElevatedButton(
        text="Descargar Video en MP4",
        bgcolor="#2a9d8f",
        color="#ffffff",
        height=48,
        width=400,
        disabled=True,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)),
    )

    def cambiar_formato(modo: str):
        estado_app["modo_formato"] = modo
        btn_mp4.bgcolor = "#3a86ff" if modo == "MP4" else "#20202e"
        btn_mp3.bgcolor = "#3a86ff" if modo == "MP3" else "#20202e"
        btn_flac.bgcolor = "#8338ec" if modo == "FLAC" else "#20202e"

        if not estado_app["datos_video"]:
            pagina.update()
            return

        # Limpiar el valor previo antes de asignar las nuevas opciones para forzar el refresco en Android
        menu_calidades.value = None

        if modo == "MP4":
            etiquetas = estado_app["datos_video"].get("lista_etiquetas", [])
            menu_calidades.label = f"Resolución original ({len(etiquetas)} disponibles)"
            menu_calidades.options = [ft.dropdown.Option(key=et, text=et) for et in etiquetas]
            menu_calidades.value = etiquetas[0] if etiquetas else None
            boton_descargar.text = "Descargar Video en MP4"
            boton_descargar.bgcolor = "#2a9d8f"
            barra_progreso.color = "#2a9d8f"

        elif modo == "MP3":
            opciones = list(calidades_mp3.keys())
            menu_calidades.label = "Calidad de audio MP3"
            menu_calidades.options = [ft.dropdown.Option(key=op, text=op) for op in opciones]
            menu_calidades.value = opciones[0]
            boton_descargar.text = "Descargar Audio en MP3"
            boton_descargar.bgcolor = "#3a86ff"
            barra_progreso.color = "#3a86ff"

        else:
            texto_flac = "FLAC Sin Pérdida (Lossless)"
            menu_calidades.label = "Calidad de estudio"
            menu_calidades.options = [ft.dropdown.Option(key=texto_flac, text=texto_flac)]
            menu_calidades.value = texto_flac
            boton_descargar.text = "Descargar Audio en FLAC"
            boton_descargar.bgcolor = "#8338ec"
            barra_progreso.color = "#8338ec"

        menu_calidades.update()
        pagina.update()

    btn_mp4 = ft.ElevatedButton("Video MP4", bgcolor="#3a86ff", color="#ffffff", expand=True, on_click=lambda _: cambiar_formato("MP4"))
    btn_mp3 = ft.ElevatedButton("Audio MP3", bgcolor="#20202e", color="#ffffff", expand=True, on_click=lambda _: cambiar_formato("MP3"))
    btn_flac = ft.ElevatedButton("Audio FLAC", bgcolor="#20202e", color="#ffffff", expand=True, on_click=lambda _: cambiar_formato("FLAC"))

    fila_formatos = ft.Row(controls=[btn_mp4, btn_mp3, btn_flac], spacing=8)

    texto_estado = ft.Text("Listo para comenzar.", size=13, weight=ft.FontWeight.BOLD, color="#a8dadc")
    texto_estadisticas = ft.Text("0% • Velocidad: --- • ETA: --:--", size=11, color="#8a8a9e")
    barra_progreso = ft.ProgressBar(value=0.0, bgcolor="#101017", color="#2a9d8f", height=10, border_radius=5)
    texto_ruta_guardado = ft.Text(f"Carpeta destino: {motor.ruta_descargas}", size=11, color="#6c6c80")

    def iniciar_analisis(e):
        enlace = (entrada_url.value or "").strip()
        if not enlace:
            texto_estado.value = "Por favor, pega un enlace válido de YouTube."
            texto_estado.color = "#e63946"
            pagina.update()
            return

        boton_analizar.disabled = True
        boton_analizar.text = "Analizando..."
        boton_descargar.disabled = True
        menu_calidades.disabled = True
        barra_progreso.value = None
        texto_estado.value = "Extrayendo metadatos y resoluciones del enlace...."
        texto_estado.color = "#a8dadc"
        pagina.update()

        def tarea_analisis():
            try:
                datos = motor.obtener_informacion_video(enlace)
                estado_app["datos_video"] = datos

                texto_titulo_video.value = datos["titulo"]
                mins, segs = divmod(datos["duracion_segundos"] or 0, 60)
                texto_metadatos.value = f"Canal: {datos['autor']}   |   Duración: {int(mins):02d}:{int(segs):02d}"

                if datos["url_miniatura"]:
                    imagen_miniatura.src = datos["url_miniatura"]
                    imagen_miniatura.visible = True
                    placeholder_miniatura.visible = False

                menu_calidades.disabled = False
                boton_descargar.disabled = False
                cambiar_formato(estado_app["modo_formato"])

                cantidad = len(datos.get("lista_etiquetas", []))
                barra_progreso.value = 0.0
                texto_estado.value = f"Video cargado. Hay {cantidad} opciones de calidad disponibles."
                texto_estado.color = "#2a9d8f"
            except Exception as err:
                barra_progreso.value = 0.0
                texto_estado.value = f"Error al analizar: {str(err)[:65]}"
                texto_estado.color = "#e63946"
            finally:
                boton_analizar.disabled = False
                boton_analizar.text = "Analizar Video"
                pagina.update()

        threading.Thread(target=tarea_analisis, daemon=True).start()

    def iniciar_descarga(e):
        if not estado_app["datos_video"]:
            return

        enlace = (entrada_url.value or "").strip()
        modo = estado_app["modo_formato"]
        seleccion = menu_calidades.value

        if modo == "MP4":
            mapa_res = estado_app["datos_video"]["resoluciones"]
            etiquetas = estado_app["datos_video"]["lista_etiquetas"]
            if seleccion in mapa_res:
                valor_calidad = mapa_res[seleccion]
            elif etiquetas:
                valor_calidad = mapa_res[etiquetas[0]]
            else:
                valor_calidad = 1080
        elif modo == "MP3":
            valor_calidad = calidades_mp3.get(seleccion, "320")
        else:
            valor_calidad = "0"

        boton_analizar.disabled = True
        boton_descargar.disabled = True
        boton_descargar.text = "Descargando..."
        menu_calidades.disabled = True
        barra_progreso.value = 0.0
        pagina.update()

        def cb_progreso(porcentaje, velocidad, eta, mensaje):
            barra_progreso.value = porcentaje
            texto_estado.value = mensaje
            texto_estado.color = "#a8dadc"
            texto_estadisticas.value = f"{int(porcentaje * 100)}% • Vel: {velocidad} • ETA: {eta}"
            pagina.update()

        def cb_completado(ruta_final):
            barra_progreso.value = 1.0
            texto_estado.value = f"¡Completado! Guardado en: {ruta_final}"
            texto_estado.color = "#2a9d8f"
            texto_estadisticas.value = "100% • Finalizado"
            boton_analizar.disabled = False
            boton_descargar.disabled = False
            menu_calidades.disabled = False
            cambiar_formato(modo)
            pagina.update()

        def cb_error(msg_error):
            texto_estado.value = f"Error: {msg_error[:75]}"
            texto_estado.color = "#e63946"
            boton_analizar.disabled = False
            boton_descargar.disabled = False
            menu_calidades.disabled = False
            cambiar_formato(modo)
            pagina.update()

        threading.Thread(
            target=motor.descargar_multimedia,
            args=(enlace, modo, valor_calidad, cb_progreso, cb_completado, cb_error),
            daemon=True,
        ).start()

    boton_analizar.on_click = iniciar_analisis
    boton_descargar.on_click = iniciar_descarga

    tarjeta_busqueda = ft.Container(
        bgcolor="#181822",
        border=ft.border.all(1, "#262636"),
        border_radius=14,
        padding=14,
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Row(controls=[entrada_url, boton_pegar], spacing=8),
                boton_analizar,
            ],
        ),
    )

    tarjeta_central = ft.Container(
        bgcolor="#181822",
        border=ft.border.all(1, "#262636"),
        border_radius=14,
        padding=14,
        content=ft.Column(
            spacing=12,
            controls=[
                ft.Container(alignment=ft.alignment.center, content=ft.Column([placeholder_miniatura, imagen_miniatura])),
                texto_titulo_video,
                texto_metadatos,
                fila_formatos,
                menu_calidades,
                boton_descargar,
            ],
        ),
    )

    tarjeta_progreso = ft.Container(
        bgcolor="#181822",
        border=ft.border.all(1, "#262636"),
        border_radius=14,
        padding=14,
        content=ft.Column(
            spacing=8,
            controls=[
                texto_estado,
                barra_progreso,
                texto_estadisticas,
                texto_ruta_guardado,
            ],
        ),
    )

    pagina.add(
        ft.SafeArea(
            content=ft.Column(
                spacing=12,
                controls=[encabezado, tarjeta_busqueda, tarjeta_central, tarjeta_progreso],
            )
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
