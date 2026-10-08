# VoiceController -- control del ordenador por voz, pensado para accesibilidad.
# Copyright (C) 2026  pipataki <pipataki@pipataki.net>
#
# Este programa es software libre: puedes redistribuirlo y/o modificarlo bajo
# los terminos de la Licencia Publica General Reducida GNU (LGPL)
# publicada por la Free Software Foundation, en su version 3 o
# cualquier version posterior.
#
# Se distribuye con la esperanza de que sea util, pero SIN NINGUNA GARANTIA;
# ni siquiera la garantia implicita de COMERCIABILIDAD o IDONEIDAD PARA UN
# PROPOSITO PARTICULAR. Consulta la LGPL para mas detalles.
#
# Deberias haber recibido una copia de la LGPL junto a este programa. Si
# no, ver <https://www.gnu.org/licenses/>.

"""
recognizer_worker.py: Worker Qt para DualLanguageRecognizer.

DualLanguageRecognizer usa threads nativos de Python; este módulo lo envuelve
en un QObject para que emita señales Qt thread-safe al GUI.

Patrón:
    - Worker corre en un QThread separado
    - Recibe señales para start/stop
    - Emite señales para partial/final/error
    - La GUI se suscribe a esas señales de forma thread-safe
"""

from PySide6.QtCore import QObject, Signal, Slot
from voice_recognizer import DualLanguageRecognizer
from microphone_manager import MicrophoneManager
import cesion_microfono
import config


class RecognizerWorker(QObject):
    """Worker que encapsula DualLanguageRecognizer para Qt."""
    
    # Señales que emite
    partial_result = Signal(str, str)  # (text, language)
    final_result = Signal(str, float, str, str, str, float, str)  # (..., speaker_verdict, peak_rms, source)
    error_occurred = Signal(str)  # (error_message)
    started = Signal()
    stopped = Signal()
    audio_level = Signal(bool, float)  # (is_silent, rms) -- VAD ligero por energía

    # Señales de control de fuente de audio. Se pueden emitir desde
    # cualquier hilo (p.ej. desde el hilo de la GUI o desde el hilo de la
    # webapp/Flask): Qt las encola automáticamente hacia este worker, que
    # vive en su propio QThread, evitando tocar el reconocedor fuera de su hilo.
    network_audio_chunk = Signal(bytes)  # audio PCM ya decodificado desde la webapp
    switch_to_network_requested = Signal()  # usar el micrófono de red (móvil)
    switch_to_device_requested = Signal(str)  # volver a un micrófono local

    def __init__(self):
        super().__init__()
        self._recognizer: DualLanguageRecognizer = None
        self._running = False

        self.network_audio_chunk.connect(self._on_network_audio_chunk)
        self.switch_to_network_requested.connect(self._on_switch_to_network)
        self.switch_to_device_requested.connect(self._on_switch_to_device)
    
    @Slot()
    def start_recognition(self):
        """Inicia el reconocimiento de voz."""
        if self._running:
            return
        
        try:
            # Seleccionar dispositivo de micrófono
            device_id = MicrophoneManager.get_best_device()
            success, msg = MicrophoneManager.verify_device(device_id)
            
            if not success:
                self.error_occurred.emit(f"Error de micrófono: {msg}")
                return
            
            if config.DEBUG:
                print(f"[recognizer_worker] Usando micrófono: {msg}")
            
            # Actualizar dispositivo en config
            config.INPUT_DEVICE = device_id
            
            # Crear reconocedor con callbacks que emiten señales
            self._recognizer = DualLanguageRecognizer(
                on_partial=self._on_partial,
                on_final=self._on_final,
                on_audio_level=self._on_audio_level,
            )
            cesion_microfono.registrar_reconocedor(self._recognizer)
            
            # Iniciar la captura de audio
            self._recognizer.start()
            self._running = True
            self.started.emit()
            
            if config.DEBUG:
                print("[recognizer_worker] Reconocimiento iniciado")
        
        except Exception as e:
            self.error_occurred.emit(f"Error iniciando reconocimiento: {e}")
    
    @Slot()
    def stop_recognition(self):
        """Detiene el reconocimiento de voz."""
        if not self._running:
            return
        
        try:
            if self._recognizer:
                self._recognizer.stop()
            self._running = False
            self.stopped.emit()
            
            if config.DEBUG:
                print("[recognizer_worker] Reconocimiento detenido")
        
        except Exception as e:
            self.error_occurred.emit(f"Error deteniendo reconocimiento: {e}")
    
    @Slot(str)
    def set_language_mode(self, mode: str):
        """Cambia el idioma primario (es/en)."""
        if self._recognizer:
            try:
                self._recognizer.set_language_mode(mode)
                if config.DEBUG:
                    print(f"[recognizer_worker] Idioma cambiado a: {mode}")
            except Exception as e:
                self.error_occurred.emit(f"Error cambiando idioma: {e}")

    @Slot(bool)
    def set_dictating(self, is_dictating: bool):
        """Informa al reconocedor si estamos en DICTATING (para que solo
        entonces analice prosodia). Lo llama CommandRouter en cada cambio
        de estado."""
        if self._recognizer:
            try:
                self._recognizer.set_dictating(is_dictating)
            except Exception as e:
                if config.DEBUG:
                    print(f"[recognizer_worker] error fijando estado dictating: {e}")

    def set_enrollment(self, source, callback):
        """Activa/desactiva el modo enrolado de un micrófono (ver
        voice_recognizer.set_enrollment)."""
        if self._recognizer:
            try:
                self._recognizer.set_enrollment(source, callback)
            except Exception as e:
                print(f"[recognizer_worker] error activando el enrolado: {e}")

    def reload_profiles(self):
        if self._recognizer:
            try:
                self._recognizer.reload_profiles()
            except Exception as e:
                print(f"[recognizer_worker] error recargando perfiles: {e}")

    def set_awaiting_login(self, awaiting: bool):
        """El router avisa de si está pidiendo el santo y seña, para que
        la verificación use su umbral propio (más exigente). Vale tanto
        para el login del arranque como para cada renovación."""
        if self._recognizer:
            try:
                self._recognizer.set_awaiting_login(awaiting)
            except Exception as e:
                print(f"[recognizer_worker] error fijando estado de login: {e}")

    def set_speaker_filter_enabled(self, enabled: bool):
        """Enciende/apaga el filtro por voz en caliente. Lo llama el
        interruptor "Filtrar por mi voz" de la bandeja del sistema (ver
        gui._toggle_speaker_filter), que es la salida de emergencia si el
        filtro empezara a rechazar al propio usuario."""
        if self._recognizer:
            try:
                self._recognizer.set_speaker_filter_enabled(enabled)
            except Exception as e:
                print(f"[recognizer_worker] error cambiando el filtro por voz: {e}")

    @Slot(bytes)
    def _on_network_audio_chunk(self, data: bytes):
        """Recibe audio PCM ya decodificado desde la webapp y lo entrega
        al reconocedor (solo tiene efecto si está en modo 'network')."""
        if self._recognizer:
            try:
                self._recognizer.feed_external_audio(data)
            except Exception as e:
                if config.DEBUG:
                    print(f"[recognizer_worker] error entregando audio de red: {e}")

    @Slot()
    def _on_switch_to_network(self):
        """Cambia a escuchar el micrófono de red (móvil, vía webapp)."""
        if not self._recognizer:
            return
        try:
            self._recognizer.switch_to_network()
            if config.DEBUG:
                print("[recognizer_worker] Cambiado a micrófono de red (móvil)")
        except Exception as e:
            self.error_occurred.emit(f"Error cambiando a micrófono de red: {e}")

    @Slot(str)
    def _on_switch_to_device(self, device_id: str):
        """Cambia a escuchar un micrófono local (por índice, nombre, o 'default')."""
        if not self._recognizer:
            return
        try:
            self._recognizer.set_input_device(device_id)
            if config.DEBUG:
                print(f"[recognizer_worker] Cambiado a micrófono local: {device_id}")
        except Exception as e:
            self.error_occurred.emit(f"Error cambiando de micrófono: {e}")
    
    # --- Callbacks internos (se conectan al DualLanguageRecognizer) ---
    
    def _on_partial(self, text: str, language: str = "es"):
        """Callback de resultado parcial (thread-safe via señal)."""
        self.partial_result.emit(text, language)
    
    def _on_final(self, text: str, confidence: float = 0.0, language: str = "es",
                  sentence_type: str = "statement", speaker_verdict: str = "him",
                  peak_rms: float = 0.0, source: str = "device"):
        """Callback de resultado final (thread-safe via señal).

        `speaker_verdict`: "him" | "other" | "unknown" (ver
        speaker_id.verdict). El tercero significa "no se ha podido
        verificar", que NO es lo mismo que "es otra persona" -- distinguir
        eso es lo que evita acusar de intrusión a un comando corto suyo.

        `peak_rms`: pico de energía de la frase -- señal de cercanía al
        micrófono, que el detector de intrusos usa para distinguir a
        alguien delante del ordenador de una tele al fondo."""
        self.final_result.emit(text, confidence, language, sentence_type,
                               speaker_verdict, peak_rms, source)

    def _on_audio_level(self, is_silent: bool, rms: float):
        """Callback del VAD ligero (thread-safe via señal)."""
        self.audio_level.emit(is_silent, rms)
