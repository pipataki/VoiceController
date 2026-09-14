#!/usr/bin/env python3
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
probar_voces: escucha las voces disponibles y elige la que más te guste.

Elegir una voz no se puede hacer leyendo especificaciones: hay que oírla.
Esta herramienta dice la MISMA frase con cada voz instalada (y con cada
hablante, en los modelos que traen varios), a la velocidad configurada, y
al final te dice exactamente qué poner en config.py para quedarte con la
que prefieras.

    ./venv/bin/python tools/probar_voces.py                 # todas
    ./venv/bin/python tools/probar_voces.py --velocidad 1.3 # más despacio
    ./venv/bin/python tools/probar_voces.py --frase "lo que sea"

No toca nada: solo reproduce.
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402  -- solo lectura

FRASE = ("Puedes decir: dictar, rejilla, tabulador, espacio. "
         "No te entiendo.")


def reproducir(pcm: bytes, rate: int):
    """paplay por la entrada estándar -- ver tts.py: la tarjeta de salida
    de esta máquina no acepta los 22050 Hz de Piper, y PulseAudio
    remuestrea solo."""
    subprocess.run(["paplay", "--raw", f"--rate={rate}", "--channels=1",
                    "--format=s16le"], input=pcm, check=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frase", default=FRASE)
    ap.add_argument("--velocidad", type=float, default=None,
                    help="velocidad del habla: MENOS de 1 habla más despacio "
                         f"(por defecto config.TTS_SPEED = {config.TTS_SPEED})")
    args = ap.parse_args()

    velocidad = args.velocidad if args.velocidad is not None else config.TTS_SPEED

    try:
        from piper import PiperVoice, SynthesisConfig
    except ImportError:
        sys.exit("Falta piper-tts: ./venv/bin/pip install piper-tts")

    voces_dir = PROJECT_ROOT / "piper_voices"
    modelos = sorted(voces_dir.glob("*.onnx"))
    if not modelos:
        sys.exit(f"No hay voces en {voces_dir}.\n"
                 "Descarga alguna con:\n"
                 "  ./venv/bin/python -m piper.download_voices es_ES-sharvard-medium "
                 "--download-dir piper_voices")

    print(f"Velocidad: {velocidad}x  (menos de 1 = más despacio)")
    print(f'Frase: "{args.frase}"\n')

    candidatas = []
    for ruta in modelos:
        voz = PiperVoice.load(str(ruta))
        mapa = getattr(voz.config, "speaker_id_map", None) or {}
        num = getattr(voz.config, "num_speakers", 1) or 1
        # un modelo con varios hablantes son varias voces distintas: hay
        # que oírlas por separado, no solo la primera
        if num > 1 and mapa:
            for clave, sid in sorted(mapa.items(), key=lambda kv: kv[1]):
                etiqueta = {"F": "femenina", "M": "masculina"}.get(clave, clave)
                candidatas.append((ruta, voz, sid, etiqueta))
        else:
            candidatas.append((ruta, voz, None, "hablante único"))

    for i, (ruta, voz, sid, etiqueta) in enumerate(candidatas, 1):
        print(f"[{i}/{len(candidatas)}] {ruta.name}  --  {etiqueta}", flush=True)
        # velocidad -> length_scale (duración), que va al revés: ver tts.py
        cfg = SynthesisConfig(speaker_id=sid, length_scale=1.0 / max(0.1, velocidad))
        chunks = list(voz.synthesize(args.frase, syn_config=cfg))
        if not chunks:
            print("    (no ha producido audio)")
            continue
        rate = chunks[0].sample_rate
        reproducir(b"".join(c.audio_int16_bytes for c in chunks), rate)

    print("\n" + "=" * 64)
    print("Para quedarte con una, en config.py:")
    print("=" * 64)
    for i, (ruta, _voz, sid, etiqueta) in enumerate(candidatas, 1):
        print(f"\n[{i}] {ruta.name} ({etiqueta})")
        print(f'    TTS_PIPER_VOICE = str(PROJECT_ROOT / "piper_voices" / "{ruta.name}")')
        if sid is not None:
            genero = "femenina" if etiqueta == "femenina" else "masculina"
            print(f'    TTS_VOICE_GENDER = "{genero}"')
    print(f"\n    TTS_SPEED = {velocidad}    # BÁJALO para hablar más despacio")


if __name__ == "__main__":
    main()
