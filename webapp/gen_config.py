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

"""Generate or update webapp_config.json with PBKDF2-hashed password.

Usage:
  python webapp/gen_config.py --user admin
  python webapp/gen_config.py --user admin --stream-fps 3
  python webapp/gen_config.py --user admin --no-streaming
  python webapp/gen_config.py --user admin --no-https

If --password not given, prompts securely. Overwrites webapp_config.json.
"""
import os
import sys
import json
import argparse
import getpass
import hashlib
from pathlib import Path


ROOT = str(Path(__file__).resolve().parent.parent)
CONFIG_PATH = os.path.join(ROOT, 'webapp_config.json')



def make_hash(password: str, iterations: int = 100000):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations)
    return f'pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--user', default='pipa')
    p.add_argument('--password', help='Password (if omitted, prompts)')
    p.add_argument('--host', help='Host to bind (saved in config)')
    p.add_argument('--port', type=int, help='Port to bind (saved in config)')
    p.add_argument('--no-streaming', action='store_true',
                    help='Disable the desktop stream (/stream). Enabled by default.')
    p.add_argument('--stream-fps', type=float,
                    help='Desktop stream frame rate (default: 2, kept low on purpose)')
    p.add_argument('--no-https', action='store_true',
                    help='Serve over plain HTTP instead of HTTPS. '
                         'Note: without HTTPS the mobile microphone will NOT work '
                         '(browsers block getUserMedia on insecure origins).')
    args = p.parse_args()

    pwd = args.password
    if not pwd:
        pwd = getpass.getpass('Password for webapp user %s: ' % args.user)
        pwd2 = getpass.getpass('Confirm: ')
        if pwd != pwd2:
            print('Passwords do not match', file=sys.stderr)
            sys.exit(2)

    h = make_hash(pwd)

    # load existing config if present, so re-running only touches what's passed
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}

    cfg['user'] = args.user
    cfg['password_hash'] = h
    if args.host:
        cfg['host'] = args.host
    if args.port:
        cfg['port'] = args.port
    if args.no_streaming:
        cfg['enable_streaming'] = False
    if args.stream_fps:
        cfg['stream_fps'] = args.stream_fps
    if args.no_https:
        cfg['use_https'] = False

    cfg.setdefault('host', '10.8.0.3')
    cfg.setdefault('port', 5000)

    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)

    print('Wrote', CONFIG_PATH)


if __name__ == '__main__':
    main()
