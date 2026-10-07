#!/bin/bash
# Dev-хелпер для NixOS: cv2/numpy из .venv требуют системные .so,
# которые не в дефолтном ld-path. Скрипт находит их в /nix/store и
# печатает LD_LIBRARY_PATH. Использование:
#   eval "$(bash scripts/dev_env.sh)"
#   .venv/bin/python -m unittest discover -s tests -v
LP=""
for lib in libstdc++.so.6 libz.so.1 libxcb.so.1 libGL.so.1 libgthread-2.0.so.0 \
    libzstd.so.1 libEGL.so.1 libxkbcommon.so.0 libfontconfig.so.1 \
    libdbus-1.so.3 libglib-2.0.so.0 libfreetype.so.6 libX11.so.6 \
    libX11-xcb.so.1 libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 \
    libxcb-keysyms.so.1 libxcb-randr.so.0 libxcb-render-util.so.0 \
    libxcb-shape.so.0 libxcb-shm.so.0 libxcb-sync.so.1 libxcb-xfixes.so.0 \
    libxcb-xinerama.so.0 libxcb-xkb.so.1 libexpat.so.1 libpng16.so.16 \
    libharfbuzz.so.0 libbz2.so.1 libffi.so.8 libpcre2-8.so.0 \
    libXau.so.6 libXdmcp.so.6 libcap.so.2 libsystemd.so.0 liblz4.so.1 \
    libgcrypt.so.20 libgpg-error.so.0 libgraphite2.so.3; do
  for f in $(find /nix/store -maxdepth 4 -name "$lib" 2>/dev/null); do
    if [ "$(python3 -c "print('64' if open('$f','rb').read(5)[4]==2 else '32')")" = "64" ]; then
      d=$(dirname "$f")
      case ":$LP:" in *":$d:"*) continue;; esac
      LP=${LP:+$LP:}$d
      break
    fi
  done
done
echo "export LD_LIBRARY_PATH=$LP"
