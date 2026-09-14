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
microphone_manager.py: Gestión robusta de dispositivo de audio.

Detecta dispositivos disponibles, busca el mejor candidato, y proporciona
fallback automático si la conexión falla.
"""

import sounddevice as sd
from typing import Optional, Tuple, List
import config


class MicrophoneManager:
    """Gestiona la selección y fallback de dispositivo de micrófono."""

    @staticmethod
    def list_input_devices() -> List[dict]:
        """Retorna lista de dispositivos de entrada disponibles."""
        devices = sd.query_devices()
        input_devices = []
        
        for i, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                input_devices.append({
                    "index": i,
                    "name": dev.get("name", f"Device {i}"),
                    "channels": dev.get("max_input_channels", 0),
                    "samplerate": dev.get("default_samplerate", 0),
                })
        
        return input_devices

    @staticmethod
    def find_device_by_name(name_pattern: str) -> Optional[int]:
        """Busca un dispositivo cuyo nombre contenga name_pattern (case-insensitive).
        
        Útil para encontrar un Bluetooth específico.
        Retorna el índice del dispositivo o None.
        """
        devices = MicrophoneManager.list_input_devices()
        name_lower = name_pattern.lower()
        
        for dev in devices:
            if name_lower in dev["name"].lower():
                return dev["index"]
        
        return None

    @staticmethod
    def get_best_device() -> Optional[int]:
        """Intenta encontrar el mejor dispositivo de entrada.
        
        Prioridad:
        1. Dispositivo configurado en config.INPUT_DEVICE (si es válido)
        2. Dispositivo por defecto del sistema
        3. Primer dispositivo de entrada disponible
        """
        devices = MicrophoneManager.list_input_devices()
        
        if not devices:
            print("[microphone_manager] ERROR: No hay dispositivos de entrada disponibles")
            return None
        
        # Si está configurado y es válido, usarlo
        if config.INPUT_DEVICE is not None:
            try:
                if isinstance(config.INPUT_DEVICE, int):
                    if 0 <= config.INPUT_DEVICE < len(sd.query_devices()):
                        return config.INPUT_DEVICE
                else:
                    # Intentar buscar por nombre
                    idx = MicrophoneManager.find_device_by_name(str(config.INPUT_DEVICE))
                    if idx is not None:
                        return idx
            except Exception as e:
                print(f"[microphone_manager] Dispositivo configurado inválido: {e}")
        
        # Usar dispositivo por defecto
        try:
            default_idx = sd.default.device[0]  # [0] es input
            if default_idx is not None and default_idx >= 0:
                return default_idx
        except Exception:
            pass
        
        # Fallback: primer dispositivo de entrada
        if devices:
            print(f"[microphone_manager] Usando fallback: {devices[0]['name']} (índice {devices[0]['index']})")
            return devices[0]["index"]
        
        return None

    @staticmethod
    def verify_device(device_id: Optional[int]) -> Tuple[bool, str]:
        """Verifica que un dispositivo sea accesible.
        
        Retorna (success, message).
        """
        if device_id is None:
            return False, "Dispositivo es None"
        
        try:
            devinfo = sd.query_devices(device_id, kind="input")
            if devinfo is None:
                return False, f"Dispositivo {device_id} no existe"
            
            name = devinfo.get("name", f"Device {device_id}")
            channels = devinfo.get("max_input_channels", 0)
            samplerate = devinfo.get("default_samplerate", 0)
            
            if channels <= 0:
                return False, f"{name}: no tiene canales de entrada"
            
            if samplerate <= 0:
                return False, f"{name}: samplerate inválido"
            
            return True, f"{name} (channels={channels}, sr={samplerate}Hz)"
        
        except Exception as e:
            return False, f"Error verificando dispositivo {device_id}: {e}"

    @staticmethod
    def print_devices():
        """Imprime lista de dispositivos de entrada disponibles."""
        devices = MicrophoneManager.list_input_devices()
        
        print("\n" + "="*70)
        print("DISPOSITIVOS DE ENTRADA DISPONIBLES")
        print("="*70)
        
        if not devices:
            print("(ninguno)")
        else:
            for dev in devices:
                print(f"[{dev['index']}] {dev['name']}")
                print(f"    Canales: {dev['channels']}, SR: {dev['samplerate']}Hz")
        
        print("="*70 + "\n")
