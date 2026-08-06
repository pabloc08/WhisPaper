# Third-Party Notices

O WhisPaper é distribuído sob a GNU GPLv3 (ver LICENSE). Também utiliza os componentes de terceiros abaixo, cada um sob sua própria licença.

## whisper.cpp
- Licença: MIT
- Fonte: https://github.com/ggml-org/whisper.cpp
- Distribuído como binário compilado em bin/ (whisper-cli + suas .dll).
- Texto completo da licença: licenses/MIT-Licenses

## Silero VAD (ggml)
- Licença: MIT
- Fonte: https://huggingface.co/ggml-org/whisper-vad (conversão para formato ggml, mantida pelo time do whisper.cpp, do modelo original do Silero Team)
- Embutido como modelo de detecção de atividade de voz.
- Texto completo da licença: licenses/MIT-Licenses

## PySide6 / Qt for Python
- Licença: LGPLv3
- Fonte: https://pypi.org/project/PySide6/
- Utilizado via importação dinâmica, sem linkagem estática.
- Texto completo da licença: licenses/LICENSE-LGPL (combinado com LICENSE, conforme instrução da FSF para a LGPLv3)

## httpx
- Licença: BSD-3-Clause
- Fonte: https://github.com/encode/httpx
- Texto completo da licença: licenses/BSD-3-Clause

## Noto Sans
- Licença: SIL Open Font License 1.1
- Fonte: https://fonts.google.com/noto/specimen/Noto+Sans
- Embutido via Qt Resource System em interface/assets/assets_rc.py.
- Texto completo da licença: interface/assets/OFL.txt (distribuído em licenses/OFL.txt no instalador)

## Modelos Whisper (OpenAI / ggml)
- Licença: MIT
- Fonte: https://github.com/openai/whisper
- Baixado sob demanda via Hugging Face pelo Gerenciador de Modelos; não é embutido.

## FFmpeg (build da Gyan)
- Licença: GPLv3
- Fonte: https://www.gyan.dev/ffmpeg/builds/
- Os builds essentials e full são estáticos e licenciados como GPLv3, por incluírem codecs como libx264/libx265. Baixado sob demanda, não é embutido.
