#!/usr/bin/env python3
"""
Генератор аудио-дорожки для дыхательной практики.
3 раунда управляемого дыхания с женским голосом и амбиентным фоном.
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
import numpy as np
from scipy.signal import butter, filtfilt
from pathlib import Path

import imageio_ffmpeg
import edge_tts
from pydub import AudioSegment

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
AudioSegment.converter = FFMPEG_EXE

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

SAMPLE_RATE = 44100
TTS_VOICE = "ru-RU-SvetlanaNeural"
TTS_RATE = "-15%"
TTS_PITCH = "-20Hz"

OUTPUT_DIR = Path("D:/REDPEAK/AgentHQ/DATA")
OUTPUT_FILE = OUTPUT_DIR / "breathing_practice_3rounds.mp3"
TEMP_DIR = Path(tempfile.mkdtemp(prefix="breathing_"))

INHALE_DUR = 2.5   # секунд
EXHALE_DUR = 2.5   # секунд

BREATH_VOLUME_DB = -10   # громкость дыхательного сигнала (dB от нормы)
AMBIENT_VOLUME_DB = -20  # громкость фона (dB от нормы)

# ============================================================
# ТЕКСТЫ ДЛЯ ОЗВУЧКИ
# ============================================================

TTS_TEXTS = {
    # Вступление
    "intro": (
        "Добро пожаловать на сеанс управляемого дыхания. "
        "Многие тратят деньги на вещества, чтобы изменить состояние сознания, "
        "но того же эффекта можно добиться бесплатно. "
        "Систематическая практика укрепляет иммунитет, повышает интеллект, "
        "выносливость и помогает выводить токсины. "
        "Данная практика снимает стресс и позволяет перепрошивать аспекты личности. "
        "Выполняйте строго в безопасном месте. "
        "Садитесь или ложитесь. "
        "Очистите голову от мыслей."
    ),

    # Раунд 1
    "r1_title": "Раунд первый.",
    "r1_intro": (
        "Вдыхай, выдыхай. В живот, в грудь, и отпускаем. "
        "Ловите волну, ловите ритм. "
        "Никакой паузы между вдохом и выдохом."
    ),
    "r1_hold_start": "Полный вдох и отпускаем. Стоп. Задержка дыхания.",
    "r1_hold_mid": "Будьте в моменте, слушайте удары сердца. Расслабьтесь.",
    "r1_recovery": "Глубокий вдох и задержка.",
    "r1_exhale": "Три, два, один. Выдох.",

    # Раунд 2
    "r2_title": "Раунд второй.",
    "r2_intro": (
        "Вдох, выдох. Ловите ритм. "
        "Наполняйте живот и грудь, отпускайте как волну."
    ),
    "r2_cue_10": "Ещё десять циклов.",
    "r2_cue_5": "Ещё пять, выкладываемся на полную.",
    "r2_hold_start": (
        "Полный вдох, секунду держим и на выдохе, стоп. "
        "Задержка дыхания."
    ),
    "r2_hold_mid": (
        "Покалывание или изменение температуры, это норма, "
        "метаболизм меняется."
    ),
    "r2_recovery": "Глубокий вдох и задержка.",
    "r2_exhale": "Три, два, один. Выдох.",

    # Раунд 3
    "r3_title": "Раунд третий.",
    "r3_intro": (
        "Вдох, выдох. Без паузы. "
        "Качественные, полные, цикличные вдохи."
    ),
    "r3_cue_10": "Ещё десять.",
    "r3_cue_5": "Последние пять. Выдох не форсируем.",
    "r3_hold_start": "Полный вдох и на выдохе, стоп. Задержка.",
    "r3_hold_mid": "Кровь несёт кислород каждой клетке, ощутите это.",
    "r3_recovery": "Глубокий вдох и задержка.",
    "r3_exhale": "Три, два, один. Выдох.",

    # Заключение
    "outro_1": (
        "Дайте дыханию вернуться к норме. Подвигайте пальцами. "
        "Сейчас вы на пике энергетического потенциала. "
        "Ваша воля обладает наибольшей силой."
    ),
    "outro_2": (
        "На задержке при вдохе напрягите живот и втолкните воздух "
        "в шею и голову для насыщения автономных систем."
    ),
    "outro_3": (
        "Рекомендуется начать обливания холодной водой. "
        "Когда сможете провести пятнадцать минут в холодной воде и согреться, "
        "вы научились приказывать автономным системам."
    ),
    "outro_4": (
        "Метод обладает противовоспалительным действием. "
        "Дополняйте этим методом терапию, назначенную врачом."
    ),
    "outro_5": "Практикуйте ежедневно. Делитесь прогрессом.",
}


# ============================================================
# ГЕНЕРАЦИЯ ЗВУКОВ
# ============================================================

def bandpass_filter(data, lowcut, highcut, order=4):
    """Полосовой фильтр."""
    nyq = 0.5 * SAMPLE_RATE
    low = max(lowcut / nyq, 0.001)
    high = min(highcut / nyq, 0.999)
    b, a = butter(order, [low, high], btype="band")
    return filtfilt(b, a, data)


def generate_one_breath_cycle():
    """Один цикл вдох-выдох: фильтрованный шум + тихий тон."""
    inhale_n = int(INHALE_DUR * SAMPLE_RATE)
    exhale_n = int(EXHALE_DUR * SAMPLE_RATE)

    # Огибающие амплитуды (smooth)
    t_in = np.linspace(0, 1, inhale_n)
    t_ex = np.linspace(0, 1, exhale_n)
    env_in = np.sin(np.pi * t_in / 2)      # 0 -> 1
    env_ex = np.cos(np.pi * t_ex / 2)      # 1 -> 0

    # Шумовая компонента (дыхание)
    noise_in = bandpass_filter(np.random.randn(inhale_n + 200), 200, 900)[:inhale_n]
    noise_ex = bandpass_filter(np.random.randn(exhale_n + 200), 150, 700)[:exhale_n]

    # Тональная компонента (тихий подтон)
    t_in_s = np.linspace(0, INHALE_DUR, inhale_n)
    t_ex_s = np.linspace(0, EXHALE_DUR, exhale_n)
    freq_in = 230 + 40 * t_in  # лёгкий подъём тона
    freq_ex = 270 - 40 * t_ex  # лёгкий спуск тона
    phase_in = 2 * np.pi * np.cumsum(freq_in / SAMPLE_RATE)
    phase_ex = 2 * np.pi * np.cumsum(freq_ex / SAMPLE_RATE) + phase_in[-1]

    tone_in = np.sin(phase_in) * 0.12
    tone_ex = np.sin(phase_ex) * 0.12

    # Сборка
    inhale = env_in * (noise_in * 0.5 + tone_in)
    exhale = env_ex * (noise_ex * 0.5 + tone_ex)

    return np.concatenate([inhale, exhale])


def generate_breathing_segment(n_cycles):
    """Генерирует n циклов дыхания как AudioSegment."""
    cycles = np.concatenate([generate_one_breath_cycle() for _ in range(n_cycles)])
    return numpy_to_segment(cycles)


def generate_ambient(duration_s):
    """Амбиентный фон: дрон + pad + шиммер."""
    n = int(duration_s * SAMPLE_RATE)
    t = np.linspace(0, duration_s, n)

    # Базовый дрон
    drone = (
        np.sin(2 * np.pi * 70 * t) * 0.15
        + np.sin(2 * np.pi * 140 * t) * 0.06
        + np.sin(2 * np.pi * 105 * t) * 0.04
    )

    # Pad с медленным LFO
    lfo1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.04 * t)
    pad = np.sin(2 * np.pi * 220 * t) * lfo1 * 0.04

    # Высокий шиммер
    lfo2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * t + 1.5)
    shimmer = np.sin(2 * np.pi * 440 * t) * lfo2 * 0.015

    return drone + pad + shimmer


def numpy_to_segment(arr):
    """numpy float [-1,1] -> pydub AudioSegment (16-bit mono)."""
    arr = np.clip(arr, -1.0, 1.0)
    pcm = (arr * 32767).astype(np.int16)
    return AudioSegment(
        pcm.tobytes(),
        frame_rate=SAMPLE_RATE,
        sample_width=2,
        channels=1,
    )


# ============================================================
# TTS
# ============================================================

def load_mp3_as_segment(mp3_path):
    """Декодирует MP3 -> raw PCM через ffmpeg, загружает как AudioSegment."""
    raw_path = str(mp3_path) + ".raw"
    subprocess.run(
        [FFMPEG_EXE, "-y", "-i", str(mp3_path),
         "-f", "s16le", "-acodec", "pcm_s16le",
         "-ar", str(SAMPLE_RATE), "-ac", "1",
         raw_path],
        capture_output=True, check=True,
    )
    raw_data = open(raw_path, "rb").read()
    os.remove(raw_path)
    return AudioSegment(
        data=raw_data,
        sample_width=2,
        frame_rate=SAMPLE_RATE,
        channels=1,
    )


async def generate_all_tts():
    """Генерирует все TTS-сегменты."""
    segments = {}
    for key, text in TTS_TEXTS.items():
        path = TEMP_DIR / f"tts_{key}.mp3"
        print(f"  TTS: {key} ...", end=" ", flush=True)
        comm = edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE, pitch=TTS_PITCH)
        await comm.save(str(path))
        seg = load_mp3_as_segment(path)
        segments[key] = seg
        print(f"{len(seg)/1000:.1f}с")
    return segments


# ============================================================
# СБОРКА ТРЕКА
# ============================================================

def silence(ms):
    return AudioSegment.silent(duration=ms)


def build_hold_section(tts_start, tts_mid, hold_duration_ms):
    """
    Собирает секцию задержки дыхания:
    голос_начало + тишина + голос_середина + тишина до конца hold.
    """
    section = tts_start + silence(1500)

    # Голос в середине задержки
    mid_point_ms = hold_duration_ms * 0.35  # голос на 35% задержки
    before_mid = max(0, int(mid_point_ms))
    after_mid = max(0, int(hold_duration_ms - before_mid - len(tts_mid)))

    section += silence(before_mid)
    section += tts_mid
    section += silence(after_mid)

    return section


def build_recovery_section(tts_recovery, tts_exhale, hold_seconds=15):
    """Секция восстановления: вдох + задержка N секунд + выдох."""
    section = tts_recovery
    section += silence(hold_seconds * 1000)
    section += tts_exhale
    return section


def build_breathing_with_cues(breath_15, breath_10, breath_5, cue_10, cue_5):
    """
    Дыхание с голосовыми подсказками:
    15 циклов -> голос 'ещё 10' поверх дыхания -> 10 циклов -> голос 'ещё 5' -> 5 циклов.
    """
    section = breath_15

    # Голос накладывается на первые секунды следующей группы
    mid_10 = breath_10.overlay(cue_10, position=500)
    section += mid_10

    last_5 = breath_5.overlay(cue_5, position=500)
    section += last_5

    return section


def build_track(tts):
    """Собирает полный трек без амбиента."""

    # Генерация дыхательных сигналов
    print("\nГенерация дыхательных сигналов...")
    breath_30 = generate_breathing_segment(30) + BREATH_VOLUME_DB
    breath_15 = generate_breathing_segment(15) + BREATH_VOLUME_DB
    breath_10 = generate_breathing_segment(10) + BREATH_VOLUME_DB
    breath_5 = generate_breathing_segment(5) + BREATH_VOLUME_DB
    print(f"  30 циклов: {len(breath_30)/1000:.0f}с")

    track = AudioSegment.empty()

    # === ВСТУПЛЕНИЕ ===
    print("Сборка: вступление")
    track += tts["intro"] + silence(3000)

    # === РАУНД 1 ===
    print("Сборка: раунд 1")
    track += tts["r1_title"] + silence(1500)
    track += tts["r1_intro"] + silence(2000)
    track += breath_30
    track += silence(1000)
    track += build_hold_section(tts["r1_hold_start"], tts["r1_hold_mid"], 30_000)
    track += build_recovery_section(tts["r1_recovery"], tts["r1_exhale"], 15)
    track += silence(3000)

    # === РАУНД 2 ===
    print("Сборка: раунд 2")
    track += tts["r2_title"] + silence(1500)
    track += tts["r2_intro"] + silence(2000)
    track += build_breathing_with_cues(
        breath_15, breath_10, breath_5,
        tts["r2_cue_10"], tts["r2_cue_5"],
    )
    track += silence(1000)
    track += build_hold_section(tts["r2_hold_start"], tts["r2_hold_mid"], 60_000)
    track += build_recovery_section(tts["r2_recovery"], tts["r2_exhale"], 15)
    track += silence(3000)

    # === РАУНД 3 ===
    print("Сборка: раунд 3")
    track += tts["r3_title"] + silence(1500)
    track += tts["r3_intro"] + silence(2000)
    track += build_breathing_with_cues(
        breath_15, breath_10, breath_5,
        tts["r3_cue_10"], tts["r3_cue_5"],
    )
    track += silence(1000)
    track += build_hold_section(tts["r3_hold_start"], tts["r3_hold_mid"], 90_000)
    track += build_recovery_section(tts["r3_recovery"], tts["r3_exhale"], 15)
    track += silence(3000)

    # === ЗАКЛЮЧЕНИЕ ===
    print("Сборка: заключение")
    track += tts["outro_1"] + silence(2500)
    track += tts["outro_2"] + silence(2500)
    track += tts["outro_3"] + silence(2500)
    track += tts["outro_4"] + silence(2500)
    track += tts["outro_5"] + silence(3000)

    return track


def add_ambient_background(track):
    """Генерирует и накладывает амбиентный фон."""
    total_s = len(track) / 1000
    print(f"\nГенерация амбиента ({total_s:.0f}с)...")

    ambient_arr = generate_ambient(total_s + 1)
    ambient_seg = numpy_to_segment(ambient_arr)[:len(track)]
    ambient_seg = ambient_seg + AMBIENT_VOLUME_DB
    ambient_seg = ambient_seg.fade_in(4000).fade_out(12000)

    print("Микширование...")
    return track.overlay(ambient_seg)


# ============================================================
# MAIN
# ============================================================

async def main():
    print("=" * 55)
    print("  Генерация аудио: дыхательная практика (3 раунда)")
    print("=" * 55)

    # 1. TTS
    print("\n[1/5] Генерация голоса (edge-tts)...")
    tts = await generate_all_tts()

    # 2. Сборка
    print("\n[2/5] Сборка трека...")
    track = build_track(tts)

    # 3. Амбиент
    print("\n[3/5] Амбиентный фон...")
    final = add_ambient_background(track)

    # 4. Нормализация + fade
    print("\n[4/5] Нормализация...")
    final = final.normalize()
    final = final.fade_in(2000).fade_out(6000)

    # 5. Экспорт
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = str(OUTPUT_FILE)
    print(f"\n[5/5] Экспорт -> {out}")
    final.export(out, format="mp3", bitrate="320k")

    dur = len(final) / 1000
    size_mb = os.path.getsize(out) / (1024 * 1024)

    print(f"\n{'=' * 55}")
    print(f"  Готово!")
    print(f"  Файл:         {out}")
    print(f"  Длительность:  {int(dur // 60)} мин {int(dur % 60)} сек")
    print(f"  Размер:        {size_mb:.1f} MB")
    print(f"{'=' * 55}")

    # Очистка
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print("Временные файлы удалены.")


if __name__ == "__main__":
    asyncio.run(main())
